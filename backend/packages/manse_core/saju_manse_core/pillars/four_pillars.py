"""Assemble the four pillars (원국) and a calculation trace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    BRANCH_YINYANG,
    NAEUM,
    STEM_ELEMENT,
    STEM_YINYANG,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Palace, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult, Pillar

from ..calendar.solar_terms import SolarTermTable
from .day_pillar import day_pillar
from .gongmang import gongmang_branches
from .hidden_stems import hidden_stems
from .hour_pillar import hour_pillar
from .month_pillar import month_pillar
from .twelve_unseong import twelve_unseong
from .year_pillar import year_pillar

_PALACE = {
    "year": Palace.YEAR, "month": Palace.MONTH, "day": Palace.DAY, "hour": Palace.HOUR,
}


def build_pillar(
    day_master: Stem,
    stem: Stem,
    branch: Branch,
    position: str,
    gongmang_set: set[Branch],
) -> Pillar:
    is_day = position == "day"
    stem_tg = TenGod.ILGAN if is_day else ten_god(day_master, stem)
    return Pillar(
        stem=str(stem),
        branch=str(branch),
        ganji=f"{stem}{branch}",
        stem_element=str(STEM_ELEMENT[stem]),
        branch_element=str(BRANCH_ELEMENT[branch]),
        stem_yinyang=str(STEM_YINYANG[stem]),
        branch_yinyang=str(BRANCH_YINYANG[branch]),
        stem_ten_god=str(stem_tg),
        branch_main_ten_god=str(ten_god(day_master, main_hidden_stem(branch))),
        twelve_unseong=twelve_unseong(day_master, branch),
        hidden_stems=hidden_stems(branch, day_master),
        naeum=NAEUM[(stem, branch)],
        gongmang_hit=branch in gongmang_set,
        palace=str(_PALACE[position]),
    )


@dataclass
class SolarTermInfo:
    month_branch: Branch
    prev_term: tuple[datetime, str]
    next_term: tuple[datetime, str]


def compute(
    absolute_instant: datetime,
    final_local: datetime,
    time_known: bool,
    day_boundary_rule: str,
    ja_hour_rule: str,
    table: SolarTermTable,
    warnings: list[str] | None = None,
) -> tuple[FourPillarsResult, SolarTermInfo]:
    warnings = list(warnings or [])

    y_stem, y_branch, eff_year, lichun = year_pillar(absolute_instant, table)
    m_stem, m_branch, prev_term, next_term = month_pillar(absolute_instant, y_stem, table)
    d_stem, d_branch = day_pillar(final_local, day_boundary_rule, ja_hour_rule)

    # 일공망(旬 기준) — 반환 순서를 canonical로 유지(set은 membership 전용).
    gongmang_list = gongmang_branches(d_stem, d_branch)
    gongmang = set(gongmang_list)

    year_p = build_pillar(d_stem, y_stem, y_branch, "year", gongmang)
    month_p = build_pillar(d_stem, m_stem, m_branch, "month", gongmang)
    day_p = build_pillar(d_stem, d_stem, d_branch, "day", gongmang)

    hour_p: Pillar | None = None
    if time_known:
        h_stem, h_branch = hour_pillar(d_stem, final_local)
        hour_p = build_pillar(d_stem, h_stem, h_branch, "hour", gongmang)
    else:
        warnings.append("hour_pillar_unknown: time not provided")

    trace = {
        "year": {
            "effective_year": eff_year,
            "lichun_utc": lichun.isoformat(),
            "rule": "입춘 boundary",
        },
        "month": {
            "month_branch": str(m_branch),
            "previous_term": [prev_term[1], prev_term[0].isoformat()],
            "next_term": [next_term[1], next_term[0].isoformat()],
            "rule": "절기 기준 둔월법",
        },
        "day": {
            "day_boundary_rule": day_boundary_rule,
            "ja_hour_rule": ja_hour_rule,
            "rule": "JDN 60갑자",
        },
        "hour": {"known": time_known, "rule": "둔시법" if time_known else "suppressed"},
    }

    result = FourPillarsResult(
        year=year_p,
        month=month_p,
        day=day_p,
        hour=hour_p,
        day_master=str(d_stem),
        gongmang_branches=[str(b) for b in gongmang_list],
        trace=trace,
        warnings=warnings,
    )
    return result, SolarTermInfo(m_branch, prev_term, next_term)
