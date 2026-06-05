"""Hour-branch mapping and day-boundary / 자시 rules.

Hour branches cover two-hour spans with 子 straddling midnight (23:00–00:59):

    子 23-01  丑 01-03  寅 03-05  卯 05-07  辰 07-09  巳 09-11
    午 11-13  未 13-15  申 15-17  酉 17-19  戌 19-21  亥 21-23
"""

from __future__ import annotations

from datetime import datetime

from saju_shared_types.constants import BRANCHES
from saju_shared_types.enums import Branch


def hour_branch(dt: datetime) -> Branch:
    """The 지지 of the two-hour span containing *dt*."""
    return BRANCHES[((dt.hour + 1) // 2) % 12]


def day_pillar_offset(dt: datetime, day_boundary_rule: str, ja_hour_rule: str) -> int:
    """Days to add to the calendar date when forming the day pillar.

    With the traditional ``23:00`` boundary and standard 자시, a birth from 23:00
    onward belongs to the *next* day's pillar. Under 야자시/조자시 (``early_late_zi``)
    or the modern ``00:00`` boundary the calendar date is used as-is.
    """
    if day_boundary_rule == "23:00" and ja_hour_rule in ("standard_zi", "none"):
        return 1 if dt.hour >= 23 else 0
    return 0
