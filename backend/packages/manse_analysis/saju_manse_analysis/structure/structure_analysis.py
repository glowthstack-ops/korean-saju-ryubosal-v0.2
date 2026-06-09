"""구조작용 집계: 합화 판정, 궁성, 안정도, volatility, structure_modifier.

`structure_modifier`는 strength_9_band 명세 §6 규칙을 합충형파해·병존·합화·공망으로
완성한다(Phase 2의 공망-only 잠정값을 대체).
"""

from __future__ import annotations

from dataclasses import dataclass

from saju_manse_core.pillars.gongmang import gongmang_branches
from saju_manse_core.relations import Relation
from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    CONTROLS,
    SEASON_ELEMENT_BY_MONTH,
    STEM_ELEMENT,
    hidden_stems_for,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Element, Stem, TenGod
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import (
    GongmangAnalysis,
    StabilityScores,
    StructuralInteraction,
    StructureAnalysis,
    TransformationCheck,
)

from .._chart import ROOT_BRANCH_WEIGHT, ROOT_HIDDEN_WEIGHT

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

# 합화(化) 가중 임계값 모델 — 월령+통근을 이진값이 아닌 가중 점수로 본다.
_CARDINAL = {Branch.JA, Branch.O, Branch.MYO, Branch.YU}  # 왕지(子午卯酉)
# 합 종류별 계수: 방합(계절세력) 최고, 육합(부부합)은 월령 없으면 化 어려워 감점.
_TRANSFORM_KIND_COEF = {
    "directional": 1.12,
    "three_harmony": 1.00,
    "half_harmony": 1.00,
    "stem_combination": 1.00,
    "six_combination": 0.80,
}
_T_FULL = 0.58  # 완전 합화(confirmed) 임계
_T_HALF = 0.40  # 가합(possible) 임계


