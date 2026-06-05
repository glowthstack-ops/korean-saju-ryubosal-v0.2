"""십이운성 (Twelve Life Stages) of a branch relative to the day master."""

from __future__ import annotations

from saju_shared_types.constants import (
    BRANCH_INDEX,
    JANGSAENG_BRANCH,
    STEM_YINYANG,
    TWELVE_STAGES,
)
from saju_shared_types.enums import Branch, Stem, YinYang


def twelve_unseong(day_master: Stem, branch: Branch) -> str:
    jangsaeng = JANGSAENG_BRANCH[day_master]
    direction = 1 if STEM_YINYANG[day_master] is YinYang.YANG else -1
    steps = (BRANCH_INDEX[branch] - BRANCH_INDEX[jangsaeng]) * direction % 12
    return TWELVE_STAGES[steps]
