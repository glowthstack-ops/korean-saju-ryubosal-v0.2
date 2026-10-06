"""리포트 잡 실행기 — 라우터(BackgroundTasks)와 관리자 재개 경로가 공유한다 (2026-10-06).

종전에는 `routers/report.py` 안의 `_run_report_job` 이 유일한 실행 경로였다. LLM 서비스
일시 중단(비용 소진) 재개가 같은 실행기를 써야 하므로 서비스 계층으로 옮겼다. 라우터는
이 모듈을 import 하고, 관리자 재개(`llm_resume_service`)도 여기서 보류 잡을 이어 돌린다.

중단 처리 규약
- 생성 도중 `LLMServiceSuspended` 가 올라오면 잡을 **보류**한다: status='queued' +
  error='LLM_SUSPENDED', 그때까지 통과한 섹션과 재실행 컨텍스트를 result 에 보존.
- 재개 시 `prior_sections` 로 통과 섹션을 돌려주어 그 섹션들은 LLM 을 다시 부르지 않는다.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date
from typing import Any

from saju_engines.report_job_store import ReportJobRecord, ReportJobStore
from saju_engines.report_plan import is_pair_relationship
from saju_engines.subject_store import SubjectStore
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind
from saju_shared_types.report import ReportSpec, SectionResult

from . import error_logging, report_service
from .llm_client import LLMServiceSuspended
from .partner_resolve import inline_to_birth

_logger = logging.getLogger(__name__)


def resolve_partner_birth(
    spec: ReportSpec, subjects: SubjectStore | None, owner_id: str | None,
) -> BirthInput | None:
    """관계운 궁합 모드 — 상대 subject를 BirthInput으로 해석.

    INLINE_TEMP(inline_birth)는 그 자리에서, COMPANION(companion_id)은 SubjectStore로 조회.
    상대를 해석하지 못하면 None(서비스는 단독 모드로 강등 — 빈 궁합 블록 안내).
    """
    if not is_pair_relationship(spec):
        return None
    partner = next((s for s in spec.subjects if s.kind != SubjectKind.SELF), None)
    if partner is None:
        return None
    if partner.inline_birth is not None:
        return inline_to_birth(partner.inline_birth)
    if subjects is not None and partner.companion_id:
        rec = subjects.get(partner.companion_id)
        if rec is not None and (owner_id is None or rec.owner_id == owner_id):
            return rec.birth
    return None


def run_report_job(
    job_id: str, birth: BirthInput, spec: ReportSpec, today: date | None, display_name: str,
    owner_id: str, subject_id: str, partner_birth: BirthInput | None = None,
    *,
    prior_sections: dict[str, SectionResult] | None = None,
    store: ReportJobStore | None = None,
) -> None:
    """백그라운드 실행 — 성공 시 complete, LLM 중단 시 suspend(보류), 그 외 실패 시 fail."""
    store = store or ReportJobStore()
    store.mark_running(job_id)

    def _on_progress(done: int, total: int) -> None:
        # total = 분할 페이지 확장 후 실제 총 장 수 — 생성 시점의 확장 전 계획 수를 교체한다.
        try:
            store.update_progress(job_id, done, total)
        except Exception:  # noqa: BLE001 — 진행 갱신 실패가 생성을 막지 않도록
            pass

    # 통과 섹션 수집(중단 시 부분 보존) — 재개 입력(prior)도 포함해 전체 집합을 유지한다.
    collected: dict[str, SectionResult] = {
        k: v for k, v in (prior_sections or {}).items() if v.passed
    }

    def _sink(sec: SectionResult) -> None:
        if sec.passed:
            collected[sec.section_id] = sec

    try:
        result = report_service.generate_report(
            birth, spec, today, display_name=display_name,
            owner_id=owner_id, subject_id=subject_id, partner_birth=partner_birth,
            progress_fn=_on_progress, prior_sections=prior_sections, section_sink=_sink,
        )
        store.complete(job_id, result.model_dump(mode="json"), len(result.sections))
    except LLMServiceSuspended:
        payload = {
            "resume": {
                "subject_id": subject_id,
                "today": today.isoformat() if today else None,
                "display_name": display_name,
            },
            "partial_sections": [s.model_dump(mode="json") for s in collected.values()],
        }
        store.suspend(job_id, payload, sections_done=len(collected))
        # 중단 자체는 llm_client 가 system_errors 에 1건 기록했다 — 잡마다 다시 쌓지 않는다.
        _logger.warning(
            "report job 보류(LLM 서비스 중단) job=%s owner=%s kept_sections=%d",
            job_id, owner_id, len(collected),
        )
    except RuntimeError as exc:
        store.fail(job_id, str(exc))
        _log_job_error(exc, job_id, owner_id, str(exc))
    except Exception as exc:  # noqa: BLE001 — 잡 실패는 사유 보존이 우선
        store.fail(job_id, f"생성 오류: {exc}")
        _log_job_error(exc, job_id, owner_id, f"생성 오류: {exc}")


def _log_job_error(exc: BaseException, job_id: str, owner_id: str, message: str) -> None:
    """리포트 잡 실패를 에러 모니터링에 적재 — 이미 기록된 예외(예: LLM 실패)는 중복 제외."""
    if error_logging.is_logged(exc):
        return
    with contextlib.suppress(Exception):
        error_logging.record_error(
            source="report_job", kind=type(exc).__name__, message=message,
            path="report.generate", owner_id=owner_id, ref_id=job_id, exc=exc,
        )


def resume_suspended_job(
    rec: ReportJobRecord, subjects: SubjectStore, store: ReportJobStore,
) -> dict[str, Any]:
    """보류 잡 1건을 이어 돌린다(이미 `claim_suspended` 로 running 전환된 레코드).

    result 에 보존된 재실행 컨텍스트로 출생정보·상대를 다시 해석하고, 통과 섹션은
    prior_sections 로 넘겨 재생성하지 않는다. 대상 사주가 삭제됐으면 fail 로 마감한다.
    """
    payload: dict[str, Any] = rec.result if isinstance(rec.result, dict) else {}
    resume_raw = payload.get("resume")
    ctx: dict[str, Any] = resume_raw if isinstance(resume_raw, dict) else {}
    subject_id = str(ctx.get("subject_id") or "")
    spec = ReportSpec.model_validate(rec.spec)
    record = subjects.get(subject_id) if subject_id else None
    if record is None or record.owner_id != rec.owner_id:
        store.fail(rec.job_id, "재개 실패 — 대상 사주를 찾을 수 없습니다.")
        return {"job_id": rec.job_id, "resumed": False, "reason": "subject_missing"}
    today_raw = ctx.get("today")
    today = date.fromisoformat(str(today_raw)) if today_raw else None
    display_name = str(ctx.get("display_name") or record.label or "회원")
    prior: dict[str, SectionResult] = {}
    for raw in payload.get("partial_sections") or []:
        try:
            sec = SectionResult.model_validate(raw)
        except Exception:  # noqa: BLE001 — 손상된 항목은 재생성 대상으로 둔다
            continue
        if sec.passed:
            prior[sec.section_id] = sec
    partner_birth = resolve_partner_birth(spec, subjects, rec.owner_id)
    run_report_job(
        rec.job_id, record.birth, spec, today, display_name,
        rec.owner_id, subject_id, partner_birth, prior_sections=prior, store=store,
    )
    return {"job_id": rec.job_id, "resumed": True, "reused_sections": len(prior)}
