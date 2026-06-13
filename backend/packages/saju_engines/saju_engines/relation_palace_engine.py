"""RelationPalaceEngine (Phase 6) — 합충형파해·궁성으로 사건화 여부와 생활 영역을 보정한다.

relation_palace_modifier.json: 관계 종류(HAP/CHUNG/HYEONG/PA/HAE) 발동 보너스 × 궁성 활성 가중 ×
운층 가중. 자극된 궁(년/월/일/시)의 event_domains에 맞는 후보를 강화하고 palace를 부여한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)


@dataclass
class RelationActivation:
    """운이 원국 궁을 자극한 관계 1건."""

    kind: RelationKind
    palace: Pillar4
    layer: LuckLayer
    position: str = "branch"  # 'stem' | 'branch'


_MAX_RELATION_DELTA = 22.0  # 발동 보너스 총량 상한(포화 보정 — reviewed:false)


class RelationPalaceEngine:
    """관계·궁성 발동 보정."""

    def __init__(self, dictionaries_dir: Path) -> None:
        raw = json.loads(
            (dictionaries_dir / "event_engine" / "relation_palace_modifier.json").read_text(
                encoding="utf-8"
            )
        )
        self._rel_bonus: dict[str, int] = {
            k: int(v["base_event_score_bonus"]) for k, v in raw["relation_types"].items()
        }
        self._palace: dict[str, dict] = raw["palace_map"]
        self._rel_to_palace: list[dict] = raw["relation_to_palace_event_rules"]
        self._compounds: list[dict] = raw["compound_relation_patterns"]
        self._layer_w: dict[str, float] = {
            k: float(v["score_multiplier"]) for k, v in raw["relation_layer_weights"].items()
        }
        self._palace_mult: dict[str, dict] = raw["palace_relation_score_multipliers"]

    def apply(
        self, candidates: list[EventCandidateV2], activations: list[RelationActivation]
    ) -> list[EventCandidateV2]:
        """후보에 관계·궁성 발동 보너스를 적용한다."""
        kinds = {a.kind for a in activations}
        compound_bonus = self._compound_bonus(kinds)
        # (relation, palace) → likely_events 빠른 조회.
        rel_palace_events: dict[tuple[str, str], set[str]] = {}
        for r in self._rel_to_palace:
            key = (r["relation"], r["target_palace"])
            rel_palace_events.setdefault(key, set()).update(r["likely_events"])

        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = str(c.event_key)
            best_palace: Pillar4 | None = c.palace
            delta = 0.0
            reasons = [*c.reason_codes]
            for act in activations:
                pinfo = self._palace[act.palace.value]
                in_domain = ek in pinfo["event_domains"]
                likely = ek in rel_palace_events.get((act.kind.value, act.palace.value), set())
                if not (in_domain or likely):
                    continue
                layer_mult = self._layer_w.get(f"{act.layer.value}_to_natal", 1.0)
                pmult = self._palace_mult[act.palace.value][act.position]
                bonus = self._rel_bonus[act.kind.value] * float(pinfo["activation_weight"])
                bonus *= layer_mult * pmult
                if likely:
                    bonus *= 1.2
                delta += bonus
                best_palace = act.palace
                reasons.append(f"REL_{act.kind.value}_{act.palace.value}")
            if compound_bonus and best_palace is not None:
                delta += compound_bonus
                reasons.append("REL_COMPOUND")
            if delta == 0 and c.palace is None:
                out.append(c)
                continue
            # 발동 보너스 총량 상한 — 다중 적중·복합이 점수를 100으로 포화시키는 것을 방지
            # (포화 보정, reviewed:false 초안). 발동 '여부'는 palace·confidence가 별도로 표현한다.
            delta = min(delta, _MAX_RELATION_DELTA)
            out.append(c.model_copy(update={
                "score": max(0, min(100, round(c.score + delta))),
                "palace": best_palace,
                "reason_codes": reasons,
            }))
        return sorted(out, key=lambda x: -x.score)

    def _compound_bonus(self, kinds: set[RelationKind]) -> int:
        """동시 발생 관계 조합(합+충, 형+충 등) 발동 보너스."""
        kset = {k.value for k in kinds}
        bonus = 0
        for comp in self._compounds:
            pat = comp.get("pattern", [])
            if all(p in kset for p in pat if p in {"HAP", "CHUNG", "HYEONG", "PA", "HAE"}) and any(
                p in {"HAP", "CHUNG", "HYEONG", "PA", "HAE"} for p in pat
            ):
                eff = comp.get("score_effect", {})
                bonus = max(bonus, int(eff.get("event_activation_bonus", 0)))
        return bonus
