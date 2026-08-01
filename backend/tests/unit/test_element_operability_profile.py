"""오행 실현도 신호 추출 회귀 (P2-1, 2026-08-01).

이 계층은 **신호만 뽑고 판단하지 않는다.** 등급·앵커·역할·활성도가 생기면 실패다.

가장 중요한 구분 하나: **금생수는 水의 뿌리가 아니다.** 기존 통근 코드의
`resource_root`(인성)를 그대로 뿌리로 세면 이 구분이 무너지고, 무근인 水가 유근으로 잡힌다.
"""

from __future__ import annotations

import inspect

from saju_engines import element_operability_profile as mod
from saju_engines.branch_relation_collector import collect_branch_relation_instances
from saju_engines.element_operability_profile import (
    CutOffStatus,
    ProfileTarget,
    RootStatus,
    StageApplicability,
    SupportPathStatus,
    SupportStatus,
    extract_element_operability_profile,
)
from saju_engines.luck_relation_graph import RelationNode


def _n(layer: str, position: str, ch: str) -> RelationNode:
    node_id = f"{layer}.{position}.branch:{ch}" if position else f"{layer}.branch:{ch}"
    return RelationNode(node_id, layer, position, "branch", ch, "?")


def _stem(layer: str, position: str, ch: str, element: str, resolved=...):
    node_id = f"{layer}.{position}.stem:{ch}" if position else f"{layer}.stem:{ch}"
    return ProfileTarget(
        node_id, layer, position, "stem", ch, element,
        element if resolved is ... else resolved,
    )


def _extract(target, nodes, relations=(), pillars=None):
    return extract_element_operability_profile(
        target=target, nodes=nodes, branch_relations=relations,
        pillar_branches=pillars or {},
    )


# ── 뿌리 ─────────────────────────────────────────────────────────────────


def test_metal_generating_water_is_not_a_water_root() -> None:
    """金生水는 생조이지 水의 뿌리가 아니다."""
    profile = _extract(_stem("sewoon", "", "癸", "水"), [_n("natal", "year", "酉")])
    assert profile.root.status is RootStatus.ABSENT
    assert profile.support.status is SupportStatus.INDIRECT_GENERATION_STABLE


def test_hidden_water_stem_is_a_direct_root() -> None:
    """亥의 지장간 壬水는 직접 뿌리다."""
    profile = _extract(_stem("sewoon", "", "癸", "水"), [_n("natal", "day", "亥")])
    assert profile.root.status is RootStatus.DIRECT_NATAL_ROOT
    assert any(i.hidden_stem == "壬" for i in profile.root.instances)


def test_natal_and_transit_roots_are_distinguished() -> None:
    natal = _extract(_stem("sewoon", "", "癸", "水"), [_n("natal", "day", "亥")])
    transit = _extract(_stem("sewoon", "", "癸", "水"), [_n("daewoon", "", "亥")])
    both = _extract(
        _stem("sewoon", "", "癸", "水"),
        [_n("natal", "day", "亥"), _n("daewoon", "", "子")])
    assert natal.root.status is RootStatus.DIRECT_NATAL_ROOT
    assert transit.root.status is RootStatus.DIRECT_TRANSIT_ROOT
    assert both.root.status is RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT


def test_same_character_at_two_positions_yields_two_root_instances() -> None:
    """일지 亥와 시지 亥는 별개 뿌리다 — 글자로 뭉개면 자리 근거가 사라진다."""
    profile = _extract(
        _stem("sewoon", "", "癸", "水"),
        [_n("natal", "day", "亥"), _n("natal", "hour", "亥")])
    ids = {i.node_id for i in profile.root.instances}
    assert ids == {"natal.day.branch:亥", "natal.hour.branch:亥"}


# ── 생조 ─────────────────────────────────────────────────────────────────


def test_stable_support_source() -> None:
    profile = _extract(_stem("sewoon", "", "癸", "水"), [_n("natal", "year", "酉")])
    (path,) = profile.support.paths
    assert path.status is SupportPathStatus.STABLE
    assert path.source_element == "金"


