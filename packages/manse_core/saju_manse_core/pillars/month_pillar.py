"""월주 (Month Pillar) — solar-term based branch + 둔월법 stem."""

from __future__ import annotations

from datetime import datetime

from saju_shared_types.constants import (
    MONTH_BRANCH_ORDER,
    MONTH_STEM_START,
    STEM_INDEX,
    STEMS,
)
from saju_shared_types.enums import Branch, Stem

from ..calendar.solar_terms import SolarTermTable


def month_pillar(
    absolute_instant: datetime,
    year_stem: Stem,
    table: SolarTermTable,
) -> tuple[Stem, Branch, tuple[datetime, str], tuple[datetime, str]]:
    """Return ``(stem, branch, prev_term, next_term)``.

    The branch is the solar month containing *absolute_instant* (tz-aware). The
    stem follows 둔월법: the year stem fixes 寅月's stem, then months run 順行.
    """
    branch, prev_term, next_term = table.month_branch(absolute_instant)
    start_stem = MONTH_STEM_START[year_stem]
    offset = MONTH_BRANCH_ORDER.index(branch)
    stem = STEMS[(STEM_INDEX[start_stem] + offset) % 10]
    return stem, branch, prev_term, next_term
