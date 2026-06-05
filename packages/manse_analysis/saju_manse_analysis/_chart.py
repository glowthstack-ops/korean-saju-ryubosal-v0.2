"""Internal helpers: decode a FourPillarsResult into stem/branch enums."""

from __future__ import annotations

from dataclasses import dataclass

from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import FourPillarsResult

# Position weights (오행/십성 effective distribution) — five_element spec §8.
STEM_POS_WEIGHT: dict[str, int] = {"year": 8, "month": 12, "day": 0, "hour": 10}
BRANCH_POS_WEIGHT: dict[str, int] = {"year": 12, "month": 28, "day": 24, "hour": 16}
HIDDEN_EFF_WEIGHT: dict[str, float] = {"main": 1.00, "middle": 0.60, "residual": 0.35}

# Root-score weights — strength_9_band spec §4 (distinct from distribution weights).
ROOT_BRANCH_WEIGHT: dict[str, int] = {"month": 35, "day": 30, "hour": 18, "year": 12}
ROOT_HIDDEN_WEIGHT: dict[str, float] = {"main": 1.00, "middle": 0.60, "residual": 0.35}
ROOT_STRENGTH_BY_POSITION: dict[str, str] = {
    "month": "strong", "day": "strong", "hour": "medium", "year": "weak",
}


@dataclass
class ChartView:
    day_master: Stem
    month_branch: Branch
    # position -> (stem, branch); hour omitted when time unknown
    stems: list[tuple[str, Stem]]  # (position, stem) including day
    branches: list[tuple[str, Branch]]
    heavenly_stems: set[Stem]
    heavenly_elements: set[str]


def view(pillars: FourPillarsResult) -> ChartView:
    items = [("year", pillars.year), ("month", pillars.month), ("day", pillars.day)]
    if pillars.hour is not None:
        items.append(("hour", pillars.hour))

    stems = [(pos, Stem(p.stem)) for pos, p in items]
    branches = [(pos, Branch(p.branch)) for pos, p in items]
    heavenly = {s for _, s in stems}
    from saju_shared_types.constants import STEM_ELEMENT

    return ChartView(
        day_master=Stem(pillars.day.stem),
        month_branch=Branch(pillars.month.branch),
        stems=stems,
        branches=branches,
        heavenly_stems=heavenly,
        heavenly_elements={str(STEM_ELEMENT[s]) for s in heavenly},
    )
