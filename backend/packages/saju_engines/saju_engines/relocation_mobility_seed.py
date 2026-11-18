"""식상+관성 운 × 이동 동반 신호 → 이사·이동(relocation) 시드 (2026-11-18 데굴님 승인).

기준 회귀 사례: 2025-08 甲申월(己 일간에게 천간 정관·지지 상관) — 실제 사건은 이사. 운영 브랜처는
이사 후보를 재성이 낀 조합(재성·인성·식상)에서만 만들어 이 달에는 이사 후보가 아예 없었고, 같은
글자가 취업·이직 후보만 만들었다(doc/v2_2/EMPLOYMENT_HISTORY_CALIBRATION.md §9-1b). 사례 규칙
'정관+합+역마+식상 → 이사·이동 우선'은 사례 픽스처(cases.jsonl)와 `events/relocation.json` 에만
있고 채점에는 쓰이지 않았다.

규칙(사전 `event_engine/transit_ten_god_branching.json` → `output_authority_relocation_rules`):
  - 채점 대상 층(세운·월운)의 운 기둥이 천간·지지 본기로 식상과 관성을 한 글자씩 가져올 때만 본다.
  - 이동 동반 신호를 센다 — ① 역마(상대 12신살, 기준 자리는 공용 상수): 운 지지가 역마 글자로
    오거나, 운 지지가 원국의 역마 글자를 충·육합으로 건드림 ② 운 지지가 그 밖의 원국 지지를 충
    ③ 운 천간이 일간과 천간합이거나 운 지지가 그 밖의 원국 지지와 육합.
  - 사전의 `required_companions`(반드시 있어야 하는 신호)와 `min_companions`(최소 개수)를 채우면
    relocation 후보 1건을 만든다. 기준점은 동반 신호 개수로 나눈다.
  - 십성만으로 이사를 만들지 않는다(사전 event_gate_rules.relocation 의 주의 문구와 같은 원칙).
길흉·충합·궁성·12운성 보정과 사건 간 충돌 해결은 뒤 계층이 그대로 적용한다(브랜처 직후 합류).
규칙 기반이며 LLM 판정을 쓰지 않는다(절대원칙 1). 점수 상수는 사전에서 읽는다(하드코딩 금지).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import BRANCH_CLASHES, SIX_COMBINATIONS, STEM_COMBINATIONS
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
)
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.twelve_sinsal import self_sinsal_bases

from .ten_god_brancher import TransitSignal

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
SECTION = "output_authority_relocation_rules"
COMPANION_YEOKMA = "yeokma"
COMPANION_CLASH = "clash"
COMPANION_HAP = "hap"
_COMPANION_ORDER = (COMPANION_YEOKMA, COMPANION_CLASH, COMPANION_HAP)


@dataclass(frozen=True)
class RelocationMobilityRule:
    """사전 `output_authority_relocation_rules` 1건."""

    rule_id: str
    incoming_groups: frozenset[str]
    layers: frozenset[LuckLayer]
    event: EventKeyV2
    required_companions: frozenset[str]
    min_companions: int
    base_by_companions: dict[int, int]
    companion_reason_codes: dict[str, str]
    event_candidate_threshold: int
    theme_only_threshold: int


@lru_cache(maxsize=8)
def load_relocation_mobility_rule(
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> RelocationMobilityRule | None:
    """브랜처 사전에서 규칙 절을 읽는다(절이 없으면 None — 시드 비활성)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get(SECTION)
    if not raw:
        return None
    thresholds = data.get("activation_thresholds", {})
    return RelocationMobilityRule(
        rule_id=str(raw["id"]),
        incoming_groups=frozenset(raw["incoming_groups"]),
        layers=frozenset(LuckLayer(x) for x in raw["layers"]),
        event=EventKeyV2(raw["event"]),
        required_companions=frozenset(raw.get("required_companions", [])),
        min_companions=int(raw["min_companions"]),
        base_by_companions={int(k): int(v) for k, v in raw["base_by_companions"].items()},
        companion_reason_codes=dict(raw.get("companion_reason_codes", {})),
        event_candidate_threshold=int(thresholds.get("event_candidate", 55)),
        theme_only_threshold=int(thresholds.get("theme_only", 35)),
    )


def _natal_branches(result: ManseV2Result) -> list[Branch]:
    """원국 지지(시주 미상이면 세 자리)."""
    pillars = result.pillars
    if pillars is None:
        return []
    out: list[Branch] = []
    for p in (pillars.year, pillars.month, pillars.day, pillars.hour):
        if p is not None and getattr(p, "branch", None):
            out.append(Branch(p.branch))
    return out


