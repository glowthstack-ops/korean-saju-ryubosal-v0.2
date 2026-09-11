"""연주 (Year Pillar) — anchored on the 입춘 boundary, not the calendar year."""

from __future__ import annotations

from datetime import datetime

from saju_shared_types.enums import Branch, Stem

from ..calendar.sexagenary_cycle import year_ganzi
from ..calendar.solar_terms import SolarTermTable


def year_pillar(
    absolute_instant: datetime, table: SolarTermTable
) -> tuple[Stem, Branch, int, datetime]:
    """Return ``(stem, branch, effective_year, lichun_instant)``.

    *absolute_instant* must be tz-aware. Births before that year's 입춘 belong to
    the previous sexagenary year.
    """
    civil_year = absolute_instant.astimezone(table.lichun_for_year(2000).tzinfo).year
    lichun = table.lichun_for_year(civil_year)
    if absolute_instant >= lichun:
        effective_year = civil_year
    else:
        effective_year = civil_year - 1
    stem, branch = year_ganzi(effective_year)
    return stem, branch, effective_year, lichun
