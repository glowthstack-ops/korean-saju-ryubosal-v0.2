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

import hashlib
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
from saju_shared_types.direction_suggestions import (
    DirectionRule,
    DirectionSuggestionDict,
    SuggestionCondition,
)
from saju_shared_types.enums import Branch, Stem, StrengthBand, YinYang
from saju_shared_types.event_engine import EventKeyV2, TenGodGroup
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


# ── risks/<domain>.json — 위험 이벤트 사전 (RISK_ENGINE.md §R0-C) ────────────
# 기존 SignalSpec(긍정 사건 생성 중심)을 재사용하지 않는다 — 위험 전용 룰은 발생(trigger)/
# 증폭(amplifier)/완화(mitigator)/차단(blocker) 역할을 분리하고, minimum_evidence로 신호
# 1개 후보 범람을 막는다. 조건은 원시 신호 사실(RawPeriodFacts) 대상 AND 결합이다.

# 위험 룰 조건 유효값 — RawPeriodFacts가 제공하는 사실 축과 1:1.
_RISK_RELATIONS = ("HAP", "CHUNG", "HYEONG", "PA", "HAE", "BOKEUM")
_RISK_PALACES = ("year_pillar", "month_pillar", "day_pillar", "hour_pillar")
_RISK_POLARITY_ROLES = (
    "YONG", "HEE", "NEUTRAL", "GI", "HAN_GOOD", "HAN_BAD", "YONG_STRONG", "GI_STRONG",
)
_RISK_TEN_GOD_GROUPS = ("peer", "output", "wealth", "authority", "resource")
_RISK_TWELVE_STAGES = (
    "JANGSAENG", "MOKYOK", "GWANDAE", "GEONROK", "JEWANG", "SOE",
    "BYEONG", "SA", "MYO", "JEOL", "TAE", "YANG",
)
# 도메인 → risk_id 접두 — 파일 간 risk_id 충돌을 접두 규약으로 차단한다.
_RISK_ID_PREFIX = {
    "finance": "FIN_", "career": "CAR_", "contract_legal": "LEG_",
    "health_safety": "HLT_", "relationship": "REL_", "relocation": "MOV_",
    "selection": "SEL_",
}
# 신호 역할 그룹(RISK_ENGINE.md §신호 역할 매트릭스, 2026-07-15 감수) — 룰 group 유효값.
# event_shape=사건 형태 결정 / target_activation=발현 영역(대상) 활성 / activation=잠재
# 구조의 기간 발동 / targeted_event_shape=사건 형태와 피자극 대상이 하나의 구조화된
# 사실에 함께 담김(배우자궁 직접 피격 등 — 형식적 중복 룰 방지) / generic=미분류(초안 전용).
_RISK_SOURCE_GROUPS = (
    "event_shape", "target_activation", "activation", "targeted_event_shape",
    "structural_weakness", "generic",
)
# requiredGroups·evidenceContract 유효값 — generic은 필수 그룹이 될 수 없다.
# structural_weakness(감수 8차): 사건 형태가 아니라 충격 흡수·검토력 등 방어 능력의
# 약화 — vulnerability 전용(R1에서 event_shape=occurrence와 달리 impact·protection에
# 기여).
_RISK_REQUIRED_GROUPS = (
    "event_shape", "target_activation", "activation", "targeted_event_shape",
    "structural_weakness",
)
# claimCeiling 유효값 — 표현 상한(허용 범위 화이트리스트 allowedClaimScope와 병용).
_RISK_CLAIM_CEILINGS = ("advisory", "watch", "conditional_warning", "warning")
# reviewScope 유효값 — reviewed:true의 의미 범위(감수 4차): shadow_structure=사전 구조·
# shadow 감수 완료(사용자 노출 승인 아님). scoring/selection/exposure는 R1/R2/R3 감수.
_RISK_REVIEW_SCOPES = ("shadow_structure", "scoring", "selection", "exposure")
# targeted_event_shape에 허용되는 관계 유형 — 관계 의미 계층(감수 5차):
# disruptive_strong(충·형)만 단독 targeted 가능. disruptive_weak(파·해)는 약한 신호라
# 대상 특정만으로 사건 형태가 되지 못한다(target_activation로 저작 — 단독 발화 불가).
# conditional_binding(합거·묶임 등 특수 합)·recurrence(복음)는 relationEffect 축이 필요해
# R1 백로그(우호 합·복음은 계속 거부). 파·해를 충·형과 동일 강도로 기계 적용 금지.
_RISK_TARGETED_RELATIONS = ("CHUNG", "HYEONG")


class RiskRuleSpec(_AliasModel):
    """위험 룰 1건 — 조건은 전부 AND. 최소 1개 조건 필수(무조건 룰 금지).

    group은 신호 역할 그룹 — trigger 룰에서 requiredGroups 판정에 쓴다. 감수 원칙
    (2026-07-15): 기신·공망·12운성은 원칙적으로 독립 사건 트리거가 아니라 증폭·취약
    신호다 — 극성·공망·운성 조건 **만**으로 구성된 룰에는 event_shape/target_activation
    그룹을 붙일 수 없다(스키마 강제).
    """

    id: str
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    group: str = "generic"  # 신호 역할 그룹(_RISK_SOURCE_GROUPS)
    ten_god: str | None = Field(default=None, alias="tenGod")  # TenGod 로마자 키
    ten_god_group: str | None = Field(default=None, alias="tenGodGroup")  # peer/output/...
    relation: str | None = None  # HAP/CHUNG/HYEONG/PA/HAE/BOKEUM
    relation_palace: str | None = Field(default=None, alias="relationPalace")
    # 관계의 '대상'(무엇을 충·형했는가) — 원국 피자극 글자의 십성/십성군. 충·형·공망은
    # 존재만으로 도메인을 못 정한다(재성 충≠배우자궁 충≠사회궁 충) — 대상 조건으로 구분.
    relation_target_ten_god: str | None = Field(default=None, alias="relationTargetTenGod")
    relation_target_ten_god_group: str | None = Field(
        default=None, alias="relationTargetTenGodGroup",
    )
    # 정확한 피자극 글자(천간/지지 한자) — 매칭 우선순위: 궁위·자리 > 글자 > 십성 >
    # 십성군 > 도메인 일반 활성(RISK_ENGINE.md §3-2).
    relation_target_letter: str | None = Field(default=None, alias="relationTargetLetter")
    polarity_role_in: list[str] | None = Field(default=None, alias="polarityRoleIn")
    void_active: bool | None = Field(default=None, alias="voidActive")
    twelve_stage_in: list[str] | None = Field(default=None, alias="twelveStageIn")

    @model_validator(mode="after")
    def _validate_rule(self) -> RiskRuleSpec:
        conditions = (
            self.ten_god, self.ten_god_group, self.relation,
            self.polarity_role_in, self.void_active, self.twelve_stage_in,
        )
        if all(c is None for c in conditions):
            raise ValueError(f"위험 룰 조건 없음(무조건 룰 금지): {self.id}")
        if self.group not in _RISK_SOURCE_GROUPS:
            raise ValueError(f"group 값 오류: {self.group} ({self.id})")
        # 감수 원칙 — 극성·공망·운성 단독 룰은 사건 형태/대상 활성 그룹 불가(증폭·취약).
        has_substantive = any(
            c is not None for c in (self.ten_god, self.ten_god_group, self.relation)
        )
        if self.group in (
            "event_shape", "target_activation", "structural_weakness",
        ) and not has_substantive:
            raise ValueError(
                f"기신·공망·12운성 단독 룰은 {self.group} 그룹 불가(증폭·취약 신호): {self.id}"
            )
        # targeted_event_shape — 사건 형태와 피자극 대상이 한 사실에 담긴 룰만 허용.
        # '대상이 특정된 일반 관계'(targeted_relation — target_activation으로 저작)와
        # 구분한다(2026-07-15 감수 3차): 관계+십성(군) 대상만으로는 부족하고,
        # ①궁위가 사건 형태를 정의(배우자궁 충 등 relationPalace 지정)하거나
        # ②사건 구조 십성 동반 조건(tenGod/tenGodGroup — 겁재-재성 경쟁이 재성을
        # 직접 대상으로 함 등)이 함께 있어야 한다.
        if self.group == "targeted_event_shape":
            has_target = any(c is not None for c in (
                self.relation_target_ten_god, self.relation_target_ten_god_group,
                self.relation_target_letter, self.relation_palace,
            ))
            if self.relation is None or not has_target:
                raise ValueError(
                    f"targeted_event_shape는 관계+대상(십성/글자/궁위) 필수: {self.id}"
                )
            shape_bearing = self.relation_palace is not None or any(
                c is not None for c in (self.ten_god, self.ten_god_group)
            )
            if not shape_bearing:
                raise ValueError(
                    f"targeted_event_shape는 궁위 지정 또는 사건 구조 십성 동반 필수"
                    f"(대상 특정 일반 관계는 target_activation): {self.id}"
                )
            if self.relation not in _RISK_TARGETED_RELATIONS:
                raise ValueError(
                    f"targeted_event_shape 관계 유형 오류({self.relation}) — 충·형만"
                    f" 단독 targeted 허용(파·해는 target_activation, 합·복음은 사건"
                    f" 형태 아님): {self.id}"
                )
        if self.ten_god is not None and self.ten_god not in {str(g) for g in _TenGodRoman}:
            raise ValueError(f"tenGod 값 오류: {self.ten_god} ({self.id})")
        if self.ten_god_group is not None and self.ten_god_group not in _RISK_TEN_GOD_GROUPS:
            raise ValueError(f"tenGodGroup 값 오류: {self.ten_god_group} ({self.id})")
        if self.relation is not None and self.relation not in _RISK_RELATIONS:
            raise ValueError(f"relation 값 오류: {self.relation} ({self.id})")
        if self.relation_palace is not None:
            if self.relation is None:
                raise ValueError(f"relationPalace는 relation과 함께만 쓴다: {self.id}")
            if self.relation_palace not in _RISK_PALACES:
                raise ValueError(f"relationPalace 값 오류: {self.relation_palace} ({self.id})")
        if (
            self.relation_target_ten_god is not None
            or self.relation_target_ten_god_group is not None
            or self.relation_target_letter is not None
        ) and self.relation is None:
            raise ValueError(f"relationTarget*은 relation과 함께만 쓴다: {self.id}")
        if self.relation_target_letter is not None and self.relation_target_letter not in (
            {s.value for s in Stem} | {b.value for b in Branch}
        ):
            raise ValueError(
                f"relationTargetLetter 값 오류: {self.relation_target_letter} ({self.id})"
            )
        if self.relation_target_ten_god is not None and (
            self.relation_target_ten_god not in {str(g) for g in _TenGodRoman}
        ):
            raise ValueError(
                f"relationTargetTenGod 값 오류: {self.relation_target_ten_god} ({self.id})"
            )
        if self.relation_target_ten_god_group is not None and (
            self.relation_target_ten_god_group not in _RISK_TEN_GOD_GROUPS
        ):
            raise ValueError(
                f"relationTargetTenGodGroup 값 오류: "
                f"{self.relation_target_ten_god_group} ({self.id})"
            )
        for role in self.polarity_role_in or []:
            if role not in _RISK_POLARITY_ROLES:
                raise ValueError(f"polarityRoleIn 값 오류: {role} ({self.id})")
        for stage in self.twelve_stage_in or []:
            if stage not in _RISK_TWELVE_STAGES:
                raise ValueError(f"twelveStageIn 값 오류: {stage} ({self.id})")
        return self


