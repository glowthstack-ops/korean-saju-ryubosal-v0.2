"""커리어 소비 계약 — P4-1 chat 최소 cohort (CAREER_TRANSITION_SYSTEM §12).

`INV-26 Consumer provenance`: 단계·사실·forecast·근거는 각각의 출처를 유지하며 LLM이
출처 간 상태를 승격·병합하지 않는다. `INV-27`: 배포 자격 없는 evidence·forecast는
직렬화 전에 제외한다. `INV-28`: 감사 실패 시 그대로 전달하지 않는다.
`INV-29`: 신규 블록 전달이 확정되기 전에는 기존 직업운 소유권을 축소하지 않는다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

#: 소비 계약 버전.
CONSUMER_CONTRACT_VERSION = "career-consumer.v1"


class ConsumerVisibilityDecision(StrEnum):
    """소비 자격 — **직렬화 전에** 결정한다(LLM에 runtime_status를 보여주지 않는다)."""

    INTERNAL_ONLY = "internal_only"
    BETA_VISIBLE = "beta_visible"
    LIVE_VISIBLE = "live_visible"
    SUPPRESSED = "suppressed"


class CareerBlockScope(StrEnum):
    """블록이 무엇을 말하는가 — 사실 유무에 따라 서술 범위가 다르다.

    사실이 없다고 Episode 를 자동 생성하지 않는다. 일반 질문("이직운 어때?")은
    **저장 없는 일시 컨텍스트**로 흐름만 말하고, 확정 단계를 만들지 않는다.
    """

    EPISODE_SPECIFIC = "episode_specific"        # 확인된 사실이 있는 단일 Episode
    GENERAL_FORECAST = "general_forecast"        # 사실 없음 — 저장·Episode 생성 없음
    MULTI_EPISODE_OVERVIEW = "multi_episode"     # 복수 Episode — 전체 흐름만
    NONE = "none"


class ClaimScope(StrEnum):
    """문장이 무엇을 주장하는가 — 출처 요구가 다르다."""

    CONFIRMED_FACT = "confirmed_fact"                  # source_fact_id 필수
    USER_REPORTED_INFERENCE = "user_reported_inference"
    FORECAST = "forecast"                              # snapshot/contribution refs 필수
    GENERAL_GUIDANCE = "general_guidance"              # factual stage 생성 금지
    UNKNOWN = "unknown"


class StateLabel(StrEnum):
    """payload가 값마다 붙이는 상태 표식 — 사실과 전망을 섞지 않기 위함."""

    CONFIRMED = "confirmed"
    FORECAST = "forecast"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class InputAuditAction(StrEnum):
    """입력 감사 결과 — 실패 시 **필드가 아니라 블록 전체**를 억제한다."""

    ALLOW = "allow"
    BLOCK_NEW_BLOCK = "block_new_block"
    FALLBACK_TO_LEGACY = "fallback_to_legacy"


class OutputAuditAction(StrEnum):
    """출력 감사 결과."""

    DELIVER = "deliver"
    REWRITE = "rewrite"
    SAFE_FALLBACK = "safe_fallback"
    BLOCK = "block"


class ConsumerViolation(StrEnum):
    """소비 감사 위반 코드(§15 지표와 1:1)."""

    NARRATIVE_COMPLETION_OVERCLAIM = "narrative_completion_overclaim"
    COUNTERPARTY_OVERCLAIM = "counterparty_overclaim"
    FACT_FORECAST_LANGUAGE_MIXING = "fact_forecast_language_mixing"
    CROSS_EPISODE_FACT_BLEED = "cross_episode_fact_bleed"
    #: 사실이 없는 일반 질문인데 진행 중인 절차·회사가 있는 것처럼 말함.
    UNFOUNDED_PROGRESS_CLAIM = "unfounded_progress_claim"
    STRUCTURED_NARRATIVE_MISMATCH = "structured_narrative_mismatch"
    CONSUMER_VISIBILITY_VIOLATION = "consumer_visibility_violation"
    ATOMIC_SECTION_HANDOFF_FAILURE = "atomic_section_handoff_failure"


class ConsumerClaim(BaseModel):
    """최종 문장 1건의 근거표 — 기계적 감사의 단위(§12-6)."""

    model_config = ConfigDict(frozen=True)

    claim_id: str
    claim_scope: ClaimScope
    episode_id: str | None = None
    track: str | None = None
    stage: str | None = None
    source_refs: tuple[str, ...] = ()
    visibility_decision: ConsumerVisibilityDecision = (
        ConsumerVisibilityDecision.INTERNAL_ONLY
    )


class CareerConsumerPayload(BaseModel):
    """LLM 입력 축약본 — §12-1 필드만 두고 늘리지 않는다.

    필드명이 사실처럼 보이지 않아야 한다(`offer_expected` 류 금지). forecast는
    `forecast_*` 접두로만 표현한다.
    """

    model_config = ConfigDict(frozen=True)

    query_focus: str
    resolved_episode_id: str | None = None
    #: (트랙, 단계, 상태표식) — confirmed 는 observed_stages 기반이며 frontier 가 아니다.
    confirmed_track_states: tuple[tuple[str, str, StateLabel], ...] = ()
    current_facts: tuple[str, ...] = ()
    forecast_stage_candidates: tuple[tuple[str, StateLabel], ...] = ()
    effect_vector: tuple[tuple[str, float], ...] = ()
    bottleneck: str | None = None
    #: 병목을 평가할 근거가 부족한 경우 — "가능성이 낮다"로 번역하면 안 된다.
    bottleneck_not_evaluable: bool = False
    #: 병목이 얼마나 뚜렷한가 — 판정이 아니라 **서술 강도**다(distinct/narrow/flat).
    bottleneck_sharpness: str = "unknown"
    #: 두 번째로 낮은 관문 − 가장 낮은 관문. 서술에 쓰지 않고 telemetry 로만 본다.
    bottleneck_margin: float | None = None
    #: 간격이 좁을 때 함께 낮은 관문들 — 단일 병목으로 단정하지 않기 위해 병렬로 말한다.
    tied_bottleneck_gates: tuple[str, ...] = ()
    #: 서술 범위 — GENERAL_FORECAST 는 확정 단계·회사·진행 상황을 말하지 않는다.
    scope: CareerBlockScope = CareerBlockScope.EPISODE_SPECIFIC
    blocking_factors: tuple[str, ...] = ()
    supporting_factors: tuple[str, ...] = ()
    prohibited_claims: tuple[str, ...] = ()
    contract_version: str = CONSUMER_CONTRACT_VERSION


class CareerBlockResult(BaseModel):
    """소비 파이프라인 결과.

    `delivered=False`면 **기존 직업운 섹션을 축소하지 않는다**(INV-29).
    """

    model_config = ConfigDict(frozen=True)

    delivered: bool = False
    block_text: str | None = None
    payload: CareerConsumerPayload | None = None
    claims: tuple[ConsumerClaim, ...] = ()
    input_action: InputAuditAction = InputAuditAction.FALLBACK_TO_LEGACY
    output_action: OutputAuditAction | None = None
    violations: tuple[ConsumerViolation, ...] = ()
    rewrite_count: int = 0
    legacy_section_reduced: bool = False
    skip_reason: str | None = None


__all__ = [
    "CONSUMER_CONTRACT_VERSION",
    "CareerBlockResult",
    "CareerBlockScope",
    "CareerConsumerPayload",
    "ClaimScope",
    "ConsumerClaim",
    "ConsumerViolation",
    "ConsumerVisibilityDecision",
    "InputAuditAction",
    "OutputAuditAction",
    "StateLabel",
]
