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

from .risk_claim_audit import (
    claim_audit_policy_hash as _claim_audit_policy_hash,
)
from .risk_presentation import (
    DEFAULT_RISK_PRESENTATION_BUDGET,
    MIN_SAFE_RISK_PRESENTATION_BUDGET,
    RENDER_TIERS,
    render_llm_payload,
    serialize_llm_payload,
)

# 노출 게이트 버전 — 전역 pipeline 계약 변경 시 올린다(항목 scope 아님).
RISK_EXPOSURE_VERSION = "risk-expose-r4.0.1-gated"

# token 계수 모드(감수 44차 §4): heuristic은 SHADOW 전용 — EXPOSE 금지.
TOKEN_COUNT_MODES = ("PROVIDER_EXACT", "MODEL_TOKENIZER",
                     "HEURISTIC_FALLBACK")
_EXPOSE_OK_TOKEN_MODES = ("PROVIDER_EXACT", "MODEL_TOKENIZER")

# payload 전체 비주입 사유(기계 판독 — 관측·감사용).
# primary reason 결정 순서(감수 45차 §7 — policy hash 포함): 정적 저비용
# 조건은 일괄 수집(all), primary는 이 순서의 첫 항목. tokenizer·직렬화 등
# 비용 조건은 정적 전부 통과 후에만 평가한다.
EXPOSURE_SUPPRESSION_REASONS = (
    "KILL_SWITCH",
    "MODE_NOT_EXPOSE",
    "CANARY_NOT_ALLOWLISTED",
    "QUESTION_TYPE_NOT_ALLOWED",
    "SCOPE_NOT_REVIEWED",
    "EXPOSE_PIPELINE_NOT_REVIEWED",
    "POLICY_HASH_MISMATCH",
    "TOKENIZER_UNAVAILABLE",
    "TOKENIZER_MODEL_MISMATCH",
    "TOKEN_BUDGET_INSUFFICIENT",
    "NO_EXPOSABLE_EPISODE",
    "CLAIM_POLICY_ERROR",
    "SERIALIZATION_ERROR",
    "FINAL_PROMPT_TOKEN_OVERFLOW",
    "RISK_BLOCK_INTEGRITY_ERROR",
)
# 하위 호환·명칭 정리(감수 48차 §2): disposition 분리 후에는 BYPASS 사유까지
# 'suppression'이라 부르지 않는다 — 게이트 반환은 decision reason 스키마
# (primary_decision_reason/all_decision_reasons)가 정본이고, 기존 키는
# 별칭으로 병기(fixture·관측 마이그레이션 후 제거).
EXPOSURE_DECISION_REASONS = EXPOSURE_SUPPRESSION_REASONS
# 노출 처분 3상태(감수 47차 §1 — suppression reason과 prompt 행동 분리):
# BYPASS=위험 노출 파이프라인의 적용 대상이 아님(정적 사유 — kill switch·
# mode·canary·질문 정책·scope·hash·tokenizer) → **prompt 한 바이트도 불변**
# (guard조차 없음·진단 로그만). SUPPRESSED=노출 자격은 있으나 런타임 조건
# (예산·episode 부재·직렬화)으로 안전 주입 불가 → suppressed guard만.
# INJECTED=instruction + 감수 risk block.
EXPOSURE_DISPOSITIONS = ("BYPASS", "SUPPRESSED", "INJECTED")
_BYPASS_REASONS = frozenset({
    "KILL_SWITCH", "MODE_NOT_EXPOSE", "CANARY_NOT_ALLOWLISTED",
    "QUESTION_TYPE_NOT_ALLOWED", "SCOPE_NOT_REVIEWED",
    "EXPOSE_PIPELINE_NOT_REVIEWED", "POLICY_HASH_MISMATCH",
    "TOKENIZER_UNAVAILABLE", "TOKENIZER_MODEL_MISMATCH",
})
# 질문 노출 정책(감수 45차 §9 — boolean intent 대체): 미래 overview·기간
# 질문은 '위험'이라는 단어 없이도 implicit 허용, 과거 회고·미등록=DENY.
RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE = {
    "specific_event": "ALLOW_IMPLICIT",
    "single_domain_period": "ALLOW_IMPLICIT",
    "period_overview": "ALLOW_IMPLICIT",
    "multi_episode_compare": "ALLOW_IMPLICIT",
    "episode_followup": "ALLOW_IMPLICIT",
}
_EXPOSURE_POLICIES = ("ALLOW_IMPLICIT", "REQUIRE_EXPLICIT", "DENY")
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
    # fail-closed(감수 45차 §5): 명시적 "validated"가 아니면(미등록·손상
    # 포함) critical 하향 유지.
    pending = (critical_validation_state().get("empirical_calibration")
               != "validated")
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
    risk_intent_allowed: bool  # REQUIRE_EXPLICIT 정책에서만 검사
    token_count_mode: str
    model_context_limit: int
    base_prompt_tokens: int
    user_input_tokens: int
    existing_context_tokens: int
    response_reserve: int
    scopes_all_reviewed: bool
    policy_hashes_match: bool
    canary_allowlisted: bool = False
    # 전역 kill switch(감수 45차 §8 — 게이트 최앞·mode 무관 비주입).
    kill_switch: bool = False
    # expose_pipeline 감수 상태(감수 45차 §6 — 현 reviewed=false: 모든 조건
    # 충족이어도 비주입).
    expose_pipeline_reviewed: bool = False
    # tokenizer-모델 일치(감수 45차 §1): counter가 계수하는 모델과 실제
    # 호출 모델(alias 해소 후)이 같아야 주입 가능.
    counter_model_id: str | None = None
    resolved_model_id: str | None = None
    # 혼합 기간(감수 45차 §9): 미래 질문 범위(기간 라벨 [시작, 끝]) — 지정
    # 시 R2 선택 episode 중 교집합만 노출 대상.
    future_period_range: tuple[str, str] | None = None
    target_domains: tuple[str, ...] = field(default_factory=tuple)


