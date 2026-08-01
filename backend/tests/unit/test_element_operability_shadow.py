"""오행 실현도 shadow 배선 회귀 (P2-4, 2026-08-01).

**평가 대상 범위와 증거 탐색 범위는 다르다.** 원국을 평가하지 않는다고 원국 신호를 무시하는
것이 아니다 — 원국 亥의 지장간 壬水는 세운 癸水의 뿌리 근거가 된다.

terminal frame 기준으로 평가한다. 그래야 세운이 대운의 생조원을 흔든 결과까지 대운 노드
평가에 반영된다.
"""

from __future__ import annotations

import pytest

from saju_engines import element_operability_shadow as mod
from saju_engines import relation_shadow_config as cfg
from saju_engines.element_operability_grade import OperabilityStatus
from saju_engines.element_operability_profile import (
    CutOffStatus,
    RootStatus,
    StageApplicability,
)
from saju_engines.element_operability_shadow import (
    MAX_OPERABILITY_TARGETS,
    OperabilityShadowError,
    build_operability_shadow_bundle,
    element_operability_shadow,
    select_operability_targets,
    status_distribution,
)
from saju_engines.luck_relation_graph import RelationNode
from saju_engines.relation_state_chain import assemble_relation_state_chain
from saju_engines.role_activation_projection import (
    ActivationLevel,
    CanonicalRole,
    CanonicalRoleBasis,
)

_PERIODS = {"natal": "natal", "daewoon": "2003", "sewoon": "2003"}
_STEMS = {"daewoon": "己", "sewoon": "癸"}
_PILLARS = {("daewoon", ""): "酉", ("sewoon", ""): "未"}
_ROLES = {"水": CanonicalRole.HAN, "金": CanonicalRole.HUI, "土": CanonicalRole.GI,
          "木": CanonicalRole.GU, "火": CanonicalRole.YONG}


def _n(layer, position, ch, element):
    node_id = f"{layer}.{position}.branch:{ch}" if position else f"{layer}.branch:{ch}"
    return RelationNode(node_id, layer, position, "branch", ch, element)


_NATAL = (_n("natal", "year", "卯", "木"), _n("natal", "month", "亥", "水"))


def _chain(daewoon="酉", sewoon="未", resolver=None):
    return assemble_relation_state_chain(
        natal_nodes=_NATAL,
        daewoon_nodes=(_n("daewoon", "", daewoon, "金"),),
        sewoon_nodes=(_n("sewoon", "", sewoon, "土"),),
        resolve_branch_hap=resolver or (lambda luck_branches=None: []),
        period_keys=_PERIODS,
    )


def _bundle(**kwargs):
    return build_operability_shadow_bundle(
        chain=kwargs.pop("chain", None) or _chain(), luck_stems=_STEMS,
        roles_by_element=_ROLES, pillar_branches=_PILLARS, **kwargs)


# ── 대상 선정 ────────────────────────────────────────────────────────────


def test_only_luck_ganji_are_targets() -> None:
    targets = select_operability_targets(
        terminal_frame=_chain().terminal_frame, luck_stems=_STEMS)
    assert {t.layer for t in targets} == {"daewoon", "sewoon"}
    assert {t.component for t in targets} == {"stem", "branch"}


def test_natal_positions_are_never_targets() -> None:
    targets = select_operability_targets(
        terminal_frame=_chain().terminal_frame, luck_stems=_STEMS)
    assert all(not t.node_id.startswith("natal.") for t in targets)


def test_natal_nodes_still_provide_root_evidence() -> None:
    """원국 亥의 지장간 壬水가 세운 癸水의 직접 뿌리가 된다."""
    bundle = _bundle()
    gye = next(t for t in bundle.targets if t.node_id == "sewoon.stem:癸")
    assert gye.profile.root.status is RootStatus.DIRECT_NATAL_ROOT
    assert any(i.node_id.startswith("natal.") for i in gye.profile.root.instances)


def test_target_count_never_exceeds_four() -> None:
    bundle = _bundle()
    assert len(bundle.targets) == MAX_OPERABILITY_TARGETS


def test_same_element_at_two_layers_stays_separate() -> None:
    """같은 오행이어도 앉은 지지·뿌리·절각·12운성이 다를 수 있다."""
    targets = select_operability_targets(
        terminal_frame=_chain().terminal_frame,
        luck_stems={"daewoon": "癸", "sewoon": "癸"})
    stems = [t for t in targets if t.component == "stem"]
    assert len(stems) == 2
    assert stems[0].node_id != stems[1].node_id


# ── 상태 소비 ────────────────────────────────────────────────────────────


def test_targets_use_the_terminal_final_snapshot() -> None:
    chain = _chain()
    bundle = _bundle(chain=chain)
    assert bundle.terminal_snapshot_id == chain.terminal_frame.snapshot.snapshot_id
    assert bundle.as_of_layer == "sewoon"
    assert bundle.relation_graph_fingerprint == (
        chain.terminal_frame.snapshot.graph_fingerprint)


