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
                "validationPolicyHash", "validationCorpusHash",
                "validationArtifactHash", "reviewed"}
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
            "validated_token_counters": (
                pipeline.get("validatedTokenCounters") or []),
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


_ARTIFACT_DIR = (Path(__file__).resolve().parents[4] / "compiled"
                 / "risk_adapter_validation")


def _artifact_corpus_ok(model_id: str, corpus_hash: str) -> bool:
    """validation artifact의 native corpus·artifact 재해시 검증(감수 59차
    §1·§3) — runtime이 artifact를 직접 신뢰 근거로 쓰므로 둘 다 확인."""
    import hashlib
    if not corpus_hash or not _ARTIFACT_DIR.exists():
        return False
    for path in sorted(_ARTIFACT_DIR.glob("*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            native = artifact["nativeValidationCorpus"]
            if native["identity"].get("resolvedModelId") != model_id:
                continue
            native_ok = hashlib.sha256(json.dumps(
                native, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest() == corpus_hash == str(
                artifact.get("validationCorpusHash"))
            artifact_ok = hashlib.sha256(json.dumps(
                {k: v for k, v in artifact.items()
                 if k not in ("volatile", "validationArtifactHash")},
                ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest() == str(artifact.get("validationArtifactHash"))
            return native_ok and artifact_ok
        except (OSError, ValueError, KeyError, TypeError):
            return False  # 손상 artifact=신뢰 불가(fail-closed)
    return False


def stamp_runtime_adapter_state(model_id: str) -> str:
    """startup/registry 초기화용 runtime 상태 결정 해소(감수 59차 §3).

    VALIDATED는 설정값이 아니라 검증 결과: adapter 존재 + artifact
    native/전체 재해시 일치 + manifest reviewed entry(7요소) 일치 +
    suspension 정상·기록 없음일 때만. 요청 처리 중 임의 대입 금지 —
    이 함수만이 VALIDATED를 스탬프한다.
    """
    from .token_counter_registry import (
        derive_runtime_adapter_state,
        resolve_counter,
        set_validation_state,
    )
    adapter = resolve_counter(model_id)
    counters = _load_manifest_snapshot()["validated_token_counters"]
    artifact_ok = (adapter is not None and _artifact_corpus_ok(
        model_id, adapter.validation_corpus_hash))
    state = derive_runtime_adapter_state(adapter, counters, artifact_ok)
    if adapter is not None:
        set_validation_state(model_id, state)
    return state


def build_risk_output_schemas(payload: dict, *,
                              question_type: str) -> dict:
    """INJECTED 전용 output schema 산출(감수 57차 §4 — canonical/transport
    분리).

    canonical(build_risk_output_schema — additionalProperties=false·요청별
    guidance_ref enum·episode 수 기반 maxItems)이 서비스 정본이고, Gemini
    transport는 provider 수용용 축소 표현이다. transport가 표현하지 못하는
    계약은 후처리 validator(validate_risk_guidance_envelope + claim
    audit)가 canonical 기준으로 전부 재검사한다.
    """
    from saju_engines.risk_claim_audit import build_risk_output_schema
    from saju_engines.risk_selection import BUDGET_BY_QUESTION_TYPE

    from .gemini_token_adapter import build_gemini_transport_schema

    episodes = payload.get("llmRiskEpisodes") or []
    policy = BUDGET_BY_QUESTION_TYPE.get(question_type)
    hard_max = policy.hard_max if policy is not None else len(episodes)
    canonical = build_risk_output_schema(episodes, hard_max=hard_max)
    return {"canonical": canonical,
            "gemini_transport": build_gemini_transport_schema(canonical)}


def map_intent_for_exposure(
    intent,
    stored_episode_keys: tuple[tuple[str, str, str], ...] = (),
) -> dict | None:
    """파서 SSOT 질문 유형 매핑 공개 helper(감수 62차 P0② — R2 예산 선별용).

    apply_risk_exposure와 동일한 매핑(map_intent_to_exposure_question)을
    노출 전에 한 번 더 쓸 수 있게 한다(payload 선별의 question_type 소스).
    stored_episode_keys는 episode_followup 결정적 해소용(직전 위험 답변
    저장 키). 실패=None(호출부는 예산 미적용 — 게이트가 어차피 BYPASS).
    """
    if intent is None:
        return None
    return map_intent_to_exposure_question(intent, stored_episode_keys)


def risk_reserve_active(
    mapped: dict | None,
    payload: dict | None,
    runtime_inputs: dict | None,
) -> bool:
    """RISK_CONTEXT_RESERVE 활성 판정(감수 62차 P0⑥ — 테스트 게이트 5).

    **실제 주입 예정 요청에만** 예약을 적용한다: 매핑 성공 + 적격 episode
    ≥1 + adapter 해소(VALIDATED — counter 존재) + reviewed shape 존재 +
    전역/동반자 kill switch off. BYPASS 사전 확정(TIMELESS·후보 0건·lease
    무효 등)에는 False — 일반 답변 예산을 줄이지 않는다.
    """
    if mapped is None or not payload or runtime_inputs is None:
        return False
    if not payload.get("llmRiskEpisodes"):
        return False
    if runtime_inputs.get("counter") is None:
        return False
    if not runtime_inputs.get("reviewed_shape_digests"):
        return False
    if risk_engine_config.RISK_EXPOSURE_KILL_SWITCH:
        return False
    if (mapped.get("subject_scope") == "companion_pair"
            and risk_engine_config.RISK_COMPANION_KILL_SWITCH):
        return False
    return True


def apply_risk_exposure(
    prompt_text: str,
    system: str | None,
    *,
    intent=None,  # IntentJson — 지정 시 파서 SSOT 매핑(감수 50차 §9-①)
    stored_episode_keys: tuple[tuple[str, str, str], ...] = (),
    subject_scope: str = "single",
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
        mapped = map_intent_to_exposure_question(intent, stored_episode_keys)
        if mapped is not None:
            question_type = mapped["question_type"]
            temporal_scope = mapped["temporal_scope"]
            future_period_range = mapped["future_period_range"]
            subject_scope = mapped.get("subject_scope", subject_scope)
    # 동반자 경로(감수 62차 P0④·⑩): ①companion kill switch — 동반자
    # 노출만 차단(본인 유지) ②claim ceiling을 게이트·감사 **이전** payload
    # 수준에 적용(프롬프트 지시가 아니라 코드·감사 단계 — 감사기는 유효
    # 수준 기준으로 검사).
    companion = subject_scope == "companion_pair"
    if companion and risk_engine_config.RISK_COMPANION_KILL_SWITCH:
        return (prompt_text, system, {
            "disposition": "BYPASS",
            "reason": "COMPANION_KILL_SWITCH",
            "subject_scope": subject_scope})
    if companion and payload:
        from saju_engines.risk_exposure import apply_companion_ceiling
        payload = apply_companion_ceiling(payload)
    mode = (RiskEngineMode.EXPOSE
            if risk_engine_config.RISK_ENGINE_MODE == "expose"
            else RiskEngineMode.EXPOSE_CANARY)
    snapshot = _load_manifest_snapshot()  # 요청 전체가 동일 snapshot 사용
    manifest_reviewed = snapshot["reviewed"]
    manifest_hash_ok = snapshot["hash_ok"]
    # 모드 인지 허용 유형(감수 62차): expose=5유형, expose_canary=3유형
    # (롤백 안전망). 미허용 유형은 __unmapped__ → 게이트 BYPASS.
    allowed_types = (
        risk_engine_config.RISK_EXPOSED_QUESTION_TYPES
        if mode is RiskEngineMode.EXPOSE
        else risk_engine_config.RISK_CANARY_QUESTION_TYPES)
    qt: str = (question_type if question_type is not None
               and question_type in allowed_types else "__unmapped__")
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
        # 감수 56차 §4: marker 기록까지 실패해도 전 worker 차단이 보장되는
        # 배포 조합에서만 EXPOSE 진입(파일 backend=단일 프로세스만).
        topology_canary_eligible=(
            (risk_engine_config.RISK_SUSPENSION_BACKEND,
             risk_engine_config.RISK_DEPLOYMENT_TOPOLOGY)
            in risk_engine_config._CANARY_ELIGIBLE_SUSPENSION_COMBOS),
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
        # provider output schema 3상태(감수 52차 §7 + 57차 §4): INJECTED만
        # risk-enabled schema — canonical 정본 + Gemini transport 변환을
        # 함께 산출(관측·provider 호출부 소비). BYPASS/SUPPRESSED는 기존
        # schema 그대로(request byte-identical / guard만).
        result["observability"]["output_schema_state"] = "RISK_ENABLED"
        # 호출부(provider 요청 조립) 소비 경로 — canonical이 정본, transport
        # 는 provider 전송용. BYPASS/SUPPRESSED 반환에는 이 키 자체가 없다.
        result["observability"]["risk_output_schemas"] = (
            build_risk_output_schemas(
                {"llmRiskEpisodes": result.get("audit_records") or []},
                question_type=qt))
        # 무결성 wrapper(감수 46·47차 — 테마사주 배선 차에서 실적용):
        # BEGIN_RISK_BLOCK:<checksum>…END marker로 감싸 flow preflight의
        # 단일 삽입·checksum 검증(verify_risk_block_integrity)과 정합.
        import hashlib as _hashlib

        from saju_engines.risk_exposure import (
            RiskPromptBlock,
            wrap_risk_block,
        )
        block = RiskPromptBlock(
            serialized_text=block_text,
            content_hash=_hashlib.sha256(
                block_text.encode()).hexdigest()[:16],
            compression_mode=str(result["observability"].get(
                "compression_mode", "TIERED")),
            exact_token_count=0)
        new_prompt = (prompt_text + "\n" + RISK_EXPOSURE_INSTRUCTION_BLOCK
                      + "\n" + wrap_risk_block(block))
        if companion:
            # 동반자 부가 고지(감수 62차 — 기존 블록 불변·부가 전용).
            from saju_engines.risk_exposure import (
                RISK_EXPOSURE_COMPANION_NOTICE_BLOCK,
            )
            new_prompt = (new_prompt + "\n"
                          + RISK_EXPOSURE_COMPANION_NOTICE_BLOCK)
            result["observability"]["subject_scope"] = subject_scope
        assert verify_risk_block_integrity(new_prompt, block)
        return new_prompt, system, result["observability"]
    result["observability"].setdefault(
        "output_schema_state", "BASE_UNCHANGED")
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
