"""삼합국 관계 역학 (Trine Dynamics, P1, 2026-07-01 / v2 렌더 연결 2026-07-26).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §5. 두 사람의 **년지(띠) 삼합국** 오행을 생극으로 비교해
관계 역학을 낸다. **위/아래·승패·서열 금지 — 오행 생극 경향(편안/지원/끌림·받음/주도/부담)** 으로만.

**v2에서 궁합 블록 렌더에 연결한다**(chat `_compat_prompt_block` · report `compatibility_block`).
점수는 여전히 미개입 — 단일 신살/궁합 점수 엔진과 독립이며 기존 score·confidence·favorability를
변경하지 않는다(설명 레이어 전용). 노출 등급은 `beta`로, 서열 어휘 금지 가드를 함께 내보낸다.
"""

from __future__ import annotations

from saju_shared_types.constants import THREE_HARMONY
from saju_shared_types.enums import Branch, Element
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.trine_dynamics import TrineDynamics

# 오행 상생/상극(삼합국 오행은 木火金水만 — 土 삼합 없음).
_GENERATES: dict[Element, Element] = {
    Element.WOOD: Element.FIRE, Element.FIRE: Element.EARTH, Element.EARTH: Element.METAL,
    Element.METAL: Element.WATER, Element.WATER: Element.WOOD,
}
_CONTROLS: dict[Element, Element] = {
    Element.WOOD: Element.EARTH, Element.EARTH: Element.WATER, Element.WATER: Element.FIRE,
    Element.FIRE: Element.METAL, Element.METAL: Element.WOOD,
}

# 지지 → (삼합국 표시명, 삼합국 오행). 삼합 3멤버는 같은 국. 표시명은 관용 순서(생지-왕지-고지).
_SAENGJI = (Branch.IN, Branch.SIN, Branch.SA, Branch.HAE)
_GOJI = (Branch.JIN, Branch.SUL, Branch.CHUK, Branch.MI)
_BRANCH_TO_TRINE: dict[Branch, tuple[str, Element]] = {}
for _members, _elem, _wangji in THREE_HARMONY:
    _saeng = next(b for b in _members if b in _SAENGJI)
    _go = next(b for b in _members if b in _GOJI)
    _name = _saeng.value + _wangji.value + _go.value
    for _b in _members:
        _BRANCH_TO_TRINE[_b] = (_name, _elem)

# 생극 관계 → (dynamics_label, reading). 승패·서열 어휘 배제.
_RELATION_READING: dict[str, tuple[str, str]] = {
    "same_group": ("편안", "삼합국 결이 비슷해 익숙하고 편안한 관계 역학"),
    "generates_target": ("지원", "내가 상대에게 에너지를 써주거나 돕는 관계 역학"),
    "generated_by_target": ("끌림·받음", "상대에게 기대거나 끌리며 받는 관계 역학"),
    "controls_target": ("주도", "내가 방향·규칙을 쥐는 주도적 관계 역학"),
    "controlled_by_target": ("부담·긴장", "상대가 규칙이나 압박처럼 느껴질 수 있는 관계 역학"),
}


def _relation(self_el: Element, target_el: Element) -> str:
    """self 삼합국 오행 대비 target 오행의 생극 관계(self 관점)."""
    if self_el is target_el:
        return "same_group"
    if _GENERATES[self_el] is target_el:
        return "generates_target"
    if _GENERATES[target_el] is self_el:
        return "generated_by_target"
    if _CONTROLS[self_el] is target_el:
        return "controls_target"
    return "controlled_by_target"  # _CONTROLS[target_el] is self_el


def analyze_trine_dynamics(
    self_chart: ManseV2Result, partner_chart: ManseV2Result,
) -> TrineDynamics | None:
    """두 명식의 년지(띠) 삼합국 오행 생극으로 관계 역학을 낸다(설명 레이어 — 점수 미개입).

    Args:
        self_chart / partner_chart: 두 명식(년주 필수).

    Returns:
        TrineDynamics(self=base·partner=target, self 관점). 년주 부재면 None.
    """
    sp, pp = self_chart.pillars, partner_chart.pillars
    if sp is None or pp is None or sp.year is None or pp.year is None:
        return None
    base_group, base_el = _BRANCH_TO_TRINE[Branch(sp.year.branch)]
    target_group, target_el = _BRANCH_TO_TRINE[Branch(pp.year.branch)]
    relation = _relation(base_el, target_el)
    label, reading = _RELATION_READING[relation]
    return TrineDynamics(
        base_group=base_group, base_element=base_el.value,
        target_group=target_group, target_element=target_el.value,
        relation=relation, dynamics_label=label, reading=reading, exposure="beta",
    )


def trine_dynamics_lines(
    self_chart: ManseV2Result, partner_chart: ManseV2Result,
    self_label: str = "본인", partner_label: str = "상대",
) -> list[str]:
    """[삼합국 관계 역학] — 궁합 블록에 덧붙일 LLM 입력 지시문.

    띠(년지)가 같은 삼합국이면 결이 비슷하고, 생극이면 에너지가 한쪽으로 흐른다는
    **경향**만 말한다. `relative_sinsal_lines` 와 같은 설명 레이어 규약을 따른다 —
    엔진 확정값만 제시하고 서술 가드를 함께 내보내며 점수에는 개입하지 않는다.

    Args:
        self_chart / partner_chart: 두 명식(년주 필수).
        self_label / partner_label: 표시용 라벨.

    Returns:
        LLM 입력 지시문 목록. 년주가 없어 판정 불가면 빈 목록(추측 금지).
    """
    dyn = analyze_trine_dynamics(self_chart, partner_chart)
    if dyn is None:
        return []
    return [
        f"[삼합국 관계 역학] {self_label} {dyn.base_group}({dyn.base_element}) ↔ "
        f"{partner_label} {dyn.target_group}({dyn.target_element}) — "
        f"{dyn.dynamics_label}: {dyn.reading}",
        "띠 삼합국의 오행 경향일 뿐이므로 궁합의 결론으로 쓰지 말고 결·에너지 흐름의 "
        "보조 근거로만 쓸 것. 우열 판정·위아래 표현과 '띠가 안 맞아서 안 된다' 류 "
        "운명론은 금지한다.",
    ]
