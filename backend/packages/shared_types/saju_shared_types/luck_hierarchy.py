"""계층형 운 grounding SSOT (P1 — 2026-07-27 데굴님 확정).

일진만 원국과 대조하던 기존 grounding은 상위 운이 만드는 결합(巳午未 방합 火, 寅午
반합 火)과 층간 충(丙壬충)을 통째로 누락했다. 이 타입은 **이번 요청에서 활성화된 운
스택**만으로 계층 구조를 표현한다.

경계(데굴님 확정):
  - P1은 관계 의미를 **재계산하지 않는다**. formation/transformation/binding·effects·
    canonical_claim은 P0(RelationSemantics)가 확정한 값을 그대로 옮긴다.
  - 클러스터는 표현 뷰다. 원본 interaction을 복사·변형하지 않고 **ID만 참조**한다.
  - 종합 판단(상위 지원 속 당일 마찰 등)은 P1이 하지 않는다. 그것은 천간·지지 상태와
    연·월·일 역할을 함께 봐야 하므로 P2의 `hierarchy_summary` 소관이다. P1은
    `interaction_summary`(구조 요약)까지만 만든다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .relation_semantics import (
    BindingState,
    EffectKind,
    FormationState,
    RelationEffect,
    TransformationState,
)


class ParticipantLayer(StrEnum):
    """참여 글자의 층위.

    만세 엔진의 `hap_modes.positions`는 운 글자를 전부 'luck'으로 뭉뚱그리므로 층위
    식별에 쓸 수 없다. 층위는 composite의 `InteractionParticipant.source`에서만 온다.
    """

    NATAL_YEAR = "natal_year"
    NATAL_MONTH = "natal_month"
    NATAL_DAY = "natal_day"
    NATAL_HOUR = "natal_hour"
    DAEWOON = "daewoon"
    ANNUAL = "annual"
    MONTHLY = "monthly"
    DAILY = "daily"

    @property
    def is_natal(self) -> bool:
        """원국 자리인가(운 층위는 요청 스택 범위 검사 대상)."""
        return self.value.startswith("natal_")


#: composite source 문자열 → 층위. 미등록 값은 임의 변환하지 않고 fail-closed 처리한다
#: (잘못된 층위 라벨을 사용자에게 보이느니 계층 요약에서 제외하는 편이 안전하다).
_SOURCE_TO_LAYER: dict[str, ParticipantLayer] = {
    "natal_year": ParticipantLayer.NATAL_YEAR,
    "natal_month": ParticipantLayer.NATAL_MONTH,
    "natal_day": ParticipantLayer.NATAL_DAY,
    "natal_hour": ParticipantLayer.NATAL_HOUR,
    "daewoon": ParticipantLayer.DAEWOON,
    "year": ParticipantLayer.ANNUAL,
    "month": ParticipantLayer.MONTHLY,
    "day": ParticipantLayer.DAILY,
}

LAYER_KO: dict[ParticipantLayer, str] = {
    ParticipantLayer.NATAL_YEAR: "원국 연지",
    ParticipantLayer.NATAL_MONTH: "원국 월지",
    ParticipantLayer.NATAL_DAY: "원국 일지",
    ParticipantLayer.NATAL_HOUR: "원국 시지",
    ParticipantLayer.DAEWOON: "대운",
    ParticipantLayer.ANNUAL: "세운",
    ParticipantLayer.MONTHLY: "월운",
    ParticipantLayer.DAILY: "일진",
}


def normalize_participant_layer(source: str) -> ParticipantLayer | None:
    """composite source → 층위. 알 수 없으면 None(호출부가 fail-closed 처리)."""
    return _SOURCE_TO_LAYER.get(source)


class SemanticResolutionStatus(StrEnum):
    """탐지기와 의미 resolver의 판정이 일치하는가.

    두 엔진이 다른 답을 내는 관계가 실재한다 — 亥未는 InteractionDetector가
    rel_卯未亥三合으로 감지하지만, 의미 SSOT인 resolve_branch_hap은 '반합은 왕지
    포함만(다수설)'이라 미성립으로 본다. 이를 '의미 미상'으로 통과시키면 LLM이 자체
    명리 지식으로 빈칸을 채워('亥未는 木 반합이니 관성 강화') P0에서 막으려던 자의적
    재해석이 되살아난다. 그래서 상태를 명시하고 서술·클러스터·점수에서 제외한다.
    """

    #: 관계·의미·효과까지 확정.
    RESOLVED = "RESOLVED"
    #: 충·형·파·해 — **관계 성립은 확정**이고 구조적 긴장은 서술에 쓴다. 길흉 점수
    #: 규칙만 미정이다. 이름을 'UNSUPPORTED'로 두면 '근거 없는 관계'로 오해해
    #: 서술에서까지 통째로 빼는 코드가 나오기 쉬워 STRUCTURAL_ONLY로 부른다.
    STRUCTURAL_ONLY = "STRUCTURAL_ONLY"
    #: 합 계열인데 의미 resolver가 성립을 인정하지 않음 — 성립 자체가 미확정.
    ENGINE_CONFLICT = "ENGINE_CONFLICT"


class HierarchyParticipant(BaseModel):
    """관계에 참여한 글자 1개 — 글자와 층위."""

    char: str
    layer: ParticipantLayer

    @property
    def occurrence_id(self) -> str:
        """클러스터 중첩 판정에 쓰는 발생 식별자('annual:午')."""
        return f"{self.layer.value}:{self.char}"


class HierarchyInteraction(BaseModel):
    """계층 구조에 실린 관계 1건.

    의미 필드는 전부 P0 RelationSemantics에서 복사한 값이다. P1이 관계 이름을 보고
    결과 오행·합화·합반을 다시 추정하는 일은 없다.
    """

    interaction_id: str  # 사전 relation_id 'rel_巳午未方合'
    relation_label: str = ""  # P0 정규 라벨(매칭 실패 시 빈 문자열)
    kind: str  # InteractionKind 값
    participants: list[HierarchyParticipant] = Field(default_factory=list)
    base_intensity: float = 0.0  # 사전 baseScore 그대로(부호·변동성 판정은 P3 소관)
    # ── P0에서 복사(재계산 금지) ─────────────────────────────────────────────
    result_element: str | None = None
    formation_state: FormationState | None = None
    transformation_state: TransformationState | None = None
    binding_state: BindingState | None = None
    effects: list[RelationEffect] = Field(default_factory=list)
    canonical_claim: str = ""
    # ── 판정 일치 여부와 사용 가능 범위 ────────────────────────────────────────
    semantic_resolution_status: SemanticResolutionStatus = (
        SemanticResolutionStatus.RESOLVED
    )
    #: 관계 성립 자체가 확정됐는가. 충·형·해는 성립 확정(길흉만 미판정)이지만
    #: ENGINE_CONFLICT는 성립 자체가 미확정이라 변동성도 반영하면 안 된다.
    formation_confirmed: bool = True
    narrative_eligible: bool = True  # 본문 서술 근거로 쓸 수 있는가
    cluster_eligible: bool = True  # 표현 클러스터에 넣을 수 있는가
    score_eligible: bool = True  # 점수(P3)에 반영할 수 있는가
    exclusion_reason: str = ""

    # ── 소비자는 enum 이름이 아니라 아래 헬퍼만 읽는다 ─────────────────────────
    # 상태 이름으로 직접 분기하면 STRUCTURAL_ONLY를 '지원 안 함'으로 오해해 서술에서
    # 통째로 빼는 실수가 나온다(2026-07-27 데굴님 지적).
    def can_render_narrative(self) -> bool:
        """본문 서술 근거로 쓸 수 있는가."""
        return self.narrative_eligible

    def can_enter_cluster(self) -> bool:
        """표현 클러스터에 넣을 수 있는가."""
        return self.cluster_eligible

    def can_affect_score(self) -> bool:
        """점수(P3)에 반영할 수 있는가."""
        return self.score_eligible

    def can_affect_volatility(self) -> bool:
        """변동성에 반영할 수 있는가 — 성립이 확정된 관계만."""
        return self.formation_confirmed

    @property
    def luck_layers(self) -> set[ParticipantLayer]:
        """참여한 운 층위(원국 제외)."""
        return {p.layer for p in self.participants if not p.layer.is_natal}

    @property
    def crosses_luck_layers(self) -> bool:
        """서로 다른 운 층위가 함께 참여했는가(층간 결합·충)."""
        return len(self.luck_layers) >= 2

    @property
    def occurrence_ids(self) -> set[str]:
        """참여 발생 식별자 집합."""
        return {p.occurrence_id for p in self.participants}


class InteractionCluster(BaseModel):
    """같은 현상을 여러 관계가 반복 설명할 때의 표현 뷰.

    원본 관계 객체를 복사하지 않고 ID만 참조한다 — 복사본이 생기면 canonical claim이
    갈라지고 P3에서 어느 쪽이 SSOT인지 불분명해진다.
    """

    cluster_definition_id: str
    result_element: str
    effect_kind: EffectKind
    primary_interaction_id: str
    supporting_interaction_ids: list[str] = Field(default_factory=list)

    @property
    def member_ids(self) -> list[str]:
        """대표 + 보조 전체."""
        return [self.primary_interaction_id, *self.supporting_interaction_ids]


class PillarSummary(BaseModel):
    """활성 층위 1개의 간지 사실. 천간·지지 역할 판정은 P2가 붙인다."""

    layer: ParticipantLayer
    ganji: str
    stem: str
    branch: str


class InteractionSummary(BaseModel):
    """구조 요약 — 개수와 존재 여부만. 길흉·종합 판단은 담지 않는다(P2 소관)."""

    total_interactions: int = 0
    cross_layer_interactions: int = 0
    clustered_interactions: int = 0
    unclustered_interactions: int = 0
    layers_present: list[ParticipantLayer] = Field(default_factory=list)


class LuckHierarchy(BaseModel):
    """이번 요청의 계층형 운 grounding SSOT."""

    requested_period: str  # '2026-07-27' | '2026-07' | '2026'
    requested_level: str  # 'day' | 'month' | 'year'
    active_layers: list[PillarSummary] = Field(default_factory=list)
    interactions: list[HierarchyInteraction] = Field(default_factory=list)
    clusters: list[InteractionCluster] = Field(default_factory=list)
    interaction_summary: InteractionSummary = Field(default_factory=InteractionSummary)
    #: 층위를 알 수 없어 계층 요약에서 제외한 관계(원본은 composite에 그대로 남는다).
    excluded_unknown_sources: list[str] = Field(default_factory=list)

    def by_id(self, interaction_id: str) -> HierarchyInteraction | None:
        """ID로 관계 조회(클러스터가 ID만 들고 있으므로 필요)."""
        return next(
            (i for i in self.interactions if i.interaction_id == interaction_id), None
        )
