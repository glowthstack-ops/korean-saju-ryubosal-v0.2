"""역할 활성도 투영 회귀 (P2-3, 2026-08-01).

가장 중요한 불변식 하나.

    SUPPRESSED 용신  ≠ 기신 전환  ≠ adverse activation  ≠ favorable quality 반전

"유리한 작용이 충분히 나타나지 않음" 과 "그 오행이 불리하게 뒤집힘" 은 다른 현상이다.
불리한 결과는 기신·구신의 활성이나 완충 실패에서 나와야 한다.

역할표를 바꿔도 P2-1 프로필과 P2-2 등급은 그대로다 — 그래서 경계 명식의 용신 모델 선택
감수가 실현도 개발을 막지 않는다.
"""

from __future__ import annotations

import inspect

from saju_engines import role_activation_projection as mod
from saju_engines.element_operability_grade import (
    OperabilityStatus,
    evaluate_element_operability,
)
from saju_engines.element_operability_profile import (
    ProfileTarget,
    extract_element_operability_profile,
)
from saju_engines.luck_relation_graph import RelationNode
from saju_engines.role_activation_projection import (
    ACTIVATION_ANCHOR,
    PRODUCTION_ALLOWED_ROLE_BASES,
    ActivationLevel,
    CanonicalRole,
    CanonicalRoleBasis,
    project_role_activation,
)


def _evaluation(status: OperabilityStatus):
    """등급을 직접 지정한 평가 결과 — 투영만 격리해 본다."""
    from saju_engines.element_operability_grade import (
        OPERABILITY_ANCHOR,
        OperabilityEvaluation,
    )
    return OperabilityEvaluation(
        status=status, anchor=OPERABILITY_ANCHOR[status],
        matched_rule_id="RXX_FIXTURE", reason_codes=("NATAL_ROOT_ABSENT",),
        evidence_ids=("clash:卯酉@natal.year.branch:卯+daewoon.branch:酉",),
    )


def _project(role: CanonicalRole, status: OperabilityStatus,
             basis: CanonicalRoleBasis = CanonicalRoleBasis.ENGINE_NATIVE):
    return project_role_activation(
        node_id="sewoon.stem:癸", canonical_role=role, role_basis=basis,
        evaluation=_evaluation(status),
    )


# ── 억제된 용신 ──────────────────────────────────────────────────────────


def test_suppressed_yong_keeps_a_favorable_axis() -> None:
    result = _project(CanonicalRole.YONG, OperabilityStatus.SUPPRESSED)
    assert result.favorable_activation.level is ActivationLevel.LOW
    assert result.favorable_activation.anchor == 0.25


def test_suppressed_yong_has_limited_mitigation() -> None:
    result = _project(CanonicalRole.YONG, OperabilityStatus.SUPPRESSED)
    assert result.mitigation.level is ActivationLevel.LOW
    assert "MITIGATION_LIMITED_BY_OPERABILITY" in result.reason_codes


def test_suppressed_yong_never_becomes_adverse() -> None:
    """억제된 용신을 기신처럼 뒤집지 않는다."""
    result = _project(CanonicalRole.YONG, OperabilityStatus.SUPPRESSED)
    assert result.adverse_activation.level is ActivationLevel.NONE
    assert result.adverse_activation.anchor == 0.0
    assert result.canonical_role is CanonicalRole.YONG
    assert "FAVORABLE_ROLE_SUPPRESSED" in result.reason_codes


def test_suppressed_hui_never_becomes_adverse() -> None:
    result = _project(CanonicalRole.HUI, OperabilityStatus.SUPPRESSED)
    assert result.adverse_activation.level is ActivationLevel.NONE
    assert result.favorable_activation.level is ActivationLevel.LOW


def test_no_favorable_role_ever_produces_adverse_activation() -> None:
    """어떤 실현도에서도 유리 역할이 불리 축을 만들지 않는다."""
    for role in (CanonicalRole.YONG, CanonicalRole.HUI):
        for status in OperabilityStatus:
            result = _project(role, status)
            assert result.adverse_activation.level is ActivationLevel.NONE


# ── 기신·구신 ────────────────────────────────────────────────────────────


