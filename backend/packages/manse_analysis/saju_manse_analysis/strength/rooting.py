"""통근 (rooting): 득령/득지/득세, root_score, and 신왕(rootedness).

통근 ≠ 득지: 통근 is the existence of a hidden-stem root anywhere; 득지 is whether
the day/month branch directly supports the day master.
"""

from __future__ import annotations

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    GENERATES,
    STEM_ELEMENT,
    hidden_stems_for,
    main_hidden_stem,
    season_state,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.pillars import FourPillarsResult

from .._chart import ROOT_BRANCH_WEIGHT, ROOT_HIDDEN_WEIGHT, ROOT_STRENGTH_BY_POSITION, view

# 통근 종류별 계수: 본기(같은 천간) > 동기(같은 오행 다른 천간) > 인성(생조).
# 동기 0.85 — 戊는 己의 실뿌리이므로 거의 무근(0.45)으로 보지 않는다. 신약화의 핵심
# 동력은 동기 감산이 아니라 '그 뿌리가 놓인 지지의 공망/충 reliability'다.
_ROOT_KIND_FACTOR = {"primary_root": 1.00, "same_element_root": 0.85, "resource_root": 0.65}


def _is_ally_element(el: Element, day_master_el: Element) -> str | None:
    """Return 'peer'/'resource' if *el* supports the day master, else None."""
    if el == day_master_el:
        return "peer_root"
    if GENERATES[el] == day_master_el:  # el generates DM → 인성
        return "resource_root"
    return None


def _root_kind(hstem: Stem, day_master: Stem, dm_el: Element) -> str | None:
    """본기/동기/인성 구분. 같은 오행이라도 천간이 다르면 동기(간접)로 약하게 본다."""
    el = STEM_ELEMENT[hstem]
    if hstem == day_master:
        return "primary_root"          # 본기(같은 천간) — 직접 통근
    if el == dm_el:
        return "same_element_root"     # 동기(같은 오행 다른 천간) — 간접 통근
    if GENERATES[el] == dm_el:
        return "resource_root"         # 인성 통근
    return None


def _clashed_branches(branches: list[tuple[str, Branch]]) -> set[Branch]:
    """원국 내 지지충에 걸린 지지 집합(통근 신뢰도 약화용)."""
    out: set[Branch] = set()
    bs = [b for _, b in branches]
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            if frozenset({bs[i], bs[j]}) in BRANCH_CLASHES:
                out.update({bs[i], bs[j]})
    return out


def _root_reliability(branch: Branch, void: set[str], clashed: set[Branch]) -> float:
    """공망·충 걸린 지지의 통근은 보수적으로(공망+충 0.45 / 공망 0.60 / 충 0.75)."""
    v = str(branch) in void
    c = branch in clashed
    if v and c:
        return 0.45
    if v:
        return 0.60
    if c:
        return 0.75
    return 1.00


def compute_rooting(
    pillars: FourPillarsResult, side_balance_score: float, gongmang_branches: list[str],
) -> dict:
    cv = view(pillars)
    dm_el = STEM_ELEMENT[cv.day_master]
    void = set(gongmang_branches)
    clashed = _clashed_branches(cv.branches)

    roots: list[dict] = []
    root_score = 0.0
    for pos, branch in cv.branches:
        reliability = _root_reliability(branch, void, clashed)
        for hstem, htype, _w in hidden_stems_for(branch):
            kind = _root_kind(hstem, cv.day_master, dm_el)
            if kind is None:
                continue
            factor = _ROOT_KIND_FACTOR[kind]
            contribution = (
                ROOT_BRANCH_WEIGHT[pos] * ROOT_HIDDEN_WEIGHT[htype.value] * factor * reliability
            )
            root_score += contribution
            roots.append(
                {
                    "position": pos,
                    "branch": str(branch),
                    "hidden_stem": str(hstem),
                    "root_type": "peer_root" if kind != "resource_root" else "resource_root",
                    "root_kind": kind,
                    "reliability": round(reliability, 2),
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
