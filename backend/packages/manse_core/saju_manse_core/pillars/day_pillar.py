"""일주 (Day Pillar) — JDN-based 60갑자 with day-boundary adjustment."""

from __future__ import annotations

from datetime import datetime, timedelta

from saju_shared_types.enums import Branch, Stem

from ..calendar.sexagenary_cycle import day_ganzi
from ..time_correction.time_boundary import day_pillar_offset


def day_pillar(
    final_local: datetime,
    day_boundary_rule: str,
    ja_hour_rule: str,
) -> tuple[Stem, Branch]:
    """Day pillar for the (wall-clock) *final_local* datetime.

    A birth past the configured day boundary rolls onto the next day's pillar.
    """
    offset = day_pillar_offset(final_local, day_boundary_rule, ja_hour_rule)
    effective_date = (final_local + timedelta(days=offset)).date()
    return day_ganzi(effective_date)
