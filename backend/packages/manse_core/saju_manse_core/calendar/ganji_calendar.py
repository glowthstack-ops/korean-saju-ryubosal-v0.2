"""간지달력: 한 달 그리드의 일자별 간지(년/월/일주) 산출.

달력은 KST 만세력 기준이다 — 각 일자를 Asia/Seoul 정오의 절대시각으로 보고 년주(입춘 경계)·
월주(절기+둔월법)를 판정하며, 일주는 해당 civil date의 일진(`day_ganzi`)을 쓴다.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime
from zoneinfo import ZoneInfo

from saju_shared_types.constants import (
    BRANCH_KO,
    MONTH_BRANCH_ORDER,
    MONTH_STEM_START,
    STEM_INDEX,
    STEM_KO,
    STEMS,
)
from saju_shared_types.enums import Branch, Stem

from .sexagenary_cycle import day_ganzi, year_ganzi
from .solar_terms import SolarTermTable, get_table

_KST = ZoneInfo("Asia/Seoul")


def _ganji(stem: Stem, branch: Branch) -> tuple[str, str]:
    return f"{stem}{branch}", f"{STEM_KO[stem]}{BRANCH_KO[branch]}"


def _year_ganji(instant: datetime, table: SolarTermTable) -> tuple[Stem, Branch]:
    civil_year = instant.year  # KST 기준 연도
    lichun = table.lichun_for_year(civil_year)
    effective = civil_year if instant >= lichun else civil_year - 1
    return year_ganzi(effective)


def _month_ganji(
    instant: datetime, year_stem: Stem, table: SolarTermTable
) -> tuple[Stem, Branch]:
    branch, _prev, _next = table.month_branch(instant)
    offset = MONTH_BRANCH_ORDER.index(branch)
    stem = STEMS[(STEM_INDEX[MONTH_STEM_START[year_stem]] + offset) % 10]
    return stem, branch


def build_month(year: int, month: int, table: SolarTermTable | None = None) -> dict:
    """Return a dict matching CalendarMonth for (year, month)."""
    table = table or get_table()
    days_in_month = _cal.monthrange(year, month)[1]

    term_marks = table.terms_in_civil_month(year, month, _KST)
    term_by_date = {d: name for d, name in term_marks}

    days = []
    for d in range(1, days_in_month + 1):
        the_date = date(year, month, d)
        instant = datetime(year, month, d, 12, 0, tzinfo=_KST)
        y_stem, y_branch = _year_ganji(instant, table)
        m_stem, m_branch = _month_ganji(instant, y_stem, table)
        d_stem, d_branch = day_ganzi(the_date)
        d_hanja, d_ko = _ganji(d_stem, d_branch)
        m_hanja, m_ko = _ganji(m_stem, m_branch)
        y_hanja, y_ko = _ganji(y_stem, y_branch)
        days.append({
            "date": the_date,
            "weekday": the_date.weekday(),
            "day_ganji": d_hanja, "day_ganji_ko": d_ko,
            "month_ganji": m_hanja, "month_ganji_ko": m_ko,
            "year_ganji": y_hanja, "year_ganji_ko": y_ko,
            "solar_term": term_by_date.get(the_date),
        })

    return {
        "year": year,
        "month": month,
        "days": days,
        "solar_terms": [{"date": d, "name": n} for d, n in term_marks],
    }
