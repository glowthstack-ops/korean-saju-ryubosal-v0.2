"""운 관계 의존성 그래프 회귀 (P1-a, 2026-08-01).

기존 resolver 는 관계를 각각 독립적으로 돌려주지만, 하나의 지지가 여러 관계에 동시에
참여한다. 기준선 측정(0B)의 사례 A 가 그렇다 — 같은 `卯` 가 木 방향(卯未)과 火 방향(卯戌)에
얽혀 있고 `酉` 와 충하는데, 출력만 보면 서로 무관한 세 줄이다.

이 그래프는 **의존을 드러내는 것까지만** 한다. 승자·차단 확정·상태 전이·환원·점수는 P1-b
이후다. 그래서 링크 이름이 `POTENTIALLY_*` 다.

여기서 고정하는 것:

    자리 기반 node_id      일지 戌 과 시지 戌 을 구별한다
    관계 인스턴스 보존      卯戌 2건은 중복이 아니라 서로 다른 자리다
    경쟁 방향              같은 글자를 다른 오행으로 끌어가는 관계쌍
    잠재 차단              충이 결합과 글자를 공유할 때
    입력 순서 비의존성      기존 resolver 가 이미 만족 — 여기서도 깨지면 안 된다
    판정 금지              승자·실제 차단 여부를 정하지 않는다
"""

from __future__ import annotations

import pytest

from saju_engines.luck_relation_graph import (
    LINK_COMPETES_FOR_DIRECTION,
    LINK_POTENTIALLY_BLOCKED_BY,
    LINK_POTENTIALLY_DISRUPTED_BY,
    LINK_SAME_FAMILY_DISTINCT_PLACEMENT,
    RelationNode,
    build_relation_dependency_graph,
    edge_from_resolution,
)

# ── 사례 A: 丁卯 丁未 丙戌 戊戌 + 己酉 대운 + 癸未 세운 ────────────────────

_NODES = (
    RelationNode("natal.year.branch:卯", "natal", "year", "branch", "卯", "木"),
    RelationNode("natal.month.branch:未", "natal", "month", "branch", "未", "土"),
    RelationNode("natal.day.branch:戌", "natal", "day", "branch", "戌", "土"),
    RelationNode("natal.hour.branch:戌", "natal", "hour", "branch", "戌", "土"),
    RelationNode("daewoon.branch:酉", "daewoon", "", "branch", "酉", "金"),
    RelationNode("sewoon.branch:未", "sewoon", "", "branch", "未", "土"),
)


def _edge(rel_id, family, rel_type, members, tier, mode, target):
    return edge_from_resolution(
        relation_id=rel_id, relation_family=family, relation_type=rel_type,
        member_node_ids=members, tier=tier, mode=mode, target_element=target,
        source_resolver="branch_hap",
    )


#: 卯 하나가 세 관계에 동시 참여한다(卯未 木 · 卯戌 火 ×2 · 卯酉 충).
_MAO_WEI = _edge(
    "half:卯未@year+month+luck", "half:卯未", "half",
    ("natal.year.branch:卯", "natal.month.branch:未", "sewoon.branch:未"),
    "none", "partial", "木",
)
_MAO_XU_DAY = _edge(
    "six:卯戌@year+day", "six:卯戌", "six",
    ("natal.year.branch:卯", "natal.day.branch:戌"), "conditional", "bind", "火",
)
_MAO_XU_HOUR = _edge(
    "six:卯戌@year+hour", "six:卯戌", "six",
    ("natal.year.branch:卯", "natal.hour.branch:戌"), "conditional", "bind", "火",
)
_CLASH = edge_from_resolution(
    relation_id="clash:卯酉@year+luck", relation_family="clash:卯酉",
    relation_type="clash",
    member_node_ids=("natal.year.branch:卯", "daewoon.branch:酉"),
    tier=None, mode=None, target_element=None, source_resolver="branch_clash",
)

_RESOLVED = (_MAO_WEI, _MAO_XU_DAY, _MAO_XU_HOUR)


