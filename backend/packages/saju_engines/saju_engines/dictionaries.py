"""사전(JSON) 스키마·로더·충돌 검사 (v2.2 Phase 1 T1.6, docs/05).

설계 문서의 zod 스키마 역할을 pydantic으로 수행한다. JSON 데이터 키는 문서 예시의
camelCase를 그대로 따르고(절대 원칙 10), Python 모델은 snake_case 필드 + alias로 받는다.

- `validate_dictionaries()`: 필수 필드·EventKey 유효성·score 범위 등 스키마 검증(dict:validate).
- `lint_dictionaries()`: 충돌 검사(dict:lint) — relation id 중복 / 기신·구신인데
  polarity=positive(또는 용신·희신인데 negative) / 같은 신호가 상반 이벤트를 동시에
  강하게 유발.

운영 코드는 원본 JSON을 직접 로드하지 않는다 — compile(snapshot) 단계는 Phase 2(T2.1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from saju_shared_types.constants import (
    BRANCH_INDEX,
    JANGSAENG_BRANCH,
    STEM_ELEMENT,
    STEM_YINYANG,
    TWELVE_STAGES,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem, YinYang
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.event_engine import TenGod as _TenGodRoman
from saju_shared_types.event_taxonomy_v2 import LEGACY_EVENT_KEY_MAP
from saju_shared_types.events import EventKey, EventPolarity, EventType
from saju_shared_types.marriage_timing import MarriageStage
from saju_shared_types.region_element import RegionGeoFeature
from saju_shared_types.structure_patterns import StructurePatternDict

_FAVORABILITY = ("용신", "희신", "기신", "구신", "한신")
_POSITIVE_FAVORABILITY = ("용신", "희신")
_NEGATIVE_FAVORABILITY = ("기신", "구신")
# 십성군 — SignalSpec.tenGodGroupStrong 유효값(엔진 groups 키와 매핑은 스코어러 담당).
_TEN_GOD_GROUPS = ("인성", "비겁", "식상", "재성", "관성")
# 배우자성/자녀성 추상화 십성군 — SignalSpec.tenGodGroup·branchHiddenTenGods 유효값
# (MARRIAGE_TIMING_ENHANCEMENT §2). partner_star/child_star는 성별로 환원(resolve_partner_star).
_PARTNER_STAR_GROUPS = ("partner_star", "child_star", "wealth", "officer_killing", "output")
# stageHint 유효값 — MarriageStage enum(임의 stage 문자열 거부, §1 base 미확장 보장).
_MARRIAGE_STAGES = frozenset(s.value for s in MarriageStage)
# '상반 이벤트 동시 강유발' 판정 임계값 — 같은 신호에서 양/부정 후보가 모두 이 점수
# 이상이면 충돌로 본다(초안 기준, 사전 검수와 함께 조정).
_STRONG_CONFLICT_SCORE = 0.7


class _AliasModel(BaseModel):
    """camelCase(JSON) ↔ snake_case(Python) 공용 베이스."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# ── common/ ──────────────────────────────────────────────────────


class StemItem(_AliasModel):
    """천간 항목 (common/stems.json)."""

    stem: str
    element: str
    yin_yang: str = Field(alias="yinYang")
    ten_god_by_day_master: dict[str, str] = Field(alias="tenGodByDayMaster")
    domains: list[str]
    reviewed: bool


class HiddenStemEntry(_AliasModel):
    """지장간 한 항목."""

    stem: str
    type: Literal["main", "middle", "residual"]
    weight: float = Field(ge=0.0, le=1.0)


class BranchItem(_AliasModel):
    """지지 항목 (common/branches.json)."""

    branch: str
    element: str
    yin_yang: str = Field(alias="yinYang")
    zodiac: str
    hidden_stems: list[HiddenStemEntry] = Field(alias="hiddenStems", min_length=1)
    reviewed: bool


class TenGodItem(_AliasModel):
    """십성 → 도메인 매핑 항목 (common/ten_gods.json)."""

    ten_god: str = Field(alias="tenGod")
    group: str
    domains: list[str]
    reviewed: bool


class ElementItem(_AliasModel):
    """오행 생극 항목 (common/elements.json)."""

    element: str
    ko: str
    generates: str
    controls: str
    generated_by: str = Field(alias="generatedBy")
    controlled_by: str = Field(alias="controlledBy")
    reviewed: bool


# ── relations.json ───────────────────────────────────────────────


class RelationItem(_AliasModel):
    """합충형파해/공망/복음/병존/간여지동 항목 (relations.json).

    글자 고정형은 participants에 간지를, 패턴형(공망·복음 등)은 participants=[] +
    pattern 설명을 갖는다.
    """

    id: str
    type: str
    name: str
    participants: list[str]
    result_element: str | None = Field(alias="resultElement")
    possible_modes: list[str] = Field(alias="possibleModes", min_length=1)
    pattern: str | None = None
    event_domains: list[str] = Field(alias="eventDomains")  # 구키 허용 — graph_builder 21키 리맵
    base_score: float = Field(alias="baseScore", ge=0.0, le=1.0)
    # 유파 차이가 큰 관계(암합 등)는 기본 비활성 — 사전 플래그로만 켠다(docs/09 2-2).
    enabled: bool = True
    reviewed: bool

    @model_validator(mode="after")
    def _fixed_or_pattern(self) -> RelationItem:
        if not self.participants and self.pattern is None:
            raise ValueError(f"{self.id}: participants가 비면 pattern 설명이 필요함")
        return self


# ── interpretations/ (v2.2.1 해석 사전, docs/05) ─────────────────


class IljuAnimal(_AliasModel):
    """일주 동물 표기 — 천간 오행색 + 지지 띠 동물."""

    color: str
    name: str
    derivation: str


class IljuTraits(_AliasModel):
    """일주 성향 — 빛(light)/그림자(shadow). 단정 표현 금지 콘텐츠."""

    light: list[str] = Field(min_length=1)
    shadow: list[str] = Field(min_length=1)


class IljuComputed(_AliasModel):
    """엔진 교차검증 대상 계산값 — lint 단계에서 만세력 계산과 전수 대조."""

    ilji_ten_god: str = Field(alias="iljiTenGod")
    twelve_stage: str = Field(alias="twelveStage")
    hidden_stems: list[str] = Field(alias="hiddenStems", min_length=1)


class IljuItem(_AliasModel):
    """60갑자 일주 해석 항목 (interpretations/ilju.json)."""

    ganji: str = Field(min_length=2, max_length=2)
    animal: IljuAnimal
    imagery: str = Field(min_length=10)
    narrative: str = Field(min_length=100)
    traits: IljuTraits
    spouse_palace_note: str = Field(min_length=10)
    computed: IljuComputed
    basis: str = Field(min_length=10)
    reviewed: bool


class TenGodTextItem(_AliasModel):
    """십성 해석 항목 (interpretations/ten_gods_text.json) — 일간 중심·상황 의존."""

    ten_god: str = Field(alias="tenGod")
    group: str
    core: str
    metaphor: str
    natal: str
    excess: str
    absence: str
    incoming: str
    as_yongsin: str = Field(alias="asYongsin")
    as_gisin: str = Field(alias="asGisin")
    basis: str
    reviewed: bool


class TwelveStageTextItem(_AliasModel):
    """십이운성 해석 항목 (interpretations/twelve_stages_text.json)."""

    stage: str
    hanja: str
    core: str
    metaphor: str
    natal: str
    incoming: str
    basis: str
    reviewed: bool


class RelationTextItem(_AliasModel):
    """관계 해석 항목 (interpretations/relations_text.json) — relations.json id와 1:1.

    role=auxiliary는 보조 자료 — 단독으로 결론을 단정할 수 없다(암합·신살,
    2026-06-12 사용자 확정).
    """

    id: str
    name: str
    type: str
    role: Literal["core", "auxiliary"]
    meaning: str
    natal: str
    from_luck: str = Field(alias="fromLuck")
    basis: str
    reviewed: bool


class SinsalByPosition(_AliasModel):
    """신살 위치별 발현(궁성론, 2026-06-12 사용자 확정) — 같은 신살도 자리에 따라 시기·
    대상·작용이 갈린다. social=년·월(사회·대외·조상/부모·초중년), personal=일·시(개인·
    가정·나/배우자/자녀·내면·중말년). 보조 자료 — 단독 결론 금지 원칙은 그대로.
    """

    social: str = Field(min_length=10)
    personal: str = Field(min_length=10)


