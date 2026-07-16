"""위험 노출 게이트 R4 — EXPOSE 주입 자격의 단일 fail-closed 평가
(doc/v2_2/RISK_DICTIONARY_REVIEW.md §27 manifest, 감수 44차 착수 — gated).

핵심 원칙(데굴님): 위험 payload 자체가 안전하게 만들어졌더라도, 실제 모델·
질문·프롬프트의 남은 토큰과 감수 상태를 모두 확인하기 전에는 절대 주입하지
않는다. 불변식:

- tokenizer 필수: heuristic fallback 추정은 SHADOW 측정 전용 — EXPOSE에서
  adapter(PROVIDER_EXACT/MODEL_TOKENIZER) 부재면 TOKENIZER_UNAVAILABLE 비주입.
- 예산은 risk JSON이 아니라 **최종 prompt 전체 headroom** 기준 — 위험
  payload가 기존 본문·용신·사건 근거를 밀어내지 않는다.
- R2 episode budget(개수)과 R3 token budget(직렬화 길이)은 별도 정책.
- computed level(감사 보존)과 exposed level(LLM 전달) 분리 — critical은
  실증 검증(pending) 해제 전 warning으로 하향(item-level downgrade reason).
- 게이트는 전역 pipeline 계약(항목 49건 scope 아님) — expose_policy_hash가
  감수 표면. EXPOSE_CANARY(allowlist)를 거쳐 EXPOSE로 승격한다.
- 하나라도 실패하면 injectRiskPayload=false + 기계 판독 suppression reason.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from saju_shared_types.risk_engine import RiskEngineMode

from .risk_presentation import (
    DEFAULT_RISK_PRESENTATION_BUDGET,
    MIN_SAFE_RISK_PRESENTATION_BUDGET,
    serialize_llm_payload,
)

# 노출 게이트 버전 — 전역 pipeline 계약 변경 시 올린다(항목 scope 아님).
RISK_EXPOSURE_VERSION = "risk-expose-r4.0.0-gated"

# token 계수 모드(감수 44차 §4): heuristic은 SHADOW 전용 — EXPOSE 금지.
TOKEN_COUNT_MODES = ("PROVIDER_EXACT", "MODEL_TOKENIZER",
                     "HEURISTIC_FALLBACK")
_EXPOSE_OK_TOKEN_MODES = ("PROVIDER_EXACT", "MODEL_TOKENIZER")

# payload 전체 비주입 사유(기계 판독 — 관측·감사용).
EXPOSURE_SUPPRESSION_REASONS = (
    "MODE_NOT_EXPOSE",
    "QUESTION_TYPE_NOT_ALLOWED",
    "SCOPE_NOT_REVIEWED",
    "POLICY_HASH_MISMATCH",
    "TOKENIZER_UNAVAILABLE",
    "TOKEN_BUDGET_INSUFFICIENT",
    "NO_EXPOSABLE_EPISODE",
    "CLAIM_POLICY_ERROR",
    "SERIALIZATION_ERROR",
    "CANARY_NOT_ALLOWLISTED",
)
# item-level 하향 사유 — payload 전체 차단이 아니라 critical 1건 하향.
CRITICAL_DOWNGRADE_REASON = "CRITICAL_EMPIRICAL_VALIDATION_PENDING"

# R3 token budget(질문 유형별 — 감수 44차 §6 초기 정책). R2 episode budget
# (risk_selection.BUDGET_BY_QUESTION_TYPE — 개수)과 **별도 값**이다.
EXPOSURE_TOKEN_BUDGET_BY_QUESTION_TYPE = {
    "specific_event": 768,
    "single_domain_period": 1024,
    "period_overview": 1024,
    "multi_episode_compare": 1024,
    "episode_followup": 768,
}
# 주입 허용 질문 유형 allowlist(미등록=fail-closed 비주입).
ALLOWED_QUESTION_TYPES = frozenset(EXPOSURE_TOKEN_BUDGET_BY_QUESTION_TYPE)
# temporal scope: 과거 회고만 묻는 질문에는 미래 경고 payload 비주입.
_ALLOWED_TEMPORAL_SCOPES = ("current", "future", "mixed")
_SAFETY_HEADROOM_TOKENS = 256  # 고정 안전 여유(잠정 — expose 감수 대상)


def critical_validation_state() -> dict:
    """critical 실증 검증 상태(감수 44차 §2 — 정책 공식과 분리 관리).

    corpus 양성 사례가 추가되면 이 상태와 EXPOSE 게이트 감수만 갱신한다 —
    49항목 shadow_presentation 감수는 강등되지 않는다.
    """
    return {
        "synthetic_fixtures": "passed",
        "corpus_positive_cases": 0,
        "empirical_calibration": "pending",
        "expose_behavior": "pending 동안 computed CRITICAL →"
                           " exposed WARNING(item-level downgrade,"
                           f" reason={CRITICAL_DOWNGRADE_REASON})",
    }


def exposure_token_budget_for(question_type: str) -> int:
    """질문 유형 → EXPOSE token budget(감수 44차 §6 — R2 개수 예산과 분리).

    미등록 유형은 fail-closed 오류 — 임의 기본값으로 주입하지 않는다.
    """
    budget = EXPOSURE_TOKEN_BUDGET_BY_QUESTION_TYPE.get(question_type)
    if budget is None:
        raise ValueError(f"미지원 질문 유형 token budget: {question_type}")
    return budget


def available_risk_tokens(
    *,
    model_context_limit: int,
    base_prompt_tokens: int,
    user_input_tokens: int,
    existing_context_tokens: int,
    response_reserve: int,
    safety_headroom: int = _SAFETY_HEADROOM_TOKENS,
) -> int:
    """최종 prompt 전체 기준의 위험 payload 가용 토큰(감수 44차 §5)."""
    return (model_context_limit - base_prompt_tokens - user_input_tokens
            - existing_context_tokens - response_reserve - safety_headroom)


def effective_risk_budget(question_type: str, available: int) -> int:
    """실제 사용 예산 = min(질문 유형 budget, DEFAULT, 실측 headroom)."""
    return min(exposure_token_budget_for(question_type),
               DEFAULT_RISK_PRESENTATION_BUDGET, max(0, available))


def apply_exposure_levels(records: list[dict]) -> list[dict]:
    """computed vs exposed level 분리(감수 44차 §2·§4).

    critical은 실증 검증 pending 동안 warning으로 하향 — 감사 기록에는
    computedPresentationLevel을 보존하고 LLM에는 exposed만 전달한다.
    입력 records는 변경하지 않는다(사본 반환).
    """
    pending = (critical_validation_state()["empirical_calibration"]
               == "pending")
    out = []
    for r in records:
        rec = dict(r)
        computed = rec["presentationLevel"]
        rec["computedPresentationLevel"] = computed
        if computed == "critical" and pending:
            rec["exposedPresentationLevel"] = "warning"
            rec["exposureDowngradeReason"] = CRITICAL_DOWNGRADE_REASON
            rec["presentationLevel"] = "warning"
            rec["presentationLabel"] = "주의 필요"
        else:
            rec["exposedPresentationLevel"] = computed
        out.append(rec)
    return out


@dataclass(frozen=True)
class ExposureGateContext:
    """게이트 입력(감수 44차 §7·§8) — 호출부(R5 파이프라인)가 채운다.

    scopes_all_reviewed·policy_hashes_match는 manifest 검증 결과를 전달
    (게이트는 순수 판정 — 파일 접근 없음). canary_allowlisted는
    EXPOSE_CANARY에서만 검사한다.
    """

    mode: RiskEngineMode
    question_type: str
    temporal_scope: str  # current | future | mixed | past_only
    risk_intent_allowed: bool
    token_count_mode: str
    model_context_limit: int
    base_prompt_tokens: int
    user_input_tokens: int
    existing_context_tokens: int
    response_reserve: int
    scopes_all_reviewed: bool
    policy_hashes_match: bool
    canary_allowlisted: bool = False
    target_domains: tuple[str, ...] = field(default_factory=tuple)


def evaluate_risk_exposure_gate(
    ctx: ExposureGateContext,
    payload: dict,
    counter=None,
) -> dict:
    """EXPOSE 주입 자격의 단일 fail-closed 평가(감수 44차 §7).

    전 조건 통과 시에만 {"inject": True, "serialized": ...}. 하나라도
    실패하면 inject=False + 기계 판독 suppression_reason. 관측값
    (observability)은 canary/EXPOSE 롤아웃 지표의 원천이다.

    Args:
        ctx: 게이트 입력(모드·질문·토큰·감수 상태).
        payload: build_presentation 결과(audit records + llm episodes).
        counter: 모델 tokenizer adapter(Callable[[str], int]) —
            EXPOSE에서는 필수(부재=TOKENIZER_UNAVAILABLE).
    """
    def _suppress(reason: str, budget: int | None = None) -> dict:
        return {
            "inject": False,
            "suppression_reason": reason,
            "serialized": None,
            "observability": {
                "attempted": True,
                "injected": False,
                "reason": reason,
                "effective_budget": budget,
                "critical_downgraded": 0,
            },
        }

    if ctx.mode not in (RiskEngineMode.EXPOSE, RiskEngineMode.EXPOSE_CANARY):
        return _suppress("MODE_NOT_EXPOSE")
    if ctx.mode is RiskEngineMode.EXPOSE_CANARY and (
            not ctx.canary_allowlisted):
        return _suppress("CANARY_NOT_ALLOWLISTED")
    if (ctx.question_type not in ALLOWED_QUESTION_TYPES
            or ctx.temporal_scope not in _ALLOWED_TEMPORAL_SCOPES
            or not ctx.risk_intent_allowed):
        return _suppress("QUESTION_TYPE_NOT_ALLOWED")
    if not ctx.scopes_all_reviewed:
        return _suppress("SCOPE_NOT_REVIEWED")
    if not ctx.policy_hashes_match:
        return _suppress("POLICY_HASH_MISMATCH")
    if ctx.token_count_mode not in _EXPOSE_OK_TOKEN_MODES or counter is None:
        return _suppress("TOKENIZER_UNAVAILABLE")
    available = available_risk_tokens(
        model_context_limit=ctx.model_context_limit,
        base_prompt_tokens=ctx.base_prompt_tokens,
        user_input_tokens=ctx.user_input_tokens,
        existing_context_tokens=ctx.existing_context_tokens,
        response_reserve=ctx.response_reserve)
    try:
        budget = effective_risk_budget(ctx.question_type, available)
    except ValueError:
        return _suppress("QUESTION_TYPE_NOT_ALLOWED")
    if budget < MIN_SAFE_RISK_PRESENTATION_BUDGET:
        return _suppress("TOKEN_BUDGET_INSUFFICIENT", budget)
    if not payload.get("llmRiskEpisodes"):
        return _suppress("NO_EXPOSABLE_EPISODE", budget)
    # computed→exposed 하향(critical 실증 pending) 후 직렬화.
    exposed_records = apply_exposure_levels(payload["llmRiskEpisodes"])
    downgraded = sum(1 for r in exposed_records
                     if r.get("exposureDowngradeReason"))
    exposed_payload = {
        "globalProhibitedClaimCodes": payload["globalProhibitedClaimCodes"],
        "globalAllowedClaimCodes": payload["globalAllowedClaimCodes"],
        # LLM에는 exposed level만 — computed·downgrade 사유는 감사 전용.
        "llmRiskEpisodes": [
            {k: v for k, v in r.items()
             if k not in ("computedPresentationLevel",
                          "exposedPresentationLevel",
                          "exposureDowngradeReason")}
            for r in exposed_records
        ],
    }
    try:
        serialized = serialize_llm_payload(exposed_payload, budget, counter)
    except ValueError:
        return _suppress("CLAIM_POLICY_ERROR", budget)
    except Exception:  # noqa: BLE001 — 직렬화 실패=비주입(fail-closed)
        return _suppress("SERIALIZATION_ERROR", budget)
    doc = json.loads(serialized)
    if doc.get("exposureSuppressedReason"):
        return _suppress("TOKEN_BUDGET_INSUFFICIENT", budget)
    return {
        "inject": True,
        "suppression_reason": None,
        "serialized": serialized,
        "audit_records": exposed_records,  # computed level·하향 사유 보존
        "observability": {
            "attempted": True,
            "injected": True,
            "reason": None,
            "effective_budget": budget,
            "compression_mode": doc.get("compressionMode", "TIERED"),
            "episode_count": len(doc.get("riskEpisodes", [])),
            "critical_downgraded": downgraded,
        },
    }


def expose_policy_hash() -> str:
    """EXPOSE 전역 pipeline 정책 해시(감수 44차 §7 — 항목 scope 아님)."""
    policy = {
        "version": RISK_EXPOSURE_VERSION,
        "token_count_modes": list(TOKEN_COUNT_MODES),
        "expose_token_modes": list(_EXPOSE_OK_TOKEN_MODES),
        "heuristic_fallback": "SHADOW 측정 전용 — EXPOSE 주입 금지"
                              "(TOKENIZER_UNAVAILABLE fail-closed)",
        "budget_basis": "최종 prompt 전체 headroom — available = limit −"
                        " base − user − context − response_reserve −"
                        f" safety({_SAFETY_HEADROOM_TOKENS}), effective ="
                        " min(질문 유형, DEFAULT, available), <512 비주입",
        "token_budget_by_question_type":
            dict(sorted(EXPOSURE_TOKEN_BUDGET_BY_QUESTION_TYPE.items())),
        "question_gate": "allowlist + temporal(past_only 비주입) +"
                         " risk_intent_allowed — 미등록 fail-closed",
        "level_split": "computed(감사 보존) vs exposed(LLM 전달) —"
                       " critical은 실증 pending 동안 warning 하향"
                       f"(item-level {CRITICAL_DOWNGRADE_REASON})",
        "suppression_reasons": list(EXPOSURE_SUPPRESSION_REASONS),
        "modes": "OFF/SHADOW/EXPOSE_CANARY(allowlist 필수)/EXPOSE",
        "injection_contract": "R3가 FULL~P0_COMPACT/SUPPRESSED를 완성 단위로"
                              " 선택해 전달 — 일반 reducer의 위험 필드 임의"
                              " 삭제 금지, suppressed 시 모델의 위험 내용"
                              " 임의 보충 금지(전역 계약)",
        "observability": ["attempted", "injected", "reason",
                          "effective_budget", "compression_mode",
                          "episode_count", "critical_downgraded"],
    }
    return hashlib.sha256(json.dumps(
        policy, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


__all__ = [
    "ALLOWED_QUESTION_TYPES",
    "CRITICAL_DOWNGRADE_REASON",
    "EXPOSURE_SUPPRESSION_REASONS",
    "EXPOSURE_TOKEN_BUDGET_BY_QUESTION_TYPE",
    "ExposureGateContext",
    "RISK_EXPOSURE_VERSION",
    "TOKEN_COUNT_MODES",
    "apply_exposure_levels",
    "available_risk_tokens",
    "critical_validation_state",
    "effective_risk_budget",
    "evaluate_risk_exposure_gate",
    "expose_policy_hash",
    "exposure_token_budget_for",
]
