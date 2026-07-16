"""위험 노출 startup 배선(감수 61차 §13 — freeze 후 통합 작업 ①②).

EXPOSE 계열 모드에서만 동작한다 — OFF/SHADOW에서는 모든 함수가 no-op
(기존 경로 byte 불변). 역할:

- **startup stamp**: 실물 Gemini adapter를 reviewed artifact의 corpus
  hash로 명시 등록하고 stamp_runtime_adapter_state로 runtime 상태를
  **검증 결과로 파생**(감수 59차 §3 — VALIDATED는 설정값이 아님).
- **runtime 입력 공급**: chat_service EXPOSE 분기에 counter(감수된
  adapter)·context limit(llm_config — 부재·0=게이트 BYPASS 유지)·
  reviewed request shape digest 집합(감수 60차 §5)을 공급한다.

주의: adapter counter는 provider countTokens **네트워크 호출**이다 —
EXPOSE 계열 요청에서만 사용되며(OFF/SHADOW 미실행), canary에서 지연·
실패율을 관측한다(실패=예외 전파 → 게이트 fail-closed).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from saju_engines import risk_engine_config

_logger = logging.getLogger("saju_api.risk")

_ARTIFACT_DIR = (Path(__file__).resolve().parents[4] / "compiled"
                 / "risk_adapter_validation")

__all__ = ["bootstrap_risk_exposure", "exposure_runtime_inputs",
           "load_reviewed_shape_digests"]


def _exposure_mode_active() -> bool:
    return risk_engine_config.RISK_ENGINE_MODE in ("expose_canary",
                                                   "expose")


def _find_artifact(model_id: str) -> dict | None:
    """모델의 validation artifact 로드(손상=None — fail-closed)."""
    if not _ARTIFACT_DIR.exists():
        return None
    for path in sorted(_ARTIFACT_DIR.glob("*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            native = artifact["nativeValidationCorpus"]
            if native["identity"].get("resolvedModelId") == model_id:
                return artifact
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return None


def load_reviewed_shape_digests(model_id: str) -> frozenset[str]:
    """artifact의 reviewed request shape digest 집합(감수 60차 §5).

    부재·손상=빈 집합 — preflight가 모든 attempt를
    REQUEST_SHAPE_NOT_REVIEWED로 차단한다(fail-closed).
    """
    artifact = _find_artifact(model_id)
    if artifact is None:
        return frozenset()
    entries = artifact.get("reviewedRequestShapeDigests") or []
    return frozenset(str(e.get("digest", "")) for e in entries
                     if isinstance(e, dict) and e.get("digest"))


def bootstrap_risk_exposure() -> str | None:
    """startup 1회 배선(감수 61차 §13-②) — EXPOSE 계열 모드 전용.

    reviewed artifact의 corpus hash로 실물 adapter를 등록하고 runtime
    상태를 검증 결과로 파생한다. OFF/SHADOW=None(아무것도 하지 않음).
    실패는 예외 대신 None+로그 — 게이트는 adapter 부재로 BYPASS.
    """
    if not _exposure_mode_active():
        return None
    try:
        from .gemini_token_adapter import register_gemini_shadow_adapter
        from .llm_client import reading_model
        from .risk_exposure_service import stamp_runtime_adapter_state

        model_id = reading_model()
        artifact = _find_artifact(model_id)
        corpus_hash = (str(artifact.get("validationCorpusHash", ""))
                       if artifact else "")
        register_gemini_shadow_adapter(model_id, corpus_hash)
        state = stamp_runtime_adapter_state(model_id)
        _logger.info("risk_adapter_bootstrap model=%s state=%s",
                     model_id, state)
        return state
    except Exception:  # noqa: BLE001 — startup 실패=미등록(BYPASS)
        _logger.exception("risk_adapter_bootstrap 실패 — BYPASS 유지")
        return None


def exposure_runtime_inputs(call_type: str = "chat_single") -> dict:
    """chat_service EXPOSE 분기용 runtime 입력(감수 61차 §13-①).

    반환: counter(감수 adapter의 단건 계수 — 미해소 시 None: 게이트
    TOKENIZER_UNAVAILABLE), counter_model_id, resolved_model_id,
    context_limit(llm_config primary.context_limit — 부재·0=BYPASS 유지),
    response_reserve(call_type 출력 한도), reviewed_shape_digests.
    """
    from saju_engines.llm_guard import LLMCallGuard

    from .llm_client import load_config, reading_model
    from .risk_exposure_service import _load_manifest_snapshot
    from .token_counter_registry import resolve_expose_counter

    model_id = reading_model()
    try:
        counters = _load_manifest_snapshot()["validated_token_counters"]
    except Exception:  # noqa: BLE001 — manifest 불가=BYPASS(fail-closed)
        counters = []
    adapter = resolve_expose_counter(model_id, counters)
    try:
        context_limit = int(
            load_config()["primary"].get("context_limit") or 0)
    except (ValueError, TypeError, KeyError):
        context_limit = 0  # 미등록·비정상=0 → 게이트 BYPASS(§11)
    try:
        response_reserve = int(
            LLMCallGuard(call_type).request_params()["max_tokens"])
    except Exception:  # noqa: BLE001
        response_reserve = 0
    return {
        "counter": adapter.counter if adapter is not None else None,
        "counter_model_id": (adapter.model_id
                             if adapter is not None else None),
        "resolved_model_id": model_id,
        "context_limit": context_limit,
        "response_reserve": response_reserve,
        "reviewed_shape_digests": load_reviewed_shape_digests(model_id),
    }
