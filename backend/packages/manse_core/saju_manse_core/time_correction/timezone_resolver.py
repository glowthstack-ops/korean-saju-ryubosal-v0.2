"""IANA timezone resolution: historical offset, DST, and validity status."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:  # tzdata version is recorded for reproducibility
    from importlib.metadata import version as _pkg_version

    TZDATA_VERSION: str | None = _pkg_version("tzdata")
except Exception:  # pragma: no cover - tzdata always present in practice
    TZDATA_VERSION = None


@dataclass
class TimezoneResolution:
    timezone: str
    total_offset_minutes: int  # standard + DST
    standard_offset_minutes: int  # without DST
    dst_offset_minutes: int
    dst_applied: bool
    local_time_status: str  # valid / ambiguous / nonexistent
    aware_datetime: datetime
    warnings: list[str] = field(default_factory=list)


def resolve(naive_local: datetime, iana_timezone: str) -> TimezoneResolution:
    """Resolve a naive local datetime against historical tz rules."""
    tz = ZoneInfo(iana_timezone)
    warnings: list[str] = []

    # Detect non-existent (spring-forward gap) and ambiguous (fall-back) times.
    status = "valid"
    earlier = naive_local.replace(tzinfo=tz, fold=0)
    later = naive_local.replace(tzinfo=tz, fold=1)

    def _roundtrips(candidate: datetime) -> bool:
        rt = candidate.astimezone(ZoneInfo("UTC")).astimezone(tz)
        return rt.replace(tzinfo=None) == naive_local

    earlier_valid = _roundtrips(earlier)
    later_valid = _roundtrips(later)
    if not earlier_valid and not later_valid:
        aware = later
        status = "nonexistent"
        warnings.append("local_time_nonexistent: time skipped by DST start")
    elif earlier.utcoffset() != later.utcoffset() and earlier_valid and later_valid:
        aware = earlier
        status = "ambiguous"
        warnings.append("dst_ambiguous: local time occurs twice; using earlier occurrence")
    else:
        aware = earlier if earlier_valid else later

    offset = aware.utcoffset() or timedelta(0)
    dst = aware.dst() or timedelta(0)

    total_minutes = int(offset.total_seconds() // 60)
    dst_minutes = int(dst.total_seconds() // 60)
    standard_minutes = total_minutes - dst_minutes

    return TimezoneResolution(
        timezone=iana_timezone,
        total_offset_minutes=total_minutes,
        standard_offset_minutes=standard_minutes,
        dst_offset_minutes=dst_minutes,
        dst_applied=dst_minutes != 0,
        local_time_status=status,
        aware_datetime=aware,
        warnings=warnings,
    )
