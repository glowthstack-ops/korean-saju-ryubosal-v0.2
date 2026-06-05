"""Solar-term table loader and lookup.

The table is pre-generated offline (``scripts/generate_solar_terms.py``) so the
runtime engine has no astronomical dependency and is fully deterministic. Each
entry stores an absolute UTC instant; comparisons against a tz-aware birth
instant are therefore correct regardless of birth timezone.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from saju_shared_types.enums import Branch

# The 12 month-defining terms (節), in 황경 order starting at 입춘 (315°), each
# paired with the solar month branch it opens.
MONTH_TERMS: dict[str, Branch] = {
    "입춘": Branch.IN, "경칩": Branch.MYO, "청명": Branch.JIN, "입하": Branch.SA,
    "망종": Branch.O, "소서": Branch.MI, "입추": Branch.SIN, "백로": Branch.YU,
    "한로": Branch.SUL, "입동": Branch.HAE, "대설": Branch.JA, "소한": Branch.CHUK,
}

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "solar_terms"
    / "solar_terms_1900_2100.json"
)


class SolarTermTable:
    """In-memory, time-sorted view of the solar-term table."""

    def __init__(self, version: str, entries: list[tuple[datetime, str]]):
        self.version = version
        # entries sorted ascending by instant
        self._instants = [e[0] for e in entries]
        self._names = [e[1] for e in entries]

    @classmethod
    def from_json(cls, path: Path | None = None) -> SolarTermTable:
        path = path or _DEFAULT_PATH
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            (datetime.fromisoformat(item["datetime_utc"]), item["term"])
            for item in data["terms"]
        ]
        entries.sort(key=lambda e: e[0])
        return cls(version=data["version"], entries=entries)

    def _to_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            raise ValueError("solar-term lookup requires a tz-aware datetime")
        return dt.astimezone(UTC)

    def surrounding_terms(
        self, dt: datetime
    ) -> tuple[tuple[datetime, str], tuple[datetime, str]]:
        """Return ``((prev_instant, prev_name), (next_instant, next_name))``."""
        u = self._to_utc(dt)
        i = bisect_right(self._instants, u)
        if i == 0 or i >= len(self._instants):
            raise ValueError(f"datetime {dt} is outside the solar-term table range")
        return (
            (self._instants[i - 1], self._names[i - 1]),
            (self._instants[i], self._names[i]),
        )

    def month_branch(
        self, dt: datetime
    ) -> tuple[Branch, tuple[datetime, str], tuple[datetime, str]]:
        """Resolve the solar month branch governing instant *dt*.

        Walks back from *dt* to the most recent month-defining 節.
        """
        u = self._to_utc(dt)
        i = bisect_right(self._instants, u) - 1
        while i >= 0:
            name = self._names[i]
            if name in MONTH_TERMS:
                prev = (self._instants[i], name)
                nxt = (self._instants[i + 1], self._names[i + 1])
                return MONTH_TERMS[name], prev, nxt
            i -= 1
        raise ValueError(f"no governing month term found for {dt}")  # pragma: no cover

    def lichun_for_year(self, year: int) -> datetime:
        """The 입춘 instant whose calendar year (UTC) equals *year*."""
        for inst, name in zip(self._instants, self._names, strict=False):
            if name == "입춘" and inst.year == year:
                return inst
        raise ValueError(f"입춘 for {year} not in table")  # pragma: no cover


@lru_cache(maxsize=1)
def get_table() -> SolarTermTable:
    return SolarTermTable.from_json()
