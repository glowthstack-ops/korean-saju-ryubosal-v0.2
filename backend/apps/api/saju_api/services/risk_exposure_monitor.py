"""위험 노출 운영 관측(감수 62차 7단계 — fail-closed but **fail-loud**).

사용자 응답은 fail-closed를 유지하되, 위험 시스템이 조용히 꺼진 상태
("서비스는 정상인데 위험만 BYPASS")를 운영이 즉시 알 수 있게 한다:

- readiness 분리: 서비스 전체 readiness와 별도의 risk_exposure_readiness
  (DEGRADED여도 일반 풀이 트래픽을 빼지 않는다 — health 응답 필드).
- 알림: EXPOSE에서 최초 BYPASS_UNVALIDATED/BYPASS_SUSPENDED 발생 시
  고우선 error_logging 적재(관리자 대시보드), 5분 창 반복은 집계 후
  임계(기본 10건) 초과 시 incident 승격 1회 적재.
- 지표: 유형별 disposition 카운터(INJECTED/BYPASS/SUPPRESSED/BLOCK),
  counted−reported delta 관측 — 관리자 조회용 스냅샷 제공.
"""

from __future__ import annotations

import threading
import time
from collections import Counter

from saju_engines import risk_engine_config

__all__ = ["observe_disposition", "risk_readiness_snapshot"]

_LOCK = threading.Lock()
_DISPOSITIONS: Counter[str] = Counter()
_FIRST_ALERTED: set[str] = set()
_WINDOW: list[tuple[float, str]] = []  # (ts, reason) — 5분 창
_WINDOW_SECONDS = 300
_INCIDENT_THRESHOLD = 10
_INCIDENT_RAISED: set[str] = set()

# 조용한 실패로 이어지는 BYPASS 사유(감수 62차) — lease 만료·modelVersion
# 변경(UNVALIDATED)이 SUSPENDED보다 발생 확률이 높다.
_LOUD_REASONS = ("TOKENIZER_UNAVAILABLE", "COMPANION_KILL_SWITCH")
_LOUD_STATES = ("SUSPENDED", "UNVALIDATED")


def observe_disposition(observability: dict, *, surface: str) -> None:
    """게이트 관측 1건 적재 — 실패는 절대 흐름을 막지 않는다(best-effort)."""
    try:
        disposition = str(observability.get("disposition", ""))
        reason = str(observability.get("reason", "") or "")
        key = f"{surface}:{disposition}:{reason or '-'}"
        with _LOCK:
            _DISPOSITIONS[key] += 1
        if risk_engine_config.RISK_ENGINE_MODE not in ("expose",
                                                       "expose_canary"):
            return
        if disposition != "BYPASS" or reason not in _LOUD_REASONS:
            return
        from .risk_exposure_service import stamp_state_snapshot
        state = stamp_state_snapshot()
        loud_key = f"{reason}:{state}"
        now = time.monotonic()
        with _LOCK:
            _WINDOW.append((now, loud_key))
            while _WINDOW and _WINDOW[0][0] < now - _WINDOW_SECONDS:
                _WINDOW.pop(0)
            first = loud_key not in _FIRST_ALERTED
            if first:
                _FIRST_ALERTED.add(loud_key)
            window_count = sum(1 for _, k in _WINDOW if k == loud_key)
            incident = (window_count >= _INCIDENT_THRESHOLD
                        and loud_key not in _INCIDENT_RAISED)
            if incident:
                _INCIDENT_RAISED.add(loud_key)
        if first or incident:
            from . import error_logging
            error_logging.record_error(
                source="risk_exposure", kind=(
                    "RISK_EXPOSE_INCIDENT" if incident
                    else "RISK_EXPOSE_BYPASS_FIRST"),
                severity="error",
                message=(f"EXPOSE 모드 위험 노출 {disposition}"
                         f" reason={reason} adapter_state={state}"
                         + (f" — 5분 창 {window_count}건(임계 초과)"
                            if incident else " — 최초 발생")),
                path=surface)
    except Exception:  # noqa: BLE001 — 관측 실패 무해
        pass


def risk_readiness_snapshot() -> dict:
    """health 응답용 위험 노출 readiness(서비스 전체와 분리 — P1)."""
    mode = risk_engine_config.RISK_ENGINE_MODE
    if mode not in ("expose", "expose_canary"):
        return {"risk_exposure_readiness": "DISABLED",
                "risk_exposure_mode": mode}
    try:
        from .risk_exposure_bootstrap import last_bootstrap_reason
        from .risk_exposure_service import stamp_state_snapshot
        state = stamp_state_snapshot()
        ready = state == "VALIDATED"
        return {
            "risk_exposure_readiness": "READY" if ready else "DEGRADED",
            "risk_exposure_mode": (
                mode if ready else f"BYPASS_{state or 'UNKNOWN'}"),
            "risk_bootstrap_reason": last_bootstrap_reason(),
        }
    except Exception:  # noqa: BLE001
        return {"risk_exposure_readiness": "DEGRADED",
                "risk_exposure_mode": "UNKNOWN"}