class SinsalTextItem(_AliasModel):
    """신살 해석 항목 (interpretations/sinsal_text.json) — 전 항목 보조 자료 강제.

    flip_side 의무(2026-06-12 사용자 확정): 길신의 그림자(예: 천을귀인 과다=나태)와
    흉성·주의 신살의 빛(예: 고신살=일 몰두형 성공·자발적 만혼)을 함께 서술한다.
    by_position(선택): 위치 발현이 통설로 뚜렷한 신살에만 저작(궁성론). 미저작 신살은
    공통 궁성 축(年月=사회 / 日時=개인)으로 해석한다.
    """

    name: str
    polarity: Literal["길신", "흉성", "중립", "주의"]
    meaning: str
    manifestation: str
    flip_side: str = Field(alias="flipSide", min_length=20)  # 양면 해석 의무
    caution: str
    role: Literal["auxiliary"]  # 신살은 보조 — 단독 결론 금지(2026-06-12 사용자 확정)
    basis: str
    reviewed: bool
    by_position: SinsalByPosition | None = Field(default=None, alias="byPosition")
    # from_luck(선택, 2026-06-12 사용자 확정): 운(대운·세운 등)에서 도래 시 현실 징후 —
    # 원국 보유(체질)와 달리 그 시기에 '사건'으로 터진다. 미저작 신살은 manifestation 폴백.
    from_luck: str | None = Field(default=None, alias="fromLuck")


class StemTextItem(_AliasModel):
    """천간 물상 항목 (interpretations/stems_branches_text.json)."""

    char: str = Field(min_length=1, max_length=1)
    element: str
    yin_yang: str = Field(alias="yinYang")
    imagery: str
    keywords: list[str] = Field(min_length=1)
    narrative: str
    reviewed: bool


class BranchTextItem(_AliasModel):
    """지지 물상 항목 (interpretations/stems_branches_text.json)."""

    char: str = Field(min_length=1, max_length=1)
    element: str
    yin_yang: str = Field(alias="yinYang")
    zodiac: str
    imagery: str
    keywords: list[str] = Field(min_length=1)
    reviewed: bool


class FavorabilityTextItem(_AliasModel):
    """용희기구한 역할 해석 항목 (interpretations/favorability_text.json).

    reversal(반전 조건) 의무 — 길흉이 고정이 아니라 생극제화로 반전됨을 담는다
    (구신·기신도 조건부로 사주를 돕는다, 2026-06-12 사용자 확정).
    """

    role: Literal["용신", "희신", "기신", "구신", "한신"]
    core: str
    manifestation: str
    reversal: str = Field(min_length=10)
    basis: str
    reviewed: bool


class TerminologyItem(_AliasModel):
    """명리 용어 항목 (terminology.json — docs/08 B12 용어 질문 대응)."""

    term: str
    hanja: str | None = None
    definition: str
    reviewed: bool


class InterpretationTemplateItem(_AliasModel):
    """이벤트×극성 해석 템플릿 항목 (templates/interpretation.json)."""

    event: str  # EventKey 또는 'generic'(폴백)
    polarity: str
    template: str
    reviewed: bool


class ProhibitedStyleItem(_AliasModel):
    """금기 표현 항목 (templates/prohibited_styles.json)."""

    pattern: str
    category: str  # 단정/승부단정/공포조장/의료단정/정책거부
    replacement_hint: str = Field(alias="replacementHint")
    reviewed: bool


class IljuFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[IljuItem] = Field(min_length=60, max_length=60)


class SinsalTextFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[SinsalTextItem] = Field(min_length=20)


class StemsBranchesTextFile(_AliasModel):
    version: str
    note: str | None = None
    stems: list[StemTextItem] = Field(min_length=10, max_length=10)
    branches: list[BranchTextItem] = Field(min_length=12, max_length=12)


class FavorabilityTextFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[FavorabilityTextItem] = Field(min_length=5, max_length=5)


class ActivityKeywordEntry(_AliasModel):
    """활동 키워드 번역 항목 (interpretations/activity_keyword_map.json).

    오행·신살 등 엔진 신호를 조언용 활동 키워드로 번역한다 — 직업 추천이 아니라
    활동축·환경·방식 제안 전용(상담 사례 파생 P1, doc/v2_2/cases/1980_1122_job_report_case.md).
    """

    source_type: Literal["element", "ten_god", "star", "structure"]
    source_id: str
    korean: str
    domains: list[str] = Field(min_length=1)
    activity_keywords: list[str] = Field(min_length=1)
    caution: str | None = None
    safe_rule: str | None = None
    reviewed: bool


class ActivityKeywordMapFile(_AliasModel):
    version: str
    purpose: str
    note: str | None = None
    entries: list[ActivityKeywordEntry] = Field(min_length=6)


class RemedyElementActions(_AliasModel):
    """오행 하나의 개운 행동 제안 (interpretations/remedy_action_map.json)."""

    core_need: str
    recommended_actions: list[str] = Field(min_length=1)
    avoid: list[str] = Field(default_factory=list)
    reviewed: bool


class RemedyActionMapFile(_AliasModel):
    """개운 행동 사전 — 오행 보완 행동 전용(remedy.json D-3 상황 6분기와 별개 축).

    principles(not_magic/behavior_first/avoid_certainty)는 주술적 확언 차단 원칙으로
    5오행 행동과 함께 고정 필수(상담 사례 파생 P2).
    """

    version: str
    purpose: str
    note: str | None = None
    principles: dict[str, str]
    element_actions: dict[str, RemedyElementActions]

    @model_validator(mode="after")
    def _check_required_keys(self) -> RemedyActionMapFile:
        required_principles = {"not_magic", "behavior_first", "avoid_certainty"}
        if not required_principles <= set(self.principles):
            raise ValueError(f"principles에 {required_principles} 필수")
        required_elements = {"wood", "fire", "earth", "metal", "water"}
        if set(self.element_actions) != required_elements:
            raise ValueError(f"element_actions는 {required_elements} 5오행 고정")
        return self


class DeficiencyPairQuestionEntry(_AliasModel):
    """CAL-P1 이원 질문 쌍 항목 (interpretations/deficiency_pair_questions.json).

    A(static_question)=평소 결핍 체감, B(transit_question)=운 작동 확인 본문(앵커 연도
    프리픽스는 질문 생성기가 부착). 길흉 단정 어휘 금지·채점 비반영(§5).
    """

    axis_type: Literal["element", "ten_god_group"]
    axis_id: str
    korean: str
    static_question: str = Field(min_length=10)
    transit_question: str = Field(min_length=10)
    basis_label: str
    reviewed: bool


class DeficiencyPairQuestionsFile(_AliasModel):
    version: str
    purpose: str
    note: str | None = None
    entries: list[DeficiencyPairQuestionEntry] = Field(min_length=10)

    @model_validator(mode="after")
    def _check_axis_coverage(self) -> DeficiencyPairQuestionsFile:
        elements = {e.axis_id for e in self.entries if e.axis_type == "element"}
        groups = {e.axis_id for e in self.entries if e.axis_type == "ten_god_group"}
        if elements != {"wood", "fire", "earth", "metal", "water"}:
            raise ValueError("element 축은 5오행 전체 필수")
        if groups != {"officer", "wealth", "output", "resource", "peer"}:
            raise ValueError("ten_god_group 축은 5그룹 전체 필수")
        return self


class TerminologyFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[TerminologyItem] = Field(min_length=30)


class InterpretationTemplatesFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[InterpretationTemplateItem] = Field(min_length=10)


class ProhibitedStylesFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[ProhibitedStyleItem] = Field(min_length=10)


class TenGodsTextFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[TenGodTextItem] = Field(min_length=10, max_length=10)


class TwelveStagesTextFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[TwelveStageTextItem] = Field(min_length=12, max_length=12)


class RelationsTextFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[RelationTextItem] = Field(min_length=1)


# ── events/ ──────────────────────────────────────────────────────


class TaxonomyItem(_AliasModel):
    """이벤트 분류 항목 (events/taxonomy.json)."""

    event_key: str = Field(alias="eventKey")  # 구키 허용(레거시 taxonomy.json)
    ko: str
    event_type: EventType = Field(alias="eventType")
    reviewed: bool