def test_suppressed_gi_still_acts_weakly() -> None:
    """억제된 기신은 불리 역할이 사라진 것이 아니라 약하게 작동하는 것이다."""
    result = _project(CanonicalRole.GI, OperabilityStatus.SUPPRESSED)
    assert result.adverse_activation.level is ActivationLevel.LOW
    assert result.favorable_activation.level is ActivationLevel.NONE
    assert result.mitigation.level is ActivationLevel.NONE


def test_operable_gi_acts_strongly() -> None:
    result = _project(CanonicalRole.GI, OperabilityStatus.OPERABLE)
    assert result.adverse_activation.level is ActivationLevel.HIGH
    assert result.structural_tension.level is ActivationLevel.HIGH
    assert "ADVERSE_ROLE_OPERABLE" in result.reason_codes


def test_gi_and_gu_share_the_projection_shape() -> None:
    """차이는 canonical_role 에 남기고 배율을 두지 않는다."""
    gi = _project(CanonicalRole.GI, OperabilityStatus.WEAKENED)
    gu = _project(CanonicalRole.GU, OperabilityStatus.WEAKENED)
    assert gi.adverse_activation == gu.adverse_activation
    assert gi.structural_tension == gu.structural_tension
    assert gi.canonical_role is not gu.canonical_role


# ── 한신 ─────────────────────────────────────────────────────────────────


def test_han_activates_only_the_neutral_axis() -> None:
    """실현도가 낮다고 유리·불리 쪽으로 옮기지 않는다."""
    result = _project(CanonicalRole.HAN, OperabilityStatus.SUPPRESSED)
    assert result.neutral_activation.level is ActivationLevel.LOW
    assert result.favorable_activation.level is ActivationLevel.NONE
    assert result.adverse_activation.level is ActivationLevel.NONE
    assert result.mitigation.level is ActivationLevel.NONE
    assert result.structural_tension.level is ActivationLevel.NONE


# ── 구조적 긴장 ──────────────────────────────────────────────────────────


def test_tension_rises_as_a_favorable_role_fails() -> None:
    expected = {
        OperabilityStatus.FULLY_OPERABLE: ActivationLevel.NONE,
        OperabilityStatus.OPERABLE: ActivationLevel.NONE,
        OperabilityStatus.PARTIALLY_OPERABLE: ActivationLevel.LOW,
        OperabilityStatus.WEAKENED: ActivationLevel.MODERATE,
        OperabilityStatus.SUPPRESSED: ActivationLevel.HIGH,
        OperabilityStatus.UNKNOWN: ActivationLevel.UNKNOWN,
    }
    for status, level in expected.items():
        assert _project(CanonicalRole.YONG, status).structural_tension.level is level


def test_tension_rises_as_an_adverse_role_works() -> None:
    """억제돼도 NONE 이 아니다 — 억제는 완전 소멸이 아니다."""
    assert _project(
        CanonicalRole.GI, OperabilityStatus.SUPPRESSED,
    ).structural_tension.level is ActivationLevel.LOW


# ── UNKNOWN 전파 ─────────────────────────────────────────────────────────


def test_unknown_operability_only_clouds_the_target_axes() -> None:
    """대상도 아닌 축까지 UNKNOWN 으로 오염시키지 않는다."""
    result = _project(CanonicalRole.YONG, OperabilityStatus.UNKNOWN)
    assert result.favorable_activation.level is ActivationLevel.UNKNOWN
    assert result.mitigation.level is ActivationLevel.UNKNOWN
    assert result.structural_tension.level is ActivationLevel.UNKNOWN
    assert result.adverse_activation.level is ActivationLevel.NONE
    assert result.neutral_activation.level is ActivationLevel.NONE


def test_unknown_axes_have_no_anchor() -> None:
    result = _project(CanonicalRole.YONG, OperabilityStatus.UNKNOWN)
    assert result.favorable_activation.anchor is None
    assert result.operability_anchor is None


# ── 역할표 교체 ──────────────────────────────────────────────────────────