def test_reverted_branch_is_evaluated_as_its_original_element() -> None:
    """환원된 지지는 원래 오행으로 평가한다 — 여기서 다시 계산하지 않는다."""
    class _Hap:
        kind = "three_harmony"
        members = ("卯", "亥", "未")
        positions = ("year", "month", "luck")
        transform_tier = "confirmed"
        hap_mode = "transform"
        transform_element = "木"

    def resolver(luck_branches=None):
        return [_Hap()] if "未" in list(luck_branches or []) else []

    chain = assemble_relation_state_chain(
        natal_nodes=_NATAL, daewoon_nodes=(_n("daewoon", "", "未", "土"),),
        sewoon_nodes=(_n("sewoon", "", "丑", "土"),),
        resolve_branch_hap=resolver, period_keys=_PERIODS)
    bundle = build_operability_shadow_bundle(
        chain=chain, luck_stems=_STEMS, roles_by_element=_ROLES,
        pillar_branches={("daewoon", ""): "未", ("sewoon", ""): "丑"})
    branch = next(t for t in bundle.targets if t.node_id == "daewoon.branch:未")
    # 丑未冲이 들어와 확정 변환이 환원됐다 → 원래 오행으로 평가한다.
    assert branch.resolved_element in ("土", "木")
    assert branch.evaluation.status is not OperabilityStatus.UNKNOWN


def test_unconfirmed_branch_is_unknown() -> None:
    class _Hap:
        kind = "three_harmony"
        members = ("卯", "亥", "未")
        positions = ("year", "month", "luck")
        transform_tier = "none"
        hap_mode = "transform"
        transform_element = "木"

    chain = assemble_relation_state_chain(
        natal_nodes=_NATAL, daewoon_nodes=(_n("daewoon", "", "未", "土"),),
        sewoon_nodes=(),
        resolve_branch_hap=lambda luck_branches=None: (
            [_Hap()] if luck_branches else []),
        period_keys=_PERIODS)
    bundle = build_operability_shadow_bundle(
        chain=chain, luck_stems={"daewoon": "己"}, roles_by_element=_ROLES,
        pillar_branches={("daewoon", ""): "未"})
    branch = next(t for t in bundle.targets if t.node_id == "daewoon.branch:未")
    assert branch.resolved_element is None
    assert branch.evaluation.status is OperabilityStatus.UNKNOWN


# ── 구성요소별 적용 ──────────────────────────────────────────────────────


def test_stems_get_cut_off_and_stage() -> None:
    """세운 癸未 — 未 정기 己土가 癸水를 극하고 12운성은 묘다."""
    gye = next(t for t in _bundle().targets if t.node_id == "sewoon.stem:癸")
    assert gye.profile.obstruction.cut_off is CutOffStatus.CUT_OFF_PRESENT
    assert gye.profile.stage.applicability is StageApplicability.APPLICABLE
    assert gye.profile.stage.stage == "묘"


def test_branches_have_no_cut_off_or_stage() -> None:
    """지지에는 절각·12운성을 붙이지 않는다.

    관계에 전혀 얽히지 않은 배치를 쓴다 — 얽히면 P1 이 UNCONFIRMED 로 두어 프로필 전체가
    UNKNOWN 이 되고, 이 계약을 격리해 볼 수 없다.
    """
    chain = assemble_relation_state_chain(
        natal_nodes=(_n("natal", "year", "子", "水"),),
        daewoon_nodes=(_n("daewoon", "", "寅", "木"),),
        sewoon_nodes=(_n("sewoon", "", "辰", "土"),),
        resolve_branch_hap=lambda luck_branches=None: [], period_keys=_PERIODS)
    bundle = build_operability_shadow_bundle(
        chain=chain, luck_stems={"sewoon": "甲"}, roles_by_element=_ROLES,
        pillar_branches={("sewoon", ""): "辰"})
    branch = next(t for t in bundle.targets if t.node_id == "sewoon.branch:辰")
    assert branch.resolved_element == "土"
    assert branch.profile.obstruction.cut_off is CutOffStatus.NOT_APPLICABLE
    assert branch.profile.stage.applicability is StageApplicability.NOT_APPLICABLE


# ── 역할 투영 ────────────────────────────────────────────────────────────


def test_production_uses_engine_native_basis() -> None:
    bundle = _bundle()
    assert bundle.role_basis is CanonicalRoleBasis.ENGINE_NATIVE
    assert all(
        t.role_projection.role_basis is CanonicalRoleBasis.ENGINE_NATIVE
        for t in bundle.targets)


def test_source_fixture_is_blocked_on_the_production_path(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "LUCK_ELEMENT_OPERABILITY_SHADOW_ENABLED", True)
    monkeypatch.setattr(mod, "should_build_element_operability", lambda: True)
    assert element_operability_shadow(
        chain=_chain(), luck_stems=_STEMS, roles_by_element=_ROLES,
        pillar_branches=_PILLARS, role_basis=CanonicalRoleBasis.SOURCE_FIXTURE,
    ) is None