def _month_bounds(label: str) -> tuple[int, int]:
    """기간 라벨 → (시작, 끝) 월 인덱스(연 라벨=그 해 전체)."""
    if len(label) == 7 and label[4] == "-":
        m = int(label[:4]) * 12 + int(label[5:7]) - 1
        return m, m
    year = int(label[:4])
    return year * 12, year * 12 + 11

def filter_payload_to_future_scope(
    payload: dict, future_range: tuple[str, str],
) -> dict:
    """혼합 기간 질문(감수 45·46차): 미래 질문 범위 ∩ episode만 LLM 노출.

    **감사 records는 전량 보존**(감수 46차 §4 — 과거 범위라서 비노출된
    episode의 흔적을 지우지 않는다): 각 record에 exposureScopeStatus
    (IN_SCOPE/OUTSIDE_FUTURE_SCOPE)를 표시하고 **llmRiskEpisodes만**
    필터한다. 판정 기준=episode의 primary activity 기간(diagnostics
    start/end — 구성원 활동 기간). recovery window·supporting 단독·배경
    vulnerability의 미래 존재는 범위 판단에 쓰지 않는다(과거 위험의 회복
    시점이 미래라고 그 위험을 미래 경고로 재노출 금지). 입력 불변.
    """
    lo, _ = _month_bounds(future_range[0])
    _, hi = _month_bounds(future_range[1])
    out_records = []
    keep_llm = []
    llm_iter = iter(payload["llmRiskEpisodes"])
    for rec in payload["presentationRecords"]:
        llm_ep = (next(llm_iter)
                  if rec["presentationLevel"] != "none" else None)
        s, _e1 = _month_bounds(rec["diagnostics"]["startPeriod"])
        _s2, e = _month_bounds(rec["diagnostics"]["endPeriod"])
        in_scope = not (e < lo or s > hi)
        out_records.append({**rec, "exposureScopeStatus": (
            "IN_SCOPE" if in_scope else "OUTSIDE_FUTURE_SCOPE")})
        if llm_ep is not None and in_scope:
            keep_llm.append(llm_ep)
    return {**payload, "presentationRecords": out_records,
            "llmRiskEpisodes": keep_llm}


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
    def _suppress(reasons: list[str], budget: int | None = None) -> dict:
        ordered = [r for r in EXPOSURE_SUPPRESSION_REASONS if r in reasons]
        primary = ordered[0] if ordered else reasons[0]
        # 처분 분리(감수 47차 §1): 정적 사유=BYPASS(파이프라인 적용 대상
        # 아님 — prompt 완전 불변), 런타임 사유=SUPPRESSED(guard 부착 가능).
        disposition = ("BYPASS" if primary in _BYPASS_REASONS
                       else "SUPPRESSED")
        alls = ordered or list(reasons)
        return {
            "inject": False,
            "disposition": disposition,
            # 정본 스키마(감수 48차 §2) — BYPASS 사유는 suppression이 아님.
            "primary_decision_reason": primary,
            "all_decision_reasons": alls,
            # 하위 호환 별칭(마이그레이션 후 제거).
            "suppression_reason": primary,
            "all_suppression_reasons": alls,
            "serialized": None,
            "observability": {
                "attempted": True,
                "injected": False,
                "disposition": disposition,
                "reason": primary,
                "all_reasons": alls,
                "effective_budget": budget,
                "critical_downgraded": 0,
            },
        }

    # ── 정적 저비용 조건 일괄 수집(감수 45차 §7 — primary+all) ──
    static: list[str] = []
    if ctx.kill_switch:
        static.append("KILL_SWITCH")
    if ctx.mode not in (RiskEngineMode.EXPOSE, RiskEngineMode.EXPOSE_CANARY):
        static.append("MODE_NOT_EXPOSE")
    elif ctx.mode is RiskEngineMode.EXPOSE_CANARY and (
            not ctx.canary_allowlisted):
        static.append("CANARY_NOT_ALLOWLISTED")
    policy = RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE.get(
        ctx.question_type, "DENY")
    question_ok = (
        policy != "DENY"
        and ctx.temporal_scope in _ALLOWED_TEMPORAL_SCOPES
        and (policy != "REQUIRE_EXPLICIT" or ctx.risk_intent_allowed)
    )
    if not question_ok:
        static.append("QUESTION_TYPE_NOT_ALLOWED")
    if not ctx.scopes_all_reviewed:
        static.append("SCOPE_NOT_REVIEWED")
    if not ctx.expose_pipeline_reviewed:
        static.append("EXPOSE_PIPELINE_NOT_REVIEWED")
    if not ctx.policy_hashes_match:
        static.append("POLICY_HASH_MISMATCH")
    if ctx.token_count_mode not in _EXPOSE_OK_TOKEN_MODES or counter is None:
        static.append("TOKENIZER_UNAVAILABLE")
    elif (ctx.counter_model_id is None or ctx.resolved_model_id is None
          or ctx.counter_model_id != ctx.resolved_model_id):
        static.append("TOKENIZER_MODEL_MISMATCH")
    if static:
        return _suppress(static)
    # ── 동적 조건(정적 전부 통과 후에만 — tokenizer·직렬화 비용) ──
    available = available_risk_tokens(
        model_context_limit=ctx.model_context_limit,
        base_prompt_tokens=ctx.base_prompt_tokens,
        user_input_tokens=ctx.user_input_tokens,
        existing_context_tokens=ctx.existing_context_tokens,
        response_reserve=ctx.response_reserve)
    try:
        budget = effective_risk_budget(ctx.question_type, available)
    except ValueError:
        return _suppress(["QUESTION_TYPE_NOT_ALLOWED"])
    if budget < MIN_SAFE_RISK_PRESENTATION_BUDGET:
        return _suppress(["TOKEN_BUDGET_INSUFFICIENT"], budget)
    if ctx.future_period_range is not None:
        payload = filter_payload_to_future_scope(
            payload, ctx.future_period_range)
    if not payload.get("llmRiskEpisodes"):
        return _suppress(["NO_EXPOSABLE_EPISODE"], budget)
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
        return _suppress(["CLAIM_POLICY_ERROR"], budget)
    except Exception:  # noqa: BLE001 — 직렬화 실패=비주입(fail-closed)
        return _suppress(["SERIALIZATION_ERROR"], budget)
    doc = json.loads(serialized)
    if doc.get("exposureSuppressedReason"):
        return _suppress(["TOKEN_BUDGET_INSUFFICIENT"], budget)
    return {
        "inject": True,
        "disposition": "INJECTED",
        "primary_decision_reason": None,
        "all_decision_reasons": [],
        "suppression_reason": None,  # 하위 호환 별칭
        "all_suppression_reasons": [],
        "serialized": serialized,
        "audit_records": exposed_records,  # computed level·하향 사유 보존
        "observability": {
            "attempted": True,
            "injected": True,
            "disposition": "INJECTED",
            "reason": None,
            "effective_budget": budget,
            "compression_mode": doc.get("compressionMode", "TIERED"),
            "episode_count": len(doc.get("riskEpisodes", [])),
            "critical_downgraded": downgraded,
        },
    }