class RiskMinimumEvidence(_AliasModel):
    """후보 생성 최소 근거 — 신호 1개로 모든 위험 후보가 생성되는 범람을 막는다.

    required_groups: 개수 조건과 별개의 **필수 신호 그룹** — '약한 범용 신호 2개'와
    '사건 형태 1 + 대상 활성 1'을 구분한다(2026-07-15 감수). incident_risk는 감수 승격
    (reviewed:true) 시 event_shape·target_activation 포함이 lint로 강제된다.
    """

    trigger_count: int = Field(alias="triggerCount", ge=1)
    independent_source_count: int = Field(alias="independentSourceCount", ge=1)
    required_groups: list[str] = Field(alias="requiredGroups", default_factory=list)

    @model_validator(mode="after")
    def _validate_groups(self) -> RiskMinimumEvidence:
        for g in self.required_groups:
            if g not in _RISK_REQUIRED_GROUPS:
                raise ValueError(f"requiredGroups 값 오류: {g}")
        if len(set(self.required_groups)) != len(self.required_groups):
            raise ValueError("requiredGroups 중복")
        return self


class RiskGroupClause(_AliasModel):
    """증거 계약의 대안 절 1개 — 나열된 그룹 전부의 trigger 근거가 있어야 충족."""

    all_of_groups: list[str] = Field(alias="allOfGroups", min_length=1)

    @model_validator(mode="after")
    def _validate_clause(self) -> RiskGroupClause:
        for g in self.all_of_groups:
            if g not in _RISK_REQUIRED_GROUPS:
                raise ValueError(f"allOfGroups 값 오류: {g}")
        return self


class RiskEvidenceContract(_AliasModel):
    """증거 계약 대안 구조(2026-07-15 감수) — requiredGroups의 상위 표현.

    anyOf 중 한 절이라도 충족하면 그룹 조건 통과. targeted_event_shape(사건 형태+대상이
    한 사실)를 별도 절로 허용해 형식적 중복 룰을 없앤다. 단 하나의 사실이 두 의미를
    충족해도 **독립 원인은 1개**로 계산한다(원인 서명 중복 방지 원칙 유지).

    **후보 생성 조건 ≠ 높은 경고 등급 조건(감수 4차 재확인)**: 독립 원인 1개도 구조가
    충족되면 후보는 생성되고(R1 등급 watch 상한), 독립 원인 2개 강제는 전체 저작
    원칙이 아니라 **예외적인 위험별 정책**이다 — minIndependentCauses ≥ 2는
    candidatePolicy="multi_cause_only" + rationale 명시가 있어야 한다(검증 강제).
    """

    any_of: list[RiskGroupClause] = Field(alias="anyOf", min_length=1)
    min_independent_causes: int = Field(alias="minIndependentCauses", ge=1, default=1)
    candidate_policy: str | None = Field(default=None, alias="candidatePolicy")
    rationale: str | None = None
    # 대상 연결 요구(감수 11차) — shape 계열과 활성 계열 trigger가 원인 원자를 공유하거나
    # 십성군 대상이 겹쳐야 적격. 서로 무관한 신호(편관=사회궁·식상=가족궁)의 느슨한
    # 조합으로 부담·경쟁 후보가 만들어지는 것을 차단한다.
    requires_linked_targets: bool = Field(default=False, alias="requiresLinkedTargets")

    @model_validator(mode="after")
    def _validate_policy(self) -> RiskEvidenceContract:
        if self.candidate_policy is not None and self.candidate_policy != "multi_cause_only":
            raise ValueError(f"candidatePolicy 값 오류: {self.candidate_policy}")
        if self.min_independent_causes >= 2 and (
            self.candidate_policy != "multi_cause_only" or not self.rationale
        ):
            raise ValueError(
                "minIndependentCauses ≥ 2는 예외 정책 — candidatePolicy="
                "'multi_cause_only' + rationale 명시 필수(생성/등급 분리 원칙)"
            )
        return self


class RiskManifestationSpec(_AliasModel):
    """가능한 발현 형태 1건 — 노출 미확인 시 조건부 제시(2~3개)의 원천."""

    id: str
    ko: str