class SignalSpec(_AliasModel):
    """신호 조건 (events/<domain>.json). 키 중 최소 1개는 지정해야 한다.

    branchTenGod(v2.2.1): 운 지지 본기의 일간 기준 십성 조건 — 동반 신호 매트릭스에서
    지지 신호(예: 甲申월의 申 상관 이동성)를 표현한다(regression_2025_08).
    """

    ten_god: str | None = Field(default=None, alias="tenGod")
    branch_ten_god: str | None = Field(default=None, alias="branchTenGod")
    relation: str | None = None
    # relationAlso(v2.2.1 감점): 같은 기간에 동시 성립해야 하는 추가 관계 — 탐합망충
    # (충이 합으로 묶여 발동 약화) 같은 복합 조건 표현용.
    relation_also: str | None = Field(default=None, alias="relationAlso")
    favorability: str | None = None
    # 운 천간 오행의 용기신 역할 단독 조건(v2.2.1) — '천간 구신 달=계약 불리' 등
    # 십성과 무관한 천간 자체의 유불리 조건(2026-06-12 사용자 도메인 지식).
    stem_favorability: str | None = Field(default=None, alias="stemFavorability")
    shinsal: str | None = None
    daewoon_transition: bool | None = Field(default=None, alias="daewoonTransition")
    # 대운 지지가 원국 공망 글자(v2.2.1 G2 — 계사월 케이스 일반화): 그 대운 하의
    # 기간 전체에 새 계약·환경 진입의 실속 부족·지연 배경 제약.
    daewoon_branch_void: bool | None = Field(default=None, alias="daewoonBranchVoid")
    # ── 십이운성 조건(v2.2.1, 2026-06-12 사용자 스펙) — modifier 전용, 합충형파해·공망·
    # 용기신보다 낮은 우선순위(가중 자체를 낮게 저작해 자연 보장).
    unseong: str | None = None  # 운 유입 글자의 십이운성 일치(예: '건록', '절')
    natal_unseong: str | None = Field(default=None, alias="natalUnseong")  # 원국 월·일주 운성
    # 십성군 세력 강(groups percent >= 30) 조건 — '인성'/'비겁'/'식상'/'재성'/'관성'.
    ten_god_group_strong: str | None = Field(default=None, alias="tenGodGroupStrong")
    # 원국 횡재 그릇 조건(v2.2 Phase 1) — wealth_capacity.capacity_band(strong/moderate)
    # 이상일 때만 성립. 운 발동 신호(삼합·충 등)와 결합해 횡재(windfall) 신호를 게이트한다
    # (재성 그릇이 받쳐줄 때만 가산 — 2026-06-16 사용자 확정 Phase 1).
    natal_wealth_capacity: str | None = Field(default=None, alias="natalWealthCapacity")
    # does_not_apply_when: 같은 기간에 이 관계들이 성립하면 룰 미적용(외부 강트리거 우선).
    absent_relations: list[str] | None = Field(default=None, alias="absentRelations")
    # ── 연애·결혼 도메인 신규 게이트(MARRIAGE_TIMING_ENHANCEMENT §6·§8·§10) ──
    # tenGodGroup(MT1): 운 천간 십성을 배우자성/자녀성 추상화군으로 게이트(성별 환원은 매칭기 담당).
    ten_god_group: str | None = Field(default=None, alias="tenGodGroup")
    # spousePalace(MT3): 관계(합/회귀)가 일지(배우자궁)를 포함할 때만 성립. 게이트 미구현 동안은
    # 매칭기가 일지 포함을 강제해야 하며, 강제 전에는 directional 엔트리를 활성화하지 않는다.
    spouse_palace: bool | None = Field(default=None, alias="spousePalace")
    # branchHiddenTenGods(MT5): 운 지지 지장간 십성군이 나열값을 모두 포함
    # (예: partner_star+child_star = 배우자성·자녀성 동시 운반).
    branch_hidden_ten_gods: list[str] | None = Field(
        default=None, alias="branchHiddenTenGods"
    )

    @model_validator(mode="after")
    def _non_empty(self) -> SignalSpec:
        if not any(
            v is not None
            for v in (
                self.ten_god, self.branch_ten_god, self.relation, self.favorability,
                self.stem_favorability, self.shinsal, self.daewoon_transition,
                self.unseong, self.natal_unseong, self.ten_god_group_strong,
                self.daewoon_branch_void, self.natal_wealth_capacity,
                self.ten_god_group, self.spouse_palace, self.branch_hidden_ten_gods,
            )
        ):
            raise ValueError("signal은 최소 1개 조건을 가져야 함")
        if (
            self.natal_wealth_capacity is not None
            and self.natal_wealth_capacity not in ("strong", "moderate")
        ):
            raise ValueError(
                f"natalWealthCapacity 값 오류: {self.natal_wealth_capacity} (strong/moderate)"
            )
        if self.relation_also is not None and self.relation is None:
            raise ValueError("relationAlso는 relation과 함께 지정해야 함")
        if (
            self.ten_god_group_strong is not None
            and self.ten_god_group_strong not in _TEN_GOD_GROUPS
        ):
            raise ValueError(f"tenGodGroupStrong 값 오류: {self.ten_god_group_strong}")
        if self.favorability is not None and self.favorability not in _FAVORABILITY:
            raise ValueError(f"favorability 값 오류: {self.favorability}")
        if (
            self.stem_favorability is not None
            and self.stem_favorability not in _FAVORABILITY
        ):
            raise ValueError(f"stemFavorability 값 오류: {self.stem_favorability}")
        if self.ten_god_group is not None and self.ten_god_group not in _PARTNER_STAR_GROUPS:
            raise ValueError(
                f"tenGodGroup 값 오류: {self.ten_god_group} ({_PARTNER_STAR_GROUPS})"
            )
        if self.branch_hidden_ten_gods is not None:
            bad = [g for g in self.branch_hidden_ten_gods if g not in _PARTNER_STAR_GROUPS]
            if bad:
                raise ValueError(
                    f"branchHiddenTenGods 값 오류: {bad} ({_PARTNER_STAR_GROUPS})"
                )
        return self

    def key(self) -> str:
        """신호 동일성 비교용 안정 키."""
        return json.dumps(self.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True)


class EventCandidateSpec(_AliasModel):
    """신호가 유발(+) 또는 억제(−)하는 이벤트 후보.

    음수 score = 감점 룰(v2.2.1, docs/02 Signal.weight '양/음수 가능' 명시 — 예: 공망
    활성 −8). 합산 단계에서 해당 이벤트 총점을 깎는다. 감점 룰의 polarity는 극성 집계
    왜곡을 막기 위해 neutral로 저작한다.
    """

    event: str  # 구키 허용 — graph_builder 21키 리맵
    score: float = Field(ge=-1.0, le=1.0)
    polarity: EventPolarity
    # ── 연애·결혼 도메인 신규(MARRIAGE_TIMING_ENHANCEMENT §6·§8·§10) ──
    # stageHint: 단독 발동 시 marriage_stage(MarriageStage enum 값만 허용 — 임의 stage 거부).
    stage_hint: str | None = Field(default=None, alias="stageHint")
    # partnerStarBonus(MT1): 배우자성 동반 시 가산폭(상한 게이트, 매칭기가 적용).
    partner_star_bonus: float | None = Field(default=None, alias="partnerStarBonus")
    # topicHint(MT5): 가정 형성 등 토픽 라우팅 힌트(stage 아님 — family_formation 등).
    topic_hint: str | None = Field(default=None, alias="topicHint")

    @model_validator(mode="after")
    def _validate_stage_hint(self) -> EventCandidateSpec:
        if self.stage_hint is not None and self.stage_hint not in _MARRIAGE_STAGES:
            raise ValueError(
                f"stageHint 값 오류: {self.stage_hint} (MarriageStage: {sorted(_MARRIAGE_STAGES)})"
            )
        return self


class EventMappingItem(_AliasModel):
    """신호→이벤트 매핑 한 건."""

    signal: SignalSpec
    event_candidates: list[EventCandidateSpec] = Field(alias="eventCandidates", min_length=1)
    note: str | None = None
    reviewed: bool


# ── favorability_rules.json ──────────────────────────────────────


class FavorabilityCondition(_AliasModel):
    """보정 규칙 조건."""

    favorability: Literal["용신", "희신", "기신", "구신", "한신"]
    ten_god: str | None = Field(default=None, alias="tenGod")


