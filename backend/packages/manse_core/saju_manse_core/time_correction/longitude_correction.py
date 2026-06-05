"""Longitude correction (경도 보정): mean solar time offset from standard time.

1° of longitude == 4 minutes of time. The standard meridian is derived from the
*standard* (non-DST) UTC offset, so any DST hour must already be removed by the
caller before this correction is applied.
"""

from __future__ import annotations


def standard_meridian(standard_offset_minutes: int) -> float:
    """Reference meridian (degrees east) for a timezone's standard UTC offset."""
    return standard_offset_minutes / 60 * 15


def longitude_correction_minutes(longitude: float, standard_offset_minutes: int) -> float:
    """Minutes to add to standard time to obtain local mean solar time."""
    return 4.0 * (longitude - standard_meridian(standard_offset_minutes))
