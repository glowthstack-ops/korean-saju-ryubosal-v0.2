"""오행분포 — raw_visible / hidden_base / effective_force layers.

Relation / void / coexistence modifiers (합충형파해, 공망, 병존) are deferred to the
구조작용 phase; this layer implements position weights, hidden-stem weights, the
seasonal coefficient, the month main-qi bonus, 투간 (exposure) and 통근 (rooting).
"""

from __future__ import annotations

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    SEASON_COEFFICIENT,
    STEM_ELEMENT,
    hidden_stems_for,
    season_state,
)
from saju_shared_types.enums import Element, Stem
from saju_shared_types.pillars import FourPillarsResult

from .._chart import (
    BRANCH_POS_WEIGHT,
    HIDDEN_EFF_WEIGHT,
    STEM_POS_WEIGHT,
    ChartView,
    view,
)

_ELEMENTS = [str(e) for e in Element]


def _empty() -> dict[str, float]:
    return {e: 0.0 for e in _ELEMENTS}


def _percent(power: dict[str, float]) -> dict[str, float]:
    total = sum(power.values())
    if total <= 0:
        return {e: 0.0 for e in power}
    return {e: round(v / total * 100, 2) for e, v in power.items()}


def _rooting_multiplier(cv: ChartView, stem: Stem) -> float:
    """1.0..1.18 — boost a heavenly stem that has a root among the branches."""
    stem_el = STEM_ELEMENT[stem]
    best = 1.0
    for _pos, branch in cv.branches:
        for hstem, htype, _w in hidden_stems_for(branch):
            strength = {"main": "strong", "middle": "medium", "residual": "weak"}[htype.value]
            if hstem == stem:
                best = max(best, {"strong": 1.18, "medium": 1.12, "weak": 1.06}[strength])
            elif STEM_ELEMENT[hstem] == stem_el:
                best = max(best, {"strong": 1.12, "medium": 1.08, "weak": 1.04}[strength])
    return best


def _exposure_multiplier(cv: ChartView, hidden_stem: Stem) -> float:
    if hidden_stem in cv.heavenly_stems:
        return 1.15
    if str(STEM_ELEMENT[hidden_stem]) in cv.heavenly_elements:
        return 1.08
    return 1.0


def compute_element_distribution(pillars: FourPillarsResult) -> dict:
    cv = view(pillars)

    # Layer 1: raw_visible — simple count of stems + branch surface elements.
    raw = _empty()
    for _pos, stem in cv.stems:
        raw[str(STEM_ELEMENT[stem])] += 1.0
    for _pos, branch in cv.branches:
        raw[str(BRANCH_ELEMENT[branch])] += 1.0

    # Layer 2: hidden_base — stems (1.0) + branch hidden stems (pillar weights).
    hidden_base = _empty()
    for _pos, stem in cv.stems:
        hidden_base[str(STEM_ELEMENT[stem])] += 1.0
    for _pos, branch in cv.branches:
        for hstem, _htype, w in hidden_stems_for(branch):
            hidden_base[str(STEM_ELEMENT[hstem])] += w

    # Layer 3: effective_force.
    eff = _empty()
    for pos, stem in cv.stems:
        w = STEM_POS_WEIGHT[pos]
        if w == 0:  # day master excluded as reference point
            continue
        eff[str(STEM_ELEMENT[stem])] += w * _rooting_multiplier(cv, stem)
    for pos, branch in cv.branches:
        for hstem, htype, _w in hidden_stems_for(branch):
            base = BRANCH_POS_WEIGHT[pos] * HIDDEN_EFF_WEIGHT[htype.value]
            if pos == "month" and htype.value == "main":
                base *= 1.12  # month main-qi bonus
            base *= _exposure_multiplier(cv, hstem)
            eff[str(STEM_ELEMENT[hstem])] += base
    # Seasonal coefficient applied to each element's total power.
    for el in Element:
        eff[str(el)] *= SEASON_COEFFICIENT[season_state(el, cv.month_branch)]
    eff = {e: round(v, 4) for e, v in eff.items()}

    percent = _percent(eff)
    strongest = max(percent, key=lambda e: percent[e])
    weakest = min(percent, key=lambda e: percent[e])
    excessive = [e for e, p in percent.items() if p > 35.0]
    deficient = [e for e, p in percent.items() if p < 8.0]

    return {
        "raw_visible": raw,
        "hidden_base": {e: round(v, 4) for e, v in hidden_base.items()},
        "effective_force": eff,
        "effective_percent": percent,
        "strongest_element": strongest,
        "weakest_element": weakest,
        "excessive_elements": excessive,
        "deficient_elements": deficient,
    }
