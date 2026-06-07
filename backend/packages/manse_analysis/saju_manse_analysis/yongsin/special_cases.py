"""특수격 검사 (보수적): 합화/전왕/종격/통관/고립.

극단 명식을 일반 억부로 처리하지 않도록 억부보다 먼저 검사한다(명세 §3).
"""

from __future__ import annotations

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.constants import CONTROLS
from saju_shared_types.enums import Element
from saju_shared_types.structure import StructureAnalysis
from saju_shared_types.yongsin import SpecialCaseCheck


def detect_special_cases(
    force: ForceAnalysis,
    structure: StructureAnalysis,
) -> dict[str, SpecialCaseCheck]:
    # 전왕/오행 과다 판단은 월령 보정 세력 기준. 폴백도 보정이 섞인 effective 대신
    # '원점수' 환경 분포(일간 제외)를 쓴다(통근/투간/공망 중복 반영 방지).
    fe = force.five_elements
    pct = fe.season_adjusted_element_strength or fe.distribution_environment
    band = force.strength.band
    root_score = force.strength.components.get("root_score", 0.0)

    # 합화/화기격: 구조작용에서 확정/가능 변환.
    confirmed = [t for t in structure.transformed_candidates if t.confirmed]
    any_conf = max((t.confidence for t in structure.transformed_candidates), default=0.0)
    transformation = SpecialCaseCheck(
        detected=bool(confirmed),
        confidence=round(max((t.confidence for t in confirmed), default=any_conf), 4),
        detail=(", ".join("".join(t.members) for t in confirmed) or None),
    )

    # 전왕/일행득기: 한 오행이 압도적이며 신강 계열.
    strongest_el = max(pct, key=lambda e: pct[e])
    maxpct = pct[strongest_el]
    dominant = SpecialCaseCheck(
        detected=maxpct >= 60.0 and band in ("신강", "태신강", "극신강"),
        confidence=round(min(max((maxpct - 50) / 50, 0.0), 0.95), 4),
        detail=f"{strongest_el} {maxpct}%",
    )

    # 종격: 극신약/태신약 + 뿌리 거의 없음.
    follow = SpecialCaseCheck(
        detected=band in ("극신약", "태신약") and root_score < 8.0,
        confidence=round(min(max((10 - root_score) / 10, 0.0), 0.9), 4) if root_score < 10 else 0.0,
        detail=f"root_score={root_score}",
    )

    # 통관: 서로 극하는 두 오행이 모두 강함(각 25%+).
    bridge_detail = None
    bridge_detected = False
    strong_els = [Element(e) for e, p in pct.items() if p >= 25.0]
    for a in strong_els:
        for b in strong_els:
            if a != b and CONTROLS[a] == b:
                bridge_detected = True
                bridge_detail = f"{a}↔{b}"
    tonggwan = SpecialCaseCheck(
        detected=bridge_detected,
        confidence=0.4 if bridge_detected else 0.0,
        detail=bridge_detail,
    )

    # 고립/병약: 부족 오행이 손상 관계에 노출.
    damaged_elements: set[str] = set()
    for i in structure.interactions:
        if i.relation_type in ("clash", "punishment", "self_punishment", "harm"):
            damaged_elements.update(i.affected_elements)
    deficient = set(force.five_elements.deficient_elements)
    isolated = deficient & damaged_elements
    isolation = SpecialCaseCheck(
        detected=bool(isolated),
        confidence=0.4 if isolated else 0.0,
        detail=", ".join(sorted(isolated)) or None,
    )

    return {
        "transformation_structure": transformation,
        "dominant_one_element": dominant,
        "follow_structure": follow,
        "bridge_required": tonggwan,
        "isolation_health": isolation,
    }