class FavorabilityEffect(_AliasModel):
    """보정 규칙 효과."""

    polarity: EventPolarity
    score_modifier: float = Field(alias="scoreModifier", ge=-1.0, le=1.0)
    interpretation: str


class FavorabilityRule(_AliasModel):
    """용신/희신/기신/구신/한신 보정 규칙 (favorability_rules.json)."""

    rule_id: str = Field(alias="ruleId")
    condition: FavorabilityCondition
    effect: FavorabilityEffect
    reviewed: bool


# ── 파일 단위 래퍼 ────────────────────────────────────────────────


class StemsFile(_AliasModel):
    version: str
    items: list[StemItem]


class BranchesFile(_AliasModel):
    version: str
    items: list[BranchItem]


class TenGodsFile(_AliasModel):
    version: str
    items: list[TenGodItem]


class ElementsFile(_AliasModel):
    version: str
    items: list[ElementItem]


class RelationsFile(_AliasModel):
    version: str
    items: list[RelationItem]


class TaxonomyFile(_AliasModel):
    version: str
    items: list[TaxonomyItem]


class EventMappingFile(_AliasModel):
    version: str
    domain: str
    items: list[EventMappingItem]


class FavorabilityRulesFile(_AliasModel):
    version: str
    items: list[FavorabilityRule]


class UnseongStageSpec(_AliasModel):
    """십이운성 한 단계의 성향 계수 (common/twelve_unseong_groups.json).

    수치는 modifier 전용(주 트리거 금지 — 2026-06-12 사용자 스펙 scoring_policy).
    """

    group: str  # '성장기'/'왕성기'/'쇠퇴기'/'재생기'
    phase_type: str = Field(alias="phaseType")
    keywords: list[str] = Field(min_length=1)
    stability: float = Field(ge=0.0, le=1.0)
    change_drive: float = Field(alias="changeDrive", ge=0.0, le=1.0)
    career_change_bias: float = Field(alias="careerChangeBias", ge=-1.0, le=1.0)
    relocation_bias: float = Field(alias="relocationBias", ge=-1.0, le=1.0)
    relationship_bias: float = Field(alias="relationshipBias", ge=-1.0, le=1.0)


class UnseongGroupSpec(_AliasModel):
    """십이운성 그룹(생애 주기 4단계) 정의."""

    members: list[str] = Field(min_length=1)
    meaning: str
    default_change_modifier: float = Field(alias="defaultChangeModifier", ge=-1.0, le=1.0)


class TwelveUnseongGroupsFile(_AliasModel):
    version: str
    stages: dict[str, UnseongStageSpec]
    groups: dict[str, UnseongGroupSpec]
    reviewed: bool


class TenGodEventItem(_AliasModel):
    """미발동 글자 기본 가감의 십성별 대표 이벤트 (common/ten_god_events.json).

    2026-06-12 사용자 원칙: 관계(합충형파해 등)·룰에 기여하지 않은 운 글자도
    용희기구한 역할에 따라 그 십성의 대표 이벤트에 가감한다(가중은 favorability_rules
    modifier 재사용 — 발동 신호보다 항상 작음).
    """

    ten_god: str = Field(alias="tenGod")
    event: str  # 구키 허용(레거시 ten_god_events.json)
    reviewed: bool


class TenGodEventsFile(_AliasModel):
    version: str
    reviewed: bool
    note: str = ""
    items: list[TenGodEventItem]


# ── 이사 고도화(Phase R1, docs/02·09) ────────────────────────────

_RISK_LEVELS = ("low", "medium_low", "medium", "high")


class RelocationTenGodItem(_AliasModel):
    """십성별 이사 분류 항목 (interpretations/relocation_ten_gods.json).

    이사 발생은 합·충·역마·재관 자극이 보고(events/relocation.json), 십성은 이사의
    이유·집 성격·리스크를 분류한다(절대원칙 1·12 — 점수·날짜 미개입, 해석 라벨 전용).
    """

    ten_god: str = Field(alias="tenGod")
    group: str
    type: str
    move_reason: list[str] = Field(alias="moveReason", min_length=1)
    property_tendency: list[str] = Field(alias="propertyTendency", min_length=1)
    risk: list[str] = Field(min_length=1)
    required_checks: list[str] = Field(alias="requiredChecks", min_length=1)
    risk_level: str = Field(alias="riskLevel")
    main_question: str = Field(alias="mainQuestion")
    basis: str
    reviewed: bool

    @model_validator(mode="after")
    def _check_enums(self) -> RelocationTenGodItem:
        if self.risk_level not in _RISK_LEVELS:
            raise ValueError(f"riskLevel 값 오류: {self.risk_level} ({_RISK_LEVELS})")
        if self.group not in _TEN_GOD_GROUPS:
            raise ValueError(f"group 값 오류: {self.group} ({_TEN_GOD_GROUPS})")
        return self


class RelocationTenGodsFile(_AliasModel):
    version: str
    note: str | None = None
    items: list[RelocationTenGodItem] = Field(min_length=10, max_length=10)


class ContractDaySpec(_AliasModel):
    """계약일 점수표 (사용자 스펙 9·11장) — 천간 십성 비중 우세."""

    ko: str
    preferred_ten_gods: dict[str, int] = Field(alias="preferredTenGods")
    preferred_elements: dict[str, int] = Field(alias="preferredElements")
    avoid_ten_gods: dict[str, int] = Field(alias="avoidTenGods")
    branch_relations: dict[str, int] = Field(alias="branchRelations")
    weights: dict[str, float]


class MoveDaySpec(_AliasModel):
    """이삿날 점수표 (사용자 스펙 10·11장) — 지지 관계 비중 우세."""

    ko: str
    preferred_ten_gods: dict[str, int] = Field(alias="preferredTenGods")
    preferred_combinations: dict[str, int] = Field(alias="preferredCombinations")
    avoid_ten_gods: dict[str, int] = Field(alias="avoidTenGods")
    branch_relations: dict[str, int] = Field(alias="branchRelations")
    weights: dict[str, float]


class OfficeMoveSpec(_AliasModel):
    """사무실 이전 궁(월주 중심) 규격 (사용자 스펙 12장) — 데이터만, 엔진 배선 R4."""

    ko: str
    primary_palace: list[str] = Field(alias="primaryPalace", min_length=1)
    preferred_relations: list[str] = Field(alias="preferredRelations")
    avoid_relations: list[str] = Field(alias="avoidRelations")
    preferred_ten_gods: list[str] = Field(alias="preferredTenGods")
    avoid_ten_gods: list[str] = Field(alias="avoidTenGods")


class ChungPolicySpec(_AliasModel):
    """충 이중성 정책 (사용자 스펙 10장) — 탐지 긍정 / 택일 감점."""

    event_detection: str = Field(alias="eventDetection")
    date_selection: str = Field(alias="dateSelection")


class DateSelectionTenGodsFile(_AliasModel):
    """계약일·이삿날 분리 택일 점수표 (calendar/date_selection_ten_gods.json)."""

    version: str
    note: str | None = None
    contract_day: ContractDaySpec = Field(alias="contractDay")
    move_day: MoveDaySpec = Field(alias="moveDay")
    office_move: OfficeMoveSpec = Field(alias="officeMove")
    chung_policy: ChungPolicySpec = Field(alias="chungPolicy")
    reviewed: bool


# ── 지역 오행 엔진 사전(Phase P1, docs/12) ───────────────────────

_REGION_ELEMENTS_SET = {"木", "火", "土", "金", "水"}
_REGION_ROLE_KEYS = {"용신", "희신", "보완", "한신", "구신", "기신"}
# §5 기본 레이어. 의도별 가중(§7)은 P3 GIS 활성 레이어를 추가로 가질 수 있다.
_BASE_LAYER_KEYS = {
    "physical_geography", "landcover_hydro_forest", "hanja_place_name",
    "relative_direction", "fengshui_form", "phonetic_reading",
}
_INTENT_LAYER_KEYS = _BASE_LAYER_KEYS | {"modern_activity", "transport_access", "forest_water"}


class RegionHanjaToken(_AliasModel):
    """지명 한자 1자 → 오행 매핑 (region/region_hanja_tokens.json tokens)."""

    char: str = Field(min_length=1, max_length=1)
    element: str
    weight: float = Field(ge=0.0, le=1.0)


