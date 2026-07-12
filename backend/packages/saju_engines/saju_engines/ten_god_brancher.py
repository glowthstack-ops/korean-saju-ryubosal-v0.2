"""TenGodEventBrancher (Phase 2) — 운 십성 조합으로 사건 '타입' 후보를 생성한다.

사양 transit_ten_god_branching.v1(단일·그룹·특정 조합) + addendum.v1(3중 그룹 조합)을 적용한다.
addendum의 transit_source_strength(천간/지지 본기/천간·지지 동일 계열 배율)를 신호 강도로
반영한다 — 규칙 점수 = 기본점수 × 기여 십성 강도의 산술평균(신호 개수 보너스 없음).
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


class _SourceStrengthEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    score_multiplier: float


class _SourceStrength(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_types: dict[str, _SourceStrengthEntry] = {}

    def multiplier(self, key: str, default: float) -> float:
        """source_types의 배율을 조회한다(사전에 없으면 사양 기본값)."""
        entry = self.source_types.get(key)
        return entry.score_multiplier if entry is not None else default


class _AddendumFile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    three_god_combination_rules: list[_ThreeGodRule] = []
    transit_source_strength: _SourceStrength = _SourceStrength()


@dataclass
class TransitSignal:
    """운에서 들어온 십성 1건.

    strength는 출처별 사건화 강도(transit_source_strength) — 천간 1.0, 지지 본기 0.9,
    천간·지지 본기가 같은 십성군이면 두 신호 모두 동일계열 집중 배율(1.25).
    """

    ten_god: TenGod
    layer: LuckLayer
    source: str  # 'stem' | 'branch_main' | 'branch_mid' | 'branch_initial'
    strength: float = 1.0
    same_group: bool = False  # 같은 기둥의 천간·지지 본기가 동일 십성군
    same_god: bool = False  # 나아가 십성까지 완전 동일(설명 태그용 — 배율은 동일)

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
    src_strength: float = 1.0  # 채택(MAX) 규칙의 출처 강도 배율 — 추적용


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
        # 출처별 사건화 강도 — 사전(transit_source_strength)에서 로드(하드코딩 금지).
        # 지장간 중기·여기 배율(0.55/0.35)은 신호 수집 자체가 본기까지라 이번 범위 밖.
        ss = addendum.transit_source_strength
        self._mult_stem = ss.multiplier("stem", 1.0)
        self._mult_branch = ss.multiplier("branch_main_qi", 0.9)
        self._mult_same_group = ss.multiplier("stem_branch_same_god", 1.25)

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ── 신호 수집 ─────────────────────────────────────────────────

    def collect_from_pillar(
        self, pillar: LuckPillar, layer: LuckLayer, is_target: bool = True,
    ) -> list[TransitSignal]:
        """운 기둥의 천간·지지(본기) 십성을 강도(strength) 포함 신호로 변환한다.

        천간=1.0, 지지 본기=0.9. 천간·지지 본기가 같은 십성군이면(운 간여지동 — 丙午·壬子처럼
        정·편이 갈려도 계열이 같으면 성립) 두 신호 모두 동일계열 집중 배율(1.25)로 대체한다.
        판정은 지지 본기만 사용하고 중기·여기로 확장하지 않는다(지장간은 후속 강도 보정).

        동일계열 집중은 해당 운 기간 자체의 특성이므로 채점 대상 기둥(is_target)에만 적용한다.
        배경 운층(거버닝 스택의 상위 운, 예: 월운 채점 시의 세운·대운)에 적용하면 그 층의
        간여지동이 하위 기간 전체를 일괄 증폭해 기간 간 변별(교운 가중 등 실측 랭킹)이 깨진다.
        """
        out: list[TransitSignal] = []
        stem = TEN_GOD_KO_TO_KEY.get(pillar.stem_ten_god)
        branch = TEN_GOD_KO_TO_KEY.get(pillar.branch_ten_god)
        same_group = (
            is_target
            and stem is not None and branch is not None
            and TEN_GOD_GROUP[stem] == TEN_GOD_GROUP[branch]
        )
        same_god = same_group and stem == branch
        if stem is not None:
            out.append(TransitSignal(
                stem, layer, "stem",
                strength=self._mult_same_group if same_group else self._mult_stem,
                same_group=same_group, same_god=same_god,
            ))
        if branch is not None:
            out.append(TransitSignal(
                branch, layer, "branch_main",
                strength=self._mult_same_group if same_group else self._mult_branch,
                same_group=same_group, same_god=same_god,
            ))
        return out

    # ── 분기 ──────────────────────────────────────────────────────

    def branch(self, signals: list[TransitSignal], period: str) -> list[EventCandidateV2]:
        """십성 신호 → 사건 타입 후보. 룰별 점수의 최댓값을 채택하고 reason_codes로 추적한다.

        규칙 점수에는 기여 십성 강도(출처 배율)의 산술평균을 곱한다 — 천간 유래는 유지,
        지지 본기 단독 유래는 감쇠(0.9), 운 간여지동(동일 십성군)은 증폭(1.25).
        신호 개수에 따른 별도 보너스는 두지 않는다(점수 포화 방지 원칙).
        """
        present_gods = {s.ten_god for s in signals}
        present_groups = {s.group for s in signals}
        # 십성별 강도 — 같은 십성이 여러 층·출처로 들어오면 최댓값 채택.
        strength: dict[TenGod, float] = {}
        for s in signals:
            strength[s.ten_god] = max(strength.get(s.ten_god, 0.0), s.strength)
        acc: dict[EventKeyV2, _Acc] = {}

        def factor(gods: set[TenGod]) -> float:
            return (
                sum(strength.get(g, 1.0) for g in gods) / len(gods) if gods else 1.0
            )

        def add(ev: _BaseEvent, rule_id: str, gods: set[TenGod]) -> None:
            # 조건부(branch) 후보는 Phase 6 이후 평가 — 여기선 무조건 후보만.
            if ev.condition:
                return
            f = factor(gods)
            eff = round(ev.score * f)
            a = acc.setdefault(ev.event, _Acc())
            if eff > a.score:
                a.score = eff
                a.quality = ev.quality or a.quality
                a.src_strength = f
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
        # 운 간여지동 설명 태그 — 배율은 동일(1.25), 甲寅류(십성까지 일치)만 구분 표기.
        same_group_gods = {s.ten_god for s in signals if s.same_group}
        same_god_gods = {s.ten_god for s in signals if s.same_god}
        out: list[EventCandidateV2] = []
        for event_key, a in acc.items():
            base = max(0, a.score)
            reasons = list(a.reasons)
            if a.ten_gods & same_god_gods:
                reasons.append("SRC_SAME_GOD")
            elif a.ten_gods & same_group_gods:
                reasons.append("SRC_SAME_GROUP")
            out.append(EventCandidateV2(
                event_key=event_key,
                period=period,
                score=base,  # 십성 base(MAX×출처배율) — 이후 모디파이어가 누적, 최종 soft_cap
                source_layers=layers,
                source_ten_gods=sorted(a.ten_gods, key=lambda g: list(TenGod).index(g)),
                reason_codes=reasons,
                raw_score=float(base),
                contributions={"base": float(base), "src_strength": a.src_strength},
            ))
        return sorted(out, key=lambda c: -c.score)
