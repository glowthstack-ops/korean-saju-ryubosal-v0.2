"""60갑자 / JDN day-pillar anchoring."""

from __future__ import annotations

from datetime import date

from saju_manse_core.calendar.sexagenary_cycle import (
    day_ganzi,
    gregorian_to_jdn,
    year_ganzi,
)
from saju_shared_types.enums import Branch, Stem


def test_jdn_known_value() -> None:
    assert gregorian_to_jdn(date(2000, 1, 1)) == 2451545
    assert gregorian_to_jdn(date(1980, 11, 22)) == 2444566


def test_day_ganzi_known_dates() -> None:
    # 2000-01-01 = 戊午 (independent of the anchor used to derive the offset)
    assert day_ganzi(date(2000, 1, 1)) == (Stem.MU, Branch.O)
    # 1980-11-22 = 己亥 (golden fixture)
    assert day_ganzi(date(1980, 11, 22)) == (Stem.GI, Branch.HAE)


def test_year_ganzi() -> None:
    assert year_ganzi(1984) == (Stem.GAP, Branch.JA)
    assert year_ganzi(1980) == (Stem.GYEONG, Branch.SIN)