def mobility_companions(target: LuckPillar, result: ManseV2Result) -> list[str]:
    """운 기둥이 이 명식에 만드는 이동 동반 신호 — 'yeokma'·'clash'·'hap' 중 성립한 것(고정 순서).

    역마는 글자살(寅申巳亥 보유)이 아니라 상대 12신살로 판정하고, 기준 자리는 공용 상수
    (`self_sinsal_bases` — 일지)를 따른다. 역마 동반은 두 갈래다 — 운 지지가 역마 글자로 오거나
    (도래), 운 지지가 원국의 역마 글자를 충·육합으로 건드리거나(활성화: 기준 회귀 사례는 원국 시지
    巳가 역마이고 申월이 巳申 육합으로 건드렸다). 같은 관계를 두 이름으로 세지 않는다 — 역마
    글자와의 충·육합은 역마로만 세고, 충·합은 그 밖의 원국 지지와의 관계(합은 일간과의 천간합
    포함)만 센다.
    """
    pillars = result.pillars
    if pillars is None:
        return []
    from .relationship_relative_sinsal import get_relative_sinsal

    branch, stem = Branch(target.branch), Stem(target.stem)
    natal = _natal_branches(result)
    yeokma_glyphs: set[Branch] = set()
    for _slot, _label, base in self_sinsal_bases(
        pillars.year.branch if pillars.year is not None else None,
        pillars.day.branch if pillars.day is not None else None,
    ):
        yeokma_glyphs |= {
            b for b in Branch if get_relative_sinsal(Branch(base), b).sinsal == "역마살"
        }

    def clashes(b: Branch) -> bool:
        return b != branch and frozenset({branch, b}) in BRANCH_CLASHES

    def combines(b: Branch) -> bool:
        return b != branch and frozenset({branch, b}) in SIX_COMBINATIONS

    found: set[str] = set()
    natal_yeokma = [b for b in natal if b in yeokma_glyphs]
    if branch in yeokma_glyphs or any(clashes(b) or combines(b) for b in natal_yeokma):
        found.add(COMPANION_YEOKMA)
    others = [b for b in natal if b not in yeokma_glyphs]
    if any(clashes(b) for b in others):
        found.add(COMPANION_CLASH)
    day_stem = Stem(pillars.day.stem)
    if (
        (stem != day_stem and frozenset({stem, day_stem}) in STEM_COMBINATIONS)
        or any(combines(b) for b in others)
    ):
        found.add(COMPANION_HAP)
    return [c for c in _COMPANION_ORDER if c in found]


def produce_relocation_mobility_seeds(
    signals: list[TransitSignal],
    target_layer: LuckLayer,
    target: LuckPillar,
    result: ManseV2Result,
    period: str,
    rule: RelocationMobilityRule | None,
) -> list[EventCandidateV2]:
    """식상+관성 운 기둥 × 이동 동반 신호 → relocation 시드(0 또는 1건).

    Args:
        signals: 거버닝 스택에서 수집한 운 십성 신호 전체(층위 포함).
        target_layer: 이번 채점 대상 층 — 규칙의 layers 에 들어야 한다.
        target: 채점 대상 운 기둥(천간·지지).
        result: 만세 결과(원국 지지·일간·역마 기준 자리).
        period: 시점 라벨.
        rule: 사전 규칙(None 이면 빈 목록).
    """
    if rule is None or target_layer not in rule.layers or result.pillars is None:
        return []
    own = [
        s for s in signals
        if s.layer is target_layer and s.source in ("stem", "branch_main")
        and TEN_GOD_GROUP.get(s.ten_god) is not None
    ]
    by_source = {s.source: TEN_GOD_GROUP[s.ten_god].value for s in own}
    if len(by_source) < 2 or set(by_source.values()) != set(rule.incoming_groups):
        return []
    companions = mobility_companions(target, result)
    if not rule.required_companions <= set(companions):
        return []
    if len(companions) < rule.min_companions:
        return []
    score = rule.base_by_companions.get(len(companions), 0)
    if score <= 0:
        return []
    if score >= rule.event_candidate_threshold:
        confidence = ConfidenceLevel.EVENT_CANDIDATE
    elif score >= rule.theme_only_threshold + 10:
        confidence = ConfidenceLevel.WEAK_EVENT_CANDIDATE
    else:
        confidence = ConfidenceLevel.THEME_ONLY
    reasons = [rule.rule_id]
    for c in companions:
        code = rule.companion_reason_codes.get(c)
        if code:
            reasons.append(code)
    stack_layers = sorted({s.layer for s in signals}, key=lambda x: list(LuckLayer).index(x))
    return [EventCandidateV2(
        event_key=rule.event,
        period=period,
        score=score,
        confidence_level=confidence,
        # 극성 자리표시 — 뒤 계층 `_period_role` 이 시점 유입 오행의 용기신 역할로 덮어쓴다.
        polarity_role=PolarityRole.NEUTRAL,
        source_layers=stack_layers or [target_layer],
        candidate_source_layers=[target_layer.value],
        source_ten_gods=sorted({s.ten_god for s in own}, key=str),
        reason_codes=reasons,
        # 단독 시드는 이 점수가 곧 base다 — 기여 로그 불변식(기여 합 ≈ raw_score, 'base' 존재) 유지.
        contributions={"base": float(score)},
    )]


def merge_relocation_mobility_seeds(
    cands: list[EventCandidateV2], seeds: list[EventCandidateV2],
) -> list[EventCandidateV2]:
    """같은 시점에 브랜처가 이미 이사 후보를 냈으면 점수는 최댓값·근거는 합집합으로 합친다."""
    if not seeds:
        return cands
    out = list(cands)
    for seed in seeds:
        existing = next((c for c in out if c.event_key is seed.event_key), None)
        if existing is None:
            out.append(seed)
            continue
        # 병합 기여는 실제 증분만 기록한다(기여 합 ≈ raw_score 불변식).
        delta = max(0, seed.score - existing.score)
        existing.score += delta
        if delta > 0 and existing.confidence_level is ConfidenceLevel.THEME_ONLY:
            existing.confidence_level = seed.confidence_level
        for code in seed.reason_codes:
            if code not in existing.reason_codes:
                existing.reason_codes.append(code)
        for tg in seed.source_ten_gods:
            if tg not in existing.source_ten_gods:
                existing.source_ten_gods.append(tg)
        for layer in seed.candidate_source_layers:
            if layer not in existing.candidate_source_layers:
                existing.candidate_source_layers.append(layer)
        existing.contributions["relocation_mobility_seed"] = float(delta)
    return out


__all__ = [
    "COMPANION_CLASH", "COMPANION_HAP", "COMPANION_YEOKMA", "SECTION", "RelocationMobilityRule",
    "load_relocation_mobility_rule", "merge_relocation_mobility_seeds", "mobility_companions",
    "produce_relocation_mobility_seeds",
]
