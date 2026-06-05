"""60갑자 (sexagenary cycle) indexing and Julian Day Number helpers.

Day-pillar anchoring: the ganzi index of a civil date is ``(JDN + 49) % 60``
with index 0 = 甲子. This offset is derived from the KASI-verified golden anchor
1980-11-22 = 己亥 (index 35) and independently confirmed by 2000-01-01 = 戊午.
"""

from __future__ import annotations

from datetime import date

from saju_shared_types.constants import BRANCHES, STEMS
from saju_shared_types.enums import Branch, Stem

GANZI_JDN_OFFSET = 49


def gregorian_to_jdn(d: date) -> int:
    """Julian Day Number (integer, at noon) for a proleptic Gregorian date."""
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return (
        d.day
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )


def ganzi_from_index(index: int) -> tuple[Stem, Branch]:
    index %= 60
    return STEMS[index % 10], BRANCHES[index % 12]


def ganzi_index(stem: Stem, branch: Branch) -> int:
    """Inverse of :func:`ganzi_from_index` (Chinese Remainder over 10 and 12)."""
    s = STEMS.index(stem)
    b = BRANCHES.index(branch)
    for n in range(60):
        if n % 10 == s and n % 12 == b:
            return n
    raise ValueError(f"invalid ganzi combination: {stem}{branch}")  # pragma: no cover


def day_ganzi(d: date) -> tuple[Stem, Branch]:
    """Day-pillar stem/branch for civil date *d* (before any 자시 boundary shift)."""
    return ganzi_from_index(gregorian_to_jdn(d) + GANZI_JDN_OFFSET)


def year_ganzi(year: int) -> tuple[Stem, Branch]:
    """Year-pillar stem/branch (1984 = 甲子). Caller applies the 입춘 boundary."""
    return ganzi_from_index((year - 1984) % 60)
