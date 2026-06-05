"""Aggregate distributions + rooting + strength into a ForceAnalysis."""

from __future__ import annotations

from saju_shared_types.analysis import (
    FiveElementAnalysis,
    ForceAnalysis,
    RootingAnalysis,
    StrengthResult,
    TenGodAnalysis,
)
from saju_shared_types.pillars import FourPillarsResult

from .distribution.element_distribution import compute_element_distribution
from .distribution.ten_god_distribution import compute_ten_god_distribution
from .strength.rooting import compute_rooting
from .strength.strength_score import compute_strength, side_balance_score


def analyze(pillars: FourPillarsResult) -> ForceAnalysis:
    elements = compute_element_distribution(pillars)
    ten_gods = compute_ten_god_distribution(pillars)

    side = side_balance_score(ten_gods["groups"])
    rooting = compute_rooting(pillars, side)

    strength = compute_strength(
        pillars=pillars,
        ten_god_groups=ten_gods["groups"],
        root_score=rooting["root_score"],
        gongmang_branches=pillars.gongmang_branches,
    )
    strength.pop("_side_balance_score", None)
    strength["basis"] = {
        "deukryeong": rooting["deukryeong"],
        "deukji": rooting["deukji"],
        "deukse": rooting["deukse"],
        "tonggeun": rooting["tonggeun"],
    }

    return ForceAnalysis(
        five_elements=FiveElementAnalysis(**elements),
        ten_gods=TenGodAnalysis(**ten_gods),
        rooting=RootingAnalysis(**rooting),
        strength=StrengthResult(**strength),
    )