class RegionHanjaAlt(_AliasModel):
    """문맥 의존 글자의 보조 오행 — when 조건은 P3 GIS 신호로만 활성(docs/12 §4-2)."""

    element: str
    weight: float = Field(ge=0.0, le=1.0)
    when: str = Field(min_length=1)


class RegionHanjaContextRule(_AliasModel):
    """문맥 의존 글자(山/石/谷/田/浦/津) 규칙 — default_element만 P1 사용."""

    char: str = Field(min_length=1, max_length=1)
    default_element: str
    default_weight: float = Field(ge=0.0, le=1.0)
    alt: list[RegionHanjaAlt] = Field(default_factory=list)
    note: str = ""


class RegionHanjaTokensFile(_AliasModel):
    version: str
    reviewed: bool
    note: str | None = None
    tokens: list[RegionHanjaToken] = Field(min_length=1)
    context_rules: list[RegionHanjaContextRule] = Field(default_factory=list)


class RegionPhoneticInitial(_AliasModel):
    """초성 그룹 → 오행 (region/region_phonetic.json initials)."""

    initials: list[str] = Field(min_length=1)
    element: str


class RegionPhoneticFile(_AliasModel):
    version: str
    reviewed: bool
    note: str | None = None
    weight_cap: float = Field(gt=0.0, le=1.0)  # 음운 레이어 유효가중 절대 상한(D1)
    initials: list[RegionPhoneticInitial] = Field(min_length=1)


class RegionLayerWeightsFile(_AliasModel):
    version: str
    reviewed: bool
    note: str | None = None
    base: dict[str, float]
    intents: dict[str, dict[str, float]]


class RegionConfidenceBands(_AliasModel):
    unknown_below: float = Field(ge=0.0, le=1.0)
    weak_below: float = Field(ge=0.0, le=1.0)


class RegionDominanceSingle(_AliasModel):
    max_element_min: float = Field(ge=0.0, le=1.0)
    gap_min: float = Field(ge=0.0, le=1.0)
    confidence_min: float = Field(ge=0.0, le=1.0)


class RegionDominanceComposite(_AliasModel):
    top2_sum_min: float = Field(ge=0.0, le=1.0)
    gap_max: float = Field(ge=0.0, le=1.0)
    confidence_min: float = Field(ge=0.0, le=1.0)


class RegionMatchPenalty(_AliasModel):
    gisin_factor: float
    gusin_factor: float
    score_penalty_scale: float
    gisin_strong_threshold: float = Field(ge=0.0, le=1.0)
    gusin_strong_threshold: float = Field(ge=0.0, le=1.0)


class RegionConfidenceAdjust(_AliasModel):
    base: float = Field(ge=0.0, le=1.0)
    scale: float = Field(ge=0.0, le=1.0)


class RegionScoreCap(_AliasModel):
    confidence_below: float = Field(ge=0.0, le=1.0)
    max_score: int = Field(ge=0, le=100)


class RegionUserMatch(_AliasModel):
    role_scores: dict[str, float]
    penalty: RegionMatchPenalty
    confidence_adjust: RegionConfidenceAdjust
    score_caps: list[RegionScoreCap] = Field(min_length=1)


class RegionDominanceRulesFile(_AliasModel):
    version: str
    reviewed: bool
    note: str | None = None
    confidence_bands: RegionConfidenceBands
    single: RegionDominanceSingle
    composite: RegionDominanceComposite
    user_match: RegionUserMatch


# ── 지형 신호 규칙·feature(Phase P3, docs/12 §3-C·§4-1) ───────────

_GEO_LAYER_KEYS = {"physical_geography", "landcover_hydro_forest"}


class RegionGeoSignal(_AliasModel):
    """지형 feature 필드 → 오행 신호 1건 (region_geo_signal_rules.json signals)."""

    field: str
    layer: str
    element: str
    scale: float = Field(ge=0.0)
    alt_element: str | None = None
    alt_scale: float | None = Field(default=None, ge=0.0)
    norm: float | None = Field(default=None, gt=0.0)  # density·고도 정규화 제수
    is_bool: bool = False


class RegionGeoContextWhen(_AliasModel):
    """한자 문맥규칙 alt.when 조건 평가 기준(docs/12 §4-2)."""

    field: str
    min: float
    require_coast: bool = False


class RegionGeoLayerConfidence(_AliasModel):
    base: float = Field(ge=0.0, le=1.0)
    per_active_signal: float = Field(ge=0.0, le=1.0)
    max: float = Field(ge=0.0, le=1.0)
    active_min_value: float = Field(ge=0.0, le=1.0)


class RegionGeoSignalRulesFile(_AliasModel):
    version: str
    reviewed: bool
    note: str | None = None
    layer_confidence: RegionGeoLayerConfidence
    signals: list[RegionGeoSignal] = Field(min_length=1)
    context_when: dict[str, RegionGeoContextWhen] = Field(default_factory=dict)


class RegionGeoFeatureFile(_AliasModel):
    version: str
    reviewed: bool
    note: str | None = None
    items: list[RegionGeoFeature] = Field(default_factory=list)


_REGION_INTENT_KEYS = {"relocation", "career", "healing", "general"}


class RegionIntentWeightsFile(_AliasModel):
    """질문 의도별 레이어 가중 preset (region_intent_weights.json, P4-1)."""

    version: str
    reviewed: bool
    note: str | None = None
    phonetic_cap: float = Field(gt=0.0, le=1.0)
    intents: dict[str, dict[str, float]]


_GEO_FEATURE_TYPES = {
    "mountain_peak", "mountain_pass", "ridge_anchor", "valley_anchor", "river_anchor",
    "stream_anchor", "lake_centroid", "lake_boundary_anchor", "wetland_centroid",
    "coast_anchor", "port", "forest_patch", "park_green",
}


class RegionGeoDistanceBucket(_AliasModel):
    bucket: str
    max_m: float = Field(gt=0.0)
    influence: float = Field(ge=0.0, le=1.0)


class RegionGeoFeatureElementsFile(_AliasModel):
    """외부 지형 feature_type → 오행 + 거리 버킷 (region_geo_feature_elements.json, P4-Data)."""

    version: str
    reviewed: bool
    note: str | None = None
    elements: list[str]
    feature_type_rules: dict[str, dict[str, float]]
    distance_buckets: list[RegionGeoDistanceBucket] = Field(min_length=1)
    line_anchor_interval_m: dict[str, float] = Field(default_factory=dict)


# 상대 경로 → 스키마. 새 사전 추가 시 여기 등록해야 검증된다(미등록은 generic 검사만).
SCHEMA_BY_PATH: dict[str, type[BaseModel]] = {
    "common/stems.json": StemsFile,
    "common/branches.json": BranchesFile,
    "common/ten_gods.json": TenGodsFile,
    "common/elements.json": ElementsFile,
    "common/twelve_unseong_groups.json": TwelveUnseongGroupsFile,
    "common/ten_god_events.json": TenGodEventsFile,
    "relations.json": RelationsFile,
    "structure_patterns.json": StructurePatternDict,
    "events/taxonomy.json": TaxonomyFile,
    "favorability_rules.json": FavorabilityRulesFile,
    "interpretations/ilju.json": IljuFile,
    "interpretations/ten_gods_text.json": TenGodsTextFile,
    "interpretations/twelve_stages_text.json": TwelveStagesTextFile,
    "interpretations/relations_text.json": RelationsTextFile,
    "interpretations/sinsal_text.json": SinsalTextFile,
    "interpretations/stems_branches_text.json": StemsBranchesTextFile,
    "interpretations/favorability_text.json": FavorabilityTextFile,
    "interpretations/relocation_ten_gods.json": RelocationTenGodsFile,
    "interpretations/activity_keyword_map.json": ActivityKeywordMapFile,
    "interpretations/remedy_action_map.json": RemedyActionMapFile,
    "interpretations/deficiency_pair_questions.json": DeficiencyPairQuestionsFile,
    "calendar/date_selection_ten_gods.json": DateSelectionTenGodsFile,
    "terminology.json": TerminologyFile,
    "templates/interpretation.json": InterpretationTemplatesFile,
    "templates/prohibited_styles.json": ProhibitedStylesFile,
    "region/region_hanja_tokens.json": RegionHanjaTokensFile,
    "region/region_phonetic.json": RegionPhoneticFile,
    "region/region_layer_weights.json": RegionLayerWeightsFile,
    "region/region_dominance_rules.json": RegionDominanceRulesFile,
    "region/region_geo_signal_rules.json": RegionGeoSignalRulesFile,
    "region/region_intent_weights.json": RegionIntentWeightsFile,
    "region/region_geo_feature_elements.json": RegionGeoFeatureElementsFile,
    "region/geo/region_geo_feature.sample.json": RegionGeoFeatureFile,
}
# events/<domain>.json (taxonomy 제외)은 신호→이벤트 매핑 스키마.
_EVENT_MAPPING_DIR = "events"


