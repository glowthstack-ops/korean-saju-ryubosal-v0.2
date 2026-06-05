"""오행분포 — visible / hidden_included / effective_force + display_summary 레이어.

버그픽스(saju_v2_five_element_weight_bugfix_spec): 지장간은 '추가'가 아니라 '분배'다 —
지지별 지장간 가중치 합은 1.0. 월령(월지) 보정은 본기에만 강하게 적용하고 중기/여기는 cap.
표면(visible)에 없고 지장간에만 있는 오행은 '암장(hidden-only)'으로 분리 표기한다.
관계/병존 보정은 구조작용 단계로 연기.
"""

from __future__ import annotations

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    STEM_ELEMENT,
    hidden_stems_for,
)
from saju_shared_types.enums import Element, Stem
from saju_shared_types.pillars import FourPillarsResult

from .._chart import (
    BRANCH_POS_WEIGHT,
    STEM_POS_WEIGHT,
    ChartView,
    view,
)

_ELEMENTS = [str(e) for e in Element]
_MONTH_MAIN_QI_BONUS = 1.30  # 월령 본기 강화
_NON_MAIN_BONUS_CAP = 1.03  # 중기/여기 보정 상한
_HIDDEN_TYPE_KO = {"main": "정", "middle": "중", "residual": "여"}


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

    # Layer 3: effective_force. 지장간은 지지별 budget(합=1.0)으로 분배.
    eff = _empty()
    void = set(pillars.gongmang_branches)  # 공망: 0.85배(제거하지 않음)
    rooting_trace: dict[str, float] = {}
    exposure_trace: dict[str, float] = {}
    month_bonus_trace: list[str] = []
    void_trace: list[str] = []
    for pos, stem in cv.stems:
        w = STEM_POS_WEIGHT[pos]
        if w == 0:  # day master excluded as reference point
            continue
        mult = _rooting_multiplier(cv, stem)
        if mult != 1.0:
            rooting_trace[f"{pos}:{stem}"] = round(mult, 4)
        eff[str(STEM_ELEMENT[stem])] += w * mult
    for pos, branch in cv.branches:
        for hstem, htype, budget in hidden_stems_for(branch):  # budget: 지지별 합=1.0
            is_main = htype.value == "main"
            base = BRANCH_POS_WEIGHT[pos] * budget
            if pos == "month" and is_main:
                base *= _MONTH_MAIN_QI_BONUS  # 월령 본기에만 강한 보정
                month_bonus_trace.append(f"{pos}:{branch}:{hstem}")
            exp = _exposure_multiplier(cv, hstem)
            if not is_main:
                exp = min(exp, _NON_MAIN_BONUS_CAP)  # 중기/여기 cap
            if exp != 1.0:
                exposure_trace[f"{pos}:{branch}:{hstem}"] = round(exp, 4)
            base *= exp
            if str(branch) in void:
                base *= 0.85  # 공망 보정(글자는 유지)
                void_trace.append(f"{pos}:{branch}")
            eff[str(STEM_ELEMENT[hstem])] += base
    eff = {e: round(v, 4) for e, v in eff.items()}

    trace = {
        "position_weights": {"stem": STEM_POS_WEIGHT, "branch": BRANCH_POS_WEIGHT},
        "hidden_weight": "지지별 budget(합=1.0)",
        "month_main_qi_bonus": {"factor": _MONTH_MAIN_QI_BONUS, "applied_to": month_bonus_trace},
        "non_main_bonus_cap": _NON_MAIN_BONUS_CAP,
        "rooting_multipliers": rooting_trace,
        "exposure_multipliers": exposure_trace,
        "void_modifier": {"factor": 0.85, "applied_to": sorted(set(void_trace))},
        "deferred_modifiers": ["relation", "coexistence"],
    }

    percent = _percent(eff)
    strongest = max(percent, key=lambda e: percent[e])
    weakest = min(percent, key=lambda e: percent[e])
    excessive = [e for e, p in percent.items() if p > 35.0]
    deficient = [e for e, p in percent.items() if p < 8.0]

    # 암장(hidden-only): 표면(visible)엔 없고 지장간에만 존재하는 오행.
    hidden_only = _hidden_only_elements(cv, raw, hidden_base)
    hidden_only_names = [h["element"] for h in hidden_only]
    deficient_visible = [e for e in _ELEMENTS if raw[e] == 0]
    visible_present = [e for e in _ELEMENTS if raw[e] > 0]
    strongest_visible = max(visible_present, key=lambda e: raw[e]) if visible_present else None
    weakest_visible = min(visible_present, key=lambda e: raw[e]) if visible_present else None
    warnings = [
        f"{name}은 지장간에만 존재(암장)하므로 화면 분포에서 강한 오행으로 보지 않습니다."
        for name in hidden_only_names
    ]
    display_summary = {
        "visible_counts": raw,
        "strongest_visible": strongest_visible,
        "weakest_visible_present": weakest_visible,
        "strongest_effective": strongest,
        "hidden_only_elements": hidden_only_names,
        "deficient_visible_elements": deficient_visible,
        "excessive_effective_elements": excessive,
        "warnings": warnings,
    }

    return {
        "raw_visible": raw,
        "hidden_base": {e: round(v, 4) for e, v in hidden_base.items()},
        "effective_force": eff,
        "effective_percent": percent,
        "strongest_element": strongest,
        "weakest_element": weakest,
        "excessive_elements": excessive,
        "deficient_elements": deficient,
        "hidden_only_elements": hidden_only,
        "display_summary": display_summary,
        "calculation_trace": trace,
    }


def _hidden_only_elements(
    cv: ChartView, raw: dict[str, float], hidden_base: dict[str, float]
) -> list[dict]:
    out: list[dict] = []
    for el in _ELEMENTS:
        if raw[el] == 0 and hidden_base[el] > 0:
            sources = [
                f"{branch}{_HIDDEN_TYPE_KO[htype.value]}{hstem}"
                for _pos, branch in cv.branches
                for hstem, htype, _w in hidden_stems_for(branch)
                if str(STEM_ELEMENT[hstem]) == el
            ]
            out.append({
                "element": el,
                "sources": sources,
                "label": "암장",
                "operability": "low",
            })
    return out
