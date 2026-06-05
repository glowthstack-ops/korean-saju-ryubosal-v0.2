"""통근 (rooting): 득령/득지/득세, root_score, and 신왕(rootedness).

통근 ≠ 득지: 통근 is the existence of a hidden-stem root anywhere; 득지 is whether
the day/month branch directly supports the day master.
"""

from __future__ import annotations

from saju_shared_types.constants import (
    GENERATES,
    STEM_ELEMENT,
    hidden_stems_for,
    main_hidden_stem,
    season_state,
)
from saju_shared_types.enums import Element
from saju_shared_types.pillars import FourPillarsResult

from .._chart import ROOT_BRANCH_WEIGHT, ROOT_HIDDEN_WEIGHT, ROOT_STRENGTH_BY_POSITION, view


def _is_ally_element(el: Element, day_master_el: Element) -> str | None:
    """Return 'peer'/'resource' if *el* supports the day master, else None."""
    if el == day_master_el:
        return "peer_root"
    if GENERATES[el] == day_master_el:  # el generates DM → 인성
        return "resource_root"
    return None


def compute_rooting(pillars: FourPillarsResult, side_balance_score: float) -> dict:
    cv = view(pillars)
    dm_el = STEM_ELEMENT[cv.day_master]

    roots: list[dict] = []
    root_score = 0.0
    for pos, branch in cv.branches:
        for hstem, htype, _w in hidden_stems_for(branch):
            kind = _is_ally_element(STEM_ELEMENT[hstem], dm_el)
            if kind is None:
                continue
            factor = 1.00 if kind == "peer_root" else 0.65
            contribution = ROOT_BRANCH_WEIGHT[pos] * ROOT_HIDDEN_WEIGHT[htype.value] * factor
            root_score += contribution
            roots.append(
                {
                    "position": pos,
                    "branch": str(branch),
                    "hidden_stem": str(hstem),
                    "root_type": kind,
                    "strength": ROOT_STRENGTH_BY_POSITION[pos],
                    "score": round(contribution, 4),
                }
            )
    root_score = round(min(root_score, 100.0), 4)

    # 득령: month seasonally supports the day master (왕 or 상).
    deukryeong = season_state(dm_el, cv.month_branch) in ("wang", "xiang")
    # 득지: day branch main hidden directly supports the day master (비겁/인성).
    day_branch = cv.branches[2][1]  # ("day", branch)
    deukji = _is_ally_element(STEM_ELEMENT[main_hidden_stem(day_branch)], dm_el) is not None
    # 득세: allied power outweighs pressure.
    deukse = side_balance_score >= 50.0
    tonggeun = root_score > 0.0

    if root_score < 10:
        label = "무근"
    elif root_score < 30:
        label = "약근"
    elif root_score < 50:
        label = "보통"
    else:
        label = "신왕"

    return {
        "roots": roots,
        "root_score": root_score,
        "deukryeong": deukryeong,
        "deukji": deukji,
        "deukse": deukse,
        "tonggeun": tonggeun,
        "rootedness_label": label,
        "rootedness_score": root_score,
    }
