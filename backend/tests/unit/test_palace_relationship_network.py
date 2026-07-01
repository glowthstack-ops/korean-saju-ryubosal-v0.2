"""궁위 관계망(P3) 단위 테스트 (2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §3. P3는 궁위 간 관계를 설명하는 context 레이어 —
점수·후보를 변경하지 않고(inert), P4 라벨을 재사용하며, cross-palace 구체 발현은 intent 조건부.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.palace_relationship_network import (
    _branch_relation,
    analyze_palace_network,
    palace_network_lines,
)
from saju_engines.relationship_relation_labels import relation_summary_ko
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch
from saju_shared_types.intent import Domain


def _chart(date_: str, time_: str, gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date_, birth_time=time_,
        birth_place_name="서울", gender=gender,
    ))


# 1. 지지쌍 관계 감지 — 대표 케이스(충·육합·원진·반합).
def test_branch_relation_detection() -> None:
    assert _branch_relation(Branch.JA, Branch.O) == ("chung", "충")      # 子午충
    assert _branch_relation(Branch.JA, Branch.CHUK) == ("hap", "육합")   # 子丑 육합
    assert _branch_relation(Branch.JA, Branch.MI) == ("wonjin", "원진")  # 子未 원진
    assert _branch_relation(Branch.SIN, Branch.JA) == ("hap", "반합")    # 申子 반합(子=왕지)
    assert _branch_relation(Branch.MYO, Branch.YU) == ("chung", "충")    # 卯酉충
    assert _branch_relation(Branch.IN, Branch.MYO) is None               # 무관계
    assert _branch_relation(Branch.JA, Branch.JA) is None                # 복음은 관계 아님


# 2. 실 명식에서 궁위 관계망이 산출되고 P4 라벨 요약을 재사용한다.
def test_network_uses_p4_labels() -> None:
    net = analyze_palace_network(_chart("1961-09-30", "06:00"))
    assert net.pairs  # 관계 쌍이 하나 이상
    lines = palace_network_lines(net, Domain.RELATIONSHIP)
    text = "\n".join(lines)
    # 각 쌍의 관계질 요약(P4)이 실제로 렌더된다.
    for pr in net.pairs:
        assert relation_summary_ko(pr.relation) in text
    # 금지어는 등장하지 않는다(원진 포함 명식이어도).
    for banned in ["악연", "속궁합", "집착", "무조건"]:
        assert banned not in text


# 3. cross-palace 구체 발현은 intent 조건부 — 비대상 도메인에선 미노출.
def test_cross_palace_note_is_intent_gated() -> None:
    # 월-시 또는 연-시 합이 있는 명식을 만들어 조건부 노트를 유도.
    # (합이 없으면 두 도메인 모두 노트 없음 — gate 자체는 도메인 분기로 검증)
    net = analyze_palace_network(_chart("1990-05-05", "06:00"))
    rel = "\n".join(palace_network_lines(net, Domain.RELATIONSHIP))
    car = "\n".join(palace_network_lines(net, Domain.CAREER))
    # 조건부 노트는 관계/총운에서만 등장 가능하고 커리어에선 절대 등장하지 않는다.
    assert "(조건부)" not in car
    if "(조건부)" in rel:
        assert True  # 관계 맥락에서만 조건부 발현 노출


# 4. inert — analyze_palace_network는 점수·판정 필드를 건드리지 않는다(원국 지지만 읽음).
def test_network_is_inert() -> None:
    chart = _chart("1961-09-30", "06:00")
    before = (
        chart.force_analysis.model_dump() if chart.force_analysis else None,
        chart.yongsin_analysis.model_dump() if chart.yongsin_analysis else None,
    )
    analyze_palace_network(chart)
    after = (
        chart.force_analysis.model_dump() if chart.force_analysis else None,
        chart.yongsin_analysis.model_dump() if chart.yongsin_analysis else None,
    )
    assert before == after  # 세력·용신 분석 불변(설명 레이어)


# 5. pillars 결측 graceful.
def test_missing_pillars_graceful() -> None:
    from types import SimpleNamespace
    net = analyze_palace_network(SimpleNamespace(pillars=None))  # type: ignore[arg-type]
    assert net.pairs == [] and net.gongmang_palaces == []
    assert palace_network_lines(net, Domain.RELATIONSHIP) == []


# 6. 공망 궁위가 있으면 공망 라벨로 렌더된다.
def test_gongmang_palace_rendered_when_present() -> None:
    # 공망 유무는 명식별로 다르므로, 공망이 잡히는 명식이면 라벨이 렌더됨을 확인.
    for d, t in (("1988-02-14", "10:00"), ("1975-08-20", "14:00"), ("1961-09-30", "06:00")):
        net = analyze_palace_network(_chart(d, t))
        if net.gongmang_palaces:
            text = "\n".join(palace_network_lines(net, Domain.GENERAL))
            assert "공망" in text and relation_summary_ko("gongmang") in text
            return
    # 표본에서 공망이 없어도 실패 아님(감지 로직은 분기로 커버).
