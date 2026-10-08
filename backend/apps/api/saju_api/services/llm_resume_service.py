"""LLM 서비스 중단/재개 운영 절차 (관리자 콘솔 — 2026-10-06, 데굴님 승인 설계).

SSOT: doc/v2_2/LLM_SERVICE_SUSPENSION.md

재개 절차(`probe_and_resume`)
1. 키가 있는 공급자마다 소액 프로브(출력 수 토큰) 실호출 — 결제 복구를 **실측**한다.
   프로브 없이 재개하면 첫 사용자 질문이 다시 소진 호출을 내고 곧바로 재중단된다.
2. 통과 공급자가 없으면 `ResumeRejected`(409) — 상태 유지, 프로브 결과만 저장.
3. 통과 공급자가 있으면 active 전이. 여전히 소진인 공급자는 쿨다운으로 남긴다.
   중단 기록(system_errors `llm_service_suspended`)은 해결 처리한다.
4. 보류 리포트 잡을 원자적으로 클레임(중복 클릭에도 1회)하고, 재개 작업은 백그라운드로.

재개 작업(`run_resume_work`)의 선별 규칙
- 리포트: 보류 마커(`LLM_SUSPENDED`) 잡 전부 — 통과 섹션은 재사용(부분 보존).
- 오늘의 운세 교정: 현재 게시 기준일 보드가 RAW 일 때 그 하나만. 지난 날짜는 무시.
- 채팅: 없음 — 중단 중·시점의 질문은 되살리지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any

from saju_engines.error_store import ErrorStore, fingerprint
from saju_engines.report_job_store import ReportJobRecord, ReportJobStore
from saju_engines.subject_store import SubjectStore

from . import llm_client, llm_service_state

_logger = logging.getLogger(__name__)


class ResumeRejected(Exception):
    """프로브를 통과한 공급자가 없어 재개를 거부했다(상태 유지)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("재개 거부 — 프로브 통과 공급자 없음")
        self.payload = payload


def _cooldown_seconds() -> float:
    return float(llm_client.load_config().get("options", {}).get("provider_cooldown_seconds", 900))


def state_overview(jobs: ReportJobStore | None) -> dict[str, Any]:
    """콘솔용 전체 스냅샷 + 재개 대기 작업 수(리포트 보류 잡·게시 기준일 보드 교정 상태)."""
    out = llm_service_state.current(force=True).snapshot(public=False)
    pending: dict[str, Any] = {"suspended_report_jobs": 0, "daily_board": None}
    if jobs is not None:
        try:
            pending["suspended_report_jobs"] = jobs.count_suspended()
        except Exception:  # noqa: BLE001 — 조회 실패가 상태 표시를 막지 않도록
            pass
    try:
        from saju_engines.daily_fortune_cache import default_cache
        from saju_engines.daily_fortune_v2 import active_content_version

        from .daily_fortune_export import threads_publish_date

        d = threads_publish_date()
        board = default_cache().load_board(d, active_content_version(d))
        pending["daily_board"] = {
            "date": d.isoformat(),
            "polish_status": board.polish_status if board is not None else None,
        }
    except Exception:  # noqa: BLE001 — Redis 미설정 등은 '정보 없음'으로
        pass
    out["pending"] = pending
    out["providers_configured"] = _configured_providers()
    return out


def _configured_providers() -> list[dict[str, Any]]:
    cfg = llm_client.load_config()
    return [
        {
            "role": role, "provider": cfg[role]["provider"], "model": cfg[role]["model"],
            "has_key": bool(llm_client._api_key(cfg[role])),
        }
        for role in ("primary", "fallback")
    ]