# 선발 방식(감수 10차) — 경쟁 평가/추첨/자격 심사/배치는 서로 다른 위험 구조다.
# 항목이 적용 가능한 방식을 명시해 추첨형에 '실력 경쟁' 표현이 확산되는 것을 막는다.
_RISK_SELECTION_MODES = (
    "competitive_assessment", "lottery_draw", "eligibility_screening",
    "placement_allocation", "mixed",
)
# 선발 단계(감수 13차) — mode와 독립 축(상호 자동 추론 금지: stage=draw여도 mode를
# lottery로 가정하지 않는다). MATCHED/UNKNOWN/MISMATCHED 3상태는 R3 노출 판정 소비
# (UNKNOWN=구조 보존·특정 표현 금지, MISMATCHED=NOT_APPLICABLE·임의 fallback 금지).
# r0.5.6부터 엔진 적격성이 실제 소비(3상태 → mismatched=BLOCKED).
# final_decision(감수 16차): 내부 승인·최종 판단이 **실제 진행 중**인 단계에만 부여 —
# 사용자가 결과를 궁금해한다는 이유만으로 추론 금지(데굴님 제한). result_wait와 함께
# HIRING_OUTCOME_SETBACK류 '결과 단계' 항목의 게이트로 쓴다(지원·면접 단계 오적용 차단).
_RISK_SELECTION_STAGES = (
    "application_document", "eligibility_check", "assessment", "draw",
    "result_wait", "final_decision", "waitlist", "placement_allocation",
)
# 선발 대상 유형(감수 14차) — CAR·SEL 소유권 라우팅: 채용=CAR primary, 그 외=SEL.
_RISK_TARGET_TYPES = (
    "employment_hiring", "examination", "public_selection", "lottery_allocation",
    "placement", "procurement_bid",
)
# 이동·주거 대상 유형/단계(감수 18차 — MOV 차수) — 운 신호만으로 이사 계획·계약·
# 차량·통근의 존재를 만들지 않는다: 항목이 적용 가능한 이동 대상·단계를 명시하고
# 현실 축은 MobilityContext(프로필·질문)가 공급한다. 3상태는 selection 축과 동일
# (UNKNOWN=하드 비노출 — 이사·차량 특정 표현은 계획 확인 없이 불가).
_RISK_MOBILITY_TARGET_TYPES = (
    "residential_move", "housing_search", "housing_contract", "workplace_relocation",
    "temporary_stay", "commute_change", "travel_transport", "vehicle_use",
)
_RISK_MOBILITY_STAGES = (
    "no_plan", "considering", "searching", "negotiating", "contracted",
    "preparing", "moving", "settled",
)
# 법적 절차 컨텍스트(감수 23차 — LEG 재검토 차수) — Selection 어휘를 재사용하지
# 않는다(선발 심사·행정 처리·계약 협의·분쟁·소송이 섞이는 것 방지): 공통 3상태
# 판정기만 공유하고 어휘·현실 의미는 LEG 전용. 문서·지연·계약·분쟁 신호만으로 모든
# 절차가 법적 위험으로 복제되지 않게, 실제 진행 중인 process episode에 연결한다.
_RISK_LEGAL_TARGET_TYPES = (
    "contract", "administrative_application", "permit_registration",
    "settlement_recovery", "rights_obligation", "dispute", "litigation",
    "claim_compensation",
)
_RISK_LEGAL_STAGES = (
    "drafting", "negotiating", "active_contract", "submission", "review",
    "supplement_request", "decision_wait", "response_required", "settlement",
    "dispute_active", "litigation_active", "closed",
)
# stage 의미 확정(감수 23차 커밋 조건): active_contract=성립·이행 중 계약(협상 중
# 미성립 negotiating과 상호 대체 불가 — 계약 종료 위험은 이 stage 없이 노출 금지).
# closed=종결 절차 — 어떤 항목의 stage 목록에도 명시되지 않으면 신규 LEG 후보를
# 만들지 못한다(엔진 _resolve_legal_all의 명시 opt-in 규칙 — 사후 정산·청구는 별도
# episode·별도 stage 컨텍스트로 병존).
# 건강 컨텍스트 유형(감수 21차 — HLT 차수) — 질병명·진단·부위는 저장·식별자 사용
# 금지: 항목이 적용 가능한 건강 맥락 유형을 명시하고, 기존 질환·치료·회복·신체 부담의
# 실재는 HealthContext(프로필·질문 — 익명 상태값)가 공급한다. 건강 질문이라는 사실이
# 질환·치료 존재를 자동 확인하지 않는다.
_RISK_HEALTH_CONTEXT_TYPES = (
    "general_wellness", "existing_condition", "current_symptom", "treatment_process",
    "recovery_process", "physical_workload", "sleep_schedule_load",
)
# 관계 역할 유형(감수 16차 — REL 차수) — 관계 위험은 십성·궁위만으로 현실의 상대를
# 만들어내지 않는다: 항목이 적용 가능한 관계 역할을 명시하고, 현실 역할·노출은
# RelationshipContext(프로필·동반자 등록·궁합/함께보기 질문 대상)가 공급한다.
# 테마사주·AI채팅 궁합 풀이에서는 동반자 관계힌트가 이 역할 어휘로 매핑된다.
_RISK_RELATIONSHIP_ROLES = (
    "current_partner", "spouse", "dating_partner", "family_member",
    "friend_peer", "business_partner", "colleague", "broader_social",
)
# 흡수 역할 힌트 어휘(감수 16차) — 항목이 대표 후보에 흡수될 때 갖는 역할을 사전에서
# 지정(kind 기반 기본값 대체). possible_trajectory: 대표 위험이 진행될 경우의 궤적
# (거리감 증가 등) — 독립 발현이 아니라 전개 방향 서술 전용.
_RISK_ABSORBED_ROLES = (
    "supporting_manifestation", "impact_amplifier", "background_vulnerability",
    "secondary_domain_effect", "possible_trajectory",
)

# exposurePolicy 유효값(감수 6차) — 현실 노출 정책을 note가 아닌 기계 판독 필드로.
_RISK_EXPOSURE_REQUIREMENTS = (
    "not_required", "required_for_warning", "required_for_exposure", "confirmed_required",
)
_RISK_UNKNOWN_ACTIONS = ("retain_structural_candidate", "downgrade")
_RISK_BLOCK_ACTIONS = ("block", "downgrade")


