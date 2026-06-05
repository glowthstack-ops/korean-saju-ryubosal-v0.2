"""Longitude correction, equation of time, and timezone resolution."""

from __future__ import annotations

from datetime import datetime

import pytest

from saju_manse_core.time_correction.equation_of_time import equation_of_time_minutes
from saju_manse_core.time_correction.longitude_correction import (
    longitude_correction_minutes,
    standard_meridian,
)
from saju_manse_core.time_correction.timezone_resolver import resolve


def test_standard_meridian_kst() -> None:
    assert standard_meridian(540) == 135.0


def test_longitude_correction_seoul() -> None:
    # Seoul 126.978°E against KST meridian 135°E ≈ -32.09 min
    assert longitude_correction_minutes(126.978, 540) == pytest.approx(-32.088, abs=1e-3)


def test_equation_of_time_november_positive() -> None:
    # EoT is strongly positive in late November (~+13..15 min).
    eot = equation_of_time_minutes(datetime(1980, 11, 22, 9, 0))
    assert 10 < eot < 17


def test_timezone_resolution_kst_no_dst() -> None:
    tz = resolve(datetime(1980, 11, 22, 9, 8), "Asia/Seoul")
    assert tz.total_offset_minutes == 540
    assert tz.dst_applied is False
    assert tz.local_time_status == "valid"


def test_timezone_resolution_ny_dst() -> None:
    # July in New York → EDT (DST active, UTC-4).
    tz = resolve(datetime(1990, 7, 1, 12, 0), "America/New_York")
    assert tz.total_offset_minutes == -240
    assert tz.dst_applied is True
    assert tz.standard_offset_minutes == -300
