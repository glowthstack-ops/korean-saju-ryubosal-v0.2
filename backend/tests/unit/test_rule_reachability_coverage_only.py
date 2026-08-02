"""규칙 도달성 coverage-only (2026-08-02).

**기존 관측 분포와 섞지 않는다.** 여기 사례는 78입력·312 target 분포의 어떤 비율에도
합산되지 않으며, 목적은 분포 개선이 아니라 현재 규칙표의 도달 가능성과 계층 연결 증명이다.

규칙 목록은 하드코딩하지 않고 **현재 평가기 소스에서 산출**한다. 01c 에서 cap 규칙이
추가됐으므로 미도달 집합도 다시 계산해야 한다(실측: R41 하나가 아니라 R01 도 미도달이었다).
"""

from __future__ import annotations

import inspect
import re

import pytest

from saju_engines import element_operability_grade as grade_mod
from saju_engines.activation_resolution import (
    ActivationAxis,
    ActivationResolutionError,
    activation_resolution_order_key,
    build_axis_activation_resolution,
    compare_same_axis_resolution,
)
from saju_engines.element_operability_grade import (
    OperabilityStatus,
    evaluate_element_operability,
)
from saju_engines.element_operability_profile import (
    CutOffStatus,
    ElementOperabilityProfile,
    ObstructionProfile,
    ProfileTarget,
    RootDepth,
    RootProfile,
    RootStatus,
    StageApplicability,
    StageModifier,
    SupportPath,
    SupportPathStatus,
    SupportProfile,
    SupportStatus,
    extract_element_operability_profile,
)
from saju_engines.luck_relation_graph import RelationNode
from saju_engines.role_activation_projection import (
    ActivationLevel,
    CanonicalRole,
    CanonicalRoleBasis,
    project_role_activation,
)


def rule_registry() -> set[str]:
    """현재 평가기가 낼 수 있는 rule ID 전체 — SSOT 는 소스다."""
    return set(re.findall(r'"(R\d+_[A-Z_]+)"', inspect.getsource(grade_mod)))


def test_rule_registry_is_not_empty_and_ids_are_unique() -> None:
    rules = rule_registry()
    assert len(rules) >= 16
    assert all(r.startswith("R") for r in rules)


# ── R41 보충 fixture ─────────────────────────────────────────────────────


def _r41_profile() -> ElementOperabilityProfile:
    """무근 + 절각 + **안정** 생조. 세 조건이 모두 성립해야 R41 이다.

    섞이면 안 되는 이웃 규칙:
        무근 + 절각 + 생조 교란·부재  → R40 (SUPPRESSED)
        직접 뿌리 + 절각 + 약한 12운성 → R2x
    """
    return ElementOperabilityProfile(
        node_id="sewoon.stem:癸", raw_element="水", resolved_element="水",
        root=RootProfile(
            RootStatus.ABSENT, (), natal_root_depth=RootDepth.NONE,
            transit_root_depth=RootDepth.NONE,
            strongest_root_depth=RootDepth.NONE, has_main_qi_root=False),
        support=SupportProfile(
            SupportStatus.INDIRECT_GENERATION_STABLE,
            (SupportPath("natal.year.branch:酉", "金", "sewoon.stem:癸", "水",
                         "generates", (), SupportPathStatus.STABLE),)),
        obstruction=ObstructionProfile(
            CutOffStatus.CUT_OFF_PRESENT, "癸", "未", "己"),
        # 약한 단계가 아니어야 한다 — 하향 원인이 겹치면 무엇이 결과를 만들었는지 모른다.
        stage=StageModifier(StageApplicability.APPLICABLE, "癸", "未", "관대"),
    )


def test_r41_is_reachable_with_a_deterministic_fixture() -> None:
    evaluation = evaluate_element_operability(_r41_profile())
    assert evaluation.matched_rule_id == "R41_ROOTLESS_CUT_OFF_WITH_SUPPORT"
    assert evaluation.status is OperabilityStatus.WEAKENED
    assert evaluation.anchor == 0.35