def _case_a_pipeline():
    """사례 A — 동일 구조를 두 역할표로 투영한다."""
    nodes = [RelationNode(
        "natal.year.branch:酉", "natal", "year", "branch", "酉", "金")]
    target = ProfileTarget(
        "sewoon.stem:癸", "sewoon", "", "stem", "癸", "水", "水")
    profile = extract_element_operability_profile(
        target=target, nodes=nodes, pillar_branches={("sewoon", ""): "未"})
    return profile, evaluate_element_operability(profile)


def test_role_table_change_leaves_profile_and_grade_identical() -> None:
    """engine-native 와 source-fixture 는 **투영만** 달라진다."""
    profile_a, eval_a = _case_a_pipeline()
    profile_b, eval_b = _case_a_pipeline()
    assert profile_a == profile_b
    assert eval_a == eval_b

    engine = project_role_activation(
        node_id="sewoon.stem:癸", canonical_role=CanonicalRole.HAN,
        role_basis=CanonicalRoleBasis.ENGINE_NATIVE, evaluation=eval_a)
    source = project_role_activation(
        node_id="sewoon.stem:癸", canonical_role=CanonicalRole.YONG,
        role_basis=CanonicalRoleBasis.SOURCE_FIXTURE, evaluation=eval_b)

    assert engine.operability_status == source.operability_status
    assert engine != source
    assert engine.neutral_activation.level is not ActivationLevel.NONE
    assert source.favorable_activation.level is not ActivationLevel.NONE
    assert source.adverse_activation.level is ActivationLevel.NONE


def test_source_fixture_is_not_production_allowed() -> None:
    assert PRODUCTION_ALLOWED_ROLE_BASES == frozenset(
        {CanonicalRoleBasis.ENGINE_NATIVE})
    for basis in (CanonicalRoleBasis.SOURCE_FIXTURE,
                  CanonicalRoleBasis.REVIEWED_OVERRIDE,
                  CanonicalRoleBasis.CALIBRATION_OVERRIDE):
        assert basis not in PRODUCTION_ALLOWED_ROLE_BASES


def test_role_basis_is_recorded_in_reasons() -> None:
    engine = _project(CanonicalRole.YONG, OperabilityStatus.WEAKENED)
    source = _project(CanonicalRole.YONG, OperabilityStatus.WEAKENED,
                      CanonicalRoleBasis.SOURCE_FIXTURE)
    assert "ROLE_BASIS_ENGINE_NATIVE" in engine.reason_codes
    assert "ROLE_BASIS_SOURCE_FIXTURE" in source.reason_codes


# ── 수치 계약 ────────────────────────────────────────────────────────────


def test_anchor_is_derived_from_the_level_never_computed() -> None:
    """수치를 독립 계산하거나 가감하지 않는다."""
    assert ACTIVATION_ANCHOR == {
        ActivationLevel.NONE: 0.0, ActivationLevel.LOW: 0.25,
        ActivationLevel.MODERATE: 0.50, ActivationLevel.HIGH: 0.75,
        ActivationLevel.UNKNOWN: None,
    }
    for role in CanonicalRole:
        for status in OperabilityStatus:
            result = _project(role, status)
            for axis in (result.favorable_activation, result.adverse_activation,
                         result.mitigation, result.neutral_activation,
                         result.structural_tension):
                assert axis.anchor == ACTIVATION_ANCHOR[axis.level]


def test_operability_and_activation_anchors_stay_separate() -> None:
    """두 앵커는 다른 축의 고정 지점이다 — 한 필드로 합치지 않는다."""
    result = _project(CanonicalRole.YONG, OperabilityStatus.WEAKENED)
    assert result.operability_anchor == 0.35
    assert result.favorable_activation.anchor == 0.25


def test_no_loss_or_mixed_binding_axis_is_created() -> None:
    result = _project(CanonicalRole.YONG, OperabilityStatus.OPERABLE)
    fields = set(vars(result))
    assert "loss" not in fields and "mixed_binding" not in fields
    params = inspect.signature(project_role_activation).parameters
    assert set(params) == {"node_id", "canonical_role", "role_basis", "evaluation"}


def test_projection_does_not_reselect_the_role() -> None:
    for role in CanonicalRole:
        assert _project(role, OperabilityStatus.SUPPRESSED).canonical_role is role
    assert not any(
        "select" in n.lower() or "choose" in n.lower()
        for n in dir(mod) if not n.startswith("_")
    )
