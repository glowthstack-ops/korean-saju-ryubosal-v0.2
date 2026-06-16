"""원국 횡재 그릇 분석 (v2.2 Phase 1, 2026-06-16).

`force_analysis`(신강약·십성·뿌리)와 지장간을 재사용해 '재물을 담을 그릇' 구조만 판정한다.
운 발동은 보지 않는다(Phase 2). **당첨을 예측하지 않는다** — 같은 戊戌 구조는 비당첨자에게도
흔하므로, 본 분석은 잠재 구조(그릇)만 표면화하고 점수 확정은 캘리브레이션에 위임한다.

근거(로또 1등 당첨 사주 1984-10-31 戌시): 戊土 극신강 + 시주 壬 편재 투출 + 년지 子 정재 뿌리
+ 戌 지장간 辛(상관) 잠복(식상생재 통로) + 子(申子辰 水국 씨앗) + 戌×3(묘고 반복) 구조.
"""

from __future__ import annotations

from saju_shared_types.constants import STEM_ELEMENT
from saju_shared_types.enums import Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.wealth_capacity import WealthCapacity

# 일간 오행 → 극하는 오행(=재성). 戊土→水, 庚金→木 등.
_CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
# 재성 오행 → 삼합 글자 집합(土는 삼합국 없음 → 씨앗 미존재).
_TRINE = {
    "水": {"申", "子", "辰"}, "木": {"亥", "卯", "未"},
    "火": {"寅", "午", "戌"}, "金": {"巳", "酉", "丑"},
}
_STORAGE = {"辰", "戌", "丑", "未"}  # 묘고(墓庫) 지지
_WEALTH_GODS = {"편재", "정재"}
_OUTPUT_GODS = {"식신", "상관"}
# 오행 상생 — 일간 오행 → 생하는 오행(=식상). 戊土→金.
_GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
# 묘고 충 쌍(충개고) — 辰戌충·丑未충.
_STORAGE_CLASH_PAIRS = ({"辰", "戌"}, {"丑", "未"})


def _is_strong(band: str, gate_passed: bool) -> bool:
    """신강 계열 판정 — 강신 게이트 통과 또는 밴드에 '강'(신약 계열 제외)."""
    return gate_passed or ("강" in band and "약" not in band)


def analyze_wealth_capacity(result: ManseV2Result) -> WealthCapacity:
    """원국 횡재 그릇 6요소를 판정한다(운 미반영).

    Args:
        result: 만세 계산 결과(force_analysis·pillars 필수).

    Returns:
        WealthCapacity — 6플래그 + 종합 밴드 + 서술용 한글 라벨.
    """
    assert result.pillars is not None
    assert result.force_analysis is not None
    p = result.pillars
    fa = result.force_analysis
    pillars = [pil for pil in (p.year, p.month, p.day, p.hour) if pil is not None]
    day_pillar = p.day
    assert day_pillar is not None

    wealth_el = _CONTROLS[str(STEM_ELEMENT[Stem(day_pillar.stem)])]

    visible_wealth_stem = any(
        pil.stem_ten_god in _WEALTH_GODS for pil in pillars if pil.stem_ten_god
    )
    wealth_rooted = any(
        pil.branch_main_ten_god in _WEALTH_GODS
        or any(h.ten_god in _WEALTH_GODS for h in pil.hidden_stems)
        for pil in pillars
    )
    band = fa.strength.band
    gate_passed = bool(fa.strength.strong_chart_gate.get("passed"))
    body_can_hold = _is_strong(band, gate_passed) and (visible_wealth_stem or wealth_rooted)

    hidden_janggan_output = sum(
        1 for pil in pillars for h in pil.hidden_stems if h.ten_god in _OUTPUT_GODS
    )
    hidden_output = (
        bool(set(fa.ten_gods.hidden_only_ten_gods) & _OUTPUT_GODS)
        or hidden_janggan_output >= 2
    )

    branch_list = [pil.branch for pil in pillars]
    wealth_trine_seed = bool(set(branch_list) & _TRINE.get(wealth_el, set()))
    storage_repeat = any(branch_list.count(b) >= 2 for b in _STORAGE)

    core = visible_wealth_stem or wealth_rooted
    if body_can_hold and core and (wealth_rooted or wealth_trine_seed):
        capacity_band = "strong"
    elif core:
        capacity_band = "moderate"
    else:
        capacity_band = "weak"

    labels = [
        (body_can_hold, "신왕임재(재성 감당)"),
        (visible_wealth_stem, "재성 천간 투출"),
        (wealth_rooted, "재성 지지 뿌리"),
        (hidden_output, "암장 식상(식상생재 통로)"),
        (wealth_trine_seed, "재성국 삼합 씨앗"),
        (storage_repeat, "묘고 반복(충개고 잠재)"),
    ]
    flags = [label for ok, label in labels if ok]

    return WealthCapacity(
        wealth_element=wealth_el,
        body_can_hold=body_can_hold,
        visible_wealth_stem=visible_wealth_stem,
        wealth_rooted=wealth_rooted,
        hidden_output=hidden_output,
        wealth_trine_seed=wealth_trine_seed,
        storage_repeat=storage_repeat,
        capacity_band=capacity_band,
        flags=flags,
    )


def detect_wealth_activations(
    *,
    day_element: str,
    wealth_element: str,
    natal_branches: set[str],
    luck_branches: set[str],
    luck_stem_elements: set[str],
) -> list[str]:
    """한 시점(거버닝 스택)의 재물 발동을 판정한다 — **운 완성 경로 포함**(v2.2 Phase 2).

    원국에 그릇/씨앗이 없어도 운에서 완성되는 경우를 잡는다(2026-06-16 사용자 보완). 모든 발동은
    **운이 참여**해야 성립한다(원국 정적 구조만으로는 '발동'이 아니다).

    Args:
        day_element: 일간 오행(식상 오행 도출용).
        wealth_element: 재성 오행(WealthCapacity.wealth_element).
        natal_branches: 원국 4지지.
        luck_branches: 이 시점 거버닝 스택(대운·세운·월 등) 지지.
        luck_stem_elements: 거버닝 스택 천간 오행.

    Returns:
        성립한 발동 한글 라벨 목록(재성국 완성 / 묘고 충개고 / 식상생재).

    Note:
        단순 '재성 투간(운)'은 평범한 재물 운(base 스코어러가 이미 wealth_change로 생성)이라 **횡재
        발동으로 가산하지 않는다** — 횡재는 평범한 재성이 구조적으로 완성·개고·생재될 때 성립한다.
    """
    acts: list[str] = []
    all_branches = natal_branches | luck_branches

    trine = _TRINE.get(wealth_element, set())
    if trine and len(trine & all_branches) >= 3 and (trine & luck_branches):
        acts.append("재성국 완성")  # 원국+운 또는 운 단독으로 삼합 재성국 완성
    for pair in _STORAGE_CLASH_PAIRS:
        if pair <= all_branches and (pair & luck_branches):
            acts.append("묘고 충개고")  # 운이 개입한 辰戌/丑未 충 → 지장간 개고
            break
    output_el = _GENERATES.get(day_element, "")
    if output_el and output_el in luck_stem_elements and wealth_element in luck_stem_elements:
        # 운 천간에 식상·재성이 동시 투간 — 식상생재 흐름이 운에서 실제 작동.
        acts.append("식상생재")

    return acts
