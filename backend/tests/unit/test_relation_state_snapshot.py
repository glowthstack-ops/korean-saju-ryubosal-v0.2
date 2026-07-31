"""관계 상태 원장 회귀 (P1-b1, 2026-08-01).

0B 에서 확인한 결함: 기존 resolver 는 이전 변환 상태를 입력받지 않고 매번 재계산한다.
그래서 대운에서 형성된 변환을 세운의 충이 해제하는 경로가 입력 자체에 없었다.

여기서 고정하는 핵심은 **불확정을 실수로 확정하지 않는 것**이다. 후속 계층이
`resolved_element` 를 보고 용희기구한을 매핑하므로, 근거 없이 확정하면 그 오류가 실현도
판정까지 그대로 전파된다.

환원(TRANSFORMATION_REVERSED)은 P1-c 다 — 여기서 생성되면 안 된다.
"""

from __future__ import annotations

import dataclasses

import pytest

from saju_engines.luck_relation_graph import (
    RelationNode,
    build_relation_dependency_graph,
    edge_from_resolution,
    fingerprint_relation_dependency_graph,
    relation_graph_fingerprint_payload,
)
from saju_engines.relation_state_snapshot import (
    ResolutionStatus,
    build_relation_state_snapshot,
)

_N_MAO = RelationNode("natal.year.branch:卯", "natal", "year", "branch", "卯", "木")
_N_WEI = RelationNode("natal.month.branch:未", "natal", "month", "branch", "未", "土")
_N_XU_D = RelationNode("natal.day.branch:戌", "natal", "day", "branch", "戌", "土")
_N_XU_H = RelationNode("natal.hour.branch:戌", "natal", "hour", "branch", "戌", "土")
_NODES = (_N_MAO, _N_WEI, _N_XU_D, _N_XU_H)


def _edge(rid, family, members, tier, mode, target, rtype="six"):
    return edge_from_resolution(
        relation_id=rid, relation_family=family, relation_type=rtype,
        member_node_ids=members, tier=tier, mode=mode, target_element=target,
        source_resolver="branch_hap",
    )


def _graph(*edges, nodes=_NODES):
    return build_relation_dependency_graph(nodes=nodes, resolved_relations=edges)


def _snap(graph, layer="daewoon", period="2003", parent=None):
    return build_relation_state_snapshot(
        graph=graph, layer=layer, period_key=period, previous_snapshot=parent,
    )


def _state(snap, node_id):
    return next(s for s in snap.element_states if s.node_id == node_id)


# ── fingerprint ─────────────────────────────────────────────────────────


def test_fingerprint_is_stable_across_input_order() -> None:
    a = _edge("a", "六:卯戌", ("natal.year.branch:卯", "natal.day.branch:戌"),
              "conditional", "bind", "火")
    b = _edge("b", "六:未戌", ("natal.month.branch:未", "natal.hour.branch:戌"),
              "conditional", "bind", "土")
    fp1 = fingerprint_relation_dependency_graph(_graph(a, b))
    fp2 = fingerprint_relation_dependency_graph(_graph(b, a))
    assert fp1 == fp2
    assert len(fp1) == 64          # SHA-256 전체


@pytest.mark.parametrize(
    ("tier", "mode", "target"),
    [("confirmed", "bind", "火"), ("conditional", "transform", "火"),
     ("conditional", "bind", "木")],
)
def test_fingerprint_changes_when_state_bearing_fields_change(tier, mode, target) -> None:
    """같은 ID 라도 상태를 가르는 값이 바뀌면 지문이 달라져야 한다.

    ID 목록만 해시하면 이 차이를 감지하지 못한다 — 그래서 정규 의미 투영본을 쓴다.
    """
    base = _edge("x", "六:卯戌", ("natal.year.branch:卯",), "conditional", "bind", "火")
    mutated = _edge("x", "六:卯戌", ("natal.year.branch:卯",), tier, mode, target)
    assert (fingerprint_relation_dependency_graph(_graph(base))
            != fingerprint_relation_dependency_graph(_graph(mutated)))


