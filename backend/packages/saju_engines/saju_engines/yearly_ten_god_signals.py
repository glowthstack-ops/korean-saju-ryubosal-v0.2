"""세운 육신별 사건 신호 보강 (2026-10-15, 외부 교재 6장 '세운 육신 사건표' 대조).

교재 표와 브랜처 단일·조합 규칙을 대조해 우리 규칙에 없던 5계열을 보조 규칙으로 더한다.
  ① 겁재 운인데 원국·대운에 관살이 있으면 겁재 해악(분쟁·손재)이 완화된다(배율).
  ② 운 천간이 원국 천간과 천간합을 이루면 그 십성 사건이 강화된다(비겁 합=애정 의심·분쟁,
     관합=결혼 성사 또는 부정 주의, 재성 합=결혼운) — 소폭 가산.
  ③ 인성 운 천간이 원국 재성 천간과 합하면 '불로 이득을 바라는' 흐름(windfall) — 가산 또는
     약한 시드.
  ④ 관성 세운: 사무실 이전·장소 변경(relocation 약한 시드).
  ⑤ 식상 세운: 현재 인연 교체(relationship_change 약한 시드).
전부 사전(`transit_ten_god_branching.json` → `yearly_ten_god_signal_rules`) 상수이며 LLM 판정을
쓰지 않는다(절대원칙 1). 시드는 기존 후보가 없을 때만, 극성은 뒤 계층 `_period_role` 이 덮어쓴다.
점수 규칙이므로 ON/OFF 는 85사례·실사례 적중률로 정한다(데굴님 2026-10-15).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from saju_shared_types.constants import ten_god as _ten_god
from saju_shared_types.enums import Stem
from saju_shared_types.event_engine import (
    TEN_GOD_GROUP,
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
    TenGod,
    TenGodGroup,
)
from saju_shared_types.ganji_calendar import RelationHit, RelationType
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

from .ten_god_brancher import TransitSignal

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
# 한글 십성 → 군(원국 천간 십성 판정용).
_KO_GROUP: dict[str, str] = {
    "비견": "peer", "겁재": "peer", "식신": "output", "상관": "output", "편재": "wealth",
    "정재": "wealth", "편관": "authority", "정관": "authority", "편인": "resource",
    "정인": "resource",
}


@dataclass(frozen=True)
class YearlySignalRule:
    """사전 `yearly_ten_god_signal_rules.rules[]` 1건."""

    rule_id: str
    signal: str
    effect: str  # multiply | add | seed_if_absent | add_or_seed
    events: tuple[EventKeyV2, ...]
    group: str | None = None
    requires_reason_prefix: str | None = None
    factor: float = 1.0
    bonus: int = 0
    seed_score: int = 0
    layers: frozenset[LuckLayer] = frozenset({LuckLayer.SEWOON, LuckLayer.WOLWOON})


@lru_cache(maxsize=4)
def load_yearly_signal_rules(
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> tuple[YearlySignalRule, ...]:
    """사전 절을 읽는다(없으면 빈 튜플 — 비활성)."""
    path = dictionaries_dir / "event_engine" / "transit_ten_god_branching.json"
    raw = json.loads(path.read_text(encoding="utf-8")).get("yearly_ten_god_signal_rules")
    if not raw:
        return ()
    default_layers = frozenset(LuckLayer(x) for x in raw.get("layers", ["sewoon", "wolwoon"]))
    out: list[YearlySignalRule] = []
    for r in raw.get("rules", []):
        out.append(YearlySignalRule(
            rule_id=str(r["id"]),
            signal=str(r["signal"]),
            effect=str(r["effect"]),
            events=tuple(EventKeyV2(e) for e in r.get("events", [])),
            group=r.get("group"),
            requires_reason_prefix=r.get("requires_reason_prefix"),
            factor=float(r.get("factor", 1.0)),
            bonus=int(r.get("bonus", 0)),
            seed_score=int(r.get("seed_score", 0)),
            layers=(
                frozenset(LuckLayer(x) for x in r["layers"]) if r.get("layers") else default_layers
            ),
        ))
    return tuple(out)


def _group_of(tg: TenGod) -> str:
    g = TEN_GOD_GROUP.get(tg)
    return g.value if isinstance(g, TenGodGroup) else str(g or "")


def _target_stem_groups(signals: Sequence[TransitSignal], target_layer: LuckLayer) -> set[str]:
    return {
        _group_of(s.ten_god) for s in signals if s.layer is target_layer and s.source == "stem"
    }


def _natal_or_daewoon_has_authority(
    result: ManseV2Result, signals: Sequence[TransitSignal],
) -> bool:
    p = result.pillars
    if p is not None:
        for pillar in (p.year, p.month, p.day, p.hour):
            if pillar is None:
                continue
            if _KO_GROUP.get(pillar.stem_ten_god) == "authority":
                return True
            if _KO_GROUP.get(pillar.branch_main_ten_god) == "authority":
                return True
    return any(
        s.layer is LuckLayer.DAEWOON and _group_of(s.ten_god) == "authority" for s in signals
    )


def _stem_hap_partners(hits: Sequence[RelationHit], target: LuckPillar) -> list[str]:
    """운 천간이 원국 천간과 맺은 천간합의 원국 파트너 천간들."""
    out: list[str] = []
    for h in hits:
        if h.type is not RelationType.STEM_COMBINATION or h.luck_ref.stem != target.stem:
            continue
        for ref in h.natal_refs:
            if ref.side == "natal" and ref.stem:
                out.append(ref.stem)
    return out


def apply_yearly_ten_god_signals(
    cands: list[EventCandidateV2],
    *,
    signals: Sequence[TransitSignal],
    target_layer: LuckLayer,
    target: LuckPillar,
    result: ManseV2Result,
    hits: Sequence[RelationHit],
    rules: Sequence[YearlySignalRule],
    period: str,
) -> list[EventCandidateV2]:
    """규칙을 적용한 후보 목록(배율·가산·시드). 규칙이 없거나 층이 다르면 불변."""
    if not rules or result.pillars is None:
        return cands
    groups = _target_stem_groups(signals, target_layer)
    partners = _stem_hap_partners(hits, target)
    dm = result.pillars.day_master
    partner_groups = {
        _KO_GROUP.get(str(_ten_god(Stem(dm), Stem(s))), "") for s in partners if dm
    }
    authority_present = _natal_or_daewoon_has_authority(result, signals)
    stack_layers = sorted({s.layer for s in signals}, key=lambda x: list(LuckLayer).index(x))
    out = list(cands)
    for rule in rules:
        if target_layer not in rule.layers:
            continue
        s = rule.signal
        fired = False
        if s == "jiecai_with_officer_present":
            fired = any(
                sg.layer is target_layer and sg.ten_god is TenGod.JIECAI for sg in signals
            ) and authority_present
        elif s == "target_stem_hap_with_natal_group":
            fired = bool(partners) and rule.group in groups
        elif s == "resource_target_hap_with_natal_wealth":
            fired = "resource" in groups and "wealth" in partner_groups
        elif s == "target_group_present":
            fired = rule.group in groups
        if not fired:
            continue
        present = {c.event_key for c in out}
        if rule.effect == "multiply":
            out = [
                c.model_copy(update={
                    "score": max(0, round(c.score * rule.factor)),
                    "reason_codes": [*c.reason_codes, rule.rule_id],
                    "contributions": {
                        **c.contributions,
                        "yearly_signal": float(round(c.score * rule.factor) - c.score),
                    },
                })
                if c.event_key in rule.events and (
                    not rule.requires_reason_prefix
                    or any(r.startswith(rule.requires_reason_prefix) for r in c.reason_codes)
                ) and rule.rule_id not in c.reason_codes
                else c
                for c in out
            ]
        elif rule.effect in ("add", "add_or_seed"):
            touched = False
            new: list[EventCandidateV2] = []
            for c in out:
                if c.event_key in rule.events and rule.rule_id not in c.reason_codes:
                    touched = True
                    new.append(c.model_copy(update={
                        "score": c.score + rule.bonus,
                        "reason_codes": [*c.reason_codes, rule.rule_id],
                        "contributions": {**c.contributions, "yearly_signal": float(rule.bonus)},
                    }))
                else:
                    new.append(c)
            out = new
            if rule.effect == "add_or_seed" and not touched and rule.seed_score > 0:
                out += _seeds(rule, present, period, stack_layers, target_layer, signals)
        elif rule.effect == "seed_if_absent" and rule.seed_score > 0:
            out += _seeds(rule, present, period, stack_layers, target_layer, signals)
    return out


def _seeds(
    rule: YearlySignalRule, present: set[EventKeyV2], period: str,
    stack_layers: list[LuckLayer], target_layer: LuckLayer, signals: Sequence[TransitSignal],
) -> list[EventCandidateV2]:
    gods = sorted({s.ten_god for s in signals if s.layer is target_layer}, key=str)
    return [
        EventCandidateV2(
            event_key=ev, period=period, score=rule.seed_score,
            confidence_level=ConfidenceLevel.THEME_ONLY, polarity_role=PolarityRole.NEUTRAL,
            source_layers=stack_layers or [target_layer],
            candidate_source_layers=[target_layer.value], source_ten_gods=gods,
            reason_codes=[rule.rule_id], contributions={"base": float(rule.seed_score)},
        )
        for ev in rule.events if ev not in present
    ]


__all__ = [
    "YearlySignalRule", "apply_yearly_ten_god_signals", "load_yearly_signal_rules",
]