# EXPOSE 계열 모드 전용 지침 2종(감수 46차 §8 — 상태별 분리, OFF/SHADOW
# prompt byte 불변 유지). 둘 다 최종 token 계수에 포함돼야 한다(§6).
# ① 위험 block이 실제 주입된 경우.
RISK_EXPOSURE_INSTRUCTION_BLOCK = (
    "[위험 표현 계약] riskEpisodes의 presentationLevel은 발생 확률이 아니며"
    " 점수가 높아도 사건을 단정하지 않는다. 각 episode의"
    " requiredQualifiers를 해당 설명 문장에 반드시 유지하고,"
    " prohibitedClaimCodes에 해당하는 문장을 생성하지 않으며, 표현 강도는"
    " 각 episode의 표시 수준(presentationLabel)을 초과하지 않는다."
)
# ② 위험 payload가 비주입(suppressed)된 경우 — 일반 후보의 위험 승격만
# 금지, '계약 검토가 필요한 시기' 수준의 권고 표현은 허용(과잉 차단 금지).
RISK_EXPOSURE_SUPPRESSED_GUARD = (
    "[위험 표현 계약] 구조화된 riskEpisodes 블록이 제공되지 않았다. 일반"
    " 사건 후보나 운세 신호를 별도의 위험·경고·사고·손실 주장으로 확대"
    " 해석하지 않는다(검토·일정 조정 권고 수준의 표현은 허용)."
)
# 하위 호환 별칭(감수 45차 명칭) — R5-b에서 분리(제거 예정 아님·감사 추적).
RISK_EXPOSURE_GUARD_BLOCK = RISK_EXPOSURE_SUPPRESSED_GUARD