@pytest.fixture
def graph():
    return build_relation_dependency_graph(
        nodes=_NODES, resolved_relations=_RESOLVED, disruptive_relations=(_CLASH,),
    )


def _links(graph, link_type):
    return [d for d in graph.relation_dependencies if d.link_type == link_type]


# ── 공유 노드·자리 ───────────────────────────────────────────────────────


def test_same_mao_node_is_shared_across_relations(graph) -> None:
    """卯未·卯戌·卯酉가 같은 卯 node 를 공유한다 — 글자가 아니라 자리로 식별한다."""
    mao = "natal.year.branch:卯"
    for dep in graph.relation_dependencies:
        if {"half:卯未@year+month+luck", "six:卯戌@year+day"} <= set(dep.relation_ids):
            assert mao in dep.shared_node_ids


def test_day_and_hour_xu_are_distinct_nodes(graph) -> None:
    """일지 戌 과 시지 戌 은 별개다. 글자를 키로 쓰면 두 관계가 허위로 붙는다.

    실제로 자리를 무시하고 만들었을 때 링크가 9건 나왔고, 자리를 반영하자 7건이 됐다 —
    2건이 두 戌 을 뭉갠 허위 공유였다.
    """
    ids = {n.node_id for n in graph.nodes}
    assert "natal.day.branch:戌" in ids
    assert "natal.hour.branch:戌" in ids
    day_edge = next(e for e in graph.edges if e.relation_id == "six:卯戌@year+day")
    hour_edge = next(e for e in graph.edges if e.relation_id == "six:卯戌@year+hour")
    assert "natal.hour.branch:戌" not in day_edge.member_node_ids
    assert "natal.day.branch:戌" not in hour_edge.member_node_ids


def test_two_mao_xu_instances_are_preserved(graph) -> None:
    """卯戌 2건은 중복 제거 대상이 아니다 — 지우면 궁위 근거가 사라진다."""
    assert sum(1 for e in graph.edges if e.relation_family == "six:卯戌") == 2
    same = _links(graph, LINK_SAME_FAMILY_DISTINCT_PLACEMENT)
    assert len(same) == 1
    assert set(same[0].relation_ids) == {"six:卯戌@year+day", "six:卯戌@year+hour"}


# ── 경쟁·차단 ────────────────────────────────────────────────────────────


def test_competing_directions_are_linked(graph) -> None:
    """같은 卯 를 木 과 火 로 끌어가는 두 관계가 경쟁으로 연결된다."""
    competes = _links(graph, LINK_COMPETES_FOR_DIRECTION)
    pairs = {frozenset(d.relation_ids) for d in competes}
    assert frozenset({"half:卯未@year+month+luck", "six:卯戌@year+day"}) in pairs
    assert frozenset({"half:卯未@year+month+luck", "six:卯戌@year+hour"}) in pairs
    target = next(d for d in competes
                  if set(d.relation_ids) == {"half:卯未@year+month+luck",
                                             "six:卯戌@year+day"})
    assert set(target.target_elements) == {"木", "火"}


def test_clash_creates_potential_block_not_confirmed_block(graph) -> None:
    """충은 **잠재** 차단으로만 연결된다 — 실제 차단 판정은 P1-b 다."""
    blocked = _links(graph, LINK_POTENTIALLY_BLOCKED_BY)
    assert any(
        d.relation_ids == ("half:卯未@year+month+luck", "clash:卯酉@year+luck")
        for d in blocked
    )
    # 확정형 링크 이름은 존재해선 안 된다.
    assert not any(
        d.link_type in {"BLOCKED_BY", "DISRUPTED_BY"}
        for d in graph.relation_dependencies
    )


def test_block_link_direction_is_fixed(graph) -> None:
    """방향은 '방해받는 쪽 → 방해하는 쪽' 이다. 반대로 만들면 인과가 뒤집힌다."""
    for dep in _links(graph, LINK_POTENTIALLY_BLOCKED_BY):
        assert dep.relation_ids[1] == "clash:卯酉@year+luck"


