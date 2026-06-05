"""공망 (Void branches) of the day pillar's 旬 (decade)."""

from __future__ import annotations

from saju_shared_types.constants import BRANCH_INDEX, BRANCHES, STEM_INDEX
from saju_shared_types.enums import Branch, Stem


def gongmang_branches(day_stem: Stem, day_branch: Branch) -> list[Branch]:
    """The two branches left unpaired in the day pillar's 旬 — its 공망."""
    s = STEM_INDEX[day_stem]
    b = BRANCH_INDEX[day_branch]
    head = (b - s) % 12  # branch of the 甲 that heads this 旬
    return [BRANCHES[(head + 10) % 12], BRANCHES[(head + 11) % 12]]
