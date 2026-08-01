"""원국→대운→세운 상태 체인 회귀 (P1-b2, 2026-08-01).

P1-b1.5 가 남긴 두 계약을 지킨다.

    frame 은 graph 와 snapshot 을 함께 들고 있어야 한다 — P1-c 는 이전 상태와 현재 충을
    둘 다 본다. parent_snapshot_id 만으로는 부모 내용을 찾을 수 없다.

    대운 지지 == 세운 지지인 해도 조립에 성공해야 한다. 12년에 한 번 오는 정상 시기를
    shadow 단계에서 빼두면 production 승격 시 데이터 공백이 그대로 남는다.

여기서 판정하지 않는 것: 어느 합이 이겼는지, 충이 합화를 풀었는지, 환원 성립 여부.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from saju_manse_analysis.relations.hap_modes import resolve_branch_hap

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines import relation_state_chain as rsc
from saju_engines.branch_relation_collector import BranchRelationKind
from saju_engines.luck_relation_graph import (
    LINK_POTENTIALLY_DISRUPTED_BY,
    RelationNode,
)
from saju_engines.relation_projection import (
    LuckNodeIndex,
    build_layer_projections,
    enumerate_cross_layer_harmony_candidates,
)
from saju_engines.relation_state_chain import (
    RelationStateAssemblyError,
    ShadowFailureKind,
    assemble_relation_state_chain,
    relation_state_chain_shadow,
)
from saju_engines.relation_state_snapshot import ResolutionStatus
from saju_shared_types.birth_input import BirthInput

_PERIODS = {"natal": "natal", "daewoon": "2003", "sewoon": "2003"}


def _node(layer: str, position: str, ch: str, element: str) -> RelationNode:
    node_id = f"{layer}.{position}.branch:{ch}" if position else f"{layer}.branch:{ch}"
    return RelationNode(node_id, layer, position, "branch", ch, element)


_NATAL = (
    _node("natal", "year", "卯", "木"), _node("natal", "month", "未", "土"),
    _node("natal", "day", "戌", "土"), _node("natal", "hour", "戌", "土"),
)


class _Hap:
    """resolver 결과 스텁 — `BranchHapLike` 계약만 만족하면 된다."""

    def __init__(self, kind, members, positions, tier, mode, target):
        self.kind, self.members, self.positions = kind, members, positions
        self.transform_tier, self.hap_mode, self.transform_element = tier, mode, target


def _real_resolver():
    r = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1987, 8, 5), birth_time="21:00",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    ))
    assert r.pillars is not None

    def call(luck_branches=None):
        return resolve_branch_hap(
            r.pillars, favorability={}, luck_branches=list(luck_branches or []),
        )
    return call


def _chain(daewoon: str | None, sewoon: str | None, resolver=None):
    return assemble_relation_state_chain(
        natal_nodes=_NATAL,
        daewoon_nodes=(_node("daewoon", "", daewoon, "土"),) if daewoon else (),
        sewoon_nodes=(_node("sewoon", "", sewoon, "土"),) if sewoon else (),
        resolve_branch_hap=resolver or _real_resolver(), period_keys=_PERIODS,
    )


# ── 동일 지지 충돌 ───────────────────────────────────────────────────────


def test_identical_daewoon_and_sewoon_branch_assembles() -> None:
    """대운 未 + 세운 未 — 기간을 제외하지 않고 조립에 성공한다."""
    chain = _chain("未", "未")
    assert [f.layer for f in chain.frames] == ["natal", "daewoon", "sewoon"]
    assert chain.failure_kind is None


def test_identical_branches_stay_distinct_nodes() -> None:
    """두 未 가 하나로 뭉개지면 층 승계가 엉뚱한 자리를 물려받는다."""
    nodes = _chain("未", "未").terminal_frame.graph.nodes
    ids = sorted(n.node_id for n in nodes if n.character == "未")
    assert ids == ["daewoon.branch:未", "natal.month.branch:未", "sewoon.branch:未"]


def test_identical_branches_do_not_raise_node_index_collision() -> None:
    """projection 분할 후에도 충돌하면 조립기 결함이다 — 정상 입력은 통과해야 한다."""
    index = LuckNodeIndex((
        *_NATAL, _node("daewoon", "", "未", "土"), _node("sewoon", "", "未", "土"),
    ))
    # 권위 키는 층을 포함하므로 겹치지 않는다.
    assert index.candidates("luck", "未") == (
        "daewoon.branch:未", "sewoon.branch:未",
    )


# ── 범위 분할 ────────────────────────────────────────────────────────────


def test_to_natal_projection_excludes_the_other_transit_layer() -> None:
    """세운→원국 범위에 대운 노드가 섞이면 안 된다."""
    dw, sw = _node("daewoon", "", "未", "土"), _node("sewoon", "", "未", "土")
    index = LuckNodeIndex((*_NATAL, dw, sw))
    projections = {
        p.projection_id: p for p in build_layer_projections(
            natal_nodes=_NATAL, daewoon_nodes=(dw,), sewoon_nodes=(sw,),
        )
    }
    assert index.candidates_in(
        projections["sewoon.to_natal"], "luck", "未") == ("sewoon.branch:未",)
    assert index.candidates_in(
        projections["daewoon.to_natal"], "luck", "未") == ("daewoon.branch:未",)


def test_to_daewoon_projection_excludes_natal_nodes() -> None:
    """세운→대운 범위에 원국의 같은 글자가 잘못 매핑되면 안 된다."""
    dw, sw = _node("daewoon", "", "未", "土"), _node("sewoon", "", "未", "土")
    index = LuckNodeIndex((*_NATAL, dw, sw))
    proj = next(
        p for p in build_layer_projections(
            natal_nodes=_NATAL, daewoon_nodes=(dw,), sewoon_nodes=(sw,))
        if p.projection_id == "sewoon.to_daewoon"
    )
    assert "natal.month.branch:未" not in proj.node_ids
    assert index.candidates_in(proj, "month", "未") == ()


# ── 삼합 보존 ────────────────────────────────────────────────────────────


_SIN = _node("natal", "month", "申", "金")
_JA = _node("daewoon", "", "子", "水")
_JIN = _node("sewoon", "", "辰", "土")


def test_cross_layer_three_harmony_is_enumerated_with_positions() -> None:
    """원국 申 + 대운 子 + 세운 辰 — 쌍 단위 범위만으로는 놓친다."""
    (cand,) = enumerate_cross_layer_harmony_candidates((_SIN, _JA, _JIN))
    assert cand.relation_type == "three_harmony"
    assert cand.member_node_ids == (
        "daewoon.branch:子", "natal.month.branch:申", "sewoon.branch:辰",
    )
    assert cand.layers == ("daewoon", "natal", "sewoon")


def test_cross_layer_three_harmony_becomes_an_edge_with_resolver_tier() -> None:
    """자리는 열거기가, 성립은 resolver 가 정한다.

    가족키 정렬이 어긋나면 tier 가 유실돼 확정 삼합이 UNCONFIRMED 로 떨어진다(실측).
    """
    def call(luck_branches=None):
        lb = list(luck_branches or [])
        if "子" in lb and "辰" in lb:
            return [_Hap("three_harmony", ("申", "子", "辰"),
                         ("month", "luck", "luck"), "confirmed", "transform", "水")]
        return []

    chain = assemble_relation_state_chain(
        natal_nodes=(_SIN,), daewoon_nodes=(_JA,), sewoon_nodes=(_JIN,),
        resolve_branch_hap=call, period_keys=_PERIODS,
    )
    term = chain.terminal_frame
    edge = next(e for e in term.graph.edges if e.relation_type == "three_harmony")
    assert edge.existing_tier == "confirmed"
    assert edge.target_element == "水"
    assert edge.member_node_ids == cand_ids()
    assert term.metrics.cross_layer_harmony_candidate_count == 1


def cand_ids() -> tuple[str, ...]:
    return ("daewoon.branch:子", "natal.month.branch:申", "sewoon.branch:辰")


# ── chain 구조 ───────────────────────────────────────────────────────────


def test_chain_parents_follow_layer_order() -> None:
    chain = _chain("酉", "未")
    natal, daewoon, sewoon = chain.frames
    assert natal.snapshot.parent_snapshot_id is None
    assert daewoon.snapshot.parent_snapshot_id == natal.snapshot.snapshot_id
    assert sewoon.snapshot.parent_snapshot_id == daewoon.snapshot.snapshot_id


def test_every_frame_carries_graph_and_snapshot() -> None:
    """snapshot 배열만 넘기면 P1-c 가 현재 층의 충 엣지를 볼 수 없다."""
    for frame in _chain("酉", "未").frames:
        assert frame.graph.nodes
        assert frame.snapshot.element_states
        assert frame.snapshot.graph_fingerprint


def test_terminal_frame_is_the_last_layer() -> None:
    chain = _chain("酉", "未")
    assert chain.terminal_frame is chain.frames[-1]
    assert chain.terminal_frame.layer == "sewoon"


def test_chain_without_sewoon_ends_at_daewoon() -> None:
    chain = _chain("酉", None)
    assert [f.layer for f in chain.frames] == ["natal", "daewoon"]
    assert chain.terminal_frame.layer == "daewoon"


def test_duplicate_edges_merge_by_positional_relation_id() -> None:
    """같은 relation_id 는 하나로, 같은 가족 다른 자리는 별개로."""
    frame = _chain("酉", "未").terminal_frame
    ids = [e.relation_id for e in frame.graph.edges]
    assert len(ids) == len(set(ids))
    provenance = dict(frame.edge_provenance)
    assert all(len(v) == len(set(v)) for v in provenance.values())


# ── P1-c 전제 ────────────────────────────────────────────────────────────


def _reversal_setup():
    """亥卯未 확정 삼합 뒤 巳 가 들어오는 체인."""
    hai, si = _node("daewoon", "", "亥", "水"), _node("sewoon", "", "巳", "火")

    def call(luck_branches=None):
        lb = list(luck_branches or [])
        if "亥" in lb:
            return [_Hap("three_harmony", ("卯", "未", "亥"),
                         ("year", "month", "luck"), "confirmed", "transform", "木")]
        return []

    return assemble_relation_state_chain(
        natal_nodes=_NATAL, daewoon_nodes=(hai,), sewoon_nodes=(si,),
        resolve_branch_hap=call, period_keys=_PERIODS,
    )


def test_previous_transformed_state_survives_into_the_next_frame() -> None:
    chain = _reversal_setup()
    prev = next(
        s for s in chain.frames[1].snapshot.element_states
        if s.node_id == "daewoon.branch:亥"
    )
    assert prev.resolution_status is ResolutionStatus.TRANSFORMED
    assert prev.original_element == "水"
    assert prev.resolved_element == "木"
    assert prev.governing_relation_ids


def test_current_clash_edge_is_present_in_the_terminal_frame() -> None:
    edges = _reversal_setup().terminal_frame.graph.edges
    clash = next(e for e in edges if e.relation_type == BranchRelationKind.CLASH.value)
    assert set(clash.member_node_ids) == {"daewoon.branch:亥", "sewoon.branch:巳"}


def test_primary_path_links_previous_transform_to_current_clash() -> None:
    """우선 경로 — governing_relation_id ↔ POTENTIALLY_DISRUPTED_BY."""
    chain = _reversal_setup()
    prev = next(
        s for s in chain.frames[1].snapshot.element_states
        if s.node_id == "daewoon.branch:亥"
    )
    dep = next(
        d for d in chain.terminal_frame.graph.relation_dependencies
        if d.link_type == LINK_POTENTIALLY_DISRUPTED_BY
    )
    subject_id, _affecting_id = dep.relation_ids
    assert subject_id in prev.governing_relation_ids


def test_backup_path_survives_without_any_dependency() -> None:
    """백업 경로 — dependency 가 없어도 node 교집합으로 이을 수 있어야 한다."""
    chain = _reversal_setup()
    prev = next(
        s for s in chain.frames[1].snapshot.element_states
        if s.node_id == "daewoon.branch:亥"
    )
    clash = next(
        e for e in chain.terminal_frame.graph.edges
        if e.relation_type == BranchRelationKind.CLASH.value
    )
    assert prev.node_id in clash.member_node_ids


def test_chain_never_produces_a_reversed_status() -> None:
    """환원은 P1-c 다."""
    for frame in _reversal_setup().frames:
        assert all(
            s.resolution_status.value != "reversed" for s in frame.snapshot.element_states
        )


def test_unconfirmed_position_binding_is_not_a_confirmed_transform() -> None:
    """자리를 모르는 채로 오행 정체성을 바꾸지 않는다."""
    from saju_engines.luck_relation_graph import edge_from_resolution
    from saju_engines.relation_state_snapshot import _is_confirmed_transform

    edge = edge_from_resolution(
        relation_id="x", relation_family="f", relation_type="six",
        member_node_ids=("a",), tier="confirmed", mode="transform",
        target_element="木", source_resolver="branch_hap",
    )
    assert _is_confirmed_transform(edge) is True
    edge.normalized_observation["position_binding"] = "unconfirmed"
    assert _is_confirmed_transform(edge) is False


# ── 실패 처리 ────────────────────────────────────────────────────────────


def test_assembly_error_is_classified_not_bare() -> None:
    """오류를 무시하지도, 분류 없이 던지지도 않는다."""
    def boom(luck_branches=None):
        raise RuntimeError("resolver 폭발")

    with pytest.raises(RelationStateAssemblyError) as caught:
        _chain("酉", "未", resolver=boom)
    assert caught.value.kind is ShadowFailureKind.UNEXPECTED_ERROR


def test_unknown_branch_is_reported_not_silently_dropped() -> None:
    with pytest.raises(RelationStateAssemblyError):
        rsc.relation_nodes_from_branches(layer="natal", branches=[("year", "Z")])


# ── production 불변 ──────────────────────────────────────────────────────


def test_flag_off_calls_nothing(monkeypatch) -> None:
    """OFF 경로에서는 조립기가 아예 불리지 않는다."""
    def explode(**_kwargs):
        raise AssertionError("OFF 인데 조립기가 호출됐다")

    monkeypatch.setattr(rsc, "assemble_relation_state_chain", explode)
    monkeypatch.setattr(rsc, "should_build_relation_state_chain", lambda: False)
    assert relation_state_chain_shadow(
        natal_branches=[("year", "卯")], daewoon_branch="酉", sewoon_branch="未",
        resolve_branch_hap=_real_resolver(), period_keys=_PERIODS,
    ) is None


def test_flag_on_builds_a_chain(monkeypatch) -> None:
    monkeypatch.setattr(rsc, "should_build_relation_state_chain", lambda: True)
    chain = relation_state_chain_shadow(
        natal_branches=[("year", "卯"), ("month", "未")],
        daewoon_branch="酉", sewoon_branch="未",
        resolve_branch_hap=_real_resolver(), period_keys=_PERIODS,
    )
    assert chain is not None
    assert chain.terminal_frame.layer == "sewoon"
    assert chain.build_duration_ms >= 0.0


def test_shadow_failure_does_not_propagate(monkeypatch) -> None:
    """shadow 가 실패해도 생산 요청은 정상 완료돼야 한다."""
    monkeypatch.setattr(rsc, "should_build_relation_state_chain", lambda: True)

    def boom(luck_branches=None):
        raise RuntimeError("resolver 폭발")

    assert relation_state_chain_shadow(
        natal_branches=[("year", "卯")], daewoon_branch="酉", sewoon_branch="未",
        resolve_branch_hap=boom, period_keys=_PERIODS,
    ) is None


def test_metrics_carry_no_ganji_text() -> None:
    """운영 로그·메트릭에 간지 원문을 남기지 않는다."""
    chain = _chain("酉", "未")
    for frame in chain.frames:
        assert frame.metrics.layer in ("natal", "daewoon", "sewoon")
        assert all(isinstance(v, int) for k, v in vars(frame.metrics).items()
                   if k != "layer")
    assert set(chain.aggregate_metrics()) >= {"snapshot_count", "resolver_call_count"}


def test_chat_service_hook_is_inert_when_flag_off(monkeypatch) -> None:
    """생산 호출부: OFF 면 shadow 진입 자체를 하지 않는다."""
    monkeypatch.setattr(chat_service, "should_build_relation_state_chain", lambda: False)

    def explode(**_kwargs):
        raise AssertionError("OFF 인데 shadow 가 호출됐다")

    monkeypatch.setattr(chat_service, "relation_state_chain_shadow", explode)
    chat_service._build_relation_state_shadow(object(), object(), "2026")


def test_period_fortune_is_byte_identical_with_the_flag_on(monkeypatch) -> None:
    """flag ON 이 생산 출력을 바꾸지 않는다 — 실제 기간 운세 경로로 확인한다.

    hook 이 inert 한지를 반환값 비교로 직접 본다. shadow 는 조립만 하고 응답·점수·순위에
    손대지 않아야 한다.
    """
    from saju_api.services.chat_service import _build_period_fortune
    from saju_engines import period_v2_config
    from saju_shared_types.intent import (
        Domain,
        Granularity,
        IntentJson,
        QueryType,
        TimeRange,
    )

    monkeypatch.setattr(period_v2_config, "RELATION_SEMANTIC_PATCH_ENABLED", True)
    birth = BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:40:00",
        birth_place_name="서울", gender="male", reference_date=date(2026, 7, 27),
    )
    intent = IntentJson(
        intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW, domain=Domain.GENERAL,
        time_range=TimeRange(type="absolute", granularity=Granularity.DAY,
                             start="2026-07-27", end="2026-07-27"),
    )

    monkeypatch.setattr(chat_service, "should_build_relation_state_chain", lambda: False)
    off = repr(_build_period_fortune(birth, intent, date(2026, 7, 27), "daily"))

    monkeypatch.setattr(chat_service, "should_build_relation_state_chain", lambda: True)
    monkeypatch.setattr(rsc, "should_build_relation_state_chain", lambda: True)
    on = repr(_build_period_fortune(birth, intent, date(2026, 7, 27), "daily"))

    assert on == off


# ── 환원 전이 배선 (P1-c1b) ──────────────────────────────────────────────


def _reversal_chain(tier: str = "confirmed"):
    """대운에서 亥卯未가 확정된 뒤 세운 巳가 들어오는 체인."""
    def call(luck_branches=None):
        if "亥" in list(luck_branches or []):
            return [_Hap("three_harmony", ("卯", "未", "亥"),
                         ("year", "month", "luck"), tier, "transform", "木")]
        return []

    return assemble_relation_state_chain(
        natal_nodes=(_NATAL[0], _NATAL[1]),
        daewoon_nodes=(_node("daewoon", "", "亥", "水"),),
        sewoon_nodes=(_node("sewoon", "", "巳", "火"),),
        resolve_branch_hap=call, period_keys=_PERIODS,
    )


def test_reversal_is_applied_in_the_sewoon_frame() -> None:
    """대운에서 木으로 확정된 亥가 세운 巳亥冲으로 水로 돌아온다."""
    sewoon = _reversal_chain().frames[2]
    assert len(sewoon.transitions) == 1
    assert sewoon.base_snapshot_id != sewoon.snapshot.snapshot_id
    state = next(
        s for s in sewoon.snapshot.element_states if s.node_id == "daewoon.branch:亥")
    assert state.resolved_element == "水"


def test_sewoon_parent_is_the_daewoon_final_snapshot() -> None:
    chain = _reversal_chain()
    assert chain.frames[2].snapshot.parent_snapshot_id == (
        chain.frames[1].snapshot.snapshot_id)


def test_applied_result_is_inherited_not_the_base_snapshot() -> None:
    """다음 층 부모는 적용 **결과**여야 한다.

    base 를 넘기면 환원이 해당 frame 내부 기록에만 남고 계층 상태에는 반영되지 않는다.
    세운에서 전이가 일어났다면 그 결과가 하위 층으로 승계돼야 한다.
    """
    chain = _reversal_chain()
    sewoon = chain.frames[2]
    assert sewoon.transitions
    # 조립 루프가 승계에 쓰는 값은 최종 snapshot 이다.
    assert sewoon.snapshot.snapshot_id != sewoon.base_snapshot_id
    hai = next(
        s for s in sewoon.snapshot.element_states if s.node_id == "daewoon.branch:亥")
    assert hai.resolution_status is ResolutionStatus.ORIGINAL


def test_frames_without_transitions_keep_their_base_snapshot_id() -> None:
    """환원과 무관한 시기마다 snapshot ID 가 흔들리면 안 된다."""
    for frame in _chain("酉", "未").frames:
        assert frame.transitions == ()
        assert frame.base_snapshot_id == frame.snapshot.snapshot_id


def test_wiring_does_not_change_chains_without_reversal() -> None:
    """배선만으로 기존 shadow chain 이 변하면 안 된다."""
    a, b = _chain("酉", "未"), _chain("酉", "未")
    assert [f.snapshot.snapshot_id for f in a.frames] == [
        f.snapshot.snapshot_id for f in b.frames]
    assert all(f.transitions == () for f in a.frames)


def test_incomplete_transform_produces_no_transition() -> None:
    """미완성 변환은 환원이 아니다 — 배선 뒤에도 그대로다."""
    chain = _reversal_chain(tier="none")
    assert all(f.transitions == () for f in chain.frames)
    assert chain.terminal_frame.base_snapshot_id == (
        chain.terminal_frame.snapshot.snapshot_id)


def test_reverted_node_is_not_reverted_again() -> None:
    """환원 뒤 상태는 TRANSFORMED 가 아니므로 다음 층에서 새 후보가 생기지 않는다."""
    from saju_engines.relation_reversal import detect_reversal_candidates

    chain = _reversal_chain()
    sewoon = chain.frames[2]
    again = detect_reversal_candidates(
        previous_snapshot=sewoon.snapshot, previous_graph=sewoon.graph,
        current_snapshot=dataclasses.replace(
            sewoon.snapshot, layer="wolwoon",
            parent_snapshot_id=sewoon.snapshot.snapshot_id),
        current_graph=sewoon.graph,
    )
    assert again.candidates == ()


def test_transition_metrics_are_counted() -> None:
    metrics = _reversal_chain().aggregate_metrics()
    assert metrics["reversal_candidate_count"] == 1
    assert metrics["reversal_applied_count"] == 1
    assert metrics["reversal_dependency_path_count"] == 1


def test_transition_stage_failure_invalidates_the_whole_chain(monkeypatch) -> None:
    """shadow 의미론은 fail-closed — 적용 전 상태로 조용히 이어가지 않는다."""
    def boom(**_kwargs):
        raise RuntimeError("전이 단계 폭발")

    monkeypatch.setattr(rsc, "detect_reversal_candidates", boom)
    with pytest.raises(RelationStateAssemblyError) as caught:
        _reversal_chain()
    assert caught.value.kind is rsc.ShadowFailureKind.TRANSITION_STAGE_FAILURE


def test_transition_failure_does_not_break_production(monkeypatch) -> None:
    """production 은 fail-open — 요청은 정상 완료된다."""
    monkeypatch.setattr(rsc, "should_build_relation_state_chain", lambda: True)

    def boom(**_kwargs):
        raise RuntimeError("전이 단계 폭발")

    monkeypatch.setattr(rsc, "detect_reversal_candidates", boom)
    assert relation_state_chain_shadow(
        natal_branches=[("year", "卯"), ("month", "未")],
        daewoon_branch="亥", sewoon_branch="巳",
        resolve_branch_hap=_real_resolver(), period_keys=_PERIODS,
    ) is None


def test_chain_with_transitions_is_deterministic() -> None:
    a, b = _reversal_chain(), _reversal_chain()
    assert [f.snapshot.snapshot_id for f in a.frames] == [
        f.snapshot.snapshot_id for f in b.frames]
    assert [t.transition_id for f in a.frames for t in f.transitions] == [
        t.transition_id for f in b.frames for t in f.transitions]


def test_rejections_are_not_mixed_into_transitions() -> None:
    """기각은 전이가 아니다 — 내부 진단으로만 둔다."""
    for frame in _reversal_chain().frames:
        assert all(hasattr(t, "transition_type") for t in frame.transitions)
        assert all(hasattr(r, "reason_codes") for r in frame.transition_rejections)
