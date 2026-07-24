"""7축 관계 효과 벡터 타입 — P1-1 (RELATIONSHIP_EVENT_SYSTEM §4·부록 D).

핵심 원칙(부록 D): **평가하지 못한 축을 0과 구분한다** — 근거 없는 축은 0점이 아니라
`INSUFFICIENT_EVIDENCE`("약하다"≠"판정할 수 없다"). P1 벡터는 shadow 전용이며 점수·
랭킹·confidence·timeline·stage·가드 어디에도 관여하지 않는다(부록 D-3 불변식).

축 방향: activation/exposure/realization/stability/formalization/separation_pressure는
높을수록 그 성질이 강함(단방향). `experience_valence`만 양·음 방향이 있어
`direction`(positive|mixed|negative)을 별도 보유 — 다른 축의 direction은 None이다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AxisStatus(StrEnum):
    """축 평가 상태 — 값 부재의 의미를 보존한다(부록 D-1)."""

    EVALUATED = "evaluated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class RelationshipAxisValue(BaseModel):
    """축 1개의 평가 결과 — status가 EVALUATED일 때만 value·band 유효."""

    status: AxisStatus = AxisStatus.INSUFFICIENT_EVIDENCE
    value: float | None = None          # 내부 실수(LLM 미전달 — §10-3 밴드 직렬화)
    band: str | None = None             # strong | moderate | weak | low
    # experience_valence 전용 방향(positive|mixed|negative) — 타 축은 None(단방향).
    direction: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)


def unevaluated(status: AxisStatus = AxisStatus.INSUFFICIENT_EVIDENCE) -> RelationshipAxisValue:
    """미평가 축 생성 헬퍼 — 0으로 채우지 않는다."""
    return RelationshipAxisValue(status=status)


class RelationshipEffectVector(BaseModel):
    """7축 효과 벡터(§4 산출 책임 SSOT 준수) — shadow 전용."""

    activation: RelationshipAxisValue = Field(default_factory=unevaluated)
    exposure: RelationshipAxisValue = Field(default_factory=unevaluated)
    realization: RelationshipAxisValue = Field(default_factory=unevaluated)
    experience_valence: RelationshipAxisValue = Field(default_factory=unevaluated)
    stability: RelationshipAxisValue = Field(default_factory=unevaluated)
    formalization: RelationshipAxisValue = Field(default_factory=unevaluated)
    separation_pressure: RelationshipAxisValue = Field(default_factory=unevaluated)


class RelationshipActivationEvidence(BaseModel):
    """배우자궁 발동 원시 증거 1건 — cap 이전 구조 보존(부록 D-2).

    **reason_codes 개수 ≠ 독립 원인 수**: 독립 원인 수는 `independent_cause_id` 고유값
    기준으로 계산한다. REL_COMPOUND는 새 원인이 아니라 기존 원인들의 결합 상태
    (`compound_group_id`)다. legacy 재변환 금지 — raw_strength는 cap(22) 이전 산식값.
    """

    evidence_id: str
    independent_cause_id: str           # layer:kind:palace:position(#n) — 결정적
    # palace_activation | partner_star_emergence | structure_pattern (§7 중복 집계 방지 그룹)
    independent_cause_group: str

    relation_kind: str                  # HAP | CHUNG | HYEONG | PA | HAE | BOKEUM
    source_layer: str                   # sewoon | wolwoon | daewoon | ilwoon
    affected_palace: str                # year|month|day|hour pillar
    on_spouse_palace: bool

    natal_participant: str = ""         # 피자극 글자(입력에 없으면 빈 값 — 미상)
    transit_participant: str = ""
    compound_group_id: str | None = None

    raw_strength: float = 0.0           # cap 이전 산식값(사전 kind×궁×층위×위치)
    legacy_delta: float = 0.0           # 동일 산식의 legacy 기여분(참고 기록)
    legacy_capped: bool = False         # 그룹 총합이 legacy 상한(22)을 초과했는가

    reason_codes: list[str] = Field(default_factory=list)