@dataclass(frozen=True)
class RiskPromptBlock:
    """주입용 위험 block(감수 45·46차 — 원자 단위·불변·checksum).

    reducer는 내부 필드를 개별 삭제할 수 없다(frozen) — 토큰이 부족하면
    R3 serializer에 더 작은 compression mode를 요청한다(재생성).
    content_hash(감수 46차 §7): provider request 직전
    verify_risk_block_integrity로 대조 — frozen이 막지 못하는 복사 후
    변형·wrapper 재구성 중 훼손을 탐지한다.
    """

    serialized_text: str
    compression_mode: str  # FULL | P1 | P0 | P0_COMPACT
    exact_token_count: int
    content_hash: str = ""
    immutable: bool = True


def _block_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def wrap_risk_block(block: RiskPromptBlock) -> str:
    """주입용 wrapper(감수 47차 §3) — 단일 삽입 검증 가능한 marker 구조."""
    return (f"BEGIN_RISK_BLOCK:{block.content_hash}\n"
            f"{block.serialized_text}\nEND_RISK_BLOCK")


def verify_risk_block_integrity(final_prompt: str,
                                block: RiskPromptBlock) -> bool:
    """provider request 직전 무결성 검증(감수 46차 §7 + 47차 §3 단일 삽입).

    조건 전부 충족 시만 True: ①시작 marker(BEGIN_RISK_BLOCK:<hash>) 정확
    1회 ②종료 marker 정확 1회 ③본문 출현 정확 1회 ④checksum 일치 — hash가
    맞아도 중복 삽입이면 실패. 실패=비주입(reducer는 그대로 포함/작은 tier
    재요청/전체 비주입만 가능).
    """
    begin = f"BEGIN_RISK_BLOCK:{block.content_hash}"
    return (
        _block_hash(block.serialized_text) == block.content_hash
        and final_prompt.count(begin) == 1
        and final_prompt.count("END_RISK_BLOCK") == 1
        and final_prompt.count(block.serialized_text) == 1
    )


