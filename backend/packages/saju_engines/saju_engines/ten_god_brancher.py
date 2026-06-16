"""TenGodEventBrancher (Phase 2) — 운 십성 조합으로 사건 '타입' 후보를 생성한다.

사양 transit_ten_god_branching.v1(단일·그룹·특정 조합) + addendum.v1(3중 그룹 조합)을 적용한다.
12운성·합충형파해·궁성·용신 품질·게이트는 후속 계층(Phase 3~6)에서 본 후보를 보정한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    TEN_GOD_KO_TO_KEY,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    TenGod,
    TenGodGroup,
)
from saju_shared_types.luck import LuckPillar

# ── 사전 로더 모델(lenient — 모델 외 필드는 무시) ─────────────────


class _BaseEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    event: EventKeyV2
    score: int
    quality: str | None = None
    condition: str | None = None


class _SingleRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    incoming: TenGod
    base_events: list[_BaseEvent]


class _GroupRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    groups: list[TenGodGroup]
    primary_events: list[_BaseEvent] = []


class _SpecificRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    combination: list[TenGod]
    events: list[_BaseEvent]


class _ThreeGodRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    groups: list[TenGodGroup]
    primary_events: list[_BaseEvent] = []


class _BranchingFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    single_transit_rules: list[_SingleRule]
    group_combination_rules: list[_GroupRule]
    specific_combination_rules: list[_SpecificRule]


class _AddendumFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    three_god_combination_rules: list[_ThreeGodRule] = []


@dataclass
class TransitSignal:
    """운에서 들어온 십성 1건."""

    ten_god: TenGod
    layer: LuckLayer
    source: str  # 'stem' | 'branch_main' | 'branch_mid' | 'branch_initial'

    @property
    def group(self) -> TenGodGroup:
        return TEN_GOD_GROUP[self.ten_god]


@dataclass
class _Acc:
    """이벤트별 후보 누적."""

    score: int = 0
    quality: str | None = None
    reasons: list[str] = field(default_factory=list)
    ten_gods: set[TenGod] = field(default_factory=set)


class TenGodEventBrancher:
    """십성 조합 → 사건 타입 후보(EventCandidateV2)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """event_engine/ 사전을 로드해 룰을 인덱싱한다."""
        d = dictionaries_dir / "event_engine"
        branching = _BranchingFile.model_validate(self._read(d / "transit_ten_god_branching.json"))
        addendum = _AddendumFile.model_validate(
            self._read(d / "transit_ten_god_branching_addendum.json")
        )
        self._single: dict[TenGod, _SingleRule] = {
            r.incoming: r for r in branching.single_transit_rules
        }
        self._group: list[tuple[frozenset[TenGodGroup], _GroupRule]] = [
            (frozenset(r.groups), r) for r in branching.group_combination_rules
        ]
        self._specific: list[tuple[frozenset[TenGod], _SpecificRule]] = [
            (frozenset(r.combination), r) for r in branching.specific_combination_rules
        ]
        self._three: list[tuple[frozenset[TenGodGroup], _ThreeGodRule]] = [
            (frozenset(r.groups), r) for r in addendum.three_god_combination_rules
        ]

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ── 신호 수집 ─────────────────────────────────────────────────

    @staticmethod
    def collect_from_pillar(pillar: LuckPillar, layer: LuckLayer) -> list[TransitSignal]:
        """운 기둥의 천간·지지(본기) 십성을 신호로 변환한다(지장간 중기·여기는 후속 강도 보정)."""
        out: list[TransitSignal] = []
        stem = TEN_GOD_KO_TO_KEY.get(pillar.stem_ten_god)
        branch = TEN_GOD_KO_TO_KEY.get(pillar.branch_ten_god)
        if stem is not None:
            out.append(TransitSignal(stem, layer, "stem"))
        if branch is not None:
            out.append(TransitSignal(branch, layer, "branch_main"))
        return out

    # ── 분기 ──────────────────────────────────────────────────────

    def branch(self, signals: list[TransitSignal], period: str) -> list[EventCandidateV2]:
        """십성 신호 → 사건 타입 후보. 룰별 점수의 최댓값을 채택하고 reason_codes로 추적한다."""
        present_gods = {s.ten_god for s in signals}
        present_groups = {s.group for s in signals}
        acc: dict[EventKeyV2, _Acc] = {}

        def add(ev: _BaseEvent, rule_id: str, gods: set[TenGod]) -> None:
            # 조건부(branch) 후보는 Phase 6 이후 평가 — 여기선 무조건 후보만.
            if ev.condition:
                return
            a = acc.setdefault(ev.event, _Acc())
            if ev.score > a.score:
                a.score = ev.score
                a.quality = ev.quality or a.quality
            a.reasons.append(rule_id)
            a.ten_gods |= gods

        # 단일 십성
        for god in present_gods:
            srule = self._single.get(god)
            if srule:
                for ev in srule.base_events:
                    add(ev, srule.id, {god})
        # 그룹 2조합
        for groups, grule in self._group:
            if groups <= present_groups:
                gods = {s.ten_god for s in signals if s.group in groups}
                for ev in grule.primary_events:
                    add(ev, grule.id, gods)
        # 특정 십성 2조합
        for combo, sprule in self._specific:
            if combo <= present_gods:
                for ev in sprule.events:
                    add(ev, sprule.id, set(combo))
        # 3중 그룹 조합
        for groups, trule in self._three:
            if groups <= present_groups:
                gods = {s.ten_god for s in signals if s.group in groups}
                for ev in trule.primary_events:
                    add(ev, trule.id, gods)

        layers = sorted({s.layer for s in signals}, key=lambda x: list(LuckLayer).index(x))
        out: list[EventCandidateV2] = []
        for event_key, a in acc.items():
            base = max(0, a.score)
            out.append(EventCandidateV2(
                event_key=event_key,
                period=period,
                score=base,  # 십성 base(MAX) — 이후 모디파이어가 누적, 최종 단계서 soft_cap
                source_layers=layers,
                source_ten_gods=sorted(a.ten_gods, key=lambda g: list(TenGod).index(g)),
                reason_codes=a.reasons,
                raw_score=float(base),
                contributions={"base": float(base)},
            ))
        return sorted(out, key=lambda c: -c.score)