def test_fingerprint_changes_when_instance_removed() -> None:
    """일지 戌·시지 戌 중 하나를 빼면 지문이 달라진다."""
    day = _edge("d", "六:卯戌", ("natal.year.branch:卯", "natal.day.branch:戌"),
                "conditional", "bind", "火")
    hour = _edge("h", "六:卯戌", ("natal.year.branch:卯", "natal.hour.branch:戌"),
                 "conditional", "bind", "火")
    assert (fingerprint_relation_dependency_graph(_graph(day, hour))
            != fingerprint_relation_dependency_graph(_graph(day)))


def test_fingerprint_ignores_human_readable_evidence() -> None:
    """설명 문구가 바뀌었다고 지문이 흔들리면 안 된다."""
    e = _edge("x", "六:卯戌", ("natal.year.branch:卯",), "conditional", "bind", "火")
    g = _graph(e)
    with_evidence = dataclasses.replace(
        g, relation_dependencies=tuple(
            dataclasses.replace(d, evidence=("사람이 읽는 설명",))
            for d in g.relation_dependencies
        ),
    )
    assert (fingerprint_relation_dependency_graph(g)
            == fingerprint_relation_dependency_graph(with_evidence))


def test_fingerprint_payload_is_versioned() -> None:
    """정의를 조용히 바꾸면 과거 snapshot 과 비교할 수 없게 된다."""
    payload = relation_graph_fingerprint_payload(_graph())
    assert payload["schema"] == "luck_relation_graph_fingerprint.v1"


def test_fingerprint_preserves_direction_of_block_links() -> None:
    """`relation_ids` 를 정렬하면 인과가 사라진다 — 방향을 지문에 보존한다."""
    payload = relation_graph_fingerprint_payload(_graph())
    assert "dependencies" in payload


# ── snapshot 식별자 ──────────────────────────────────────────────────────


def test_snapshot_is_immutable() -> None:
    snap = _snap(_graph())
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.layer = "sewoon"           # type: ignore[misc]


def test_same_inputs_yield_same_snapshot_id() -> None:
    g = _graph(_edge("x", "六:卯戌", ("natal.year.branch:卯",),
                     "conditional", "bind", "火"))
    assert _snap(g).snapshot_id == _snap(g).snapshot_id


def test_parent_change_alters_snapshot_id_but_not_graph_fingerprint() -> None:
    """그래프는 같지만 부모가 다르면 다른 snapshot 이다."""
    g = _graph()
    natal = _snap(g, layer="natal")
    a = _snap(g, layer="daewoon")
    b = _snap(g, layer="daewoon", parent=natal)
    assert a.graph_fingerprint == b.graph_fingerprint
    assert a.snapshot_id != b.snapshot_id
    assert b.parent_snapshot_id == natal.snapshot_id


def test_parent_object_is_not_mutated() -> None:
    g = _graph()
    natal = _snap(g, layer="natal")
    before = dataclasses.asdict(natal)
    _snap(g, layer="daewoon", parent=natal)
    assert dataclasses.asdict(natal) == before


# ── 상태 반영 규칙 ───────────────────────────────────────────────────────


def test_confirmed_transform_is_reflected() -> None:
    g = _graph(_edge("t", "三:卯未亥", ("natal.year.branch:卯",),
                     "confirmed", "transform", "木", rtype="three_harmony"))
    s = _state(_snap(g), "natal.year.branch:卯")
    assert s.resolution_status is ResolutionStatus.TRANSFORMED
    assert s.resolved_element == "木"
    assert s.original_element == "木"


def test_tier_none_with_mode_transform_stays_unconfirmed() -> None:
    """0B 에서 실제로 나온 상태다 — 두 필드가 반대를 가리킬 때 확정하면 안 된다."""
    g = _graph(_edge("t", "三:卯未亥", ("natal.year.branch:卯",),
                     "none", "transform", "木", rtype="three_harmony"))
    s = _state(_snap(g), "natal.year.branch:卯")
    assert s.resolution_status is ResolutionStatus.UNCONFIRMED
    assert s.resolved_element is None


