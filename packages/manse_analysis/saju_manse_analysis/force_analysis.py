"""Chart-level analysis orchestrator: distributions → 통근 → 구조작용 → 신강약 → 격국."""

from __future__ import annotations

from dataclasses import dataclass

from saju_manse_core.relations import detect
from saju_shared_types.analysis import (
    FiveElementAnalysis,
    ForceAnalysis,
    RootingAnalysis,
    StrengthResult,
    TenGodAnalysis,
)
from saju_shared_types.enums import Stem
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import GeokgukResult, StructureAnalysis

from .distribution.element_distribution import compute_element_distribution
from .distribution.ten_god_distribution import compute_ten_god_distribution
from .strength.rooting import compute_rooting
from .strength.strength_score import compute_strength, side_balance_score
from .structure.geokguk import detect_geokguk
from .structure.structure_analysis import analyze_structure


@dataclass
class ChartAnalysis:
    force: ForceAnalysis
    structure: StructureAnalysis
    geokguk: GeokgukResult


def analyze(pillars: FourPillarsResult) -> ForceAnalysis:
    """Force analysis only (distributions + 통근 + 신강약). Kept for convenience."""
    return analyze_chart(pillars).force


def analyze_chart(pillars: FourPillarsResult) -> ChartAnalysis:
    dm = Stem(pillars.day.stem)

    elements = compute_element_distribution(pillars)
    ten_gods = compute_ten_god_distribution(pillars)

    side = side_balance_score(ten_gods["groups"])
    rooting = compute_rooting(pillars, side)
    root_positions = {r["position"] for r in rooting["roots"]}

    relations = detect(pillars)
    bundle = analyze_structure(
        pillars=pillars,
        relations=relations,
        day_master=dm,
        root_positions=root_positions,
        gongmang_branches=pillars.gongmang_branches,
    )

    strength = compute_strength(
        pillars=pillars,
        ten_god_groups=ten_gods["groups"],
        root_score=rooting["root_score"],
        structure_modifier=bundle.structure_modifier,
        relation_stability=bundle.relation_stability,
    )
    strength.pop("_side_balance_score", None)
    strength["basis"] = {
        "deukryeong": rooting["deukryeong"],
        "deukji": rooting["deukji"],
        "deukse": rooting["deukse"],
        "tonggeun": rooting["tonggeun"],
    }

    force = ForceAnalysis(
        five_elements=FiveElementAnalysis(**elements),
        ten_gods=TenGodAnalysis(**ten_gods),
        rooting=RootingAnalysis(**rooting),
        strength=StrengthResult(**strength),
    )
    geokguk = detect_geokguk(pillars, dm, bundle.analysis, pillars.gongmang_branches)
    return ChartAnalysis(force=force, structure=bundle.analysis, geokguk=geokguk)