class RiskExposurePolicy(_AliasModel):
    """현실 노출 정책 — R1 노출 판정·등급 상한이 이 필드를 소비한다(R0.5는 저작만).

    requirement: not_required(운 신호만으로 유지) / required_for_warning(경고 승격에
    노출 필요) / required_for_exposure(사용자 노출에 노출 확인 필요 — UNKNOWN은 조건부
    표현) / confirmed_required(노출 CONFIRMED 없이는 사건 적용 불가 — 운 구조만으로
    보증·투자 등을 추론 금지).
    """

    requirement: str = "not_required"
    unknown_action: str = Field(default="retain_structural_candidate", alias="unknownAction")
    denied_action: str = Field(default="block", alias="deniedAction")
    not_applicable_action: str = Field(default="block", alias="notApplicableAction")
    claim_ceiling_when_unknown: str | None = Field(
        default=None, alias="claimCeilingWhenUnknown",
    )
    # UNKNOWN 노출 가부(감수 14차) — false면 노출 확인 전 사용자 노출 절대 불가
    # (구조 후보만 보존, "~일 수 있다면" 표현도 금지). 기계 판독 — is_exposable이 소비.
    unknown_exposable: bool = Field(default=True, alias="unknownExposable")
    fallback_risk_id: str | None = Field(default=None, alias="fallbackRiskId")
    # 관계 노출 실질 조건(감수 16차 — REL 차수): 관계 역할 존재만으로는 부족한 항목의
    # 추가 노출 요건. requiresFinancialTie=실제 금전 거래·공동 비용·대여·보증·정산 관계
    # (대인 금전 사건은 이것 없이 구체 사건 노출 금지). requiresSharedResponsibility=
    # 돌봄·가족 재정·동거/주거·가족 의사결정 중 1개 이상의 실제 책임(가족 부담 항목).
    # 엔진 유도: 조건 True인데 컨텍스트 값 False→해당 관계에 대해 DENIED, None(미확인)
    # →CONFIRMED여도 UNKNOWN으로 강등(존재 추론 금지).
    requires_financial_tie: bool = Field(default=False, alias="requiresFinancialTie")
    requires_shared_responsibility: bool = Field(
        default=False, alias="requiresSharedResponsibility",
    )
    # 이동·주거 노출 실질 조건(감수 18차 — MOV 차수): 수리 책임(하자 비용 위험),
    # 통근 의존(통근 부담), 차량 노출(차량·운송 사건 — 대중교통 사용자에게 차량 경고
    # 금지). 유도 규칙은 관계 조건과 동일: False→DENIED, None→CONFIRMED여도 UNKNOWN.
    requires_repair_responsibility: bool = Field(
        default=False, alias="requiresRepairResponsibility",
    )
    requires_commute_dependency: bool = Field(
        default=False, alias="requiresCommuteDependency",
    )
    requires_vehicle_exposure: bool = Field(
        default=False, alias="requiresVehicleExposure",
    )
    # 건강 노출 실질 조건(감수 21차 — HLT 차수): 기존 질환/치료 과정/회복 과정/신체적
    # 업무 부담이 실제 확인된 경우에만 해당 맥락 위험을 설명한다. 유도: 상태 'none'
    # (명시 부재)→DENIED, None(미확인)→CONFIRMED여도 UNKNOWN 강등, physical_demand는
    # none·low→DENIED(직업 존재만으로 신체 부하 추론 금지).
    # 법적 절차 실질 조건(감수 23차): 기존 분쟁/소송이 실제 확인된 경우에만 해당
    # 맥락 위험을 설명한다(False=DENIED, None=미확인 강등 — 분쟁·소송 존재 추론 금지).
    requires_existing_dispute: bool = Field(
        default=False, alias="requiresExistingDispute",
    )
    requires_existing_litigation: bool = Field(
        default=False, alias="requiresExistingLitigation",
    )
    requires_existing_condition: bool = Field(
        default=False, alias="requiresExistingCondition",
    )
    requires_treatment_process: bool = Field(
        default=False, alias="requiresTreatmentProcess",
    )
    requires_recovery_process: bool = Field(
        default=False, alias="requiresRecoveryProcess",
    )
    requires_physical_demand: bool = Field(
        default=False, alias="requiresPhysicalDemand",
    )

    @model_validator(mode="after")
    def _validate_policy(self) -> RiskExposurePolicy:
        if self.requirement not in _RISK_EXPOSURE_REQUIREMENTS:
            raise ValueError(f"exposurePolicy.requirement 값 오류: {self.requirement}")
        if self.unknown_action not in _RISK_UNKNOWN_ACTIONS:
            raise ValueError(f"unknownAction 값 오류: {self.unknown_action}")
        if self.denied_action not in _RISK_BLOCK_ACTIONS:
            raise ValueError(f"deniedAction 값 오류: {self.denied_action}")
        if self.not_applicable_action not in _RISK_BLOCK_ACTIONS:
            raise ValueError(f"notApplicableAction 값 오류: {self.not_applicable_action}")
        if (
            self.claim_ceiling_when_unknown is not None
            and self.claim_ceiling_when_unknown not in _RISK_CLAIM_CEILINGS
        ):
            raise ValueError(
                f"claimCeilingWhenUnknown 값 오류: {self.claim_ceiling_when_unknown}"
            )
        if self.unknown_action == "downgrade" and self.fallback_risk_id is None:
            raise ValueError("unknownAction=downgrade는 fallbackRiskId 필수")
        return self