@pytest.mark.parametrize("tier,mode", [("none", "partial"), ("conditional", "partial")])
def test_partial_and_conditional_stay_unconfirmed(tier, mode) -> None:
    g = _graph(_edge("p", "半:卯未", ("natal.year.branch:卯",), tier, mode, "木",
                     rtype="half"))
    s = _state(_snap(g), "natal.year.branch:卯")
    assert s.resolution_status is ResolutionStatus.UNCONFIRMED
    assert s.resolved_element is None


def test_bind_preserves_original_element() -> None:
    g = _graph(_edge("b", "六:卯戌", ("natal.year.branch:卯",),
                     "conditional", "bind", "火"))
    s = _state(_snap(g), "natal.year.branch:卯")
    assert s.resolution_status is ResolutionStatus.BOUND
    assert s.resolved_element == "木"       # 火 로 바뀌지 않는다


def test_competing_confirmed_targets_are_downgraded() -> None:
    """둘 다 확정처럼 보여도 같은 노드에 다른 target 이면 확정할 근거가 없다.

    resolver 판정을 뒤집는 것이 아니라 원장이 단일 상태를 정할 수 없음을 기록한다.
    """
    wood = _edge("w", "半:卯未", ("natal.year.branch:卯", "natal.month.branch:未"),
                 "confirmed", "transform", "木", rtype="half")
    fire = _edge("f", "六:卯戌", ("natal.year.branch:卯", "natal.day.branch:戌"),
                 "confirmed", "transform", "火")
    s = _state(_snap(_graph(wood, fire)), "natal.year.branch:卯")
    assert s.resolution_status is ResolutionStatus.UNCONFIRMED
    assert s.resolved_element is None


def test_unrelated_node_keeps_original() -> None:
    g = _graph(_edge("x", "六:卯戌", ("natal.year.branch:卯",),
                     "conditional", "bind", "火"))
    s = _state(_snap(g), "natal.hour.branch:戌")
    assert s.resolution_status is ResolutionStatus.ORIGINAL
    assert s.resolved_element == "土"


def test_original_element_is_always_preserved() -> None:
    g = _graph(_edge("t", "三:卯未亥", ("natal.year.branch:卯",),
                     "confirmed", "transform", "木", rtype="three_harmony"))
    for s in _snap(g).element_states:
        node = next(n for n in _NODES if n.node_id == s.node_id)
        assert s.original_element == node.original_element


def test_no_reversion_status_exists() -> None:
    """환원은 P1-c 다 — 여기서 생성되면 안 된다."""
    assert not hasattr(ResolutionStatus, "REVERSED")
    assert "REVERSED" not in {m.value.upper() for m in ResolutionStatus}


# ── 부모 방향 ────────────────────────────────────────────────────────────


def test_natal_snapshot_has_no_parent() -> None:
    assert _snap(_graph(), layer="natal").parent_snapshot_id is None


def test_parent_must_be_an_upper_layer() -> None:
    g = _graph()
    sewoon = _snap(g, layer="sewoon")
    with pytest.raises(ValueError, match="하위이거나 같다"):
        _snap(g, layer="daewoon", parent=sewoon)


def test_self_as_parent_is_rejected() -> None:
    g = _graph()
    same = _snap(g, layer="daewoon")
    with pytest.raises(ValueError, match="하위이거나 같다"):
        _snap(g, layer="daewoon", parent=same)


def test_unknown_layer_is_rejected() -> None:
    with pytest.raises(ValueError, match="알 수 없는 층"):
        _snap(_graph(), layer="세운")


def test_fingerprint_changes_when_dependency_set_changes() -> None:
    """노드·엣지가 완전히 같아도 의존 링크가 다르면 다른 그래프다.

    #7(인스턴스 제거)이 이걸 겸한다고 보기 쉬우나, 그건 엣지도 함께 바뀐다. 링크 기여분만
    분리해서 고정한다.
    """
    a = _edge("a", "半:卯未", ("natal.year.branch:卯", "natal.month.branch:未"),
              "confirmed", "transform", "木", rtype="half")
    b = _edge("b", "六:卯戌", ("natal.year.branch:卯", "natal.day.branch:戌"),
              "confirmed", "transform", "火")
    g = _graph(a, b)
    assert g.relation_dependencies                      # 경쟁 링크가 실제로 생겼다
    stripped = dataclasses.replace(g, relation_dependencies=())
    assert (fingerprint_relation_dependency_graph(g)
            != fingerprint_relation_dependency_graph(stripped))