def finalize_risk_prompt_block(
    exposed_payload: dict,
    budget: int,
    counter,
    final_prompt_builder,
    final_token_limit: int,
) -> tuple[RiskPromptBlock | None, str | None]:
    """최종 prompt 2차 계수(감수 45차 §1·§2) — 사전 headroom만으로 주입 금지.

    각 compression mode에 대해: ①block 자체가 budget 이내인지 counter로
    계수 ②final_prompt_builder(block_text)로 **최종 prompt를 조립해 전체를
    재계수** ③final_token_limit 이내면 채택. 모든 mode가 초과하면
    (None, "FINAL_PROMPT_TOKEN_OVERFLOW") — 전체 비주입.

    Args:
        exposed_payload: apply_exposure_levels 반영·LLM 필드만 남긴 payload.
        budget: effective_risk_budget 결과.
        counter: 실제 모델 tokenizer adapter(필수 — 게이트가 보장).
        final_prompt_builder: block 문자열 → 완성된 최종 prompt 문자열.
        final_token_limit: 최종 prompt 전체 허용 토큰(context limit −
            response reserve − safety headroom).
    """
    # FULL 우선(감수 46차 §5 — FULL=P2 별칭·최대 표현부터 시도).
    # final_prompt_builder는 instruction/guard block 포함 **전체 provider
    # request**를 조립해야 한다(§6 — 지침도 token 계수 대상).
    for tier in RENDER_TIERS:
        text = render_llm_payload(exposed_payload, tier)
        if counter(text) > budget:
            continue
        final_prompt = final_prompt_builder(text)
        if counter(final_prompt) <= final_token_limit:
            return (RiskPromptBlock(
                serialized_text=text, compression_mode=tier,
                exact_token_count=int(counter(text)),
                content_hash=_block_hash(text)), None)
    return None, "FINAL_PROMPT_TOKEN_OVERFLOW"


