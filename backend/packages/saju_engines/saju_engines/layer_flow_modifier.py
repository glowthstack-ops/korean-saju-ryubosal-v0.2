"""LayerFlowModifier (Phase 4) — 운 층위 결합·반복성·십성 흐름으로 후보 강도를 보정한다.

transit_ten_god_branching.layer_combination_rules / repetition_rules + addendum.ten_god_flow_rules.
사건 타입을 만들지 않고 점수만 조정한다(대운+세운 결합 ×배율, 동일 십성 반복 가점, 생성/역 흐름).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    TenGod,
    TenGodGroup,
)

from .ten_god_brancher import TransitSignal

# MIXED 룰 id → 함께 등장 시 가점하는 십성 쌍(사양 텍스트 조건의 기계화).
_MIXED_PAIRS: dict[str, frozenset[TenGod]] = {
    "MIXED_AUTHORITY": frozenset({TenGod.ZHENGGUAN, TenGod.QISHA}),
    "MIXED_WEALTH": frozenset({TenGod.ZHENGCAI, TenGod.PIANCAI}),
    "MIXED_OUTPUT": frozenset({TenGod.SHISHEN, TenGod.SHANGGUAN}),
    "MIXED_RESOURCE": frozenset({TenGod.ZHENGYIN, TenGod.PIANYIN}),
}
# 십성 그룹 생성(상생) 흐름: peer→output→wealth→authority→resource→peer.
_GEN_NEXT: dict[TenGodGroup, TenGodGroup] = {
    TenGodGroup.PEER: TenGodGroup.OUTPUT,
    TenGodGroup.OUTPUT: TenGodGroup.WEALTH,
    TenGodGroup.WEALTH: TenGodGroup.AUTHORITY,
    TenGodGroup.AUTHORITY: TenGodGroup.RESOURCE,
    TenGodGroup.RESOURCE: TenGodGroup.PEER,
}


class LayerFlowModifier:
    """층위 결합·반복·흐름 보정."""

    def __init__(self, dictionaries_dir: Path) -> None:
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "transit_ten_god_branching.json").read_text(
                encoding="utf-8"
            )
        )
        self._layer_mult: dict[frozenset[LuckLayer], float] = {
            frozenset(LuckLayer(x) for x in r["layers"]): float(r["score_multiplier"])
            for r in raw["layer_combination_rules"]
        }
        self._repetition: list[dict] = raw["repetition_rules"]
        add_path = dictionaries_dir / "event_engine" / "transit_ten_god_branching_addendum.json"
        addendum = json.loads(add_path.read_text(encoding="utf-8"))
        self._flow = addendum["ten_god_flow_rules"]

    def apply(
        self, candidates: list[EventCandidateV2], signals: list[TransitSignal]
    ) -> list[EventCandidateV2]:
        """후보별 층위 배율·반복·MIXED·흐름 보정을 적용한다."""
        god_layers: dict[TenGod, set[LuckLayer]] = defaultdict(set)
        layer_group: dict[LuckLayer, TenGodGroup] = {}
        for s in signals:
            god_layers[s.ten_god].add(s.layer)
        for layer in {s.layer for s in signals}:
            stems = [s for s in signals if s.layer == layer and s.source == "stem"]
            layer_signals = [s for s in signals if s.layer == layer]
            layer_group[layer] = (stems[0] if stems else layer_signals[0]).group
        repeated_gods = {g for g, ls in god_layers.items() if len(ls) >= 2}
        repeated_groups = {
            grp for grp in TenGodGroup
            if len({lyr for lyr, g in layer_group.items() if g == grp}) >= 2
        }
        present_gods = set(god_layers)

        mixed_bonus: dict[str, int] = defaultdict(int)
        for rep in self._repetition:
            pair = _MIXED_PAIRS.get(rep["id"])
            if pair and pair <= present_gods:
                for e in rep.get("events", []):
                    mixed_bonus[e["event"]] += int(e["score_bonus"])

        flow_delta = self._flow_delta(layer_group)

        out: list[EventCandidateV2] = []
        for c in candidates:
            mult = self._layer_mult.get(frozenset(c.source_layers), 1.0)
            score = c.score * mult
            reasons = [*c.reason_codes]
            if set(c.source_ten_gods) & repeated_gods:
                score += 8
                reasons.append("REPEAT_SAME_TEN_GOD")
            cand_groups = {layer_group.get(lyr) for lyr in c.source_layers}
            if cand_groups & repeated_groups:
                score += 6
                reasons.append("REPEAT_SAME_GROUP")
            bonus = mixed_bonus.get(str(c.event_key), 0)
            if bonus:
                score += bonus
                reasons.append("MIXED_TEN_GOD")
            if flow_delta:
                score += flow_delta
                reasons.append("FLOW_GEN" if flow_delta > 0 else "FLOW_REVERSE")
            new_score = max(0, round(score))  # 중간 100 클램프 제거 — raw 누적 보존
            out.append(c.model_copy(update={
                "score": new_score,
                "reason_codes": reasons,
                "raw_score": float(round(score, 2)),
                "contributions": {**c.contributions, "flow": float(new_score - c.score)},
            }))
        return sorted(out, key=lambda x: -x.score)

    def _flow_delta(self, layer_group: dict[LuckLayer, TenGodGroup]) -> int:
        """대운→세운→월운 그룹이 상생 흐름이면 +, 역흐름이면 - (생성/역 흐름)."""
        seq = [
            layer_group[lyr]
            for lyr in (LuckLayer.DAEWOON, LuckLayer.SEWOON, LuckLayer.WOLWOON)
            if lyr in layer_group
        ]
        if len(seq) < 2:
            return 0
        gen = all(_GEN_NEXT.get(seq[i]) == seq[i + 1] for i in range(len(seq) - 1))
        rev = all(_GEN_NEXT.get(seq[i + 1]) == seq[i] for i in range(len(seq) - 1))
        if gen:
            return int(self._flow["upper_to_lower_layer_flow"]["score_bonus"])
        if rev:
            return int(self._flow["reverse_flow"]["score_penalty"])
        return 0
