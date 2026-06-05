"""구조작용 집계: 합화 판정, 궁성, 안정도, volatility, structure_modifier.

`structure_modifier`는 strength_9_band 명세 §6 규칙을 합충형파해·병존·합화·공망으로
완성한다(Phase 2의 공망-only 잠정값을 대체).
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_manse_core.relations import Relation
from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    SEASON_ELEMENT_BY_MONTH,
    STEM_ELEMENT,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Element, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import (
    StabilityScores,
    StructuralInteraction,
    StructureAnalysis,
    TransformationCheck,
)

_PALACE = {
    "year": "뿌리·가족궁", "month": "직업·환경궁", "day": "배우자궁", "hour": "자녀·결과궁",
}
_HARMONIOUS = {
    "stem_combination", "six_combination", "three_harmony", "half_harmony", "directional",
}
_STABILITY_EFFECT = {
    "clash": -0.12, "punishment": -0.10, "harm": -0.08, "break": -0.08,
    "self_punishment": -0.12,
}
_SEVERITY = {
    "clash": "high", "punishment": "medium", "self_punishment": "medium",
    "three_harmony": "medium", "directional": "medium",
}
_VOLATILITY = {
    "clash": 3.0, "punishment": 2.0, "self_punishment": 2.0, "break": 1.0, "harm": 1.0,
}
_ALLY = {TenGod.BIGYEON, TenGod.GEOMJAE, TenGod.JEONGIN, TenGod.PYEONIN}
_PEER = {TenGod.BIGYEON, TenGod.GEOMJAE}


@dataclass
class StructureBundle:
    analysis: StructureAnalysis
    structure_modifier: float
    relation_stability: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _affected(rel: Relation, dm: Stem) -> tuple[list[str], list[str]]:
    elements: set[str] = set()
    ten_gods: set[str] = set()
    for m in rel.members:
        try:
            br = Branch(m)
            elements.add(str(BRANCH_ELEMENT[br]))
            ten_gods.add(str(ten_god(dm, main_hidden_stem(br))))
        except ValueError:
            st = Stem(m)
            elements.add(str(STEM_ELEMENT[st]))
            if st != dm:
                ten_gods.add(str(ten_god(dm, st)))
    return sorted(elements), sorted(ten_gods)


def _transformation(
    rel: Relation, pillars: FourPillarsResult, month_branch: Branch
) -> TransformationCheck:
    target = Element(rel.transform_element)  # type: ignore[arg-type]
    season_el = SEASON_ELEMENT_BY_MONTH[month_branch]
    month_supports = season_el == target or BRANCH_ELEMENT[month_branch] == target

    branches = [pillars.year.branch, pillars.month.branch, pillars.day.branch]
    if pillars.hour is not None:
        branches.append(pillars.hour.branch)
    root_exists = any(
        BRANCH_ELEMENT[Branch(b)] == target or STEM_ELEMENT[main_hidden_stem(Branch(b))] == target
        for b in branches
    )
    blockers: list[str] = []
    confidence = 0.3 + 0.3 * month_supports + 0.2 * root_exists
    confirmed = month_supports and root_exists and not blockers
    if confirmed:
        confidence += 0.2
    return TransformationCheck(
        members=rel.members,
        target_element=str(target),
        exists=True,
        possible=month_supports or root_exists,
        confirmed=confirmed,
        confidence=round(min(confidence, 0.95), 4),
        blockers=blockers,
    )


def analyze_structure(
    pillars: FourPillarsResult,
    relations: list[Relation],
    day_master: Stem,
    root_positions: set[str],
    gongmang_branches: list[str],
) -> StructureBundle:
    month_branch = Branch(pillars.month.branch)
    interactions: list[StructuralInteraction] = []
    amplifiers: list[StructuralInteraction] = []
    palace_interactions: list[dict] = []
    transformed: list[TransformationCheck] = []

    for rel in relations:
        elements, ten_gods = _affected(rel, day_master)
        palaces = [_PALACE[p] for p in rel.positions if p in _PALACE]
        effect = _STABILITY_EFFECT.get(rel.rel_type, 0.05 if rel.rel_type in _HARMONIOUS else 0.0)
        item = StructuralInteraction(
            relation_type=rel.rel_type,
            scope=rel.scope,
            positions=rel.positions,
            members=rel.members,
            palaces=palaces,
            affected_elements=elements,
            affected_ten_gods=ten_gods,
            transform_element=rel.transform_element,
            severity=_SEVERITY.get(rel.rel_type, "low"),
            stability_effect=effect,
            notes=rel.notes,
        )
        if rel.rel_type in ("stem_duplication", "branch_duplication", "gan_yeo_ji_dong"):
            amplifiers.append(item)
        else:
            interactions.append(item)
        if len(palaces) >= 2:
            palace_interactions.append(
                {"relation": rel.rel_type, "positions": rel.positions, "palaces": palaces}
            )
        if rel.transform_element is not None and rel.rel_type in (
            "stem_combination", "six_combination", "three_harmony", "directional"
        ):
            transformed.append(_transformation(rel, pillars, month_branch))

    # 안정도
    all_effects = sum(i.stability_effect for i in interactions)
    month_effects = sum(
        i.stability_effect for i in interactions if "month" in i.positions
    )
    root_effects = sum(
        i.stability_effect
        for i in interactions
        if set(i.positions) & root_positions and i.stability_effect < 0
    )
    stability = StabilityScores(
        yongsin_stability=round(_clamp(1.0 + all_effects, 0, 1), 4),
        geokguk_stability=round(_clamp(1.0 + month_effects, 0, 1), 4),
        root_stability=round(_clamp(1.0 + root_effects, 0, 1), 4),
    )
    volatility = round(
        sum(_VOLATILITY.get(i.relation_type, 0.0) for i in interactions), 2
    )

    modifier, breakdown, relation_stability = _structure_modifier(
        pillars, relations, day_master, root_positions, gongmang_branches, transformed
    )

    analysis = StructureAnalysis(
        interactions=interactions,
        transformed_candidates=transformed,
        palace_interactions=palace_interactions,
        amplifiers=amplifiers,
        stability=stability,
        volatility_score=volatility,
        structure_modifier=modifier,
        structure_modifier_breakdown=breakdown,
        calculation_trace={
            "stability_modifier_table": _STABILITY_EFFECT,
            "relation_count": len(relations),
        },
    )
    return StructureBundle(analysis, modifier, relation_stability)


def _structure_modifier(
    pillars: FourPillarsResult,
    relations: list[Relation],
    dm: Stem,
    root_positions: set[str],
    gongmang_branches: list[str],
    transformed: list[TransformationCheck],
) -> tuple[float, list[str], float]:
    breakdown: list[str] = []
    modifier = 0.0
    void = set(gongmang_branches)
    dm_el = STEM_ELEMENT[dm]

    clash_positions = {
        p for r in relations if r.rel_type in ("clash", "punishment") for p in r.positions
    }
    root_clashed = bool(root_positions & clash_positions)

    if root_clashed and len(root_positions) == 1:
        modifier -= 6
        breakdown.append("only_root_damaged:-6")
    elif root_clashed:
        modifier -= 4
        breakdown.append("day_master_root_clashed:-4")

    # 비겁 병존 → 일간 직접 강화
    for r in relations:
        if r.rel_type == "stem_duplication":
            st = Stem(r.members[0])
            if ten_god(dm, st) in _PEER:
                modifier += 3
                breakdown.append("strong_peer_duplication:+3")
                break

    # 강한 인성 뿌리(월/일지 본기 인성)
    for pos in ("month", "day"):
        pillar = getattr(pillars, pos)
        main_el = STEM_ELEMENT[main_hidden_stem(Branch(pillar.branch))]
        from saju_shared_types.constants import GENERATES

        if GENERATES[main_el] == dm_el and main_el != dm_el:
            modifier += 2
            breakdown.append("strong_resource_support:+2")
            break

    if pillars.day.branch in void:
        modifier -= 2
        breakdown.append("day_branch_void:-2")
    if pillars.month.branch in void:
        modifier -= 2
        breakdown.append("month_branch_void:-2")

    # 확정 합화의 일간 방향성
    for t in transformed:
        if not t.confirmed:
            continue
        tg_group_supports = Element(t.target_element) == dm_el or (
            _generates(Element(t.target_element), dm_el)
        )
        if tg_group_supports:
            modifier += 3
            breakdown.append("transformation_supports_day_master:+3")
        else:
            modifier -= 3
            breakdown.append("transformation_against_day_master:-3")
        break

    # 비겁/인성 뿌리 자리의 자형
    for r in relations:
        if r.rel_type == "self_punishment" and set(r.positions) & root_positions:
            modifier -= 2
            breakdown.append("self_punishment_on_support_root:-2")
            break

    modifier = _clamp(modifier, -10, 10)

    penalties = (
        int(pillars.day.branch in void)
        + int(pillars.month.branch in void)
        + int(root_clashed)
    )
    relation_stability = round(_clamp(1.0 - 0.15 * penalties, 0, 1), 4)
    return modifier, breakdown, relation_stability


def _generates(a: Element, b: Element) -> bool:
    from saju_shared_types.constants import GENERATES

    return GENERATES[a] == b