def test_confirmed_transform_gets_disrupted_not_blocked() -> None:
    """이미 성립한 변환은 '차단' 이 아니라 '교란' 이다 — 두 상태를 구분한다."""
    done = _edge(
        "three:亥卯未@x", "three:亥卯未", "three_harmony",
        ("natal.year.branch:卯",), "confirmed", "transform", "木",
    )
    g = build_relation_dependency_graph(
        nodes=_NODES, resolved_relations=(done,), disruptive_relations=(_CLASH,),
    )
    assert len(_links(g, LINK_POTENTIALLY_DISRUPTED_BY)) == 1
    assert not _links(g, LINK_POTENTIALLY_BLOCKED_BY)


# ── 결정성 ───────────────────────────────────────────────────────────────


def test_result_is_independent_of_input_order() -> None:
    """입력 순서를 바꿔도 그래프가 같아야 한다. 기존 resolver 가 이미 만족하는 성질이라
    여기서 깨뜨리면 회귀다."""
    import itertools

    sigs = set()
    for order in itertools.permutations(_RESOLVED):
        g = build_relation_dependency_graph(
            nodes=_NODES, resolved_relations=order, disruptive_relations=(_CLASH,),
        )
        sigs.add(tuple(
            (d.link_type, d.relation_ids, d.shared_node_ids)
            for d in g.relation_dependencies
        ))
    assert len(sigs) == 1


def test_unrelated_relations_get_no_link() -> None:
    """글자를 공유하지 않으면 링크를 만들지 않는다 — 링크가 자동 생성되면 안 된다."""
    a = _edge("six:子丑@x", "six:子丑", "six", ("n1", "n2"), "conditional", "bind", "土")
    b = _edge("six:寅亥@y", "six:寅亥", "six", ("n3", "n4"), "conditional", "bind", "木")
    g = build_relation_dependency_graph(nodes=(), resolved_relations=(a, b))
    assert g.relation_dependencies == ()


# ── tier/mode 의미 충돌 관찰 ─────────────────────────────────────────────


def test_semantic_conflict_is_observed_without_changing_fields() -> None:
    """`tier=none · mode=transform` 을 관찰값으로 병기한다 — 기존 필드는 안 바꾼다.

    0B 에서 卯未亥 가 이 상태로 나왔다. 두 필드가 반대를 가리키는데, 지금 의미를 고치면
    영향 범위를 모른 채 기존 소비자를 흔든다.
    """
    e = _edge("three:卯未亥@x", "three:卯未亥", "three_harmony",
              ("natal.year.branch:卯",), "none", "transform", "木")
    assert e.existing_tier == "none"          # 원본 불변
    assert e.existing_mode == "transform"
    obs = e.normalized_observation
    assert obs["transformation_intent"] == "present"
    assert obs["transformation_completion"] == "unconfirmed"
    assert obs["semantic_conflict"] is True


def test_no_conflict_when_tier_and_mode_agree() -> None:
    e = _edge("six:卯戌@x", "six:卯戌", "six", ("n1",), "conditional", "bind", "火")
    assert e.normalized_observation["semantic_conflict"] is False


# ── 관측치 ───────────────────────────────────────────────────────────────


def test_metrics_summarize_without_leaking_characters(graph) -> None:
    """운영 로그에 간지 원문을 남기지 않기 위한 요약이다."""
    m = graph.metrics()
    assert m["node_count"] == 6
    assert m["edge_count"] == 4          # 합 3 + 충 1
    # fixture 에는 卯未·卯戌×2 만 있다(戌酉 방합 미포함) — 경쟁은 卯 를 공유하는 2쌍.
    assert m["competing_direction_count"] == 2
    assert m["potential_block_count"] == 3
    assert m["distinct_placement_family_count"] == 1
    assert all(isinstance(v, int) for v in m.values())


# ── 어댑터 (P1-b0) ───────────────────────────────────────────────────────


class _FakeHap:
    """resolve_branch_hap 결과의 최소 형태."""

    def __init__(self, kind, members, positions, tier, mode, target):
        self.kind = kind
        self.members = members
        self.positions = positions
        self.transform_tier = tier
        self.hap_mode = mode
        self.transform_element = target