def schema_for(rel_path: str) -> type[BaseModel] | None:
    """상대 경로에 해당하는 스키마를 찾는다. 미등록 경로는 None."""
    if rel_path in SCHEMA_BY_PATH:
        return SCHEMA_BY_PATH[rel_path]
    parent = str(Path(rel_path).parent)
    if parent == _EVENT_MAPPING_DIR:
        return EventMappingFile
    return None


def validate_dictionaries(directory: Path) -> list[str]:
    """디렉토리 하위 사전을 스키마 검증하고 위반 메시지 목록을 반환한다(dict:validate)."""
    errors: list[str] = []
    # event_key 필드는 레거시 호환을 위해 str로 완화됐으므로, 유효성은 여기서 명시 검사한다
    # (21키 + 리맵 가능한 레거시 키 허용, 그 외 미등록은 위반).
    valid_keys = {str(k) for k in EventKey} | set(LEGACY_EVENT_KEY_MAP)
    for path in sorted(directory.rglob("*.json")):
        rel = str(path.relative_to(directory))
        schema = schema_for(rel)
        if schema is None:
            continue  # 미등록 사전은 generic 검사(스크립트)만 적용
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{rel}: 스키마 위반 — {exc}")
            continue
        if rel == "events/taxonomy.json":
            for item in data.get("items", []):
                if item.get("eventKey") not in valid_keys:
                    errors.append(f"{rel}: 미등록 이벤트 키 — {item.get('eventKey')}")
    return errors


def _lint_relations(file: RelationsFile) -> list[str]:
    """relations.json 충돌: id 중복."""
    errors: list[str] = []
    seen: set[str] = set()
    for item in file.items:
        if item.id in seen:
            errors.append(f"relations.json: relation id 중복 — {item.id}")
        seen.add(item.id)
    return errors


def _lint_event_mapping(rel: str, file: EventMappingFile) -> list[str]:
    """events/<domain>.json 충돌 검사.

    - 기신·구신 신호인데 polarity=positive / 용신·희신 신호인데 negative_or_forced.
    - 같은 신호 항목 안에서 상반 polarity 후보가 모두 강(score>=임계값).
    - 동일 신호 키가 같은 파일에 중복 정의.
    """
    errors: list[str] = []
    seen_signals: set[str] = set()
    for item in file.items:
        sig = item.signal
        key = sig.key()
        if key in seen_signals:
            errors.append(f"{rel}: 동일 신호 중복 정의 — {key}")
        seen_signals.add(key)

        for cand in item.event_candidates:
            if (
                sig.favorability in _NEGATIVE_FAVORABILITY
                and cand.polarity is EventPolarity.POSITIVE
            ):
                errors.append(
                    f"{rel}: {sig.favorability} 신호인데 polarity=positive — {cand.event}"
                )
            if (
                sig.favorability in _POSITIVE_FAVORABILITY
                and cand.polarity is EventPolarity.NEGATIVE_OR_FORCED
            ):
                errors.append(
                    f"{rel}: {sig.favorability} 신호인데 polarity=negative — {cand.event}"
                )

        strong_pos = [
            c for c in item.event_candidates
            if c.polarity is EventPolarity.POSITIVE and c.score >= _STRONG_CONFLICT_SCORE
        ]
        strong_neg = [
            c for c in item.event_candidates
            if c.polarity is EventPolarity.NEGATIVE_OR_FORCED
            and c.score >= _STRONG_CONFLICT_SCORE
        ]
        if strong_pos and strong_neg:
            errors.append(
                f"{rel}: 같은 신호가 상반 이벤트를 동시에 강하게 유발 — "
                f"{[c.event for c in strong_pos]} vs {[c.event for c in strong_neg]}"
            )
    return errors


def _lint_favorability(file: FavorabilityRulesFile) -> list[str]:
    """favorability_rules.json 충돌: 조건과 효과 극성의 모순."""
    errors: list[str] = []
    for rule in file.items:
        fav = rule.condition.favorability
        pol = rule.effect.polarity
        if fav in _NEGATIVE_FAVORABILITY and pol is EventPolarity.POSITIVE:
            errors.append(f"favorability_rules.json: {fav}인데 polarity=positive — {rule.rule_id}")
        if fav in _POSITIVE_FAVORABILITY and pol is EventPolarity.NEGATIVE_OR_FORCED:
            errors.append(f"favorability_rules.json: {fav}인데 polarity=negative — {rule.rule_id}")
    return errors


# ── interpretations/ 교차검증 (v2.2.1) ───────────────────────────

# 천간 오행 → 일주 동물 색 (오방색 통설: 목청/화적/토황/금백/수흑).
_ELEMENT_COLOR = {"木": "푸른", "火": "붉은", "土": "노란", "金": "흰", "水": "검은"}
# 지지 → 띠 동물 (common/branches.json zodiac과 동일 기준).
_BRANCH_ZODIAC = {
    "子": "쥐", "丑": "소", "寅": "호랑이", "卯": "토끼", "辰": "용", "巳": "뱀",
    "午": "말", "未": "양", "申": "원숭이", "酉": "닭", "戌": "개", "亥": "돼지",
}
_STEMS_ORDER = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES_ORDER = "子丑寅卯辰巳午未申酉戌亥"
_TEN_GOD_NAMES = ("비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인")


def _expected_twelve_stage(stem: Stem, branch: Branch) -> str:
    """십이운성 기대값 — saju_manse_core.twelve_unseong과 동일 공식(공유 상수 기반).

    공식이 갈라지면 회귀 테스트(엔진 함수 직접 대조)에서 잡힌다.
    """
    jangsaeng = JANGSAENG_BRANCH[stem]
    direction = 1 if STEM_YINYANG[stem] is YinYang.YANG else -1
    steps = (BRANCH_INDEX[branch] - BRANCH_INDEX[jangsaeng]) * direction % 12
    return TWELVE_STAGES[steps]


def _lint_ilju(file: IljuFile) -> list[str]:
    """ilju.json 교차검증 — 60갑자 커버리지 + computed 블록 ↔ 만세력 계산 전수 대조."""
    errors: list[str] = []
    expected_order = [_STEMS_ORDER[i % 10] + _BRANCHES_ORDER[i % 12] for i in range(60)]
    got = [item.ganji for item in file.items]
    if got != expected_order:
        errors.append("interpretations/ilju.json: 60갑자 순서/커버리지 불일치 (甲子→癸亥 순)")
        return errors
    for item in file.items:
        stem, branch = Stem(item.ganji[0]), Branch(item.ganji[1])
        hidden = [entry[0].value for entry in hidden_stems_for(branch)]
        main = next(entry[0] for entry in hidden_stems_for(branch) if entry[1].value == "main")
        expected_ten_god = str(ten_god(stem, Stem(main.value)))
        if item.computed.ilji_ten_god != expected_ten_god:
            errors.append(
                f"interpretations/ilju.json: {item.ganji} iljiTenGod="
                f"{item.computed.ilji_ten_god} ≠ 엔진 {expected_ten_god}"
            )
        expected_stage = _expected_twelve_stage(stem, branch)
        if item.computed.twelve_stage != expected_stage:
            errors.append(
                f"interpretations/ilju.json: {item.ganji} twelveStage="
                f"{item.computed.twelve_stage} ≠ 엔진 {expected_stage}"
            )
        if item.computed.hidden_stems != hidden:
            errors.append(
                f"interpretations/ilju.json: {item.ganji} hiddenStems 불일치 — 엔진 {hidden}"
            )
        element = STEM_ELEMENT[stem]
        expected_color = _ELEMENT_COLOR[str(getattr(element, "value", element))]
        if item.animal.color != expected_color:
            errors.append(
                f"interpretations/ilju.json: {item.ganji} 동물 색 {item.animal.color}"
                f" ≠ 오행색 {expected_color}"
            )
        if item.animal.name != _BRANCH_ZODIAC[item.ganji[1]]:
            errors.append(
                f"interpretations/ilju.json: {item.ganji} 띠 동물 {item.animal.name}"
                f" ≠ {_BRANCH_ZODIAC[item.ganji[1]]}"
            )
    return errors