class RiskItem(_AliasModel):
    """위험 이벤트 정의 1건."""

    risk_id: str = Field(alias="riskId")
    domain: str  # RiskDomain 값 — 파일 domain과 일치(lint)
    kind: str  # pressure | vulnerability | incident_risk
    # 도메인 교차 중복 관리(2026-07-15 감수) — 같은 현실 사건(예: 임대차 하자)이 여러
    # 도메인 risk_id로 갈라질 때 주 위험 1건 + 파생 설명으로 통합하기 위한 통합 키.
    risk_family: str | None = Field(default=None, alias="riskFamily")
    related_domains: list[str] = Field(alias="relatedDomains", default_factory=list)
    # 특이도(2026-07-15 감수) — 동일 원인·family·기간에서 대표 후보 결정에 쓴다:
    # 구체 대상 사건 3 > 도메인 일반 사건 2 > 취약성 1 > 전반 압박 0. 미지정 시 kind로
    # 유도(incident=2, vulnerability=1, pressure=0 — 구체 대상 사건은 명시 3 권장).
    specificity_rank: int | None = Field(default=None, alias="specificityRank", ge=0, le=3)
    base_impact: float = Field(alias="baseImpact", ge=0.0, le=1.0)
    trigger_rules: list[RiskRuleSpec] = Field(alias="triggerRules", min_length=1)
    amplifier_rules: list[RiskRuleSpec] = Field(alias="amplifierRules", default_factory=list)
    mitigator_rules: list[RiskRuleSpec] = Field(alias="mitigatorRules", default_factory=list)
    blocker_rules: list[RiskRuleSpec] = Field(alias="blockerRules", default_factory=list)
    minimum_evidence: RiskMinimumEvidence = Field(alias="minimumEvidence")
    # 증거 계약 대안 구조 — 있으면 requiredGroups 대신 이 계약으로 그룹·독립 원인 판정.
    evidence_contract: RiskEvidenceContract | None = Field(
        default=None, alias="evidenceContract",
    )
    manifestations: list[RiskManifestationSpec] = Field(min_length=1)
    # 표현 정책 — 블랙리스트(prohibited)만으로는 건강·법률 빈틈이 생긴다: 허용 범위
    # 화이트리스트(allowedClaimScope) + 표현 상한(claimCeiling)을 병용한다.
    prohibited_claims: list[str] = Field(alias="prohibitedClaims", default_factory=list)
    allowed_claim_scope: list[str] = Field(alias="allowedClaimScope", default_factory=list)
    claim_ceiling: str | None = Field(default=None, alias="claimCeiling")
    note: str | None = None
    reviewed: bool
    # 감수 범위 메타데이터(감수 5차 — 누적 구조): 항목은 여러 단계 감수를 순차 통과한다.
    # shadow_structure는 사전 구조·shadow 감수 완료를 뜻하며 사용자 노출 승인이 아니다
    # (노출은 exposure 감수). reviewVersions는 scope→감수 차수 기록.
    review_scopes: list[str] = Field(alias="reviewScopes", default_factory=list)
    review_versions: dict[str, str] = Field(alias="reviewVersions", default_factory=dict)
    # 감수 무효화 가드(감수 6차 — 범위별 해시): scope→감수 당시 해당 범위 본문 해시.
    # 현재 해시와 다르면 lint 실패(본문을 고치면 그 범위 감수가 자동 무효 — 재스탬프).
    review_hashes: dict[str, str] = Field(alias="reviewHashes", default_factory=dict)
    # 감수 당시 엔진 의미론 버전(감수 9차) — RISK_REVIEW_ENVIRONMENT_VERSION과 대조.
    review_environment_version: str | None = Field(
        default=None, alias="reviewEnvironmentVersion",
    )
    # 현실 노출 정책(감수 6차) — note가 아니라 기계 판독 필드. R1이 소비한다.
    exposure_policy: RiskExposurePolicy | None = Field(default=None, alias="exposurePolicy")
    # 교차 도메인 파생 효과 — 후보 복제 대신 주 도메인 후보에 부착(예: contract_review_needed).
    cross_domain_effects: list[str] = Field(alias="crossDomainEffects", default_factory=list)
    # 적용 가능한 선발 방식(감수 10차, selection 도메인 전용) — 미지정=방식 무관.
    # 방식 UNKNOWN이면 claim은 '선발 조건 부담' 일반 수준으로 제한(R3).
    applicable_selection_modes: list[str] = Field(
        alias="applicableSelectionModes", default_factory=list,
    )
    applicable_selection_stages: list[str] = Field(
        alias="applicableSelectionStages", default_factory=list,
    )
    # 적용 가능한 선발 대상 유형(감수 14차) — CAR·SEL 소유권: 명시 목록 밖의
    # target_type이 확인되면 MISMATCHED(차단). 미지정=유형 무관.
    applicable_target_types: list[str] = Field(
        alias="applicableTargetTypes", default_factory=list,
    )
    # 적용 가능한 관계 역할(감수 16차 — REL 차수): 미지정=역할 무관(일반 대인).
    # 지정 항목은 RelationshipContext의 역할·노출로 유효 노출을 유도하며, 질문 직접
    # 대상(궁합·함께보기)의 역할이 목록 밖이면 MISMATCHED(차단, fallback 금지).
    applicable_relationship_roles: list[str] = Field(
        alias="applicableRelationshipRoles", default_factory=list,
    )
    # 적용 가능한 이동 대상 유형·단계(감수 18차 — MOV 차수): 미지정=무관. 소유권
    # 라우팅 포함(발령·보직=CAR primary — workplace_relocation을 목록에서 제외하면
    # 해당 질문 대상에서 MISMATCHED 차단).
    applicable_mobility_target_types: list[str] = Field(
        alias="applicableMobilityTargetTypes", default_factory=list,
    )
    applicable_mobility_stages: list[str] = Field(
        alias="applicableMobilityStages", default_factory=list,
    )
    # 적용 가능한 건강 컨텍스트 유형(감수 21차 — HLT 차수): 미지정=유형 무관.
    applicable_health_context_types: list[str] = Field(
        alias="applicableHealthContextTypes", default_factory=list,
    )
    # 적용 가능한 법적 절차 유형·단계(감수 23차 — LEG 차수): 미지정=무관.
    applicable_legal_target_types: list[str] = Field(
        alias="applicableLegalTargetTypes", default_factory=list,
    )
    applicable_legal_stages: list[str] = Field(
        alias="applicableLegalStages", default_factory=list,
    )
    # 흡수 시 역할 힌트(감수 16차) — 대표 후보에 흡수될 때 kind 기본값 대신 쓸 역할
    # (감정 충돌=supporting_manifestation, 거리감=possible_trajectory 등).
    absorbed_role_hint: str | None = Field(default=None, alias="absorbedRoleHint")
    # 재감수 대기 차수(감수 19차 — 절차 가드): 구조가 변경된 reviewed 항목은 자동
    # 강등(reviewed:false)되고 이 필드에 대기 차수를 기록한다. 감수 승인 시 재승격하며
    # 이 필드를 지운다. reviewed:true와 동시 존재 금지(lint).
    review_pending: str | None = Field(default=None, alias="reviewPending")

    @model_validator(mode="after")
    def _validate_item(self) -> RiskItem:
        if self.kind not in ("pressure", "vulnerability", "incident_risk"):
            raise ValueError(f"kind 값 오류: {self.kind} ({self.risk_id})")
        if len(set(self.review_scopes)) != len(self.review_scopes):
            raise ValueError(f"reviewScopes 중복: {self.risk_id}")
        for scope in self.review_scopes:
            if scope not in _RISK_REVIEW_SCOPES:
                raise ValueError(f"reviewScopes 값 오류: {scope} ({self.risk_id})")
        for scope in (*self.review_versions, *self.review_hashes):
            if scope not in self.review_scopes:
                raise ValueError(
                    f"review 메타에 미감수 scope 기록: {scope} ({self.risk_id})"
                )
        if self.domain not in _RISK_ID_PREFIX:
            raise ValueError(f"domain 값 오류: {self.domain} ({self.risk_id})")
        for d in self.related_domains:
            if d not in _RISK_ID_PREFIX:
                raise ValueError(f"relatedDomains 값 오류: {d} ({self.risk_id})")
            if d == self.domain:
                raise ValueError(f"relatedDomains에 자기 도메인 포함: {self.risk_id}")
        if self.claim_ceiling is not None and self.claim_ceiling not in _RISK_CLAIM_CEILINGS:
            raise ValueError(f"claimCeiling 값 오류: {self.claim_ceiling} ({self.risk_id})")
        for mode in self.applicable_selection_modes:
            if mode not in _RISK_SELECTION_MODES:
                raise ValueError(
                    f"applicableSelectionModes 값 오류: {mode} ({self.risk_id})"
                )
        for stage in self.applicable_selection_stages:
            if stage not in _RISK_SELECTION_STAGES:
                raise ValueError(
                    f"applicableSelectionStages 값 오류: {stage} ({self.risk_id})"
                )
        for tt in self.applicable_target_types:
            if tt not in _RISK_TARGET_TYPES:
                raise ValueError(
                    f"applicableTargetTypes 값 오류: {tt} ({self.risk_id})"
                )
        for mt in self.applicable_mobility_target_types:
            if mt not in _RISK_MOBILITY_TARGET_TYPES:
                raise ValueError(
                    f"applicableMobilityTargetTypes 값 오류: {mt} ({self.risk_id})"
                )
        for ms in self.applicable_mobility_stages:
            if ms not in _RISK_MOBILITY_STAGES:
                raise ValueError(
                    f"applicableMobilityStages 값 오류: {ms} ({self.risk_id})"
                )
        for lt in self.applicable_legal_target_types:
            if lt not in _RISK_LEGAL_TARGET_TYPES:
                raise ValueError(
                    f"applicableLegalTargetTypes 값 오류: {lt} ({self.risk_id})"
                )
        for ls in self.applicable_legal_stages:
            if ls not in _RISK_LEGAL_STAGES:
                raise ValueError(
                    f"applicableLegalStages 값 오류: {ls} ({self.risk_id})"
                )
        for ht in self.applicable_health_context_types:
            if ht not in _RISK_HEALTH_CONTEXT_TYPES:
                raise ValueError(
                    f"applicableHealthContextTypes 값 오류: {ht} ({self.risk_id})"
                )
        for role in self.applicable_relationship_roles:
            if role not in _RISK_RELATIONSHIP_ROLES:
                raise ValueError(
                    f"applicableRelationshipRoles 값 오류: {role} ({self.risk_id})"
                )
        if (
            self.absorbed_role_hint is not None
            and self.absorbed_role_hint not in _RISK_ABSORBED_ROLES
        ):
            raise ValueError(
                f"absorbedRoleHint 값 오류: {self.absorbed_role_hint} ({self.risk_id})"
            )
        return self