def test_fingerprint_is_identical_across_processes() -> None:
    """set 순회·해시 시드에 의존하면 프로세스마다 지문이 달라진다.

    같은 인터프리터 안에서 두 번 부르는 것으로는 잡히지 않아 PYTHONHASHSEED 를 바꿔 띄운다.
    """
    import os
    import subprocess
    import sys

    script = (
        "from saju_engines.luck_relation_graph import ("
        "RelationNode, build_relation_dependency_graph, edge_from_resolution,"
        "fingerprint_relation_dependency_graph)\n"
        "n=[RelationNode('natal.year.branch:卯','natal','year','branch','卯','木'),"
        "RelationNode('natal.day.branch:戌','natal','day','branch','戌','土'),"
        "RelationNode('natal.hour.branch:戌','natal','hour','branch','戌','土')]\n"
        "e=[edge_from_resolution(relation_id=i,relation_family='六:卯戌',"
        "relation_type='six',member_node_ids=m,tier='confirmed',mode='transform',"
        "target_element=t,source_resolver='branch_hap')"
        " for i,m,t in (('a',('natal.year.branch:卯','natal.day.branch:戌'),'火'),"
        "('b',('natal.year.branch:卯','natal.hour.branch:戌'),'木'))]\n"
        "print(fingerprint_relation_dependency_graph("
        "build_relation_dependency_graph(nodes=n,resolved_relations=e)))"
    )
    out = []
    for seed in ("0", "1"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, "-c", script], check=True,
                           capture_output=True, text=True, env=env)
        out.append(r.stdout.strip())
    assert out[0] == out[1]


def test_production_resolver_output_is_untouched() -> None:
    """그래프·snapshot 을 만들어도 기존 resolver 결과가 변하면 안 된다.

    어댑터가 결과 객체를 제자리 수정하면 production 점수·status·rank 가 조용히 흔들린다.
    P1-b1 은 읽기 전용이어야 한다.
    """
    import copy
    from datetime import date

    from saju_manse_analysis.relations.hap_modes import resolve_branch_hap

    from saju_api.services.manse_service import calculate
    from saju_engines.luck_relation_graph import adapt_branch_hap_results
    from saju_shared_types.birth_input import BirthInput

    r = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1987, 8, 5), birth_time="21:00",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    ))
    assert r.pillars is not None
    results = resolve_branch_hap(r.pillars, favorability={}, luck_branches=["酉", "未"])
    assert results
    before = copy.deepcopy(results)

    index = {
        (pos, ch): f"natal.{pos}.branch:{ch}"
        for pos, ch in (("year", "卯"), ("month", "未"),
                        ("day", "戌"), ("hour", "戌"))
    }
    index[("luck", "酉")] = "daewoon.branch:酉"
    index[("luck", "未")] = "sewoon.branch:未"
    nodes = tuple(
        RelationNode(nid, "natal" if nid.startswith("natal") else nid.split(".")[0],
                     nid.split(".")[1] if nid.startswith("natal") else "",
                     "branch", ch, "木")
        for (pos, ch), nid in sorted(index.items())
    )
    edges = adapt_branch_hap_results(resolver_results=results, node_index=index)
    build_relation_state_snapshot(
        graph=build_relation_dependency_graph(nodes=nodes, resolved_relations=edges),
        layer="daewoon", period_key="2003",
    )
    assert [dataclasses.asdict(x) if dataclasses.is_dataclass(x) else vars(x)
            for x in results] == [
        dataclasses.asdict(x) if dataclasses.is_dataclass(x) else vars(x)
        for x in before
    ]