def resolve_block_integrity_failure(result: dict) -> dict:
    """provider 직전 integrity 실패의 재조립 계약(감수 48차 §7).

    잘못된 상태(instruction은 남고 block만 제거)를 만들지 않는다 —
    INJECTED 결과를 **SUPPRESSED로 강등**: instruction+block 전부 제거 대상,
    suppressed guard 삽입, 사유=RISK_BLOCK_INTEGRITY_ERROR. 호출부는 이
    결과로 prompt를 처음부터 재조립하고(부분 편집 금지) 최종 재계수·재검증을
    다시 수행해야 한다.
    """
    obs = dict(result.get("observability", {}))
    obs.update({"injected": False, "disposition": "SUPPRESSED",
                "reason": "RISK_BLOCK_INTEGRITY_ERROR",
                "all_reasons": ["RISK_BLOCK_INTEGRITY_ERROR"]})
    return {
        "inject": False,
        "disposition": "SUPPRESSED",
        "primary_decision_reason": "RISK_BLOCK_INTEGRITY_ERROR",
        "all_decision_reasons": ["RISK_BLOCK_INTEGRITY_ERROR"],
        "suppression_reason": "RISK_BLOCK_INTEGRITY_ERROR",
        "all_suppression_reasons": ["RISK_BLOCK_INTEGRITY_ERROR"],
        "serialized": None,
        "observability": obs,
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
                       " critical은 'validated' 명시 전(미등록·손상 포함)"
                       f" warning 하향(item-level {CRITICAL_DOWNGRADE_REASON})",
        "critical_validation_state": critical_validation_state(),
        "suppression_reason_order": list(EXPOSURE_SUPPRESSION_REASONS),
        "suppression_collection": "정적 저비용 조건 일괄 수집(primary+all),"
                                  " tokenizer·직렬화는 정적 통과 후만",
        "question_exposure_policy": dict(sorted(
            RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE.items())),
        "temporal_intersection": "혼합 기간=R2 선택 episode 기간 ∩ 미래 질문"
                                 " 범위만(past_only=false 전체 주입 금지)",
        "tokenizer_model_match": "counter.model_id == resolved model —"
                                 " 불일치=TOKENIZER_MODEL_MISMATCH,"
                                 " fallback 라우팅 시 재계수",
        "final_prompt_recount": "위험 block 포함 최종 prompt를 동일"
                                " tokenizer로 재계수 — 초과 시 더 작은"
                                " compression 재시도, 전부 초과="
                                "FINAL_PROMPT_TOKEN_OVERFLOW 비주입",
        "prompt_block": "RiskPromptBlock immutable — reducer 내부 편집"
                        " 금지(부족 시 serializer에 작은 mode 재요청)",
        "kill_switch": "게이트 최앞 — mode 무관 비주입",
        "dispositions": {"BYPASS": sorted(_BYPASS_REASONS),
                         "SUPPRESSED": ["TOKEN_BUDGET_INSUFFICIENT",
                                        "NO_EXPOSABLE_EPISODE",
                                        "CLAIM_POLICY_ERROR",
                                        "SERIALIZATION_ERROR",
                                        "FINAL_PROMPT_TOKEN_OVERFLOW"],
                         "contract": "BYPASS=prompt 한 바이트도 불변(guard"
                                     " 없음·진단 로그만) / SUPPRESSED="
                                     "guard만 / INJECTED=instruction+block"
                                     "(감수 47차 §1)"},
        "instruction_blocks": "INJECTED=RISK_EXPOSURE_INSTRUCTION_BLOCK /"
                              " SUPPRESSED=RISK_EXPOSURE_SUPPRESSED_GUARD /"
                              " BYPASS=없음(감수 46차 §8 + 47차 §1) — 전부"
                              " EXPOSE 계열 전용·최종 token 계수 포함",
        "block_integrity": "RiskPromptBlock.content_hash + BEGIN/END"
                           " marker — provider request 직전 단일 삽입"
                           "(각 1회·본문 1회)·checksum 대조(감수 47차 §3)."
                           " 실패 시 재조립 계약(감수 48차 §7):"
                           " instruction+block 전부 제거 → SUPPRESSED 강등"
                           "(RISK_BLOCK_INTEGRITY_ERROR) → guard 삽입 →"
                           " 전체 재계수·재검증(부분 편집 금지)",
        "decision_reason_schema": "primary_decision_reason/"
                                  "all_decision_reasons 정본(BYPASS 사유는"
                                  " suppression 아님 — 감수 48차 §2), 관측"
                                  "은 bypass/suppressed/injected 분리 집계",
        "compression_order": "FULL(=P2)→P1→P0→P0_COMPACT(감수 46차 §5)",
        "future_scope_audit": "OUTSIDE_FUTURE_SCOPE records 전량 보존 —"
                              " LLM episodes만 필터(감수 46차 §4), 판정="
                              "primary activity 기간(recovery·supporting"
                              " 단독 미래는 재노출 사유 아님)",
        "canary_question_types": "초기 canary=specific_event·"
                                 "single_domain_period·period_overview"
                                 " 3유형(compare·followup은 2차 확대 —"
                                 " 감수 46차 §3)",
        "answer_claim_audit": "생성 답변 사후 검사(risk_claim_audit) —"
                              " episode별 section + 전체 답변 병행, 위반 시"
                              " REVISE(1회)→REGENERATE_WITHOUT_RISK→BLOCK",
        "claim_audit_policy_hash": _claim_audit_policy_hash(),
        "modes": "OFF/SHADOW/EXPOSE_CANARY(allowlist 필수·기본 거부·내부"
                 " subject ID)/EXPOSE",
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
    "RISK_EXPOSURE_GUARD_BLOCK",
    "RISK_EXPOSURE_INSTRUCTION_BLOCK",
    "RISK_EXPOSURE_SUPPRESSED_GUARD",
    "verify_risk_block_integrity",
    "wrap_risk_block",
    "EXPOSURE_DISPOSITIONS",
    "EXPOSURE_DECISION_REASONS",
    "resolve_block_integrity_failure",
    "RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE",
    "RiskPromptBlock",
    "filter_payload_to_future_scope",
    "finalize_risk_prompt_block",
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