def test_clashed_support_source_is_disrupted() -> None:
    """생조원 酉가 卯酉冲을 맞으면 그 경로가 흔들린다."""
    nodes = [_n("natal", "year", "卯"), _n("sewoon", "", "酉")]
    profile = _extract(
        _stem("sewoon", "", "癸", "水"), nodes,
        collect_branch_relation_instances(nodes=nodes))
    assert profile.support.status is SupportStatus.INDIRECT_GENERATION_DISRUPTED
    assert profile.evidence_ids


def test_clash_does_not_propagate_to_the_other_position() -> None:
    """다른 자리의 같은 글자까지 함께 교란됐다고 보지 않는다."""
    nodes = [
        _n("natal", "year", "卯"), _n("natal", "month", "酉"), _n("natal", "day", "酉"),
    ]
    relations = [
        r for r in collect_branch_relation_instances(nodes=nodes)
        if "natal.month.branch:酉" in r.member_node_ids
    ]
    profile = _extract(_stem("sewoon", "", "癸", "水"), nodes, relations)
    by_node = {p.source_node_id: p.status for p in profile.support.paths}
    assert by_node["natal.month.branch:酉"] is SupportPathStatus.DISRUPTED
    assert by_node["natal.day.branch:酉"] is SupportPathStatus.STABLE
    assert profile.support.status is SupportStatus.INDIRECT_GENERATION_PRESENT_MIXED


# ── 절각 ─────────────────────────────────────────────────────────────────


def test_main_hidden_stem_controlling_the_stem_is_cut_off() -> None:
    """癸未 — 未 정기 己土가 癸水를 극한다."""
    profile = _extract(
        _stem("sewoon", "", "癸", "水"), [], pillars={("sewoon", ""): "未"})
    assert profile.obstruction.cut_off is CutOffStatus.CUT_OFF_PRESENT
    assert profile.obstruction.controlling_hidden_stem == "己"


def test_only_middle_or_residual_control_is_not_cut_off() -> None:
    """癸寅 — 여기 戊土가 극하지만 정기는 甲木이다. 정기만 본다(2026-08-01 확정)."""
    profile = _extract(
        _stem("sewoon", "", "癸", "水"), [], pillars={("sewoon", ""): "寅"})
    assert profile.obstruction.cut_off is CutOffStatus.CUT_OFF_ABSENT
    assert profile.obstruction.controlling_hidden_stem == "甲"


def test_adjacent_pillar_does_not_create_cut_off() -> None:
    """같은 기둥만 본다 — 옆 기둥의 未는 세지 않는다."""
    profile = _extract(
        _stem("sewoon", "", "癸", "水"), [_n("natal", "month", "未")],
        pillars={("natal", "month"): "未"})
    assert profile.obstruction.cut_off is CutOffStatus.NOT_APPLICABLE


def test_transit_stem_over_natal_branch_is_not_cut_off() -> None:
    """운 천간 ↔ 원국 지지 조합은 절각으로 세지 않는다."""
    profile = _extract(
        _stem("sewoon", "", "癸", "水"), [_n("natal", "month", "未")],
        pillars={("natal", "month"): "未", ("natal", "day"): "戌"})
    assert profile.obstruction.cut_off is CutOffStatus.NOT_APPLICABLE


def test_transformed_stem_element_requires_review() -> None:
    """천간합으로 평가 오행이 실제 천간과 달라지면 자동 판단에 쓰지 않는다."""
    target = _stem("sewoon", "", "癸", "水", resolved="火")
    profile = _extract(target, [], pillars={("sewoon", ""): "未"})
    assert profile.obstruction.cut_off is CutOffStatus.CUT_OFF_REQUIRES_REVIEW


# ── 12운성 ───────────────────────────────────────────────────────────────


