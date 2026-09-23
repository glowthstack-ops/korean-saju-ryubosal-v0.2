"""삼합국 관계 역학(P1, shadow-only) 단위 테스트 (2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §5. 년지 삼합국 오행 생극으로 관계 역학을 내되, 위/아래·
승패·서열 어휘를 쓰지 않고 오행 생극 경향으로만 서술한다. v1은 shadow-only(렌더/점수 미연결).
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.relationship_trine_dynamics import (
    _BRANCH_TO_TRINE,
    _relation,
    analyze_trine_dynamics,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Element


def _chart(date_: str, time_: str = "12:00", gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date_, birth_time=time_,
        birth_place_name="서울", gender=gender,
    ))


# 1. 지지 → 삼합국 매핑(4국·오행) 정확성.
def test_branch_to_trine_map() -> None:
    # 亥卯未=木, 申子辰=水, 寅午戌=火, 巳酉丑=金
    assert _BRANCH_TO_TRINE[Branch.HAE][0] == "亥卯未"
    assert _BRANCH_TO_TRINE[Branch.MYO][1] is Element.WOOD
    assert _BRANCH_TO_TRINE[Branch.JA][1] is Element.WATER
    assert _BRANCH_TO_TRINE[Branch.O][1] is Element.FIRE
    assert _BRANCH_TO_TRINE[Branch.YU][1] is Element.METAL
    # 삼합 3멤버는 같은 국명·오행.
    hae, myo, mi = (_BRANCH_TO_TRINE[b] for b in (Branch.HAE, Branch.MYO, Branch.MI))
    assert hae == myo == mi


# 2. 생극 관계 판정(5종).
def test_relation_kinds() -> None:
    assert _relation(Element.WOOD, Element.WOOD) == "same_group"
    assert _relation(Element.WOOD, Element.FIRE) == "generates_target"      # 木生火
    assert _relation(Element.WOOD, Element.WATER) == "generated_by_target"  # 水生木
    assert _relation(Element.WOOD, Element.EARTH) == "controls_target"      # 木克土
    assert _relation(Element.WOOD, Element.METAL) == "controlled_by_target"  # 金克木


# 3. 두 명식 분석 — self 관점, exposure=beta(2026-07-26 렌더 연결).
def test_analyze_self_perspective() -> None:
    a = _chart("1990-05-05")   # 庚午년 → 午=火국
    b = _chart("1992-11-12")   # 壬申년 → 申=水국
    dyn = analyze_trine_dynamics(a, b)
    assert dyn is not None
    assert dyn.base_element == "火" and dyn.target_element == "水"
    # 火 대비 水: 水克火 → 상대가 나를 극 → controlled_by_target.
    assert dyn.relation == "controlled_by_target"
    assert dyn.dynamics_label == "부담·긴장"
    assert dyn.exposure == "beta"


# 4. 중립성 — 승패·서열·위아래 어휘 미포함.
def test_no_ranking_words() -> None:
    from saju_engines.relationship_trine_dynamics import _RELATION_READING
    for _label, reading in _RELATION_READING.values():
        for banned in ("이긴다", "진다", "승패", "서열", "위", "아래", "못 이김", "상전"):
            assert banned not in reading


# 5. 연주 결측 graceful → None.
def test_missing_year_graceful() -> None:
    from types import SimpleNamespace
    stub = SimpleNamespace(pillars=SimpleNamespace(year=None))
    assert analyze_trine_dynamics(stub, stub) is None  # type: ignore[arg-type]
    assert analyze_trine_dynamics(SimpleNamespace(pillars=None), stub) is None  # type: ignore[arg-type]
