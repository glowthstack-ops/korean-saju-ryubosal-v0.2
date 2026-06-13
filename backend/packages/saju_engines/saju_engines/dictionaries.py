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
from saju_shared_types.event_taxonomy_v2 import LEGACY_EVENT_KEY_MAP
from saju_shared_types.events import EventKey, EventPolarity, EventType

_FAVORABILITY = ("용신", "희신", "기신", "구신", "한신")
_POSITIVE_FAVORABILITY = ("용신", "희신")
_NEGATIVE_FAVORABILITY = ("기신", "구신")
# 십성군 — SignalSpec.tenGodGroupStrong 유효값(엔진 groups 키와 매핑은 스코어러 담당).
_TEN_GOD_GROUPS = ("인성", "비겁", "식상", "재성", "관성")
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
    # does_not_apply_when: 같은 기간에 이 관계들이 성립하면 룰 미적용(외부 강트리거 우선).
    absent_relations: list[str] | None = Field(default=None, alias="absentRelations")

    @model_validator(mode="after")
    def _non_empty(self) -> SignalSpec:
        if not any(
            v is not None
            for v in (
                self.ten_god, self.branch_ten_god, self.relation, self.favorability,
                self.stem_favorability, self.shinsal, self.daewoon_transition,
                self.unseong, self.natal_unseong, self.ten_god_group_strong,
                self.daewoon_branch_void,
            )
        ):
            raise ValueError("signal은 최소 1개 조건을 가져야 함")
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


# 상대 경로 → 스키마. 새 사전 추가 시 여기 등록해야 검증된다(미등록은 generic 검사만).
SCHEMA_BY_PATH: dict[str, type[BaseModel]] = {
    "common/stems.json": StemsFile,
    "common/branches.json": BranchesFile,
    "common/ten_gods.json": TenGodsFile,
    "common/elements.json": ElementsFile,
    "common/twelve_unseong_groups.json": TwelveUnseongGroupsFile,
    "common/ten_god_events.json": TenGodEventsFile,
    "relations.json": RelationsFile,
    "events/taxonomy.json": TaxonomyFile,
    "favorability_rules.json": FavorabilityRulesFile,
    "interpretations/ilju.json": IljuFile,
    "interpretations/ten_gods_text.json": TenGodsTextFile,
    "interpretations/twelve_stages_text.json": TwelveStagesTextFile,
    "interpretations/relations_text.json": RelationsTextFile,
    "interpretations/sinsal_text.json": SinsalTextFile,
    "interpretations/stems_branches_text.json": StemsBranchesTextFile,
    "interpretations/favorability_text.json": FavorabilityTextFile,
    "terminology.json": TerminologyFile,
    "templates/interpretation.json": InterpretationTemplatesFile,
    "templates/prohibited_styles.json": ProhibitedStylesFile,
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
    return errors
