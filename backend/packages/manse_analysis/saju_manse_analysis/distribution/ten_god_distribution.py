"""십성분포 — raw_visible / effective layers + group powers + presence diagnosis."""

from __future__ import annotations

from saju_shared_types.constants import (
    hidden_stems_for,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import TenGod
from saju_shared_types.pillars import FourPillarsResult

from .._chart import BRANCH_POS_WEIGHT, STEM_POS_WEIGHT, view
from .element_distribution import (
    _MONTH_MAIN_QI_BONUS,
    _NON_MAIN_BONUS_CAP,
    _exposure_multiplier,
    _rooting_multiplier,
)

TEN_GODS = [str(tg) for tg in TenGod if tg is not TenGod.ILGAN]

GROUPS: dict[str, list[str]] = {
    "peer": [str(TenGod.BIGYEON), str(TenGod.GEOMJAE)],
    "resource": [str(TenGod.JEONGIN), str(TenGod.PYEONIN)],
    "output": [str(TenGod.SIKSIN), str(TenGod.SANGGWAN)],
    "wealth": [str(TenGod.JEONGJAE), str(TenGod.PYEONJAE)],
    "officer": [str(TenGod.JEONGGWAN), str(TenGod.PYEONGWAN)],
}


def _percent(power: dict[str, float]) -> dict[str, float]:
    total = sum(power.values())
    if total <= 0:
        return {k: 0.0 for k in power}
    return {k: round(v / total * 100, 2) for k, v in power.items()}


def compute_ten_god_distribution(pillars: FourPillarsResult) -> dict:
    cv = view(pillars)
    dm = cv.day_master

    raw = {tg: 0.0 for tg in TEN_GODS}
    eff = {tg: 0.0 for tg in TEN_GODS}

    visible: set[str] = set()
    anywhere: set[str] = set()

    # Heavenly stems (exclude the day master itself = 일간).
    for pos, stem in cv.stems:
        if pos == "day":
            continue
        tg = str(ten_god(dm, stem))
        raw[tg] += 1.0
        visible.add(tg)
        anywhere.add(tg)
        w = STEM_POS_WEIGHT[pos]
        if w:
            eff[tg] += w * _rooting_multiplier(cv, stem)

    # Branch hidden stems; branch's representative ten god = main hidden 본기.
    void = set(pillars.gongmang_branches)  # 공망: 0.85배(제거하지 않음)
    for pos, branch in cv.branches:
        main_tg = str(ten_god(dm, main_hidden_stem(branch)))
        raw[main_tg] += 1.0
        visible.add(main_tg)
        for hstem, htype, budget in hidden_stems_for(branch):  # budget: 지지별 합=1.0
            is_main = htype.value == "main"
            tg = str(ten_god(dm, hstem))
            anywhere.add(tg)
            base = BRANCH_POS_WEIGHT[pos] * budget
            if pos == "month" and is_main:
                base *= _MONTH_MAIN_QI_BONUS  # 월령 본기에만 강한 보정
            exp = _exposure_multiplier(cv, hstem)
            if not is_main:
                exp = min(exp, _NON_MAIN_BONUS_CAP)
            base *= exp
            if str(branch) in void:
                base *= 0.85
            eff[tg] += base

    eff = {tg: round(v, 4) for tg, v in eff.items()}
    groups = {
        g: round(sum(eff[tg] for tg in members), 4) for g, members in GROUPS.items()
    }
    strongest = max(eff, key=lambda t: eff[t])
    missing = [tg for tg in TEN_GODS if tg not in anywhere]
    hidden_only = [tg for tg in TEN_GODS if tg in anywhere and tg not in visible]

    # 표시용(display) 십성분포 — 천간(일간 제외) + 지지 본기, 암장 제외, 정규화.
    vis = {tg: 0.0 for tg in TEN_GODS}
    for pos, stem in cv.stems:
        if pos == "day":
            continue
        w = STEM_POS_WEIGHT[pos]
        if w:
            vis[str(ten_god(dm, stem))] += w
    for pos, branch in cv.branches:
        vis[str(ten_god(dm, main_hidden_stem(branch)))] += BRANCH_POS_WEIGHT[pos]
    visible_percent = _percent(vis)
    visible_absent = [tg for tg in TEN_GODS if vis[tg] == 0]

    return {
        "raw_visible": raw,
        "effective": eff,
        "effective_percent": _percent(eff),
        "visible_percent": visible_percent,
        "visible_absent": visible_absent,
        "groups": groups,
        "strongest_ten_god": strongest,
        "missing_ten_gods": missing,
        "hidden_only_ten_gods": hidden_only,
    }
