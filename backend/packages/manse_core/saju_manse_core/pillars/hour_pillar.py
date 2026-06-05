"""시주 (Hour Pillar) — 둔시법 stem + two-hour branch."""

from __future__ import annotations

from datetime import datetime

from saju_shared_types.constants import BRANCH_INDEX, HOUR_STEM_START, STEM_INDEX, STEMS
from saju_shared_types.enums import Branch, Stem

from ..time_correction.time_boundary import hour_branch


def hour_pillar(day_stem: Stem, local_dt: datetime) -> tuple[Stem, Branch]:
    """Hour pillar from the day stem and the (wall-clock) local datetime.

    The day stem fixes 子時's stem (둔시법); each successive branch advances the
    stem by one. 子 is index 0 so the branch offset is its own index.
    """
    branch = hour_branch(local_dt)
    start_stem = HOUR_STEM_START[day_stem]
    offset = BRANCH_INDEX[branch]  # 子=0 .. 亥=11
    stem = STEMS[(STEM_INDEX[start_stem] + offset) % 10]
    return stem, branch


def hour_pillar_for_branch(day_stem: Stem, branch: Branch) -> tuple[Stem, Branch]:
    """Hour pillar given a known hour branch (used for civil/true-solar compare)."""
    start_stem = HOUR_STEM_START[day_stem]
    offset = BRANCH_INDEX[branch]
    return STEMS[(STEM_INDEX[start_stem] + offset) % 10], branch
