"""관계(합·충·형) 의미 구조화 타입 — P0 의미 역전 방지 (2026-07-27 데굴님 확정).

`resolve_stem_hap` / `resolve_branch_hap`이 이미 판정한 결과를 **재계산 없이** 직교 축으로
재표현한다. 단일 enum 하나에 "성립했는가 / 化했는가 / 무엇이 억제됐는가"를 섞으면
'합은 성립했으나 化는 불성이고 특정 글자만 억제됨' 같은 실제 조합을 표현할 수 없어,
축을 셋으로 분리하고 표시용 `result_state`는 여기서 파생한다.

이 타입의 목적은 두 가지다.
  1. LLM 입력에 '금지 해석'을 명시해 엔진 확정값의 역전 서술을 사전 차단한다.
  2. 생성 후 감사(`relation_claim_audit`)가 문자열이 아니라 **구조화 필드**로 위반을
     판정하게 한다(어휘 목록에 의존하는 감사는 우회 표현에 뚫린다).

절대원칙 1 — 판정은 전부 엔진이 한 것이며 이 모듈은 매핑만 한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FormationState(StrEnum):
    """관계 자체가 성립했는가."""

    FORMED = "FORMED"          # 완전 성립(삼합 3자·방합 3자·육합·천간합)
    PARTIAL = "PARTIAL"        # 부분 성립(반합·부분 방합)
    NOT_FORMED = "NOT_FORMED"  # 불성립(간격극 등으로 차단)


class TransformationState(StrEnum):
    """합화(化)가 성립했는가 — 성립 여부(FormationState)와 독립이다."""

    TRANSFORMED = "TRANSFORMED"            # 化 확정
    NO_TRANSFORMATION = "NO_TRANSFORMATION"  # 化 불성(합반)
    NOT_APPLICABLE = "NOT_APPLICABLE"      # 化 개념이 아님(방합=기존 오행 강화)


class BindingState(StrEnum):
    """묶임·제거가 일어났는가."""

    BOUND = "BOUND"      # 합반 — 묶여서 작용이 둔해짐
    REMOVED = "REMOVED"  # 합거 — 운이 원국 글자를 끌어가 작용이 제거됨
    NONE = "NONE"


class EffectKind(StrEnum):
    """개별 대상에게 일어난 일.

    PARTIALLY_STRENGTHENED는 반합(半合)·부분 방합처럼 국을 다 이루지 못한 보조 강화다.
    이를 SUPPRESSED나 '합반(合絆)'으로 옮기면 엔진이 주장한 적 없는 묶임이 생긴다
    (2026-07-27 실측 — 午寅 반합은 direction=None·affected=[]로 묶임이 전혀 없다).
    """

    STRENGTHENED = "STRENGTHENED"
    PARTIALLY_STRENGTHENED = "PARTIALLY_STRENGTHENED"
    SUPPRESSED = "SUPPRESSED"
    RELEASED = "RELEASED"
    NEUTRAL = "NEUTRAL"


class EffectFavorability(StrEnum):
    """그 효과가 일간에게 유리한가 — 엔진 AffectedGod.effect(boon/harm/neutral) 유래."""

    BENEFICIAL = "BENEFICIAL"
    ADVERSE = "ADVERSE"
    MIXED = "MIXED"


class PolarityState(StrEnum):
    """길흉 부호의 상태.

    NEUTRAL(길흉 영향이 실제로 중립)과 UNRESOLVED(관계는 발동했으나 현 규칙으로
    길흉을 판정하지 않음)를 반드시 구분한다 — 둘을 뭉개면 신호가 있는 슬롯을
    'NO_SIGNAL'로 오판한다(2026-07-27 데굴님 지적).
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNRESOLVED = "UNRESOLVED"


class ManifestationPressure(StrEnum):
    """발현 압력 — 사전(favorability_rules.json)의 'negative_or_forced' 보존용.

    '불리함'과 '강제로 표출됨'은 다른 축이라, 사전이 두 의미를 한 값에 담고 있는
    현 상태를 임의 해석하지 않고 그대로 보존한다.
    """

    NORMAL = "NORMAL"
    FORCED = "FORCED"


class RelationOccurrence(BaseModel):
    """참여 글자 1개의 발생 위치 — 정규화된 라벨에서 복원하면 안 되는 정보.

    같은 亥라도 월지인지 일지인지가 다르고, 합거의 작용 대상도 자리로 정해진다.
    relation_label은 표시·집계를 위해 지지 표준순으로 정렬하지만, 이 목록은 엔진이
    준 순서와 자리를 그대로 보존한다(2026-07-27 데굴님 지적).

    position은 만세 엔진 표기('year'|'month'|'day'|'hour'|'luck')다. 운 글자는 전부
    'luck'으로 뭉뚱그려지므로, 대운·세운·월운·일운 층위 식별은 composite의
    InteractionParticipant.source를 써야 한다.
    """

    char: str
    position: str


class RelationEffect(BaseModel):
    """관계가 특정 글자에 미친 효과 1건."""

    target: str  # 대상 글자(한자)
    ten_god: str = ""
    role: str = ""  # 용신/희신/기신/구신/한신
    effect: EffectKind
    favorability: EffectFavorability


class RelationSemantics(BaseModel):
    """관계 1건의 구조화 의미 — 엔진 판정의 재표현(재계산 없음)."""

    relation_label: str  # 표시·집계용 정규 라벨 '寅亥合'(지지 표준순)
    members: tuple[str, ...]  # 정규 순서. 자리 정보는 occurrences를 볼 것
    occurrences: list[RelationOccurrence] = Field(default_factory=list)
    kind: str  # 'stem_combination' | 'six' | 'three_harmony' | 'half' | 'directional'
    formation_state: FormationState
    transformation_state: TransformationState
    binding_state: BindingState
    transform_element: str | None = None  # 化神/局 오행(한자) — 化 불성이어도 후보 오행 보존
    transform_tier: str = ""  # 엔진 원값 'confirmed'|'conditional'|'none'
    role: str = ""  # transform_element의 용희기구한 역할
    luck_origin: bool = False
    effects: list[RelationEffect] = Field(default_factory=list)
    # 엔진이 확정한 서술 문장. LLM은 이 의미를 바꾸지 말고 그대로 쓰거나 생략만 한다.
    # 관계 사실을 자유 작문 영역에서 빼는 것이 최초 오류율을 낮추는 가장 큰 지렛대다
    # (2026-07-27 데굴님 확정 — 재생성 대신 canonical claim 우선).
    canonical_claim: str = ""
    allowed_interpretations: list[str] = Field(default_factory=list)
    forbidden_interpretations: list[str] = Field(default_factory=list)

    @property
    def result_state(self) -> str:
        """표시용 파생 상태 — 저장·판정 근거로 쓰지 말 것(축 3개가 SSOT)."""
        if self.formation_state is FormationState.NOT_FORMED:
            return "NOT_FORMED"
        if self.transformation_state is TransformationState.TRANSFORMED:
            return "TRANSFORMED"
        if self.binding_state is BindingState.REMOVED:
            return "BOUND_REMOVED"
        if self.binding_state is BindingState.BOUND:
            return "BOUND_NO_TRANSFORMATION"
        if self.transformation_state is TransformationState.NOT_APPLICABLE:
            return "STRENGTHEN"
        return "PARTIAL_STRENGTHEN"
