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
    """health 응답용 위험 노출 readiness(서비스 전체와 분리 — P1).

    구필드 3종(risk_exposure_readiness·risk_exposure_mode·
    risk_bootstrap_reason)은 그대로 유지하고, 저하 **원인**을 분리한
    세부 필드를 추가한다(2026-08-04 데굴님 승인). 상위 기능 상태와 원인
    상태를 함께 보여 "위험 판정에 LLM을 쓴다"는 오해를 없애는 것이
    목적이다 — 검증 대상은 생성 모델의 위험 판단이 아니라 countTokens
    계수 경로와 identity 정합성이다.
    """
    mode = risk_engine_config.RISK_ENGINE_MODE
    if mode not in ("expose", "expose_canary"):
        return {"risk_exposure_readiness": "DISABLED",
                "risk_exposure_mode": mode}
    try:
        from .llm_client import reading_model
        from .risk_exposure_bootstrap import last_bootstrap_reason
        from .risk_exposure_service import stamp_state_snapshot
        from .risk_validation_lease import LEASE_STATUS_VALID, lease_status
        from .token_counter_registry import (
            adapter_identity_hash,
            cache_path_state,
            cache_protection_expires_at,
            cache_protection_metrics,
            resolve_counter,
        )
        state = stamp_state_snapshot()
        ready = state == "VALIDATED"
        model_id = reading_model()
        # adapter 미등록(artifact 결함 등)이면 identity 대조는 생략한다 —
        # 없는 identity로 MISMATCH를 단정하지 않는다.
        adapter = resolve_counter(model_id)
        lease = lease_status(
            model_id,
            adapter_identity_hash(adapter) if adapter is not None else None)
        bootstrap_reason = last_bootstrap_reason()
        # lease 결함이 있으면 그것이 복구를 막는 근본 원인이다. lease가
        # 정상인데 저하 상태면 artifact·manifest·topology 쪽 사유를 쓴다.
        degradation = (f"RISK_TOKEN_COUNTER_{lease['status']}"
                       if lease["status"] != LEASE_STATUS_VALID
                       else bootstrap_reason)
        cache_state = cache_path_state(model_id)
        cache_protected = cache_state == "CACHE_PATH_OBSERVED_UNVALIDATED"
        # readiness와 mode의 의미 분리(2026-08-04 승인 §4):
        #   readiness = 검증된 비캐시 adapter가 등록되어 있는가(자격)
        #   mode      = 지금 요청이 실제로 타는 경로(현재 동작)
        # 보호창이 열리면 자격은 유효해도 주입은 BYPASS되므로, READY인
        # 채로 mode만 정상으로 보이면 운영이 오독한다.
        if ready and cache_protected:
            effective_mode = "BYPASS_CACHE_PATH_UNVALIDATED"
        elif ready:
            effective_mode = mode
        else:
            effective_mode = f"BYPASS_{state or 'UNKNOWN'}"
        if degradation is None and cache_protected:
            degradation = "RISK_CACHE_PATH_OBSERVED_UNVALIDATED"
        return {
            "risk_exposure_readiness": "READY" if ready else "DEGRADED",
            "risk_exposure_mode": effective_mode,
            "risk_bootstrap_reason": bootstrap_reason,
            "risk_token_counter_validation": lease["status"],
            "risk_token_counter_model": model_id,
            "risk_token_counter_lease_expires_at": lease["expires_at"],
            # 캐시 경로 관측 상태 — CACHE_PATH_OBSERVED_UNVALIDATED는
            # 휘발성 주입 보호창이 열린 상태다(identity 무효 아님).
            # 이 상태는 readiness=READY 인데도 주입이 BYPASS되므로 별도
            # 노출하지 않으면 운영에서 보이지 않는다.
            "risk_cache_path_state": cache_state,
            "risk_cache_protection_expires_at": (
                cache_protection_expires_at(model_id)),
            # 보호창이 정상적으로 풀릴 예정인지·연장이 쌓이는지 관측.
            "risk_cache_protection_metrics": {
                k: v for k, v in cache_protection_metrics(model_id).items()
                if k != "expires_at"},
            "risk_degradation_reason": degradation,
        }
    except Exception:  # noqa: BLE001
        return {"risk_exposure_readiness": "DEGRADED",
                "risk_exposure_mode": "UNKNOWN",
                "risk_token_counter_validation": None,
                "risk_token_counter_model": None,
                "risk_token_counter_lease_expires_at": None,
                "risk_cache_path_state": None,
                "risk_cache_protection_expires_at": None,
                "risk_cache_protection_metrics": None,
                "risk_degradation_reason": "RISK_READINESS_SNAPSHOT_FAILED"}
