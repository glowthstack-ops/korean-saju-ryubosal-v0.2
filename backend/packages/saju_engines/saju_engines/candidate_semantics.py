"""후보 의미론 공용 헬퍼 — 결실 뉘앙스·검토월 판정(채팅·리포트 공유, 2026-08-21).

context_reducer(채팅)와 report_event_input(리포트)이 같은 판정을 쓰도록 분리했다.
판정 규칙은 기존과 동일(이 파일은 이동·공유일 뿐 판정 변경 없음):
- 결실 뉘앙스: 천간 역할 × 지지 생극 — 흉천간 통관 순화 / ⚠계약·결실 불리 / ⚠길신 누설.
- 검토월: 공망 **충발**('공망 지연' 신호) 동반 시에만 — 전실·해소(합)는 '공망' 문자열이
  있어도 근거가 아니다(2026-08-21 확정 의미론, doc/v2_2/GONGMANG_HAP_SEMANTICS.md).
"""

from __future__ import annotations

from saju_manse_analysis.yongsin.operational_role_config import (
    is_favorable_role,
    is_unfavorable_role,
)

from saju_shared_types.constants import (
    BRANCH_ELEMENT,
    CONTROLS,
    GENERATES,
    STEM_ELEMENT,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.events import EventCandidate, Signal


def ganji_result_nuance(
    stem_el: str, branch_el: str, stem_role: str, fav_map: dict[str, str]
) -> tuple[str, str, str]:
    """그 기간 천간 역할 × 지지와의 생극으로 본 '결실(계약·실속)' 유불리 뉘앙스.

    Returns:
        (마커, 설명, 카테고리). 카테고리 ∈ {'unfavorable','tonggwan','leak',''}.
    """
    try:
        s_el, b_el = Element(stem_el), Element(branch_el)
    except ValueError:
        return "", "", ""
    branch_role = fav_map.get(branch_el, "")
    stem_gen_branch = GENERATES.get(s_el) == b_el  # 천간 → 지지 생
    branch_ctrl_stem = CONTROLS.get(b_el) == s_el  # 지지 → 천간 극
    if is_unfavorable_role(stem_role):
        if stem_gen_branch and is_favorable_role(branch_role):
            return (
                "↗통관 순화",
                "천간이 흉신이나 그 달 지지(용·희신)를 생하는 통관(관인상생)으로 순화 — "
                "흉이 일간을 돕는 쪽으로 흐른다(다만 천간 흉신이라 과한 낙관은 금물).",
                "tonggwan",
            )
        return (
            "⚠계약·결실 불리",
            "천간 흉신 — 사건이 일어나도 계약·결실·실속에 불리한 시기(우호 단정 금지).",
            "unfavorable",
        )
    if is_favorable_role(stem_role):
        if (stem_gen_branch and is_unfavorable_role(branch_role)) or branch_ctrl_stem:
            return (
                "⚠천간 길신 누설",
                "천간은 길신이나 그 달 지지로 누설·피극되어 결실·실속이 약화 — "
                "'좋은 달'로 과하게 단정하지 말 것.",
                "leak",
            )
    return "", "", ""


def review_month_from_signals(signals: list[Signal]) -> bool:
    """검토월 판정 — 공망 충발('공망 지연') 신호 동반 시에만 True."""
    return any("공망 지연" in (s.effect or "") for s in signals)


def candidate_semantics(
    c: EventCandidate, period_ganji: str, fav_map: dict[str, str] | None
) -> tuple[str, str, bool]:
    """후보 1건의 (뉘앙스 카테고리, 뉘앙스 설명, 검토월) — 채팅·리포트 공용 진입점."""
    cat = note = ""
    if fav_map and len(period_ganji) == 2:
        try:
            stem_el = str(STEM_ELEMENT[Stem(period_ganji[0])])
            branch_el = str(BRANCH_ELEMENT[Branch(period_ganji[1])])
        except ValueError:
            stem_el = branch_el = ""
        if stem_el and branch_el:
            _m, note, cat = ganji_result_nuance(
                stem_el, branch_el, fav_map.get(stem_el, ""), fav_map
            )
    return cat, note, review_month_from_signals(list(c.signals))