# 해시 스키마 버전 — 해시 대상 구성이 바뀌면 올린다(공백·키 순서 무관 canonical 직렬화).
# v3(감수 7차): specificityRank를 scoring에서 제거 — 대표·흡수 우선순위는 selection 소관,
# scoring은 위험도 prior(baseImpact)만. 매처 의미론 변경 감지(reviewEnvironmentVersion/
# reviewDependencyHash)는 R1 전 도입 예정.
# v4(감수 8차): 후보 상태를 바꾸는 exposurePolicy 필드(requirement·unknown/denied/
# notApplicable action·fallbackRiskId)를 structure 해시에 편입 — deniedAction 변경으로
# active 밀도가 변하는데 구조 감수 해시가 유지되는 구멍 차단. claimCeilingWhenUnknown은
# 표현 정책이라 exposure 해시 유지.
# v5(감수 16차): ①적용 가능성 축(applicableSelectionModes/Stages/TargetTypes/
# RelationshipRoles)을 structure 해시에 편입 — 축이 MISMATCHED→BLOCKED를 만드는 구조적
# 상태 재료인데 어느 해시에도 없던 구멍 차단(v4의 exposurePolicy와 같은 원칙).
# ②requiresFinancialTie/SharedResponsibility(노출 유도 상태 재료)를 structure 해시에,
# ③absorbedRoleHint(흡수 역할 — 대표·흡수 소관)를 selection 해시에 편입.
# v6(감수 18차): 이동 축(applicableMobilityTargetTypes/Stages)·이동 실질 조건
# (requiresRepairResponsibility/CommuteDependency/VehicleExposure)을 structure 해시에
# 편입 — v5와 같은 원칙(BLOCKED·노출 상태 재료는 구조 감수 대상).
# v7(감수 21차): 건강 축(applicableHealthContextTypes)·건강 실질 조건(requiresExisting
# Condition/TreatmentProcess/RecoveryProcess/PhysicalDemand)을 structure 해시에 편입.
# v8(감수 23차): 법적 절차 축(applicableLegalTargetTypes/Stages)·법적 실질 조건
# (requiresExistingDispute/Litigation)을 structure 해시에 편입.
_RISK_HASH_SCHEMA_VERSION = 8
# 매처·억제 의미론 버전(감수 9차 도입) — matcher/eligibility/cause atom/suppression의
# 의미가 바뀔 때 올린다. reviewed 항목은 감수 당시 이 값을 스탬프하며, 불일치 시 lint
# 실패(사전 JSON이 그대로여도 엔진 의미가 바뀌면 재감수 대상).
# r0.5.4: 흡수 대표 우선순위에 노출 적격성 추가 + 관계 대상 서명 정규화(궁위·자리·글자·십성).
# r0.5.5: 증거 계약 requiresLinkedTargets — 역할 활성과 부담 shape가 같은 대상/연결된
# 원인에 속해야 적격(무관 신호의 느슨한 조합 차단, 감수 11차).
# r0.5.6: SelectionContext(mode/stage/target_type) 3상태(MATCHED/UNKNOWN/MISMATCHED)를
# 엔진 적격성에 실제 소비 + stage-aware suppression + 소유권 차단(감수 14차 C3-d).
# r0.5.7(감수 16·17차 — REL 차수): RelationshipContext(역할·target_id·관계별 노출·실질
# 조건)를 적격성에 소비 — 관계 항목의 유효 노출은 전역 파라미터가 아니라 매칭 컨텍스트
# 에서 유도. 억제는 relationship 도메인에서 family를 넘어 '같은 상대(target_id·역할)'
# 기준으로 확장(감정충돌·오해·신뢰·거리감의 동일 원인 확산을 대표 1건+보조 역할로 수렴).
# 17차 확정: ①대표 선택은 사전 순서 무관 결정적 비교자(노출 적격→구체 상대→역할 특정→
# 특이도→risk_id) ②REL cross-family 흡수는 absorbedRoleHint 명시 항목 + 같은 target_id
# 또는 관계 사실(relation 원자) 공유 필수(십성 유입 공유만으로 다른 상대 수렴 금지)
# ③역할 특정 항목의 UNKNOWN 조건부 노출은 alignment=matched(관계 확인·질문 대상)에서만.
# r0.5.8(감수 18차 — MOV 차수): MobilityContext(target_type·stage 축, 이동 실질 조건)를
# 적격성에 소비 — UNKNOWN 축은 selection과 동일한 하드 비노출. 현실 대상 수렴 도메인을
# relationship→{relationship, relocation}으로 확장(같은 이동 episode의 일정 차질·적응
# 부담을 대표 1건+보조 역할로 수렴 — relation 원자 공유+absorbedRoleHint 게이트 동일).
# r0.5.9(감수 21차 — HLT 차수): HealthContext(context_type 축·건강 실질 조건 4종·
# health_episode_id)를 적격성에 소비 — 건강 질문·명리 신호만으로 질병·치료·신체 부위를
# 만들지 않는다. 수렴 도메인에 health_safety 추가(같은 건강 episode 수렴 — relation
# 원자·hint 게이트 동일). 이동과 동일한 UNKNOWN 차등(구체 항목 비노출/일반 조건부).
# r0.5.10(감수 23차 — LEG 재검토): LegalProcessContext(target·stage 축·process
# episode·기존 분쟁/소송 조건)를 적격성에 소비. 수렴 도메인에 contract_legal 추가
# (같은 process episode의 문서·지연·검토 취약을 대표 1건+보조로 수렴).
# r0.5.11(감수 23차 커밋 조건 — 데굴님 검토 반영): ①vulnerability 대표 금지 일반화 —
# 단독 노출 없음(r0.5.10)에 더해 어느 도메인에서도 다른 후보를 흡수하는 대표가 될 수
# 없다(RCW 역할 보장 목록의 기계 강제 — 배경 근거 전용) ②legal stage 'closed' 명시
# opt-in — 항목 stage 목록에 없으면 종결 절차 컨텍스트로 신규 후보 생성 불가
# ③legal stage 'active_contract' 신설(협상 중 미성립≠진행 중 계약).
# r0.5.12(감수 25차 — SEL-e): SelectionContext 단수→복수 episode(selection_episode_
# id·exposure·is_question_target 기본 True=단수 시절 질문 대상 의미 보존). 후보
# identity에 selection episode 편입, episode별 CAR-SEL 소유권(mismatch의 episode 간
# 전파 금지 — 호환 episode 우선), 같은 유형 복수 episode 병존(examination_1/2),
# 결정적 병합+보완(축별 명시 값 1개) vs 명시 충돌=CONTEXT_CONFLICT(구조 보존·비노출·
# 위생 로그), 서로 다른 선발 episode 간 자동 흡수 금지. 단수 selection_context와
# [ctx]는 결과 동일(하위 호환 어댑터).
RISK_REVIEW_ENVIRONMENT_VERSION = "risk-engine-r0.5.12"