def test_r41_fixture_does_not_collide_with_neighbouring_rules() -> None:
    """생조가 흔들리면 R40, 뿌리가 있으면 R2x — 경계가 실제로 갈리는지 본다."""
    import dataclasses

    base = _r41_profile()
    disrupted = dataclasses.replace(
        base, support=SupportProfile(SupportStatus.INDIRECT_GENERATION_DISRUPTED))
    assert evaluate_element_operability(disrupted).matched_rule_id == (
        "R40_ROOTLESS_CUT_OFF_NO_RELIABLE_SUPPORT")

    rooted = dataclasses.replace(
        base, root=RootProfile(
            RootStatus.DIRECT_NATAL_ROOT, (),
            natal_root_depth=RootDepth.MAIN_QI,
            strongest_root_depth=RootDepth.MAIN_QI, has_main_qi_root=True))
    assert evaluate_element_operability(rooted).matched_rule_id.startswith("R2")


def test_r41_root_depth_is_none_not_unknown() -> None:
    """조사했으나 뿌리가 없는 것이지 판정 불가가 아니다 — UNKNOWN 이면 fixture 결함이다."""
    root = _r41_profile().root
    assert root.strongest_root_depth is RootDepth.NONE
    assert root.has_main_qi_root is False


def test_r41_profile_is_reproducible_from_the_real_extractor() -> None:
    """손으로 만든 프로필이 실제 추출기 결과와 같은 형태인지 확인한다."""
    target = ProfileTarget(
        "sewoon.stem:癸", "sewoon", "", "stem", "癸", "水", "水")
    profile = extract_element_operability_profile(
        target=target,
        nodes=[RelationNode(
            "natal.year.branch:酉", "natal", "year", "branch", "酉", "金")],
        pillar_branches={("sewoon", ""): "未"})
    assert profile.root.status is RootStatus.ABSENT
    assert profile.root.strongest_root_depth is RootDepth.NONE
    assert profile.support.status is SupportStatus.INDIRECT_GENERATION_STABLE
    assert profile.obstruction.cut_off is CutOffStatus.CUT_OFF_PRESENT
    assert evaluate_element_operability(profile).matched_rule_id == (
        "R41_ROOTLESS_CUT_OFF_WITH_SUPPORT")


# ── 여섯 계층 연결 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "axis", "attr"),
    [(CanonicalRole.YONG, ActivationAxis.FAVORABLE, "favorable_activation"),
     (CanonicalRole.GI, ActivationAxis.ADVERSE, "adverse_activation"),
     (CanonicalRole.HAN, ActivationAxis.NEUTRAL, "neutral_activation")],
)
def test_r41_chain_reaches_ordering(role, axis, attr) -> None:
    """profile → status → projection → order key 까지 한 번에 확인한다."""
    evaluation = evaluate_element_operability(_r41_profile())
    projection = project_role_activation(
        node_id="sewoon.stem:癸", canonical_role=role,
        role_basis=CanonicalRoleBasis.ENGINE_NATIVE, evaluation=evaluation)

    target_axis = getattr(projection, attr)
    assert target_axis.level is ActivationLevel.LOW
    # 비대상 축은 NONE 이다.
    others = {"favorable_activation", "adverse_activation", "neutral_activation"} - {attr}
    for name in others:
        if role in (CanonicalRole.YONG,) and name == "adverse_activation":
            pass
        assert getattr(projection, name).level in (
            ActivationLevel.NONE, ActivationLevel.LOW)

    resolution = build_axis_activation_resolution(
        axis=axis, level=target_axis.level,
        operability_status=evaluation.status, operability_anchor=evaluation.anchor)
    key = activation_resolution_order_key(resolution)
    assert key is not None
    assert key.within_level_anchor == 0.35


