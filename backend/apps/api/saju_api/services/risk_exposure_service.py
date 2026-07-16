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
from saju_engines.risk_question_mapping import (
    map_intent_to_exposure_question,
)
from saju_shared_types.risk_engine import RiskEngineMode

_logger = logging.getLogger("saju.risk_exposure")
_MANIFEST_PATH = (Path(__file__).resolve().parents[4].parent
                  / "doc" / "v2_2" / "RISK_REVIEW_MANIFEST.json")

__all__ = ["apply_risk_exposure", "exposure_mode_active"]


# manifest snapshot이 지원하는 해시 스키마(감수 49차 §2 — 미지원=fail-closed).
_SUPPORTED_MANIFEST_SCHEMA_VERSIONS = (10,)


def _load_manifest_snapshot() -> dict:
    """요청 단위의 일관된 manifest snapshot(감수 49차 §2).

    파일을 **한 번** 읽어 불변 snapshot으로 만든다 — reviewed·hash·schema
    version이 서로 다른 파일 버전에서 섞이는 혼합 상태(배포 중 교체)를
    차단한다. parse 실패·schema 미지원·필드 부재·digest 계산 실패 전부
    fail-closed(reviewed=False·hash_ok=False). 관측에는 원문 대신
    snapshot_hash만 남긴다.
    """
    try:
        raw = _MANIFEST_PATH.read_text(encoding="utf-8")  # 단일 read
        manifest = json.loads(raw)
        schema = int(manifest.get("hash_schema_version", -1))
        if schema not in _SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
            raise ValueError(f"미지원 manifest schema: {schema}")
        pipeline = manifest["expose_pipeline"]  # strict — 부재=실패
        if not isinstance(pipeline, dict):
            raise ValueError("expose_pipeline 타입 불일치")
        # 정책 구간 additionalProperties=false(감수 52차 §5 + 53차 §7):
        # 작성자는 적용됐다고 믿고 런타임은 무시하는 미등록 필드 차단 —
        # expose_pipeline·critical_validation_state·validatedTokenCounters
        # 전 구간.
        unknown = set(pipeline) - {"reviewed", "expose_policy_hash",
                                   "critical_validation_state",
                                   "validatedTokenCounters"}
        if unknown:
            raise ValueError(f"expose_pipeline 미등록 필드: {unknown}")
        cvs = pipeline.get("critical_validation_state") or {}
        cvs_unknown = set(cvs) - {"synthetic_fixtures",
                                  "corpus_positive_cases",
                                  "empirical_calibration",
                                  "expose_behavior"}
        if cvs_unknown:
            raise ValueError(f"critical_validation_state 미등록 필드:"
                             f" {cvs_unknown}")
        for counter_entry in pipeline.get("validatedTokenCounters") or []:
            entry_unknown = set(counter_entry) - {
                "providerId", "resolvedModelId", "counterVersion",
                "providerRequestSchemaVersion", "countMode",
                "validationPolicyHash", "validationCorpusHash", "reviewed"}
            if entry_unknown:
                raise ValueError(f"validatedTokenCounters 미등록 필드:"
                                 f" {entry_unknown}")
        reviewed = pipeline["reviewed"]
        if not isinstance(reviewed, bool):
            raise ValueError("reviewed 타입 불일치")
        policy_hash = pipeline["expose_policy_hash"]
        if not isinstance(policy_hash, str):
            raise ValueError("expose_policy_hash 타입 불일치")
        # canonical hash(감수 50차 §2): 공백·키 순서 차이에 불변 — parse된
        # JSON의 canonical 직렬화 기준.
        canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
        return {
            "reviewed": reviewed,
            "hash_ok": policy_hash == expose_policy_hash(),
            "schema_version": schema,
            "snapshot_hash": hashlib.sha256(
                canonical.encode()).hexdigest()[:16],
        }
    except (OSError, ValueError, TypeError, KeyError):
        return {"reviewed": False, "hash_ok": False,
                "schema_version": None, "snapshot_hash": None}


def _manifest_expose_state() -> tuple[bool, bool]:
    """(reviewed, hash 일치) — 하위 호환 wrapper(snapshot 단일 소스)."""
    snap = _load_manifest_snapshot()
    return snap["reviewed"], snap["hash_ok"]


def exposure_mode_active() -> bool:
    """EXPOSE 계열 모드 여부 — OFF/SHADOW면 배선 분기 자체를 건너뛴다."""
    return risk_engine_config.RISK_ENGINE_MODE in ("expose_canary", "expose")


_DEV_HMAC_KEY = b"dev-only-rotate-before-canary"


def _audit_hmac_key_valid() -> bool:
    """운영 HMAC 키 검증(감수 53차 §8 — 구조적 차단): 개발 기본키·32byte
    미만이면 False → 게이트 AUDIT_HMAC_KEY_INVALID BYPASS. secret 자체는
    policy hash 비포함(회전≠정책 변경) — 알고리즘·truncation만 hash에."""
    key = risk_engine_config.RISK_AUDIT_HMAC_KEY
    return key != _DEV_HMAC_KEY and len(key) >= 32


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
    intent=None,  # IntentJson — 지정 시 파서 SSOT 매핑(감수 50차 §9-①)
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
    if intent is not None:
        # 파서 정본 매핑(감수 50차 §9-① — fail-closed): 매핑 실패(None)면
        # 미매핑 상태 유지 → 게이트가 QUESTION_TYPE_NOT_ALLOWED로 BYPASS.
        mapped = map_intent_to_exposure_question(intent)
        if mapped is not None:
            question_type = mapped["question_type"]
            temporal_scope = mapped["temporal_scope"]
            future_period_range = mapped["future_period_range"]
    mode = (RiskEngineMode.EXPOSE
            if risk_engine_config.RISK_ENGINE_MODE == "expose"
            else RiskEngineMode.EXPOSE_CANARY)
    snapshot = _load_manifest_snapshot()  # 요청 전체가 동일 snapshot 사용
    manifest_reviewed = snapshot["reviewed"]
    manifest_hash_ok = snapshot["hash_ok"]
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
        audit_key_valid=_audit_hmac_key_valid(),
    )
    empty: dict = {
        "globalProhibitedClaimCodes": [], "globalAllowedClaimCodes": [],
        "presentationRecords": [], "llmRiskEpisodes": []}
    result = evaluate_risk_exposure_gate(ctx, payload or empty, counter)
    result["observability"]["manifest_snapshot_hash"] = (
        snapshot["snapshot_hash"])
    result["observability"]["manifest_schema_version"] = (
        snapshot["schema_version"])
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