def _lint_ten_gods_text(file: TenGodsTextFile) -> list[str]:
    """ten_gods_text.json — 십성 10종 정확 커버리지."""
    got = {item.ten_god for item in file.items}
    if got != set(_TEN_GOD_NAMES):
        return [f"interpretations/ten_gods_text.json: 십성 커버리지 불일치 — {sorted(got)}"]
    return []


def _lint_twelve_stages_text(file: TwelveStagesTextFile) -> list[str]:
    """twelve_stages_text.json — 십이운성 12종 정확 커버리지(엔진 상수 기준)."""
    got = {item.stage for item in file.items}
    if got != set(TWELVE_STAGES):
        return [f"interpretations/twelve_stages_text.json: 운성 커버리지 불일치 — {sorted(got)}"]
    return []


def _lint_stems_branches_text(file: StemsBranchesTextFile) -> list[str]:
    """stems_branches_text.json — 10천간/12지지 커버리지 + 오행·띠 엔진 상수 교차검증."""
    errors: list[str] = []
    if {s.char for s in file.stems} != set(_STEMS_ORDER):
        errors.append("interpretations/stems_branches_text.json: 천간 10 커버리지 불일치")
    if {b.char for b in file.branches} != set(_BRANCHES_ORDER):
        errors.append("interpretations/stems_branches_text.json: 지지 12 커버리지 불일치")
    for s in file.stems:
        try:
            element = STEM_ELEMENT[Stem(s.char)]
        except ValueError:
            continue
        if s.element != str(getattr(element, "value", element)):
            errors.append(
                f"interpretations/stems_branches_text.json: {s.char} 오행 {s.element} 불일치"
            )
    for b in file.branches:
        expected = _BRANCH_ZODIAC.get(b.char)
        if expected and b.zodiac != expected:
            errors.append(
                f"interpretations/stems_branches_text.json: {b.char} 띠 {b.zodiac} ≠ {expected}"
            )
    return errors


def _lint_templates(file: InterpretationTemplatesFile) -> list[str]:
    """templates/interpretation.json — event 키 유효성('generic' 폴백 허용)·중복 검사."""
    errors: list[str] = []
    # 21키 + 리맵 가능한 레거시 키(그래프 빌더가 21키로 변환) + 'generic' 폴백.
    valid_events = {str(k) for k in EventKey} | set(LEGACY_EVENT_KEY_MAP) | {"generic"}
    seen: set[tuple[str, str]] = set()
    for item in file.items:
        if item.event not in valid_events:
            errors.append(f"templates/interpretation.json: 미등록 이벤트 — {item.event}")
        key = (item.event, item.polarity)
        if key in seen:
            errors.append(f"templates/interpretation.json: 이벤트×극성 중복 — {key}")
        seen.add(key)
    return errors


