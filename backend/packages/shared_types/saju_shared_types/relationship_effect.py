"""7축 관계 효과 벡터 타입 — P1-1 (RELATIONSHIP_EVENT_SYSTEM §4·부록 D).

핵심 원칙(부록 D): **평가하지 못한 축을 0과 구분한다** — 근거 없는 축은 0점이 아니라
`INSUFFICIENT_EVIDENCE`("약하다"≠"판정할 수 없다"). P1 벡터는 shadow 전용이며 점수·
랭킹·confidence·timeline·stage·가드 어디에도 관여하지 않는다(부록 D-3 불변식).

축 방향(2026-07-24 명문화):
- activation/exposure/realization/formalization/separation_pressure: **0 이상 단방향** —
  높을수록 그 성질이 강함. separation_pressure는 "종료 쪽으로 미는 압력"이다.
- `stability`: **signed 양방향** — 음수=불안정 압력, 0=중립, 양수=안정 순효과.
  separation_pressure와 관련되지만 동일하지 않다: 형·해처럼 안정성을 떨어뜨리되 즉시
  종료까지 밀지는 않는 신호가 두 축을 분리한 의미다.
- `experience_valence`만 `direction`(positive|mixed|negative)을 별도 보유 — 다른 축의
  direction은 None이다.
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
    기준으로 계산한다. REL_COMPOUND는 새 원인이 아니라 기존 원인들의 결합 상태이며,
    `compound_group_id`는 **구성 evidence 각각에** 연결된다(어떤 원인들이 복합을
    이뤘는지 합성기가 추적 — 같은 기간의 우연한 공존과 복합 구조를 구분).

    강도 필드 의미 분리(2026-07-24 보완): `base_relation_strength`는 이벤트 키와 무관한
    궁위 관계의 기본 강도(사전 kind×궁×층위×위치, cap·likely ×1.2·MT4 미적용)다.
    실제 legacy 후보의 cap 적용 전/후 값은 **특정 이벤트와 결합된 뒤에만 정의**되므로
    event_adjusted_legacy_strength/legacy_delta/legacy_capped는 어댑터 단계에서 None이고
    후보 결합 단계(P1-7 비교 감사)에서만 채운다 — base 값을 실제 pre-cap 점수로
    오해하지 않게 한다.
    """

    evidence_id: str
    # 독립 원인 ID — layer:kind:palace:position(+hap_subtype·element)(#k). 동일 서명 hit
    # 반복은 정렬 무관 개수 기반 suffix(#k)라 **입력 순서 불변**(permutation invariant).
    independent_cause_id: str
    # palace_activation | partner_star_emergence | structure_pattern — 증거의 해석 역할
    # 그룹(중복 집계 방지 자체는 shared_trigger_id·합성기 소관).
    independent_cause_group: str
    # 동일 root trigger(같은 운 글자) 파생 신호 식별 — RelationPalace 합과 MT2 재출현이
    # 같은 글자에서 나왔으면 증거 2종·독립 root 1개로 계산하기 위한 키(§7).
    # 어댑터 입력에 운 글자가 없으면 확보 가능한 서명으로 잠정 기록(P1-3에서 정밀화).
    shared_trigger_id: str = ""

    relation_kind: str                  # HAP | CHUNG | HYEONG | PA | HAE | BOKEUM
    source_layer: str                   # sewoon | wolwoon | daewoon | ilwoon
    affected_palace: str                # year|month|day|hour pillar
    on_spouse_palace: bool

    natal_participant: str = ""         # 피자극 글자(입력에 없으면 빈 값 — 미상)
    transit_participant: str = ""
    compound_group_id: str | None = None
    # 파생 modifier(구조 패턴 등)가 기저 evidence에서 나온 경우의 역추적(§8).
    derived_from_evidence_ids: list[str] = Field(default_factory=list)

    base_relation_strength: float = 0.0  # 이벤트 무관 기본 강도(cap·×1.2·MT4 미적용)
    event_adjusted_legacy_strength: float | None = None  # 후보 결합 후에만(어댑터=None)
    legacy_delta: float | None = None                    # 후보 결합 후에만(어댑터=None)
    legacy_capped: bool | None = None                    # 후보 결합 후에만(어댑터=None)

    reason_codes: list[str] = Field(default_factory=list)
