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

from saju_shared_types.events import EventKey, EventPolarity, EventType

_FAVORABILITY = ("용신", "희신", "기신", "구신", "한신")
_POSITIVE_FAVORABILITY = ("용신", "희신")
_NEGATIVE_FAVORABILITY = ("기신", "구신")
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
    event_domains: list[EventKey] = Field(alias="eventDomains")
    base_score: float = Field(alias="baseScore", ge=0.0, le=1.0)
    reviewed: bool

    @model_validator(mode="after")
    def _fixed_or_pattern(self) -> RelationItem:
        if not self.participants and self.pattern is None:
            raise ValueError(f"{self.id}: participants가 비면 pattern 설명이 필요함")
        return self


# ── events/ ──────────────────────────────────────────────────────


class TaxonomyItem(_AliasModel):
    """이벤트 분류 항목 (events/taxonomy.json)."""

    event_key: EventKey = Field(alias="eventKey")
    ko: str
    event_type: EventType = Field(alias="eventType")
    reviewed: bool


class SignalSpec(_AliasModel):
    """신호 조건 (events/<domain>.json). 키 중 최소 1개는 지정해야 한다."""

    ten_god: str | None = Field(default=None, alias="tenGod")
    relation: str | None = None
    favorability: str | None = None
    shinsal: str | None = None
    daewoon_transition: bool | None = Field(default=None, alias="daewoonTransition")

    @model_validator(mode="after")
    def _non_empty(self) -> SignalSpec:
        if not any(
            v is not None
            for v in (
                self.ten_god, self.relation, self.favorability,
                self.shinsal, self.daewoon_transition,
            )
        ):
            raise ValueError("signal은 최소 1개 조건을 가져야 함")
        if self.favorability is not None and self.favorability not in _FAVORABILITY:
            raise ValueError(f"favorability 값 오류: {self.favorability}")
        return self

    def key(self) -> str:
        """신호 동일성 비교용 안정 키."""
        return json.dumps(self.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True)


class EventCandidateSpec(_AliasModel):
    """신호가 유발하는 이벤트 후보 (사전 점수는 0~1)."""

    event: EventKey
    score: float = Field(ge=0.0, le=1.0)
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


# 상대 경로 → 스키마. 새 사전 추가 시 여기 등록해야 검증된다(미등록은 generic 검사만).
SCHEMA_BY_PATH: dict[str, type[BaseModel]] = {
    "common/stems.json": StemsFile,
    "common/branches.json": BranchesFile,
    "common/ten_gods.json": TenGodsFile,
    "common/elements.json": ElementsFile,
    "relations.json": RelationsFile,
    "events/taxonomy.json": TaxonomyFile,
    "favorability_rules.json": FavorabilityRulesFile,
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
    for path in sorted(directory.rglob("*.json")):
        rel = str(path.relative_to(directory))
        schema = schema_for(rel)
        if schema is None:
            continue  # 미등록 사전은 generic 검사(스크립트)만 적용
        try:
            schema.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"{rel}: 스키마 위반 — {exc}")
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
    return errors
