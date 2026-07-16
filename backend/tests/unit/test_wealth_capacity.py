"""원국 횡재 그릇 분석 단위 테스트 (v2.2 Phase 1).

로또 1등 당첨 사주(1984-10-31 戌시 戊戌 일간) 구조 플래그 검출을 검증한다. **당첨 예측이 아니라
구조(그릇) 판정**임을 명확히 하기 위해, 그릇이 약한 대조 사주가 weak/부분 플래그로 갈리는 것도
함께 확인한다(같은 구조가 흔하다는 전제 — 확증편향 차단).
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.graph_builder import build_event_graph
from saju_engines.wealth_activation_modifier import WealthActivationModifier
from saju_engines.wealth_capacity import analyze_wealth_capacity, detect_wealth_activations
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventCandidateV2
from saju_shared_types.event_taxonomy_v2 import EventKeyV2
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.wealth_capacity import WealthCapacity

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


def _chart(date_: str, time_: str) -> ManseV2Result:
    return calculate(
        BirthInput(
            calendar_type="solar", birth_date=date_, birth_time=time_,
            birth_place_name="서울", gender="male",
        )
    )


def test_lottery_winner_full_capacity() -> None:
    """당첨 사주 — 6요소 전부 성립, 종합 strong, 재성 오행 水."""
    wc = analyze_wealth_capacity(_chart("1984-10-31", "19:30"))
    assert wc.wealth_element == "水"  # 戊土 일간 → 극하는 水가 재성
    assert wc.body_can_hold  # 극신강 + 재성 존재
    assert wc.visible_wealth_stem  # 시주 壬 편재 투출
    assert wc.wealth_rooted  # 년지 子 정재 뿌리
    assert wc.hidden_output  # 戌 지장간 辛(상관) 잠복 — 식상생재 통로
    assert wc.wealth_trine_seed  # 子 = 申子辰 水국 씨앗
    assert wc.storage_repeat  # 戌×3 묘고 반복
    assert wc.capacity_band == "strong"
    assert len(wc.flags) == 6


def test_capacity_is_structure_not_prediction() -> None:
    """그릇은 운 미반영 구조다 — 약한 사주는 weak/부분 플래그로 갈린다(예측 아님)."""
    weak = analyze_wealth_capacity(_chart("2001-07-15", "04:00"))
    assert weak.capacity_band in ("weak", "moderate")
    assert len(weak.flags) < 6  # 당첨 사주와 달리 일부만 성립


def test_graph_has_wealth_capacity_nodes_and_supports_edges() -> None:
    """그래프 RAG — 원국 횡재 그릇 노드 + windfall 해석 규칙으로의 supports 엣지(Phase 1)."""
    graph = build_event_graph(_DICTS)
    node_ids = {n.id for n in graph.nodes}
    assert "wealth_capacity_strong" in node_ids
    assert "wealth_capacity_moderate" in node_ids
    # 그릇(강) → 해석 규칙 supports 엣지가 1개 이상, 그 규칙은 windfall을 triggers 한다.
    cap_supported = {
        e.to for e in graph.edges
        if e.from_ == "wealth_capacity_strong" and e.type == "supports"
    }
    assert cap_supported
    windfall_rules = {
        e.from_ for e in graph.edges
        if e.to == "event_windfall" and e.type == "triggers"
    }
    assert cap_supported & windfall_rules  # 그릇이 받치는 규칙이 windfall을 유발


def test_detect_activations_luck_completion() -> None:
    """운 완성 경로 — 원국에 씨앗이 없어도 운 글자로 재성국 완성·충개고가 잡힌다(Phase 2)."""
    # 戊 일간(재성=水, 식상=金). 원국 지지에 재성 삼합(申子辰) 글자 없음.
    # 운에서 申·子·辰이 모두 들어오면 재성국 '운 완성'.
    acts = detect_wealth_activations(
        day_element="土", wealth_element="水",
        natal_branches={"寅", "卯", "巳", "午"},  # 재성국 씨앗 없음
        luck_branches={"申", "子", "辰"},  # 운에서 申子辰 완성
        luck_stem_elements={"金"},
    )
    assert "재성국 완성" in acts
    # 묘고 충개고 — 운 辰 + 운 戌(원국 묘고 없어도 운끼리 충).
    acts2 = detect_wealth_activations(
        day_element="土", wealth_element="水",
        natal_branches={"寅", "卯"}, luck_branches={"辰", "戌"}, luck_stem_elements=set(),
    )
    assert "묘고 충개고" in acts2
    # 정적 원국만(운 미참여)으로는 발동 아님.
    acts3 = detect_wealth_activations(
        day_element="土", wealth_element="水",
        natal_branches={"辰", "戌"}, luck_branches={"寅"}, luck_stem_elements=set(),
    )
    assert "묘고 충개고" not in acts3


def test_activation_modifier_boosts_only_wealth_keys() -> None:
    """발동 가산은 windfall/wealth_change에만, 그릇 배율 적용(weak도 0.5 인정)."""
    cap = WealthCapacity(
        wealth_element="水", body_can_hold=False, visible_wealth_stem=False,
        wealth_rooted=False, hidden_output=False, wealth_trine_seed=False,
        storage_repeat=False, capacity_band="weak", flags=[],
    )
    cands = [
        EventCandidateV2(event_key=EventKeyV2.WINDFALL, period="2030", score=50),
        EventCandidateV2(event_key=EventKeyV2.CAREER_CHANGE, period="2030", score=50),
    ]
    out = WealthActivationModifier.apply(cands, cap, ["재성국 완성"])
    wf = next(c for c in out if c.event_key == EventKeyV2.WINDFALL)
    cc = next(c for c in out if c.event_key == EventKeyV2.CAREER_CHANGE)
    assert wf.score > 50 and any(r.startswith("WEALTHACT_") for r in wf.reason_codes)
    assert cc.score == 50 and not any(r.startswith("WEALTHACT_") for r in cc.reason_codes)
    # 발동 없으면 무변.
    assert WealthActivationModifier.apply(cands, cap, []) == cands