def _target_root_ratio(target: Element, pillars: FourPillarsResult) -> float:
    """타깃 오행의 가중 통근 비율(0~1). 자리(월35·일30·시18·년12)×지장간 위계(정1.0·중0.6·여0.35).

    월지 정기(35) 1개를 1.0 기준으로 정규화한다.
    """
    positions = [
        ("year", pillars.year.branch),
        ("month", pillars.month.branch),
        ("day", pillars.day.branch),
    ]
    if pillars.hour is not None:
        positions.append(("hour", pillars.hour.branch))
    raw = 0.0
    for pos, b in positions:
        for hstem, htype, _w in hidden_stems_for(Branch(b)):
            if STEM_ELEMENT[hstem] == target:
                raw += ROOT_BRANCH_WEIGHT[pos] * ROOT_HIDDEN_WEIGHT[htype.value]
    return min(raw / 35.0, 1.0)


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
    rel: Relation,
    pillars: FourPillarsResult,
    month_branch: Branch,
    relations: list[Relation],
    heavenly_stems: set[Stem],
) -> TransformationCheck:
    target = Element(rel.transform_element)  # caller ensures non-None
    season_el = SEASON_ELEMENT_BY_MONTH[month_branch]
    season_match = season_el == target
    month_br_match = BRANCH_ELEMENT[month_branch] == target
    month_supports = season_match or month_br_match
    # 월령 지원 등급: 월지 오행 일치(1.0) > 계절 일치(0.7) > 없음(0.0).
    wol = 1.0 if month_br_match else (0.7 if season_match else 0.0)

    # 타깃 오행의 가중 통근(0~1) + 왕지가 월지일 때 가산(왕지월령 → 化 세력 극대화).
    root_ratio = _target_root_ratio(target, pillars)
    wangji_bonus = 0.15 if (month_branch in _CARDINAL and month_br_match) else 0.0
    coef = _TRANSFORM_KIND_COEF.get(rel.rel_type, 1.0)

    # 방해 요소(blockers): 합에 참여한 글자가 충/형으로 흔들리거나, 천간합 글자가
    # 다른 천간에 의해 극당하면 합화가 불완전해진다.
    blockers: list[str] = []
    member_set = set(rel.members)
    member_positions = set(rel.positions)
    disruptive = ("clash", "punishment", "self_punishment")
    for other in relations:
        if other is rel or other.rel_type not in disruptive:
            continue
        if member_set & set(other.members) or member_positions & set(other.positions):
            blockers.append(f"{other.rel_type}:{'·'.join(other.members)}")
    if rel.rel_type == "stem_combination":
        member_stems = {Stem(m) for m in rel.members}
        for stem in member_stems:
            for hv in heavenly_stems:
                if hv in member_stems:
                    continue
                if CONTROLS[STEM_ELEMENT[hv]] == STEM_ELEMENT[stem]:
                    blockers.append(f"극:{hv}→{stem}")
    blockers = sorted(set(blockers))

    # 가중 점수: (기본 + 월령등급 + 통근 + 왕지가산)·합종류계수 − blocker감산.
    score = (0.30 + 0.35 * wol + 0.25 * root_ratio + wangji_bonus) * coef - 0.15 * len(blockers)
    score = _clamp(score, 0.0, 0.95)
    # 완전 합화는 월령 지원이 전제(계절·월지). 가합(possible)은 통근만으로도 인정.
    confirmed = score >= _T_FULL and month_supports and not blockers
    possible = score >= _T_HALF and not blockers
    return TransformationCheck(
        members=rel.members,
        target_element=str(target),
        exists=True,
        possible=possible,
        confirmed=confirmed,
        confidence=round(score, 4),
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
    heavenly_stems = {
        Stem(p.stem) for p in (pillars.year, pillars.month, pillars.day, pillars.hour) if p
    }
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
            transformed.append(
                _transformation(rel, pillars, month_branch, relations, heavenly_stems)
            )

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

    gongmang = _gongmang_analysis(pillars, gongmang_branches)

    analysis = StructureAnalysis(
        interactions=interactions,
        transformed_candidates=transformed,
        palace_interactions=palace_interactions,
        amplifiers=amplifiers,
        stability=stability,
        volatility_score=volatility,
        gongmang=gongmang,
        structure_modifier=modifier,
        structure_modifier_breakdown=breakdown,
        calculation_trace={
            "stability_modifier_table": _STABILITY_EFFECT,
            "relation_count": len(relations),
        },
    )
    return StructureBundle(analysis, modifier, relation_stability)


def _affected_positions(pillars: FourPillarsResult, void: set[str]) -> list[str]:
    return [
        pos for pos in ("year", "month", "day", "hour")
        if getattr(pillars, pos) is not None and getattr(pillars, pos).branch in void
    ]


def _gongmang_analysis(
    pillars: FourPillarsResult, day_basis: list[str]
) -> GongmangAnalysis:
    """일공망(중심) + 년공망(참조). 일공망만 신강약/격국 보정에 사용한다."""
    year_basis = [
        str(b) for b in gongmang_branches(Stem(pillars.year.stem), Branch(pillars.year.branch))
    ]
    day_void, year_void = set(day_basis), set(year_basis)
    day_affected = _affected_positions(pillars, day_void)
    return GongmangAnalysis(
        day_basis_empty_branches=list(day_basis),
        day_affected_positions=day_affected,
        day_affected_palaces=[_PALACE[p] for p in day_affected if p in _PALACE],
        year_basis_empty_branches=year_basis,
        year_affected_positions=_affected_positions(pillars, year_void),
        primary_basis="day",
        activation_note=(
            "일공망 중심. 년공망은 참조. 원국 공망은 배경값이며 "
            "대운·세운·운에서 충/합으로 자극될 때 발동 가능."
        ),
    )


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

    # 주: 뿌리 지지의 충/공망은 rooting.root_score의 reliability(공망0.60·충0.75·둘다0.45)가
    # 전담한다. 여기서 root_clashed를 또 감산하면 사용자 §7의 이중 감산이 되므로 두지 않는다.
    # structure_modifier는 '전체 구조 불안정'(병존·자형·합화·궁성 공망)만 작게 반영한다.

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

    # 궁성 공망 — 단, 그 지지가 일간 뿌리면 공망 약화는 rooting.reliability가 전담하므로
    # 여기서 다시 감산하지 않는다(이중 반영 방지). 비root 지지의 궁성 공망만 반영.
    if pillars.day.branch in void and "day" not in root_positions:
        modifier -= 2
        breakdown.append("day_branch_void:-2")
    if pillars.month.branch in void and "month" not in root_positions:
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

    # relation_stability(안정도 0~1, 점수 아님) — 참고용 지표라 충/공망을 그대로 센다.
    clash_positions = {
        p for r in relations if r.rel_type in ("clash", "punishment") for p in r.positions
    }
    penalties = (
        int(pillars.day.branch in void)
        + int(pillars.month.branch in void)
        + int(bool(root_positions & clash_positions))
    )
    relation_stability = round(_clamp(1.0 - 0.15 * penalties, 0, 1), 4)
    return modifier, breakdown, relation_stability


def _generates(a: Element, b: Element) -> bool:
    from saju_shared_types.constants import GENERATES

    return GENERATES[a] == b
