"""특수격 검사 (보수적): 합화/전왕/종격/통관/고립.

극단 명식을 일반 억부로 처리하지 않도록 억부보다 먼저 검사한다(명세 §3).
"""

from __future__ import annotations

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.constants import CONTROLS, GENERATES
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

    # 종격(從格): 비겁(同氣)이 무근이고 식·재·관 한 세력이 압도할 때 일간이 그 세력에 순응.
    #   진종(眞從): 뿌리 자체가 거의 없음(root_score<8) — 강하게 성립(special 축 단독 주도).
    #   가종(假從): 비겁 무근이나 약한 인성이 남아 의지처가 있음 — 진위 불확실(억부와 경쟁·검증).
    # root_score는 비겁 통근 + 인성 생조를 합산하므로(인성만으로도 커짐) 종격 진위는
    # root_score 단독이 아니라 비겁/인성 세력비로 판별한다.
    tg = force.ten_gods.groups
    g_total = sum(tg.values()) or 1.0
    peer_ratio = tg.get("peer", 0.0) / g_total
    resource_ratio = tg.get("resource", 0.0) / g_total
    _pressure = {k: tg.get(k, 0.0) for k in ("output", "wealth", "officer")}
    dom_grp = max(_pressure, key=lambda k: _pressure[k])
    dom_ratio = _pressure[dom_grp] / g_total
    follow_kind: str | None = None
    if band in ("극신약", "태신약"):
        if root_score < 8.0:
            follow_kind = "real"  # 무근 → 진종(종세 포함)
        elif peer_ratio < 0.07 and dom_ratio >= 0.33:
            if resource_ratio < 0.12 and dom_ratio >= 0.40:
                follow_kind = "real"
            elif resource_ratio < 0.28:
                follow_kind = "pseudo"  # 약한 인성 의지처 → 가종
    follow = SpecialCaseCheck(
        detected=follow_kind is not None,
        confidence=(0.85 if follow_kind == "real" else 0.5) if follow_kind else 0.0,
        detail=(
            f"{follow_kind}:{dom_grp}:peer={round(peer_ratio, 3)}:res={round(resource_ratio, 3)}"
            if follow_kind
            else f"root_score={root_score}"
        ),
    )

    # 통관: 서로 극하는 두 오행이 모두 강함(각 25%+). 후보가 여럿이면
    # 대립축 강도와 통관 오행 부족도를 함께 봐 가장 선명한 쌍을 고른다.
    bridge_detail = None
    bridge_detected = False
    bridge_mediator: str | None = None
    bridge_score = -1.0
    strong_els = [Element(e) for e, p in pct.items() if p >= 25.0]
    for a in strong_els:
        for b in strong_els:
            if a != b and CONTROLS[a] == b:
                med = GENERATES[a]  # a生M, M生b → M이 상극을 상생으로 잇는 통관 오행
                med_pct = pct.get(str(med), 0.0)
                # min(a,b): 둘 다 강해야 통관 필요가 선명. max(15-med,0): 약신 가치.
                score = min(pct[str(a)], pct[str(b)]) + max(15.0 - med_pct, 0.0)
                if score > bridge_score:
                    bridge_score = score
                    bridge_detected = True
                    bridge_detail = f"{a}→{med}→{b}"
                    bridge_mediator = str(med) if med_pct < 15.0 else None
    tonggwan = SpecialCaseCheck(
        detected=bridge_detected,
        confidence=(
            round(min(0.35 + bridge_score / 100, 0.65), 4)
            if bridge_mediator else (0.4 if bridge_detected else 0.0)
        ),
        detail=(
            f"{bridge_detail}|통관용신={bridge_mediator}" if bridge_mediator else bridge_detail
        ),
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
