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

from .marriage_hap_subtype import mt4_subtype_multiplier, partner_elements

# MT4 합 종류 재가중 적용 대상 — 관계/결혼 도메인 한정(타 도메인 합은 항상 ×1.0).
_MT4_DOMAIN = frozenset({"new_relationship", "marriage_signal", "relationship_change"})


@dataclass
class RelationActivation:
    """운이 원국 궁을 자극한 관계 1건."""

    kind: RelationKind
    palace: Pillar4
    layer: LuckLayer
    position: str = "branch"  # 'stem' | 'branch'
    # MT4(MARRIAGE_TIMING_ENHANCEMENT §9): HAP은 RelationKind로 유지하되 원 합 종류를 곁들인다.
    # 'six_harmony'|'three_harmony'|'directional'|'stem'|None. element=삼합/방합 완성 오행(한자).
    hap_subtype: str | None = None
    element: str | None = None


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
        self,
        candidates: list[EventCandidateV2],
        activations: list[RelationActivation],
        *,
        mt4_mode: str = "off",
        gender: str = "unknown",
        day_element: str = "",
        shadow_sink: list[dict] | None = None,
    ) -> list[EventCandidateV2]:
        """후보에 관계·궁성 발동 보너스를 적용한다.

        MT4(§9): mt4_mode='off'면 기존 동작 그대로(byte 불변). 'shadow'면 관계 도메인 HAP 활성의
        합 종류(subtype) multiplier를 **계산만** 해 shadow_sink에 기록하고 점수·reason은 불변.
        'apply'면 합산 전 보너스에 multiplier를 곱하고(상향 없음 ≤1.0) MT4 reason을 단다.
        """
        kinds = {a.kind for a in activations}
        compound_bonus = self._compound_bonus(kinds)
        # (relation, palace) → likely_events 빠른 조회.
        rel_palace_events: dict[tuple[str, str], set[str]] = {}
        for r in self._rel_to_palace:
            key = (r["relation"], r["target_palace"])
            rel_palace_events.setdefault(key, set()).update(r["likely_events"])
        partner_els = partner_elements(day_element, gender) if mt4_mode != "off" else set()

        out: list[EventCandidateV2] = []
        for c in candidates:
            ek = str(c.event_key)
            best_palace: Pillar4 | None = c.palace
            delta = 0.0
            reasons = [*c.reason_codes]
            mt4_reasons: list[str] = []
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
                # MT4 — 관계 도메인 HAP 활성만 합 종류 재가중(상향 없음). off는 건너뜀.
                if mt4_mode != "off" and act.kind is RelationKind.HAP and ek in _MT4_DOMAIN:
                    mult, mt4_reason = mt4_subtype_multiplier(
                        act.hap_subtype,
                        on_spouse_palace=act.palace is Pillar4.DAY,
                        partner_element=bool(act.element) and act.element in partner_els,
                    )
                    if mt4_mode == "apply":
                        if mult != 1.0:
                            mt4_reasons.append(mt4_reason)
                        bonus *= mult
                    elif mt4_mode == "shadow" and shadow_sink is not None:
                        shadow_sink.append({
                            "event": ek, "palace": act.palace.value,
                            "hapSubtype": act.hap_subtype, "multiplier": mult,
                            "relation_original": round(bonus, 3),
                            "relation_mt4": round(bonus * mult, 3),
                            "relation_mt4_diff": round(bonus * mult - bonus, 3),
                            "reason": mt4_reason,
                        })
                delta += bonus
                best_palace = act.palace
                reasons.append(f"REL_{act.kind.value}_{act.palace.value}")
            if compound_bonus and best_palace is not None:
                delta += compound_bonus
                reasons.append("REL_COMPOUND")
            if mt4_mode == "apply" and mt4_reasons:
                reasons.extend(dict.fromkeys(mt4_reasons))  # 중복 제거·순서 보존
            if delta == 0 and c.palace is None:
                out.append(c)
                continue
            # 발동 보너스 총량 상한 — 다중 적중·복합이 점수를 100으로 포화시키는 것을 방지
            # (포화 보정, reviewed:false 초안). 발동 '여부'는 palace·confidence가 별도로 표현한다.
            delta = min(delta, _MAX_RELATION_DELTA)
            new_score = max(0, round(c.score + delta))  # 중간 100 클램프 제거 — raw 보존
            out.append(c.model_copy(update={
                "score": new_score,
                "palace": best_palace,
                "reason_codes": reasons,
                "contributions": {**c.contributions, "relation": float(new_score - c.score)},
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
