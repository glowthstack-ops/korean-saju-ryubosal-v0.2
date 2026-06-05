"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from saju_manse_core.pillars.four_pillars import build_pillar
from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

PillarSpec = tuple[Stem, Branch]


@pytest.fixture
def make_pillars() -> Callable[..., FourPillarsResult]:
    """Factory: build a FourPillarsResult from (stem, branch) specs + day master."""

    def _make(
        year: PillarSpec,
        month: PillarSpec,
        day: PillarSpec,
        hour: PillarSpec,
        dm: Stem,
    ) -> FourPillarsResult:
        g = set(gongmang_branches(dm, day[1]))
        return FourPillarsResult(
            year=build_pillar(dm, year[0], year[1], "year", g),
            month=build_pillar(dm, month[0], month[1], "month", g),
            day=build_pillar(dm, day[0], day[1], "day", g),
            hour=build_pillar(dm, hour[0], hour[1], "hour", g),
            day_master=str(dm),
            gongmang_branches=[str(b) for b in g],
        )

    return _make
