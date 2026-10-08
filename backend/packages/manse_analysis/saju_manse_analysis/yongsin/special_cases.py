"""특수격 검사 (보수적): 합화/전왕/종격/통관/고립.

극단 명식을 일반 억부로 처리하지 않도록 억부보다 먼저 검사한다(명세 §3).
"""

from __future__ import annotations

from saju_shared_types.analysis import ForceAnalysis
from saju_shared_types.constants import CONTROLS, GENERATES
from saju_shared_types.enums import Element
from saju_shared_types.pillars import FourPillarsResult
from saju_shared_types.structure import StructureAnalysis
from saju_shared_types.yongsin import SpecialCaseCheck

from ..relations.hap_modes import detect_hwagi
from ..strength.follow_check import detect_follow
from .operational_role_config import DOMINANT_CONTROLLER_PRESENT_PCT


def detect_special_cases(
    force: ForceAnalysis,
    structure: StructureAnalysis,
    pillars: FourPillarsResult | None = None,
) -> dict[str, SpecialCaseCheck]:
    # 전왕/오행 과다 판단은 월령 보정 세력 기준. 폴백도 보정이 섞인 effective 대신
    # '원점수' 환경 분포(일간 제외)를 쓴다(통근/투간/공망 중복 반영 방지).
    fe = force.five_elements
    pct = fe.season_adjusted_element_strength or fe.distribution_environment
    band = force.strength.band
    root_score = force.strength.components.get("root_score", 0.0)

    # 합화/화기격(2026-10-08 데굴님 결정): 정본은 hap_modes.detect_hwagi(일간 천간합 3단계 + 滴天髓
    # 진화 조건). 구조작용의 TransformationCheck 는 성패·신강약 보조로만 남긴다.
    hwagi = detect_hwagi(pillars) if pillars is not None else None
    transformation = SpecialCaseCheck(
        detected=hwagi is not None,
        confidence=(0.85 if hwagi.kind == "real" else 0.45) if hwagi else 0.0,
        detail=(
            f"{hwagi.kind}:{hwagi.target_element}:{hwagi.name}:pair={''.join(hwagi.pair)}"
            f":partner={hwagi.partner_pos}"
            if hwagi else None
        ),
    )

    # 전왕/일행득기: 한 오행이 압도적이며 신강 계열.
    strongest_el = max(pct, key=lambda e: pct[e])
    maxpct = pct[strongest_el]
    dominant_detected = maxpct >= 60.0 and band in ("신강", "태신강")  # 7단계(2026-10-07)
    # E(2026-10-01): 압도 오행을 극하는 오행이 분포 임계 이상 남아 있으면 기세 집중이 깨져 진전왕이
    # 아니다 → detail 을 'pseudo:'로 표기(플래그 ON 시 build_yongsin 이 억부와 경쟁시킨다). 플래그
    # OFF 면 detail 표기만 바뀌고 판정은 기존과 같다.
    controller = next(e for e in Element if CONTROLS[e] == Element(strongest_el))
    ctrl_pct = pct.get(controller, 0.0)
    dominant_kind = (
        None if not dominant_detected
        else "pseudo" if ctrl_pct >= DOMINANT_CONTROLLER_PRESENT_PCT
        else "real"
    )
    dominant = SpecialCaseCheck(
        detected=dominant_detected,
        confidence=round(min(max((maxpct - 50) / 50, 0.0), 0.95), 4),
        detail=(
            f"{dominant_kind}:{strongest_el} {maxpct}%:ctrl={controller} {round(ctrl_pct, 1)}%"
            if dominant_kind else f"{strongest_el} {maxpct}%"
        ),
    )

    # 종격(從格) — 공통 판정기(strength.follow_check.detect_follow, 2026-10-08 데굴님 결정):
    # 격국(special_signal)과 같은 기준(비겁 뿌리 무근·압도 세력·인성 의지처·진종/가종). 옛
    # root_score<8 분기(인성 통근 포함)와 용신 전용 세력비 분기는 폐기.
    fc = detect_follow(force)
    follow = SpecialCaseCheck(
        detected=fc is not None,
        confidence=fc.confidence if fc else 0.0,
        detail=(
            f"{fc.kind}:{fc.group}:peer_root={fc.peer_root}:peer={fc.peer_ratio}"
            f":res={fc.resource_ratio}:dom={fc.dom_ratio}"
            if fc else f"peer_root={force.strength.components.get('peer_root_score', root_score)}"
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