def risk_scope_hash(item: RiskItem, scope: str) -> str:
    """감수 범위별 본문 해시 — 범위별 감수 무효화 가드(감수 6차).

    범위별 해시 대상: shadow_structure=kind·룰 4종·minimumEvidence·evidenceContract·
    상태 변경 exposure 조건·적용 가능성 축(v5) / scoring=baseImpact(등급·가중 재료) /
    selection=riskFamily·relatedDomains·crossDomainEffects·specificityRank·
    absorbedRoleHint(흡수·소유권) / exposure=manifestations·claim 정책·exposurePolicy.
    결정적이며 키 순서·공백에 무관하다.
    """
    if scope == "shadow_structure":
        body: dict = {
            "kind": item.kind,
            "triggerRules": [r.model_dump(by_alias=True, exclude_none=True)
                             for r in item.trigger_rules],
            "amplifierRules": [r.model_dump(by_alias=True, exclude_none=True)
                               for r in item.amplifier_rules],
            "mitigatorRules": [r.model_dump(by_alias=True, exclude_none=True)
                               for r in item.mitigator_rules],
            "blockerRules": [r.model_dump(by_alias=True, exclude_none=True)
                             for r in item.blocker_rules],
            "minimumEvidence": item.minimum_evidence.model_dump(by_alias=True),
            "evidenceContract": (
                item.evidence_contract.model_dump(by_alias=True, exclude_none=True)
                if item.evidence_contract is not None else None
            ),
            # 상태 변경 exposurePolicy 필드 — 구조적 적격성(BLOCKED 등)을 바꾸므로
            # structure 감수 대상(v4). 관계 실질 조건(v5)도 유효 노출 상태를 바꾼다.
            "exposureEligibility": (
                {
                    "requirement": item.exposure_policy.requirement,
                    "unknownAction": item.exposure_policy.unknown_action,
                    "deniedAction": item.exposure_policy.denied_action,
                    "notApplicableAction": item.exposure_policy.not_applicable_action,
                    "fallbackRiskId": item.exposure_policy.fallback_risk_id,
                    "requiresFinancialTie": item.exposure_policy.requires_financial_tie,
                    "requiresSharedResponsibility": (
                        item.exposure_policy.requires_shared_responsibility
                    ),
                    "requiresRepairResponsibility": (
                        item.exposure_policy.requires_repair_responsibility
                    ),
                    "requiresCommuteDependency": (
                        item.exposure_policy.requires_commute_dependency
                    ),
                    "requiresVehicleExposure": (
                        item.exposure_policy.requires_vehicle_exposure
                    ),
                    "requiresExistingDispute": (
                        item.exposure_policy.requires_existing_dispute
                    ),
                    "requiresExistingLitigation": (
                        item.exposure_policy.requires_existing_litigation
                    ),
                    "requiresExistingCondition": (
                        item.exposure_policy.requires_existing_condition
                    ),
                    "requiresTreatmentProcess": (
                        item.exposure_policy.requires_treatment_process
                    ),
                    "requiresRecoveryProcess": (
                        item.exposure_policy.requires_recovery_process
                    ),
                    "requiresPhysicalDemand": (
                        item.exposure_policy.requires_physical_demand
                    ),
                }
                if item.exposure_policy is not None else None
            ),
            # 적용 가능성 축(v5·v6) — MISMATCHED→BLOCKED의 재료(축 변경=구조 재감수).
            "applicability": {
                "selectionModes": sorted(item.applicable_selection_modes),
                "selectionStages": sorted(item.applicable_selection_stages),
                "targetTypes": sorted(item.applicable_target_types),
                "relationshipRoles": sorted(item.applicable_relationship_roles),
                "mobilityTargetTypes": sorted(item.applicable_mobility_target_types),
                "mobilityStages": sorted(item.applicable_mobility_stages),
                "healthContextTypes": sorted(item.applicable_health_context_types),
                "legalTargetTypes": sorted(item.applicable_legal_target_types),
                "legalStages": sorted(item.applicable_legal_stages),
            },
        }
    elif scope == "scoring":
        body = {"baseImpact": item.base_impact}
    elif scope == "selection":
        body = {
            "riskFamily": item.risk_family,
            "relatedDomains": sorted(item.related_domains),
            "crossDomainEffects": sorted(item.cross_domain_effects),
            "specificityRank": item.specificity_rank,
            "absorbedRoleHint": item.absorbed_role_hint,  # 흡수 역할(v5)
        }
    elif scope == "exposure":
        body = {
            "manifestations": [m.model_dump(by_alias=True) for m in item.manifestations],
            "prohibitedClaims": sorted(item.prohibited_claims),
            "allowedClaimScope": sorted(item.allowed_claim_scope),
            "claimCeiling": item.claim_ceiling,
            "exposurePolicy": (
                item.exposure_policy.model_dump(by_alias=True, exclude_none=True)
                if item.exposure_policy is not None else None
            ),
        }
    else:
        raise ValueError(f"미지원 감수 범위: {scope}")
    canonical = json.dumps(
        {"hashSchemaVersion": _RISK_HASH_SCHEMA_VERSION, "scope": scope, "body": body},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def risk_rule_hash(item: RiskItem) -> str:
    """shadow_structure 범위 해시(하위 호환 별칭)."""
    return risk_scope_hash(item, "shadow_structure")


class RiskMappingFile(_AliasModel):
    version: str
    domain: str
    items: list[RiskItem]


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
    "direction_suggestions.json": DirectionSuggestionDict,
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
# risks/<domain>.json — 위험 이벤트 사전(RISK_ENGINE.md, EventKeyV2와 별도 risk_id 네임스페이스).
_RISK_MAPPING_DIR = "risks"


def schema_for(rel_path: str) -> type[BaseModel] | None:
    """상대 경로에 해당하는 스키마를 찾는다. 미등록 경로는 None."""
    if rel_path in SCHEMA_BY_PATH:
        return SCHEMA_BY_PATH[rel_path]
    parent = str(Path(rel_path).parent)
    if parent == _EVENT_MAPPING_DIR:
        return EventMappingFile
    if parent == _RISK_MAPPING_DIR:
        return RiskMappingFile
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


def _lint_risk_mapping(rel: str, file: RiskMappingFile) -> list[str]:
    """risks/<domain>.json 충돌 검사.

    - 파일 domain과 항목 domain 불일치 / risk_id 접두 규약 위반(파일 간 충돌 차단).
    - 같은 파일 안 risk_id 중복, 항목 안 룰 id 중복(역할 전체 통합).
    - incident_risk인데(evidenceContract 부재 시) independent_source_count < 2 — 신호
      1개 사건 위험 범람 방지. evidenceContract가 있으면 그 계약이 개수 조건을 대신한다.
    - requiredGroups/evidenceContract 절이 trigger 룰 group에 없으면 충족 불가능 항목.
    - 감수 승격(reviewed:true) 게이트 — kind별 최소 계약(2026-07-15 감수 2차):
      incident_risk = (event_shape+target_activation) 또는 targeted_event_shape 경로 +
      generic trigger 금지 / pressure = 비generic trigger 1개 이상 / vulnerability =
      target_activation·targeted_event_shape 또는 event_shape 1개 이상.
    - manifestation 문구가 prohibitedClaims와 충돌하면 실패. 건강·법률 incident_risk는
      승격 시 claimCeiling + allowedClaimScope 필수(건강은 conditional_warning 이하).
    """
    errors: list[str] = []
    prefix = _RISK_ID_PREFIX.get(file.domain)
    if prefix is None:
        errors.append(f"{rel}: 파일 domain 값 오류 — {file.domain}")
        return errors
    seen_ids: set[str] = set()
    for item in file.items:
        if item.domain != file.domain:
            errors.append(f"{rel}: 항목 domain({item.domain}) ≠ 파일 domain — {item.risk_id}")
        if not item.risk_id.startswith(prefix):
            errors.append(f"{rel}: risk_id 접두 규약 위반({prefix}*) — {item.risk_id}")
        if item.risk_id in seen_ids:
            errors.append(f"{rel}: risk_id 중복 — {item.risk_id}")
        seen_ids.add(item.risk_id)
        rule_ids = [
            r.id
            for rules in (
                item.trigger_rules, item.amplifier_rules,
                item.mitigator_rules, item.blocker_rules,
            )
            for r in rules
        ]
        if len(rule_ids) != len(set(rule_ids)):
            errors.append(f"{rel}: 룰 id 중복 — {item.risk_id}")
        if (
            item.kind == "incident_risk"
            and item.evidence_contract is None
            and item.minimum_evidence.independent_source_count < 2
        ):
            errors.append(
                f"{rel}: incident_risk는 독립 출처 2개 이상 필요"
                f"(또는 evidenceContract 저작) — {item.risk_id}"
            )
        trigger_groups = {r.group for r in item.trigger_rules}
        for g in item.minimum_evidence.required_groups:
            if g not in trigger_groups:
                errors.append(
                    f"{rel}: requiredGroups({g})를 만족할 trigger 룰 없음(충족 불가) — "
                    f"{item.risk_id}"
                )
        if item.evidence_contract is not None and not any(
            set(clause.all_of_groups) <= trigger_groups
            for clause in item.evidence_contract.any_of
        ):
            errors.append(
                f"{rel}: evidenceContract의 어떤 절도 trigger 룰 group으로 충족 불가 — "
                f"{item.risk_id}"
            )
        # manifestation ↔ prohibitedClaims 충돌(기계 검사 가능한 substring 수준).
        for m in item.manifestations:
            for banned in item.prohibited_claims:
                if banned and banned in m.ko:
                    errors.append(
                        f"{rel}: manifestation({m.id})이 prohibitedClaims와 충돌 — "
                        f"{item.risk_id}"
                    )
        if item.reviewed:
            errors.extend(_lint_reviewed_risk_item(rel, item, trigger_groups))
        elif item.review_scopes:
            errors.append(
                f"{rel}: reviewed:false인데 reviewScopes 기록 존재(불일치) — {item.risk_id}"
            )
    return errors


def _lint_reviewed_risk_item(
    rel: str, item: RiskItem, trigger_groups: set[str]
) -> list[str]:
    """감수 승격(reviewed:true) 항목의 kind별 최소 계약 게이트(2026-07-15 감수 2차).

    기신·공망·운성·불리 극성만으로는 pressure의 증폭, vulnerability의 보조 근거는 될 수
    있어도 incident_risk의 직접 trigger는 될 수 없다 — 승격 시점에 강제한다.
    """
    errors: list[str] = []
    if not item.review_scopes:
        errors.append(
            f"{rel}: reviewed:true는 reviewScopes 명시 필수(shadow_structure 등 — "
            f"사용자 노출 승인과 구분) — {item.risk_id}"
        )
    if item.review_pending is not None:
        errors.append(
            f"{rel}: reviewed:true와 reviewPending 동시 존재 금지(재감수 대기 항목은 "
            f"강등 상태여야 함) — {item.risk_id}"
        )
    if item.review_environment_version != RISK_REVIEW_ENVIRONMENT_VERSION:
        errors.append(
            f"{rel}: 엔진 의미론 버전 불일치(감수 당시 "
            f"{item.review_environment_version} ≠ 현재 "
            f"{RISK_REVIEW_ENVIRONMENT_VERSION}) — 재감수 필요 — {item.risk_id}"
        )
    for scope in item.review_scopes:
        if scope not in item.review_versions:
            errors.append(
                f"{rel}: reviewScope({scope})에 reviewVersion 누락 — {item.risk_id}"
            )
        stamped = item.review_hashes.get(scope)
        if stamped is None:
            errors.append(
                f"{rel}: reviewScope({scope})에 reviewHash 누락(감수 무효화 가드) — "
                f"{item.risk_id}"
            )
        elif stamped != risk_scope_hash(item, scope):
            errors.append(
                f"{rel}: {scope} 본문이 감수 이후 변경됨(해시 불일치 — 재감수 후 "
                f"재스탬프 필요) — {item.risk_id}"
            )
    non_generic = trigger_groups - {"generic"}
    if item.kind == "incident_risk":
        required = set(item.minimum_evidence.required_groups)
        contract_ok = item.evidence_contract is not None and all(
            ("targeted_event_shape" in set(clause.all_of_groups))
            or ({"event_shape", "target_activation"} <= set(clause.all_of_groups))
            for clause in item.evidence_contract.any_of
        )
        groups_ok = {"event_shape", "target_activation"} <= required
        if not (contract_ok or groups_ok):
            errors.append(
                f"{rel}: 감수 승격 incident_risk는 (event_shape+target_activation) 또는 "
                f"targeted_event_shape 증거 계약 필수 — {item.risk_id}"
            )
        if "generic" in trigger_groups:
            errors.append(
                f"{rel}: 감수 승격 incident_risk에 generic 그룹 trigger 금지 — "
                f"{item.risk_id}"
            )
        if item.domain in ("health_safety", "contract_legal"):
            if item.claim_ceiling is None or not item.allowed_claim_scope:
                errors.append(
                    f"{rel}: 감수 승격 건강·법률 incident_risk는 claimCeiling·"
                    f"allowedClaimScope 필수 — {item.risk_id}"
                )
            if item.domain == "health_safety" and item.claim_ceiling == "warning":
                errors.append(
                    f"{rel}: 건강 incident_risk의 claimCeiling은 conditional_warning "
                    f"이하 — {item.risk_id}"
                )
    elif item.kind == "pressure":
        if not non_generic:
            errors.append(
                f"{rel}: 감수 승격 pressure는 비generic trigger(도메인 관련 activation "
                f"등) 1개 이상 필요 — {item.risk_id}"
            )
    elif item.kind == "vulnerability":
        if not non_generic & {"target_activation", "targeted_event_shape",
                              "structural_weakness"}:
            errors.append(
                f"{rel}: 감수 승격 vulnerability는 구체적 대상 활성(target_activation) "
                f"또는 구조적 약화(structural_weakness) trigger 필요 — {item.risk_id}"
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


_CONFLICT_KINDS = ("충", "형", "파", "해")


def _lint_suggestion_condition(
    where: str, cond: SuggestionCondition, valid_patterns: set[str] | None
) -> list[str]:
    """direction_suggestions 조건 1건의 enum·교차참조 유효성 검사."""
    errors: list[str] = []
    rel = "direction_suggestions.json"
    groups = {g.value for g in TenGodGroup}
    ten_gods = {t.value for t in _TenGodRoman}
    bands = {b.value for b in StrengthBand}
    if cond.group is not None and cond.group not in groups:
        errors.append(f"{rel}: {where} 미지원 십성군 — {cond.group}")
    for t in cond.ten_gods:
        if t not in ten_gods:
            errors.append(f"{rel}: {where} 미지원 십성 — {t}")
    if cond.target is not None and cond.target not in ten_gods | groups:
        errors.append(f"{rel}: {where} yongsin_role target 미지원 — {cond.target}")
    for r in cond.roles:
        if r not in _FAVORABILITY:
            errors.append(f"{rel}: {where} 미지원 용신 역할 — {r}")
    for b in cond.bands:
        if b not in bands:
            errors.append(f"{rel}: {where} 미지원 신강약 밴드 — {b}")
    for c in cond.conflict_kinds:
        if c not in _CONFLICT_KINDS:
            errors.append(f"{rel}: {where} 미지원 충파 종류 — {c}")
    if valid_patterns is not None:
        for pid in cond.pattern_ids:
            if pid not in valid_patterns:
                errors.append(f"{rel}: {where} 미등록 구조패턴 — {pid}")
    return errors


def _lint_direction_rule(
    rule: DirectionRule, valid_patterns: set[str] | None
) -> list[str]:
    """direction_suggestions 룰 1건 — 내부 id 중복·다요소 축·guard/caution 짝 검사."""
    errors: list[str] = []
    rel = "direction_suggestions.json"
    rid = rule.suggestion_id
    if rule.group not in {g.value for g in TenGodGroup}:
        errors.append(f"{rel}: {rid} 미지원 십성군 — {rule.group}")
    conditions: list[tuple[str, SuggestionCondition]] = [
        (f"{rid}.trigger", c) for c in rule.trigger
    ]
    seen_channels: set[str] = set()
    trigger_kinds = {c.kind for c in rule.trigger}
    for ch in rule.channels:
        if ch.channel_id in seen_channels:
            errors.append(f"{rel}: {rid} 중복 channel_id — {ch.channel_id}")
        seen_channels.add(ch.channel_id)
        conditions.extend((f"{rid}.{ch.channel_id}", c) for c in ch.conditions)
        # 다요소 원칙(설계 §4): trigger+channel 조건 축(kind) 2종 이상 — 십성 단독 판정 금지.
        if len(trigger_kinds | {c.kind for c in ch.conditions}) < 2:
            errors.append(f"{rel}: {rid}.{ch.channel_id} 조건 축 1종 — 다요소 원칙 위반")
    seen_guards: set[str] = set()
    for g in rule.guards:
        if g.guard_id in seen_guards:
            errors.append(f"{rel}: {rid} 중복 guard_id — {g.guard_id}")
        seen_guards.add(g.guard_id)
        conditions.extend((f"{rid}.guard.{g.guard_id}", c) for c in g.conditions)
    conditions.extend((f"{rid}.support", s.condition) for s in rule.supports)
    if rule.guards and not rule.caution_headline:
        errors.append(f"{rel}: {rid} guards 존재하나 caution_headline 비어 있음")
    if len(rule.llm_tag) > 120:
        errors.append(f"{rel}: {rid} llm_tag {len(rule.llm_tag)}자(>120)")
    for where, cond in conditions:
        errors.extend(_lint_suggestion_condition(where, cond, valid_patterns))
    return errors


def _lint_direction_suggestions(
    directory: Path, file: DirectionSuggestionDict
) -> list[str]:
    """direction_suggestions.json — 중복 id·enum 유효성·구조패턴 교차참조 검사."""
    errors: list[str] = []
    rel = "direction_suggestions.json"
    valid_patterns: set[str] | None = None
    sp_path = directory / "structure_patterns.json"
    if sp_path.exists():
        try:
            sp = StructurePatternDict.model_validate(
                json.loads(sp_path.read_text(encoding="utf-8"))
            )
            valid_patterns = {p.pattern_id for p in sp.patterns}
        except (json.JSONDecodeError, ValidationError):
            valid_patterns = None  # structure_patterns 자체 위반은 별도 보고
    seen: set[str] = set()
    for rule in file.rules:
        if rule.suggestion_id in seen:
            errors.append(f"{rel}: 중복 suggestion_id — {rule.suggestion_id}")
        seen.add(rule.suggestion_id)
        errors.extend(_lint_direction_rule(rule, valid_patterns))
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
        elif isinstance(parsed, DirectionSuggestionDict):
            errors.extend(_lint_direction_suggestions(directory, parsed))
        elif isinstance(parsed, EventMappingFile):
            errors.extend(_lint_event_mapping(rel, parsed))
        elif isinstance(parsed, RiskMappingFile):
            errors.extend(_lint_risk_mapping(rel, parsed))
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