def test_role_is_looked_up_by_resolved_element() -> None:
    """raw 가 아니라 최종 resolved element 로 역할을 조회한다."""
    gye = next(t for t in _bundle().targets if t.node_id == "sewoon.stem:癸")
    assert gye.resolved_element == "水"
    assert gye.role_projection.canonical_role is CanonicalRole.HAN
    assert gye.role_projection.neutral_activation.level is not ActivationLevel.NONE


# ── 플래그 ───────────────────────────────────────────────────────────────


def test_operability_flag_forces_the_relation_state_chain(monkeypatch) -> None:
    monkeypatch.setattr(cfg, "LUCK_RELATION_STATE_SHADOW_ENABLED", False)
    monkeypatch.setattr(cfg, "LUCK_ELEMENT_OPERABILITY_SHADOW_ENABLED", True)
    assert cfg.should_build_relation_state_chain() is True
    assert cfg.should_build_relation_graph() is True


def test_both_flags_on_does_not_duplicate_the_chain(monkeypatch) -> None:
    """조건 함수는 boolean 하나만 낸다 — 호출부가 한 번만 부른다."""
    monkeypatch.setattr(cfg, "LUCK_RELATION_STATE_SHADOW_ENABLED", True)
    monkeypatch.setattr(cfg, "LUCK_ELEMENT_OPERABILITY_SHADOW_ENABLED", True)
    assert cfg.should_build_relation_state_chain() is True


def test_flag_off_calls_nothing(monkeypatch) -> None:
    def explode(**_kwargs):
        raise AssertionError("OFF 인데 평가기가 호출됐다")

    monkeypatch.setattr(mod, "should_build_element_operability", lambda: False)
    monkeypatch.setattr(mod, "build_operability_shadow_bundle", explode)
    assert element_operability_shadow(
        chain=_chain(), luck_stems=_STEMS, roles_by_element=_ROLES,
        pillar_branches=_PILLARS) is None


def test_flag_on_builds_a_bundle(monkeypatch) -> None:
    monkeypatch.setattr(mod, "should_build_element_operability", lambda: True)
    bundle = element_operability_shadow(
        chain=_chain(), luck_stems=_STEMS, roles_by_element=_ROLES,
        pillar_branches=_PILLARS)
    assert bundle is not None and bundle.targets


# ── 실패 정책 ────────────────────────────────────────────────────────────


def test_failure_is_classified_and_swallowed_by_the_wrapper(monkeypatch) -> None:
    """production 은 fail-open — 부분 결과를 정상처럼 쓰지 않고 묶음 전체를 버린다."""
    monkeypatch.setattr(mod, "should_build_element_operability", lambda: True)

    def boom(**_kwargs):
        raise RuntimeError("평가 폭발")

    monkeypatch.setattr(mod, "build_operability_shadow_bundle", boom)
    assert element_operability_shadow(
        chain=_chain(), luck_stems=_STEMS, roles_by_element=_ROLES,
        pillar_branches=_PILLARS) is None


def test_unknown_stem_raises_a_classified_error() -> None:
    with pytest.raises(OperabilityShadowError):
        select_operability_targets(
            terminal_frame=_chain().terminal_frame, luck_stems={"sewoon": "Z"})


def test_missing_chain_yields_no_bundle(monkeypatch) -> None:
    monkeypatch.setattr(mod, "should_build_element_operability", lambda: True)
    assert element_operability_shadow(
        chain=None, luck_stems=_STEMS, roles_by_element=_ROLES) is None


def test_unknown_status_is_not_a_failure() -> None:
    """UNKNOWN 은 shadow 실패가 아니라 유효한 관측값이다."""
    distribution = status_distribution(_bundle())
    assert set(distribution) == {s.value for s in OperabilityStatus}
    assert sum(distribution.values()) == MAX_OPERABILITY_TARGETS


# ── 결정성·비노출 ────────────────────────────────────────────────────────


def test_bundle_is_deterministic() -> None:
    a, b = _bundle(), _bundle()
    assert [t.node_id for t in a.targets] == [t.node_id for t in b.targets]
    assert [t.evaluation for t in a.targets] == [t.evaluation for t in b.targets]


def test_target_order_is_canonical_regardless_of_input_order() -> None:
    forward = select_operability_targets(
        terminal_frame=_chain().terminal_frame,
        luck_stems={"daewoon": "己", "sewoon": "癸"})
    backward = select_operability_targets(
        terminal_frame=_chain().terminal_frame,
        luck_stems={"sewoon": "癸", "daewoon": "己"})
    assert [t.node_id for t in forward] == [t.node_id for t in backward]


def test_metrics_carry_no_ganji_or_node_id() -> None:
    metrics = _bundle().build_metrics
    for key, _count in metrics.status_counts:
        assert key in {s.value for s in OperabilityStatus}
    assert isinstance(metrics.target_count, int)