def test_weakened_outranks_suppressed_in_the_same_axis() -> None:
    """R41(WEAKENED 0.35) vs R40(SUPPRESSED 0.15) — 같은 LOW 안의 순서."""
    import dataclasses

    weakened = evaluate_element_operability(_r41_profile())
    suppressed = evaluate_element_operability(dataclasses.replace(
        _r41_profile(),
        support=SupportProfile(SupportStatus.INDIRECT_GENERATION_DISRUPTED)))
    assert suppressed.status is OperabilityStatus.SUPPRESSED

    def _res(ev):
        return build_axis_activation_resolution(
            axis=ActivationAxis.ADVERSE, level=ActivationLevel.LOW,
            operability_status=ev.status, operability_anchor=ev.anchor)

    assert compare_same_axis_resolution(_res(weakened), _res(suppressed)) > 0
    with pytest.raises(ActivationResolutionError, match="CROSS_AXIS"):
        compare_same_axis_resolution(
            _res(weakened),
            build_axis_activation_resolution(
                axis=ActivationAxis.FAVORABLE, level=ActivationLevel.LOW,
                operability_status=suppressed.status,
                operability_anchor=suppressed.anchor))


# ── R01 — 추출기로는 도달하지 않는 방어 가드 ─────────────────────────────


def test_r01_is_a_defensive_guard_not_reachable_from_the_extractor() -> None:
    """`RootStatus.UNKNOWN` 은 resolved_element 가 없을 때만 생기고, 그때는 R00 이 먼저다.

    따라서 추출기를 통해서는 R01 에 도달할 수 없다. 규칙을 억지로 통과시키지 않고 **방어
    가드**로 분류한다 — 평가기에 직접 넣으면 동작하므로 죽은 코드는 아니다.
    """
    profile = ElementOperabilityProfile(
        node_id="x", raw_element="水", resolved_element="水",
        root=RootProfile(RootStatus.UNKNOWN),
        support=SupportProfile(SupportStatus.UNKNOWN),
        obstruction=ObstructionProfile(CutOffStatus.UNKNOWN),
        stage=StageModifier(StageApplicability.UNKNOWN),
    )
    evaluation = evaluate_element_operability(profile)
    assert evaluation.matched_rule_id == "R01_UNKNOWN_ROOT"
    assert evaluation.status is OperabilityStatus.UNKNOWN
    assert activation_resolution_order_key(build_axis_activation_resolution(
        axis=ActivationAxis.FAVORABLE, level=ActivationLevel.UNKNOWN,
        operability_status=evaluation.status,
        operability_anchor=evaluation.anchor)) is None

    # 추출기 경로에서는 resolved_element 부재가 R00 을 먼저 선점한다.
    target = ProfileTarget("y", "sewoon", "", "stem", "癸", "水", None)
    natural = extract_element_operability_profile(target=target, nodes=[])
    assert evaluate_element_operability(natural).matched_rule_id == (
        "R00_UNRESOLVED_ELEMENT")


def test_every_registry_rule_is_classified() -> None:
    """미분류 규칙 0건 — 새 규칙이 생기면 이 회귀가 먼저 깨진다."""
    classified = {
        "R00_UNRESOLVED_ELEMENT", "R01_UNKNOWN_ROOT",
        "R10_NATAL_AND_TRANSIT_ROOT_CLEAR",
        "R10_NATAL_AND_TRANSIT_NON_MAIN_ROOT_CAP",
        "R11_NATAL_AND_TRANSIT_ROOT_CUT_OFF_WEAK_STAGE",
        "R12_NATAL_AND_TRANSIT_ROOT_CUT_OFF",
        "R20_NATAL_ROOT_STABLE_SUPPORT", "R20_NATAL_NON_MAIN_ROOT_CAP",
        "R21_NATAL_ROOT_CLEAR", "R22_NATAL_ROOT_CUT_OFF_WEAK_STAGE",
        "R23_NATAL_ROOT_CUT_OFF", "R30_TRANSIT_ROOT_CLEAR",
        "R31_TRANSIT_ROOT_CUT_OFF_WEAK_STAGE", "R32_TRANSIT_ROOT_CUT_OFF",
        "R40_ROOTLESS_CUT_OFF_NO_RELIABLE_SUPPORT",
        "R41_ROOTLESS_CUT_OFF_WITH_SUPPORT",
        "R42_ROOTLESS_NO_RELIABLE_SUPPORT", "R43_ROOTLESS_WITH_SUPPORT",
    }
    assert rule_registry() == classified