def probe_and_resume(
    admin_id: str, jobs: ReportJobStore | None, errors: ErrorStore | None,
) -> dict[str, Any]:
    """프로브 → 전이 → 보류 잡 클레임. 결과 dict 의 `claimed_jobs` 는 호출 측이 백그라운드로 돌린다.

    Raises:
        ResumeRejected: 통과 공급자 없음(payload 에 프로브 상세).
    """
    before = llm_service_state.current(force=True)
    probes = llm_client.probe_all()
    probe_summary = {"at": llm_service_state._iso(llm_service_state._now()), "results": probes}
    ok = [p for p in probes if p.get("ok")]
    if not ok:
        llm_service_state.record_probe(probe_summary)
        raise ResumeRejected({
            "message": "재개 거부 — 프로브를 통과한 공급자가 없습니다. 결제 상태를 확인해 주세요.",
            "probes": probes,
            "state": llm_service_state.current(force=True).snapshot(public=False),
        })
    still_blocked = {
        str(p["provider"]): (str(p["model"]), str(p.get("detail") or ""))
        for p in probes if not p.get("ok") and p.get("kind") == "quota"
    }
    changed = llm_service_state.resume(
        admin_id, probe=probe_summary, still_blocked=still_blocked,
        cooldown_seconds=_cooldown_seconds(),
    )
    resolved = 0
    if changed and errors is not None:
        try:
            resolved = errors.resolve(fingerprint=fingerprint(
                "llm", llm_service_state.SUSPENDED_ERROR_KIND,
                llm_service_state.SUSPENDED_ERROR_MESSAGE,
            ))
        except Exception:  # noqa: BLE001 — 해결 처리 실패가 재개를 막지 않도록
            pass
    claimed: list[ReportJobRecord] = []
    if changed and jobs is not None:
        try:
            claimed = jobs.claim_suspended()
        except Exception:  # noqa: BLE001 — 클레임 실패는 로그만(잡은 보류 상태로 남는다)
            _logger.exception("보류 리포트 잡 클레임 실패")
    return {
        "resumed": changed,
        "was_suspended": before.is_suspended,
        "probes": probes,
        "still_blocked": sorted(still_blocked),
        "resolved_errors": resolved,
        "requeued_reports": len(claimed),
        "daily_polish_scheduled": changed,
        "claimed_jobs": claimed,
        "state": llm_service_state.current(force=True).snapshot(public=False),
    }


def run_resume_work(claimed: list[ReportJobRecord]) -> dict[str, Any]:
    """재개 작업 — 보류 리포트 잡 이어 돌리기 + 게시 기준일 일운 보드 교정(백그라운드)."""
    from . import daily_fortune_polish, report_job_runner

    summary: dict[str, Any] = {"reports": [], "daily": None}
    if claimed:
        subjects: SubjectStore | None
        store: ReportJobStore | None
        try:
            subjects = SubjectStore()
            store = ReportJobStore()
        except ValueError:
            subjects = store = None
        for rec in claimed:
            if subjects is None or store is None:
                break
            try:
                summary["reports"].append(
                    report_job_runner.resume_suspended_job(rec, subjects, store)
                )
            except Exception as exc:  # noqa: BLE001 — 한 잡의 실패가 나머지를 막지 않도록
                _logger.exception("보류 리포트 잡 재개 실패 job=%s", rec.job_id)
                summary["reports"].append({"job_id": rec.job_id, "resumed": False,
                                           "reason": f"{type(exc).__name__}: {exc}"})
    try:
        from saju_engines.daily_fortune_cache import default_cache

        summary["daily"] = daily_fortune_polish.resume_polish_after_suspension(default_cache())
    except ValueError:
        summary["daily"] = {"action": "skipped_no_cache"}
    except Exception as exc:  # noqa: BLE001 — 일운 교정 실패가 재개를 되돌리지 않는다
        _logger.exception("재개 후 일운 교정 실패")
        summary["daily"] = {"action": "error", "detail": f"{type(exc).__name__}: {exc}"}
    _logger.info("LLM 재개 작업 완료 — %s", summary)
    return summary


def manual_suspend(admin_id: str, reason: str) -> dict[str, Any]:
    """수동 중단(점검용) — 이미 중단이면 no-op."""
    changed = llm_service_state.suspend(reason or "manual")
    if changed:
        _logger.warning("LLM 서비스 수동 중단 — by=%s reason=%s", admin_id, reason)
    return {
        "suspended": changed,
        "state": llm_service_state.current(force=True).snapshot(public=False),
    }