_INDEX = {
    ("year", "卯"): "natal.year.branch:卯",
    ("month", "未"): "natal.month.branch:未",
    ("day", "戌"): "natal.day.branch:戌",
    ("hour", "戌"): "natal.hour.branch:戌",
    ("luck", "酉"): "daewoon.branch:酉",
    ("luck", "未"): "sewoon.branch:未",
}


def test_adapter_uses_positions_not_character_guessing() -> None:
    """자리로 노드를 고른다 — 글자만 보면 두 戌 이 하나로 뭉개진다."""
    from saju_engines.luck_relation_graph import adapt_branch_hap_results

    day, hour = adapt_branch_hap_results(
        resolver_results=[
            _FakeHap("six", ("卯", "戌"), ("year", "day"), "conditional", "bind", "火"),
            _FakeHap("six", ("卯", "戌"), ("year", "hour"), "conditional", "bind", "火"),
        ],
        node_index=_INDEX,
    )
    assert "natal.hour.branch:戌" not in day.member_node_ids
    assert "natal.day.branch:戌" not in hour.member_node_ids


def test_adapter_handles_members_positions_length_mismatch() -> None:
    """`members` 는 글자쌍, `positions` 는 참여 자리다 — 길이가 다른 것이 정상이다.

    半合 卯未 는 원국 未 와 운 未 가 모두 참여해 members 2 / positions 3 이 된다.
    zip 으로 짝지으면 ValueError 가 났다(실측).
    """
    from saju_engines.luck_relation_graph import adapt_branch_hap_results

    (edge,) = adapt_branch_hap_results(
        resolver_results=[
            _FakeHap("half", ("卯", "未"), ("year", "month", "luck"),
                     "none", "partial", "木"),
        ],
        node_index=_INDEX,
    )
    assert set(edge.member_node_ids) == {
        "natal.year.branch:卯", "natal.month.branch:未", "sewoon.branch:未",
    }


def test_adapter_preserves_raw_tier_and_mode() -> None:
    """어댑터는 판정하지 않는다 — 원시 의미를 그대로 옮긴다."""
    from saju_engines.luck_relation_graph import adapt_branch_hap_results

    (edge,) = adapt_branch_hap_results(
        resolver_results=[
            _FakeHap("three_harmony", ("卯", "未"), ("year", "month"),
                     "none", "transform", "木"),
        ],
        node_index=_INDEX,
    )
    assert edge.existing_tier == "none"
    assert edge.existing_mode == "transform"
    assert edge.normalized_observation["semantic_conflict"] is True


def test_adapter_raises_on_unknown_position() -> None:
    """자리 매칭 실패는 인덱스 구성 오류다 — 조용히 건너뛰면 관계가 사라진다."""
    import pytest as _pytest

    from saju_engines.luck_relation_graph import adapt_branch_hap_results

    with _pytest.raises(ValueError, match="node_index"):
        adapt_branch_hap_results(
            resolver_results=[
                _FakeHap("six", ("子", "丑"), ("year", "day"), "none", "bind", "土"),
            ],
            node_index=_INDEX,
        )


def test_non_breaking_relations_do_not_create_block_links() -> None:
    """형·파·해는 수집돼도 차단 링크를 만들지 않는다.

    분리하지 않으면 사례 A 에서 차단 링크가 4건 → 20건으로 불어난다(실측).
    """
    from saju_engines.branch_relation_collector import collect_branch_relation_instances
    from saju_engines.luck_relation_graph import edges_from_branch_relations

    instances = collect_branch_relation_instances(nodes=_NODES)
    disruptive = edges_from_branch_relations(instances)
    g = build_relation_dependency_graph(
        nodes=_NODES, resolved_relations=_RESOLVED, disruptive_relations=disruptive,
    )
    blocked = _links(g, LINK_POTENTIALLY_BLOCKED_BY)
    assert blocked, "충에 대한 차단 링크는 있어야 한다"
    for dep in blocked:
        assert dep.relation_ids[1].startswith("clash:")
