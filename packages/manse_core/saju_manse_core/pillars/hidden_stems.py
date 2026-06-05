"""지장간 (hidden stems) for a branch, with pillar weights and ten gods."""

from __future__ import annotations

from saju_shared_types.constants import STEM_ELEMENT, hidden_stems_for, ten_god
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.pillars import HiddenStem


def hidden_stems(branch: Branch, day_master: Stem) -> list[HiddenStem]:
    result: list[HiddenStem] = []
    for stem, kind, weight in hidden_stems_for(branch):
        result.append(
            HiddenStem(
                stem=str(stem),
                element=str(STEM_ELEMENT[stem]),
                type=str(kind),
                weight=weight,
                ten_god=str(ten_god(day_master, stem)),
            )
        )
    return result
