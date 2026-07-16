"""위험 노출 배선 서비스 R5-b (감수 46차 — EXPOSE 계열 모드 전용).

chat_service가 최종 prompt 조립 직전에 호출한다. **OFF/SHADOW에서는 호출
분기 자체가 실행되지 않아 기존 prompt·system이 byte 불변**이다(회귀 fixture).

현 단계 계약(EXPOSE_CANARY 개시 전):
- expose_pipeline.reviewed=false + tokenizer adapter 부재 → 게이트가 전부
  비주입하고 suppressed guard만 부착된다(위험 정보는 어떤 경로로도 미주입).
- 질문 유형·temporal scope 매핑이 미확정이면 fail-closed(DENY — guard만).
- canary allowlist는 인증된 내부 subject ID 기준·조회 실패=비주입.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from saju_engines import risk_engine_config
from saju_engines.risk_exposure import (
    RISK_EXPOSURE_INSTRUCTION_BLOCK,
    RISK_EXPOSURE_SUPPRESSED_GUARD,
    ExposureGateContext,
    evaluate_risk_exposure_gate,
    expose_policy_hash,
    verify_risk_block_integrity,
)
from saju_shared_types.risk_engine import RiskEngineMode

_logger = logging.getLogger("saju.risk_exposure")
_MANIFEST_PATH = (Path(__file__).resolve().parents[4].parent
                  / "doc" / "v2_2" / "RISK_REVIEW_MANIFEST.json")

__all__ = ["apply_risk_exposure", "exposure_mode_active"]


def _manifest_expose_state() -> tuple[bool, bool]:
    """(expose_pipeline reviewed, policy hash 일치) — 감수 SSOT는 manifest.

    로드 실패·필드 부재·해시 불일치 전부 (False, False) — fail-closed
    (환경변수가 감수 사실을 대체할 수 없다, 감수 48차 §4).
    """
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        pipeline = manifest.get("expose_pipeline") or {}
        reviewed = bool(pipeline.get("reviewed"))
        hash_ok = (pipeline.get("expose_policy_hash")
                   == expose_policy_hash())
        return reviewed, hash_ok
    except (OSError, ValueError):
        return False, False


def exposure_mode_active() -> bool:
    """EXPOSE 계열 모드 여부 — OFF/SHADOW면 배선 분기 자체를 건너뛴다."""
    return risk_engine_config.RISK_ENGINE_MODE in ("expose_canary", "expose")


def _canary_allowlisted(subject_id: str | None) -> bool:
    """canary allowlist 판정(감수 46차 §14 — 기본 거부).

    인증된 내부 subject ID만 인정: ID 부재·allowlist 비어 있음·조회 실패
    전부 False. 로그에는 원문 대신 해시를 남긴다.
    """
    if not subject_id:
        return False
    allow = risk_engine_config.RISK_EXPOSE_CANARY_SUBJECT_IDS
    ok = bool(allow) and subject_id in allow
    _logger.info("risk_canary_check subject=%s allowed=%s",
                 hashlib.sha256(subject_id.encode()).hexdigest()[:12], ok)
    return ok


def apply_risk_exposure(
    prompt_text: str,
    system: str | None,
    *,
    payload: dict | None = None,
    question_type: str | None = None,
    temporal_scope: str | None = None,
    future_period_range: tuple[str, str] | None = None,
    subject_id: str | None = None,
    counter=None,
    counter_model_id: str | None = None,
    resolved_model_id: str | None = None,
    model_context_limit: int = 0,
    base_prompt_tokens: int = 0,
    user_input_tokens: int = 0,
    existing_context_tokens: int = 0,
    response_reserve: int = 0,
) -> tuple[str, str | None, dict]:
    """EXPOSE 계열 모드의 위험 노출 적용(단일 진입점 — fail-closed).

    게이트 전 조건 통과 시 instruction block + immutable risk block을
    prompt에 부착하고, 아니면 suppressed guard만 부착한다(주입 실패 상태로
    위험 정보를 절대 싣지 않음). 반환: (prompt, system, observability).
    """
    mode = (RiskEngineMode.EXPOSE
            if risk_engine_config.RISK_ENGINE_MODE == "expose"
            else RiskEngineMode.EXPOSE_CANARY)
    manifest_reviewed, manifest_hash_ok = _manifest_expose_state()
    canary_types = risk_engine_config.RISK_CANARY_QUESTION_TYPES
    qt = question_type if question_type in canary_types else "__unmapped__"
    ctx = ExposureGateContext(
        mode=mode,
        question_type=qt,
        temporal_scope=temporal_scope or "past_only",  # 미확정=fail-closed
        risk_intent_allowed=True,
        token_count_mode=("MODEL_TOKENIZER" if counter is not None
                          else "HEURISTIC_FALLBACK"),
        model_context_limit=model_context_limit,
        base_prompt_tokens=base_prompt_tokens,
        user_input_tokens=user_input_tokens,
        existing_context_tokens=existing_context_tokens,
        response_reserve=response_reserve,
        scopes_all_reviewed=True,  # 항목 5 scope 49/49(회귀 테스트 강제)
        policy_hashes_match=manifest_hash_ok,
        canary_allowlisted=_canary_allowlisted(subject_id),
        kill_switch=risk_engine_config.RISK_EXPOSURE_KILL_SWITCH,
        # 감수 SSOT=manifest(reviewed+hash), runtime enabled는 활성화만 —
        # **둘 다** true여야 주입 가능(한쪽만 true=BYPASS, 감수 48차 §4).
        expose_pipeline_reviewed=(
            manifest_reviewed
            and risk_engine_config.RISK_EXPOSURE_RUNTIME_ENABLED),
        counter_model_id=counter_model_id,
        resolved_model_id=resolved_model_id,
        future_period_range=future_period_range,
    )
    empty: dict = {
        "globalProhibitedClaimCodes": [], "globalAllowedClaimCodes": [],
        "presentationRecords": [], "llmRiskEpisodes": []}
    result = evaluate_risk_exposure_gate(ctx, payload or empty, counter)
    disposition = result["disposition"]
    if disposition == "INJECTED":
        block_text = result["serialized"]
        new_prompt = (prompt_text + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                      + "\n" + block_text)
        # provider request 직전 무결성 재확인(감수 46·47차)은 canary 개시
        # 차수에서 RiskPromptBlock+wrap_risk_block 경유로 교체·검증한다.
        _ = verify_risk_block_integrity
        return new_prompt, system, result["observability"]
    if disposition == "SUPPRESSED":
        # 노출 자격은 있으나 런타임 조건으로 안전 주입 불가 — guard만
        # (위험 정보 자체는 어떤 필드에도 없음).
        return (prompt_text + "\n" + RISK_EXPOSURE_SUPPRESSED_GUARD, system,
                result["observability"])
    # BYPASS(감수 47차 §1): 위험 노출 파이프라인의 적용 대상이 아닌 요청 —
    # "위험 정보가 없는 노출 요청"이 아니라 "파이프라인을 전혀 거치지 않은
    # 기존 요청"이다. guard조차 없이 prompt 한 바이트도 바꾸지 않는다
    # (진단은 observability 로그로만).
    return prompt_text, system, result["observability"]
