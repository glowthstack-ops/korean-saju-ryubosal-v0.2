"""신강/신약 9단계 점수 + 신왕/신강 분리 게이트 (strength_9_band spec)."""

from __future__ import annotations

from saju_shared_types.constants import (
    SEASON_SCORE,
    STEM_ELEMENT,
    main_hidden_stem,
    season_state,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult

from .._chart import view

_BAND_BOUNDS = [
    (11, "극신약"), (22, "태신약"), (34, "신약"), (44, "중화신약"), (55, "중화"),
    (65, "중화신강"), (77, "신강"), (88, "태신강"), (100, "극신강"),
]
_BOUNDARY_POINTS = [11, 22, 34, 44, 55, 65, 77, 88]
_ALLY_GROUPS = {TenGod.BIGYEON, TenGod.GEOMJAE, TenGod.JEONGIN, TenGod.PYEONIN}


def classify_band(score: float) -> str:
    for upper, name in _BAND_BOUNDS:
        if score <= upper:
            return name
    return "극신강"


def is_borderline(score: float) -> bool:
    return any(abs(score - b) <= 2 for b in _BOUNDARY_POINTS)


def side_balance_score(groups: dict[str, float]) -> float:
    ally = groups["peer"] * 1.00 + groups["resource"] * 0.85
    pressure = groups["output"] * 0.55 + groups["wealth"] * 0.75 + groups["officer"] * 1.00
    denom = ally + pressure
    if denom <= 1e-6:
        return 50.0
    return 100 * ally / denom


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _is_ally_branch(dm: Stem, branch: Branch) -> bool:
    return ten_god(dm, main_hidden_stem(branch)) in _ALLY_GROUPS


def compute_strength(
    pillars: FourPillarsResult,
    ten_god_groups: dict[str, float],
    root_score: float,
    gongmang_branches: list[str],
) -> dict:
    cv = view(pillars)
    dm = cv.day_master
    dm_el = STEM_ELEMENT[dm]
    warnings: list[str] = []

    season = SEASON_SCORE[season_state(dm_el, cv.month_branch)]
    side = side_balance_score(ten_god_groups)

    # structure_modifier — only non-relation factors in this phase (공망 on
    # day/month branch). 합충형파해/병존/합화 보정은 구조작용 단계에서 추가.
    void = set(gongmang_branches)
    structure_modifier = 0.0
    day_void = pillars.day.branch in void
    month_void = pillars.month.branch in void
    if day_void:
        structure_modifier -= 2
    if month_void:
        structure_modifier -= 2
    structure_modifier = _clamp(structure_modifier, -10, 10)

    score = _clamp(0.35 * season + 0.35 * root_score + 0.30 * side + structure_modifier, 0, 100)
    band = classify_band(score)
    borderline = is_borderline(score)

    # confidence — clarity of each component + relation stability (voids only here).
    season_clarity = _clamp(abs(season - 50) / 40, 0, 1)
    root_clarity = _clamp(abs(root_score - 50) / 50, 0, 1)
    side_clarity = _clamp(abs(side - 50) / 50, 0, 1)
    relation_stability = _clamp(1.0 - 0.15 * (int(day_void) + int(month_void)), 0, 1)
    confidence = round(
        0.35 * season_clarity + 0.30 * root_clarity + 0.20 * side_clarity
        + 0.15 * relation_stability,
        4,
    )

    requires_validation = (35 <= score <= 65) or confidence < 0.70 or borderline

    # 신강 최소 조건 게이트 (신왕 ≠ 신강).
    month_ally = _is_ally_branch(dm, cv.month_branch)
    day_ally = _is_ally_branch(dm, cv.branches[2][1])
    ally_positions = 0
    for pos, stem in cv.stems:
        if pos == "day":
            continue
        if ten_god(dm, stem) in _ALLY_GROUPS:
            ally_positions += 1
    for _pos, branch in cv.branches:
        if ten_god(dm, main_hidden_stem(branch)) in _ALLY_GROUPS:
            ally_positions += 1
    month_or_day_ally = month_ally or day_ally
    another_ally_exists = ally_positions >= 2
    gate_passed = month_or_day_ally and another_ally_exists

    if band in ("중화신약", "중화", "중화신강"):
        warnings.append("neutral_zone: 용신 단정 금지, 경쟁 모델/검증 필요")
    if root_score >= 50 and not gate_passed:
        warnings.append("rooted_but_not_strong: 신왕하나 신강 게이트 미통과")

    rootedness_label = (
        "무근" if root_score < 10 else
        "약근" if root_score < 30 else
        "보통" if root_score < 50 else "신왕"
    )

    return {
        "score": round(score, 2),
        "band": band,
        "borderline": borderline,
        "confidence": confidence,
        "requires_validation": requires_validation,
        "components": {
            "season_score": float(season),
            "root_score": round(root_score, 2),
            "side_balance_score": round(side, 2),
            "structure_modifier": structure_modifier,
        },
        "basis": {},  # filled by aggregator from rooting
        "rootedness": {"label": rootedness_label, "score": round(root_score, 2)},
        "strong_chart_gate": {
            "month_or_day_branch_ally": month_or_day_ally,
            "another_ally_position_exists": another_ally_exists,
            "passed": gate_passed,
        },
        "explanation": [
            f"season_score={season}, root_score={round(root_score, 1)}, "
            f"side_balance={round(side, 1)}, structure={structure_modifier}",
        ],
        "warnings": warnings,
        "_side_balance_score": round(side, 2),
    }
