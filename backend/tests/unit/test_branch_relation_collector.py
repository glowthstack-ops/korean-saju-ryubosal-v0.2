"""지지 파괴 관계 수집기 회귀 (P1-b0, 2026-08-01).

`ganji_calendar.relation_hits` 를 실현도 파이프라인이 직접 소비하지 않는 이유를 여기서
고정한다 — 실측상 그 함수는 **운↔원국 전용**이라 원국 내부 충과 운↔운 충을 낼 수 없다.

    relation_hits(DAEWOON, "己", "酉", relations_to_chart=["충:酉-卯"], ...)
    → branch_clash  luck=daewoon:酉  natal=[(year, 卯)]

그리고 **탐지와 효과를 분리한다.** 충·형·파·해를 모두 수집하되 "형·파·해가 있으면 합화가
풀린다" 는 일반화는 하지 않는다. 근거가 확인된 것은 충뿐이다(사례의 巳亥冲·卯酉冲).
분리하지 않으면 사례 A 에서 차단 링크가 4건 → 20건으로 불어난다(실측).
"""

from __future__ import annotations

from saju_engines.branch_relation_collector import (
    BranchRelationKind,
    RelationScope,
    collect_branch_relation_instances,
)
from saju_engines.luck_relation_graph import RelationNode

# 사례 A: 丁卯 丁未 丙戌 戊戌 + 己酉 대운 + 癸未 세운
_NODES = (
    RelationNode("natal.year.branch:卯", "natal", "year", "branch", "卯", "木"),
    RelationNode("natal.month.branch:未", "natal", "month", "branch", "未", "土"),
    RelationNode("natal.day.branch:戌", "natal", "day", "branch", "戌", "土"),
    RelationNode("natal.hour.branch:戌", "natal", "hour", "branch", "戌", "土"),
    RelationNode("daewoon.branch:酉", "daewoon", "", "branch", "酉", "金"),
    RelationNode("sewoon.branch:未", "sewoon", "", "branch", "未", "土"),
)


def test_transit_to_natal_clash_is_collected_without_hand_building() -> None:
    """卯酉冲을 테스트가 손으로 만들지 않아도 산출된다."""
    got = collect_branch_relation_instances(nodes=_NODES)
    clash = [i for i in got if i.kind is BranchRelationKind.CLASH]
    assert len(clash) == 1
    assert clash[0].relation_family == "clash:卯酉"
    assert clash[0].scope is RelationScope.TRANSIT_TO_NATAL
    assert set(clash[0].member_node_ids) == {
        "natal.year.branch:卯", "daewoon.branch:酉",
    }


def test_natal_internal_scope_is_supported() -> None:
    """relation_hits 가 내지 못하는 원국 내부 관계를 낸다."""
    nodes = (
        RelationNode("natal.day.branch:子", "natal", "day", "branch", "子", "水"),
        RelationNode("natal.hour.branch:午", "natal", "hour", "branch", "午", "火"),
    )
    got = collect_branch_relation_instances(nodes=nodes)
    assert [i.scope for i in got] == [RelationScope.NATAL_INTERNAL]
    assert got[0].relation_family == "clash:午子"


def test_transit_to_transit_scope_is_supported() -> None:
    """대운↔세운 충도 낸다 — relation_hits 는 운 하나만 입력받는다."""
    nodes = (
        RelationNode("daewoon.branch:子", "daewoon", "", "branch", "子", "水"),
        RelationNode("sewoon.branch:午", "sewoon", "", "branch", "午", "火"),
    )
    got = collect_branch_relation_instances(nodes=nodes)
    assert [i.scope for i in got] == [RelationScope.TRANSIT_TO_TRANSIT]


def test_same_character_different_position_yields_distinct_instances() -> None:
    """같은 글자가 여러 자리에 있으면 자리마다 별개 인스턴스다."""
    nodes = (
        RelationNode("natal.day.branch:戌", "natal", "day", "branch", "戌", "土"),
        RelationNode("natal.hour.branch:戌", "natal", "hour", "branch", "戌", "土"),
        RelationNode("daewoon.branch:辰", "daewoon", "", "branch", "辰", "土"),
    )
    got = collect_branch_relation_instances(nodes=nodes)
    families = [i.relation_family for i in got]
    assert families.count("clash:戌辰") == 2      # 일지·시지 각각
    assert len({i.relation_id for i in got}) == len(got)


def test_only_clash_is_a_transformation_breaking_candidate() -> None:
    """충만 변환 해제 후보다 — 형·파·해는 수집하되 효과를 부여하지 않는다."""
    got = collect_branch_relation_instances(nodes=_NODES)
    kinds = {i.kind for i in got}
    assert BranchRelationKind.BREAK in kinds      # 戌未 파가 실제로 잡힌다
    assert BranchRelationKind.HARM in kinds       # 戌酉 해
    for inst in got:
        expected = inst.kind is BranchRelationKind.CLASH
        assert inst.breaks_transformation is expected, inst.relation_family


def test_scope_and_kind_filters_apply() -> None:
    got = collect_branch_relation_instances(
        nodes=_NODES,
        scopes=frozenset({RelationScope.TRANSIT_TO_NATAL}),
        relation_kinds=frozenset({BranchRelationKind.CLASH}),
    )
    assert all(i.scope is RelationScope.TRANSIT_TO_NATAL for i in got)
    assert all(i.kind is BranchRelationKind.CLASH for i in got)


def test_result_is_independent_of_node_order() -> None:
    import itertools

    sigs = set()
    for order in itertools.islice(itertools.permutations(_NODES), 12):
        got = collect_branch_relation_instances(nodes=order)
        sigs.add(tuple(i.relation_id for i in got))
    assert len(sigs) == 1


def test_stems_are_ignored() -> None:
    """천간 노드는 지지 관계 수집 대상이 아니다."""
    nodes = (
        RelationNode("natal.day.stem:丙", "natal", "day", "stem", "丙", "火"),
        RelationNode("natal.hour.stem:壬", "natal", "hour", "stem", "壬", "水"),
    )
    assert collect_branch_relation_instances(nodes=nodes) == ()


# ── relation_hits parity ────────────────────────────────────────────────


def test_parity_with_relation_hits_is_positional_expansion() -> None:
    """겹치는 범위에서 문자 관계는 같고, 신규 수집기는 자리별로 확장된다.

    차이를 자동으로 버그로 보지 않는다 — 이 경우는 POSITIONAL_EXPANSION 이다.
    """
    import datetime as dt

    from saju_api.services.manse_service import calculate
    from saju_engines.ganji_calendar import relation_hits
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.ganji_calendar import GanjiLevel

    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=dt.date(1987, 8, 5), birth_time="21:00",
        birth_place_name="서울", gender="male", reference_date=dt.date(2026, 8, 1),
    ))
    legacy = relation_hits(
        GanjiLevel.DAEWOON, "己", "酉",
        relations_to_chart=["충:酉-卯"], gongmang_activation=[], pillars=chart.pillars,
    )
    legacy_chars = {
        frozenset({"酉", *(n.branch for n in h.natal_refs if n.branch)})
        for h in legacy
    }
    mine = collect_branch_relation_instances(
        nodes=_NODES,
        scopes=frozenset({RelationScope.TRANSIT_TO_NATAL}),
        relation_kinds=frozenset({BranchRelationKind.CLASH}),
    )
    assert {frozenset(i.characters) for i in mine} == legacy_chars