def _lint_relations_text(directory: Path, file: RelationsTextFile) -> list[str]:
    """relations_text.json — relations.json id와 1:1 정합 + 암합 auxiliary 강제."""
    errors: list[str] = []
    relations_path = directory / "relations.json"
    try:
        relations = RelationsFile.model_validate(
            json.loads(relations_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValidationError):
        return ["interpretations/relations_text.json: relations.json 로드 실패로 정합 검사 불가"]
    base_ids = {item.id for item in relations.items}
    text_ids = {item.id for item in file.items}
    for missing in sorted(base_ids - text_ids):
        errors.append(f"interpretations/relations_text.json: 해석 누락 — {missing}")
    for orphan in sorted(text_ids - base_ids):
        errors.append(f"interpretations/relations_text.json: relations.json에 없는 id — {orphan}")
    for item in file.items:
        # 암합은 보조 자료 — 단독 결론 금지(2026-06-12 사용자 확정).
        if item.type == "amhap" and item.role != "auxiliary":
            errors.append(f"interpretations/relations_text.json: {item.id}는 role=auxiliary여야 함")
    return errors


def _lint_relocation_ten_gods(file: RelocationTenGodsFile) -> list[str]:
    """relocation_ten_gods.json — 십성 10종 정확 커버리지."""
    got = {item.ten_god for item in file.items}
    if got != set(_TEN_GOD_NAMES):
        return [f"interpretations/relocation_ten_gods.json: 십성 커버리지 불일치 — {sorted(got)}"]
    return []


def _lint_date_selection_ten_gods(file: DateSelectionTenGodsFile) -> list[str]:
    """date_selection_ten_gods.json — 십성/오행 유효성 + 작업별 가중 합 ≈ 1.0.

    충 이중성 보존 검사: 충은 탐지엔 긍정이나 택일엔 감점이어야 한다(사용자 스펙 10장).
    """
    errors: list[str] = []
    valid_tg = set(_TEN_GOD_NAMES)
    valid_elem = {"木", "火", "土", "金", "水"}

    def _check_tg(label: str, keys: Iterable[str]) -> None:
        for k in keys:
            if k not in valid_tg:
                errors.append(f"date_selection_ten_gods.json: {label} 십성 오류 — {k}")

    for label, spec in (("contractDay", file.contract_day), ("moveDay", file.move_day)):
        _check_tg(label, spec.preferred_ten_gods)
        _check_tg(label, spec.avoid_ten_gods)
        total = round(sum(spec.weights.values()), 6)
        if total != 1.0:
            errors.append(f"date_selection_ten_gods.json: {label} weights 합 {total} ≠ 1.0")
    for elem in file.contract_day.preferred_elements:
        if elem not in valid_elem:
            errors.append(f"date_selection_ten_gods.json: contractDay 오행 오류 — {elem}")
    _check_tg("officeMove", file.office_move.preferred_ten_gods)
    _check_tg("officeMove", file.office_move.avoid_ten_gods)
    # 충 이중성: 이삿날 점수표는 충을 감점으로 다뤄야 한다(탐지 긍정과 분리).
    for rel, val in file.move_day.branch_relations.items():
        if "충" in rel and val >= 0:
            errors.append(
                f"date_selection_ten_gods.json: moveDay 충 관계는 감점이어야 함 — {rel}={val}"
            )
    if file.chung_policy.date_selection != "negative_for_move_day":
        errors.append(
            "date_selection_ten_gods.json: chungPolicy.dateSelection은 감점 정책이어야 함"
        )
    return errors


def _lint_region_hanja_tokens(file: RegionHanjaTokensFile) -> list[str]:
    """region_hanja_tokens.json — 오행 유효성 + char 중복 검사."""
    errors: list[str] = []
    seen: set[str] = set()
    for t in file.tokens:
        if t.element not in _REGION_ELEMENTS_SET:
            errors.append(f"region/region_hanja_tokens.json: 오행 오류 — {t.char}={t.element}")
        if t.char in seen:
            errors.append(f"region/region_hanja_tokens.json: token char 중복 — {t.char}")
        seen.add(t.char)
    for r in file.context_rules:
        if r.default_element not in _REGION_ELEMENTS_SET:
            errors.append(
                f"region/region_hanja_tokens.json: context default 오행 오류 — {r.char}"
            )
        for a in r.alt:
            if a.element not in _REGION_ELEMENTS_SET:
                errors.append(
                    f"region/region_hanja_tokens.json: context alt 오행 오류 — {r.char}"
                )
    return errors


def _lint_region_phonetic(file: RegionPhoneticFile) -> list[str]:
    """region_phonetic.json — 오행 유효성 + cap 보조 신호 범위(≤0.1) 강제(D1)."""
    errors: list[str] = []
    for it in file.initials:
        if it.element not in _REGION_ELEMENTS_SET:
            errors.append(f"region/region_phonetic.json: 오행 오류 — {it.initials}={it.element}")
    if file.weight_cap > 0.1:
        errors.append(
            f"region/region_phonetic.json: weight_cap {file.weight_cap} 과대 — 음운은 보조(≤0.1)"
        )
    return errors


def _lint_region_layer_weights(file: RegionLayerWeightsFile) -> list[str]:
    """region_layer_weights.json — base/intents 가중 합 ≈ 1.0 + 레이어 키 유효성."""
    errors: list[str] = []
    base_total = round(sum(file.base.values()), 6)
    if base_total != 1.0:
        errors.append(f"region/region_layer_weights.json: base 가중 합 {base_total} ≠ 1.0")
    for k in file.base:
        if k not in _BASE_LAYER_KEYS:
            errors.append(f"region/region_layer_weights.json: base 미지원 레이어 — {k}")
    for intent, weights in file.intents.items():
        total = round(sum(weights.values()), 6)
        if total != 1.0:
            errors.append(
                f"region/region_layer_weights.json: intents.{intent} 가중 합 {total} ≠ 1.0"
            )
        for k in weights:
            if k not in _INTENT_LAYER_KEYS:
                errors.append(
                    f"region/region_layer_weights.json: intents.{intent} 미지원 레이어 — {k}"
                )
    return errors


def _lint_region_dominance_rules(file: RegionDominanceRulesFile) -> list[str]:
    """region_dominance_rules.json — confidence 밴드 단조성 + 역할 키 유효성 + cap 정렬."""
    errors: list[str] = []
    cb = file.confidence_bands
    if not 0.0 <= cb.unknown_below < cb.weak_below <= 1.0:
        errors.append(
            f"region/region_dominance_rules.json: confidence_bands 단조성 위반 — "
            f"unknown<{cb.unknown_below} weak<{cb.weak_below}"
        )
    for role in file.user_match.role_scores:
        if role not in _REGION_ROLE_KEYS:
            errors.append(f"region/region_dominance_rules.json: 미등록 역할 — {role}")
    caps = file.user_match.score_caps
    for lower, higher in zip(caps, caps[1:], strict=False):
        if lower.confidence_below > higher.confidence_below:
            errors.append(
                "region/region_dominance_rules.json: score_caps는 confidence 오름차순이어야 함"
            )
            break
    return errors


def _lint_region_geo_signal_rules(file: RegionGeoSignalRulesFile) -> list[str]:
    """region_geo_signal_rules.json — layer/오행 유효성 + context_when 신뢰도 단조성."""
    errors: list[str] = []
    valid_fields = set(RegionGeoFeature.model_fields)
    rel = "region/region_geo_signal_rules.json"
    for sig in file.signals:
        if sig.layer not in _GEO_LAYER_KEYS:
            errors.append(f"{rel}: 미지원 layer — {sig.layer}")
        if sig.element not in _REGION_ELEMENTS_SET:
            errors.append(f"{rel}: 오행 오류 — {sig.field}={sig.element}")
        if sig.alt_element is not None and sig.alt_element not in _REGION_ELEMENTS_SET:
            errors.append(f"{rel}: alt 오행 오류 — {sig.field}")
        if sig.field not in valid_fields:
            errors.append(f"{rel}: 미정의 feature 필드 — {sig.field}")
    lc = file.layer_confidence
    if not lc.base <= lc.max:
        errors.append(f"{rel}: layer_confidence base>max")
    for name, cond in file.context_when.items():
        if cond.field not in valid_fields:
            errors.append(f"{rel}: context_when[{name}] 미정의 필드 — {cond.field}")
    return errors


def _lint_region_geo_feature_elements(file: RegionGeoFeatureElementsFile) -> list[str]:
    """region_geo_feature_elements.json — feature_type/오행 유효성 + 버킷 단조성."""
    errors: list[str] = []
    rel = "region/region_geo_feature_elements.json"
    for ftype, weights in file.feature_type_rules.items():
        if ftype not in _GEO_FEATURE_TYPES:
            errors.append(f"{rel}: 미지원 feature_type — {ftype}")
        for el in weights:
            if el not in _REGION_ELEMENTS_SET:
                errors.append(f"{rel}: 오행 오류 — {ftype}.{el}")
    buckets = file.distance_buckets
    for lower, higher in zip(buckets, buckets[1:], strict=False):
        if lower.max_m > higher.max_m:
            errors.append(f"{rel}: distance_buckets는 max_m 오름차순이어야 함")
            break
    return errors


def _lint_region_intent_weights(file: RegionIntentWeightsFile) -> list[str]:
    """region_intent_weights.json — intent 키·레이어 키 유효성 + preset 합 ≈ 1.0."""
    errors: list[str] = []
    rel = "region/region_intent_weights.json"
    for intent, weights in file.intents.items():
        if intent not in _REGION_INTENT_KEYS:
            errors.append(f"{rel}: 미지원 intent — {intent}")
        total = round(sum(weights.values()), 6)
        if total != 1.0:
            errors.append(f"{rel}: intents.{intent} 가중 합 {total} ≠ 1.0")
        for layer in weights:
            if layer not in _INTENT_LAYER_KEYS:
                errors.append(f"{rel}: intents.{intent} 미지원 레이어 — {layer}")
    return errors


def _lint_structure_patterns(file: StructurePatternDict) -> list[str]:
    """structure_patterns.json — 중복 id·domain_hints·ten_god_chain·llm_tag 길이 검사."""
    errors: list[str] = []
    rel = "structure_patterns.json"
    event_keys = {e.value for e in EventKeyV2}
    ten_gods = {t.value for t in _TenGodRoman}
    seen: set[str] = set()
    for p in file.patterns:
        if p.pattern_id in seen:
            errors.append(f"{rel}: 중복 pattern_id — {p.pattern_id}")
        seen.add(p.pattern_id)
        for h in p.domain_hints:
            if h not in event_keys:
                errors.append(f"{rel}: {p.pattern_id} domain_hints 미정렬(EventKeyV2 아님) — {h}")
        for t in p.ten_god_chain:
            if t not in ten_gods:
                errors.append(f"{rel}: {p.pattern_id} ten_god_chain 미지원 십성 — {t}")
        if len(p.llm_tag) > 120:
            errors.append(f"{rel}: {p.pattern_id} llm_tag {len(p.llm_tag)}자(>120)")
    return errors


def lint_dictionaries(directory: Path) -> list[str]:
    """충돌 검사(dict:lint). 스키마 위반 파일은 여기서 건너뛴다(validate가 보고)."""
    errors: list[str] = []
    for path in sorted(directory.rglob("*.json")):
        rel = str(path.relative_to(directory))
        schema = schema_for(rel)
        if schema is None:
            continue
        try:
            parsed = schema.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError):
            continue
        if isinstance(parsed, RelationsFile):
            errors.extend(_lint_relations(parsed))
        elif isinstance(parsed, StructurePatternDict):
            errors.extend(_lint_structure_patterns(parsed))
        elif isinstance(parsed, EventMappingFile):
            errors.extend(_lint_event_mapping(rel, parsed))
        elif isinstance(parsed, FavorabilityRulesFile):
            errors.extend(_lint_favorability(parsed))
        elif isinstance(parsed, IljuFile):
            errors.extend(_lint_ilju(parsed))
        elif isinstance(parsed, TenGodsTextFile):
            errors.extend(_lint_ten_gods_text(parsed))
        elif isinstance(parsed, TwelveStagesTextFile):
            errors.extend(_lint_twelve_stages_text(parsed))
        elif isinstance(parsed, RelationsTextFile):
            errors.extend(_lint_relations_text(directory, parsed))
        elif isinstance(parsed, StemsBranchesTextFile):
            errors.extend(_lint_stems_branches_text(parsed))
        elif isinstance(parsed, InterpretationTemplatesFile):
            errors.extend(_lint_templates(parsed))
        elif isinstance(parsed, RelocationTenGodsFile):
            errors.extend(_lint_relocation_ten_gods(parsed))
        elif isinstance(parsed, DateSelectionTenGodsFile):
            errors.extend(_lint_date_selection_ten_gods(parsed))
        elif isinstance(parsed, RegionHanjaTokensFile):
            errors.extend(_lint_region_hanja_tokens(parsed))
        elif isinstance(parsed, RegionPhoneticFile):
            errors.extend(_lint_region_phonetic(parsed))
        elif isinstance(parsed, RegionLayerWeightsFile):
            errors.extend(_lint_region_layer_weights(parsed))
        elif isinstance(parsed, RegionDominanceRulesFile):
            errors.extend(_lint_region_dominance_rules(parsed))
        elif isinstance(parsed, RegionGeoSignalRulesFile):
            errors.extend(_lint_region_geo_signal_rules(parsed))
        elif isinstance(parsed, RegionIntentWeightsFile):
            errors.extend(_lint_region_intent_weights(parsed))
        elif isinstance(parsed, RegionGeoFeatureElementsFile):
            errors.extend(_lint_region_geo_feature_elements(parsed))
    return errors