def test_twelve_stage_follows_the_actual_stem() -> None:
    """壬-未는 양, 癸-未는 묘 — 대표 천간을 지어내면 판정이 뒤집힌다."""
    gye = _extract(_stem("sewoon", "", "癸", "水"), [], pillars={("sewoon", ""): "未"})
    im = _extract(_stem("sewoon", "", "壬", "水"), [], pillars={("sewoon", ""): "未"})
    assert gye.stage.stage != im.stage.stage
    assert gye.stage.stem == "癸" and im.stage.stem == "壬"


def test_branch_target_has_no_applicable_stage() -> None:
    """지지 노드의 오행 실현도에는 12운성을 붙이지 않는다."""
    target = ProfileTarget(
        "daewoon.branch:亥", "daewoon", "", "branch", "亥", "水", "水")
    profile = _extract(target, [_n("natal", "day", "子")])
    assert profile.stage.applicability is StageApplicability.NOT_APPLICABLE
    assert profile.obstruction.cut_off is CutOffStatus.NOT_APPLICABLE


# ── P1 상태 소비 ─────────────────────────────────────────────────────────


def test_reverted_node_uses_its_final_resolved_element() -> None:
    """환원된 노드는 P1 최종값(水)을 쓴다 — 여기서 다시 판정하지 않는다."""
    target = ProfileTarget(
        "daewoon.branch:亥", "daewoon", "", "branch", "亥", "水", "水")
    profile = extract_element_operability_profile(
        target=target, nodes=[_n("natal", "year", "酉")],
        extra_reason_codes=("RESOLVED_ELEMENT_REVERSED",))
    assert profile.resolved_element == "水"
    assert "RESOLVED_ELEMENT_REVERSED" in profile.reason_codes
    assert profile.support.status is SupportStatus.INDIRECT_GENERATION_STABLE


def test_unconfirmed_resolution_yields_unknown_profiles() -> None:
    """정체성이 확정되지 않았으면 프로필을 억지로 계산하지 않는다."""
    target = ProfileTarget(
        "daewoon.branch:亥", "daewoon", "", "branch", "亥", "水", None)
    profile = _extract(target, [_n("natal", "year", "酉")])
    assert profile.root.status is RootStatus.UNKNOWN
    assert profile.support.status is SupportStatus.UNKNOWN
    assert profile.obstruction.cut_off is CutOffStatus.UNKNOWN
    assert profile.stage.applicability is StageApplicability.UNKNOWN
    assert "OPERABILITY_UNKNOWN_CONFLICTING_RESOLUTION" in profile.reason_codes


# ── 역할 중립 ────────────────────────────────────────────────────────────


#: 이 계층에 들어오면 안 되는 어휘. **심볼**로 검사한다 — 원문 문자열을 훑으면 "용신인지
#: 기신인지도 모른다" 같은 정당한 설명까지 잡힌다(실측).
_FORBIDDEN = (
    "role", "yong", "hui", "gi", "gu", "han", "favorable", "adverse", "canonical",
    "operabilitystatus", "fully_operable", "weakened", "suppressed", "anchor",
    "activation", "score", "grade",
)


def _public_symbols() -> list[str]:
    return [n for n in dir(mod) if not n.startswith("_")]


def test_module_exposes_no_role_or_grade_symbol() -> None:
    """역할표를 바꿔도 결과가 같으려면, 애초에 역할을 몰라야 한다."""
    for name in _public_symbols():
        lowered = name.lower()
        assert not any(w in lowered for w in _FORBIDDEN), f"어휘 유입: {name}"


def test_signature_and_output_carry_no_judgement() -> None:
    """등급·앵커·활성도는 P2-2 이후다."""
    params = inspect.signature(extract_element_operability_profile).parameters
    for name in params:
        assert not any(w in name.lower() for w in _FORBIDDEN), name
    profile = _extract(_stem("sewoon", "", "癸", "水"), [])
    for field, value in vars(profile).items():
        assert not any(w in field.lower() for w in _FORBIDDEN), field
        assert not isinstance(value, float), f"수치 유입: {field}"
