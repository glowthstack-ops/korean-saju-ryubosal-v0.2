"""P2 효과 벡터·병목 회귀 — CAREER_TRANSITION_SYSTEM §4·§9·§13-2·§15.

핵심 절대 게이트는 `double_contribution`(INV-11)이다. 그 외 병목이 Kind별로 다르고
(INV-4), 예측 여건이 실제 완료를 만들지 않는지(INV-15) 검증한다.
"""

from __future__ import annotations

from saju_engines.career_effect_vector import (
    assess_bottleneck,
    audit_contributions,
    build_effect_vector,
    split_factors,
)
from saju_shared_types.career_effect_vector import (
    AXIS_TRACK,
    REQUIRED_GATES,
    BottleneckAssessment,
    BottleneckStatus,
    CareerEffectVector,
    CareerGate,
    ContributionRole,
    EffectAxis,
    EffectContribution,
    FactorKind,
)
from saju_shared_types.career_transition import CareerTrack, CareerTransitionKind


def _c(evidence: str, axis: EffectAxis, value: float = 1.0, *, signal: str | None = None,
       role: ContributionRole = ContributionRole.PRIMARY) -> EffectContribution:
    return EffectContribution(
        evidence_id=evidence, signal_ref=signal or f"SIG_{evidence}",
        axis=axis, value=value, role=role,
        prediction_snapshot_id="snap-1", candidate_id="cand-1", period="2027",
    )


# ── double_contribution (P2 핵심 절대 게이트) ──────────────────────────────


def test_same_evidence_twice_on_same_axis_is_violation() -> None:
    """같은 evidence가 같은 축에 중복 가산되면 위반이며 벡터를 만들지 않는다."""
    contribs = (
        _c("EV-1", EffectAxis.AGREEMENT_QUALITY),
        _c("EV-1", EffectAxis.AGREEMENT_QUALITY),
    )
    vector, audit = build_effect_vector(contribs)
    assert not audit.is_clean
    assert ("EV-1", "agreement_quality") in audit.duplicates
    assert vector is None  # fail-closed — 조용한 이중 가산 금지


def test_same_signal_on_different_axes_via_distinct_evidence_is_allowed() -> None:
    """같은 원천 신호가 서로 다른 evidence로 다른 축에 기여하는 것은 허용된다(§15-3)."""
    contribs = (
        _c("EV-1", EffectAxis.AGREEMENT_QUALITY, signal="STRUCT_GWAN_IN"),
        _c("EV-2", EffectAxis.STABILIZATION, signal="STRUCT_GWAN_IN"),
    )
    vector, audit = build_effect_vector(contribs)
    assert audit.is_clean
    assert vector is not None
    assert vector.by_axis[EffectAxis.AGREEMENT_QUALITY] == 1.0
    assert vector.by_axis[EffectAxis.STABILIZATION] == 1.0


def test_derived_summary_is_not_re_added_as_primary() -> None:
    """파생 요약값을 원천 기여로 다시 합산하면 위반이다."""
    contribs = (
        _c("EV-1", EffectAxis.SELECTION_PROGRESS),
        _c("PROC-ACT", EffectAxis.SELECTION_PROGRESS, role=ContributionRole.DERIVED),
    )
    vector, audit = build_effect_vector(contribs)
    assert not audit.is_clean
    assert "PROC-ACT" in audit.derived_as_primary
    assert vector is None


def test_legacy_scored_evidence_cannot_be_added_again() -> None:
    """legacy 점수에 이미 반영된 evidence를 신규 adapter가 다시 가산하면 위반이다."""
    contribs = (_c("EV-LEGACY", EffectAxis.OPPORTUNITY_ACTIVATION),)
    vector, audit = build_effect_vector(
        contribs, legacy_scored_evidence_ids=frozenset({"EV-LEGACY"})
    )
    assert not audit.is_clean
    assert "EV-LEGACY" in audit.legacy_mixed
    assert vector is None


def test_process_activation_is_derived_not_stored_contribution() -> None:
    """process_activation은 파생 요약값이며 기여 목록에 들어가지 않는다."""
    vector, audit = build_effect_vector(
        (_c("EV-1", EffectAxis.SELECTION_PROGRESS, 0.4),
         _c("EV-2", EffectAxis.AGREEMENT_QUALITY, 0.6))
    )
    assert audit.is_clean and vector is not None
    assert abs(vector.process_activation - 0.5) < 1e-9
    assert "process_activation" not in CareerEffectVector.model_fields


# ── 축 소유권 ──────────────────────────────────────────────────────────────


def test_each_axis_is_owned_by_exactly_one_track() -> None:
    """축은 정확히 한 트랙이 소유한다 — 트랙 간 이중 소유 금지."""
    assert set(AXIS_TRACK) == set(EffectAxis)
    opportunity = {a for a, t in AXIS_TRACK.items() if t is CareerTrack.OPPORTUNITY}
    assert opportunity == {
        EffectAxis.OPPORTUNITY_ACTIVATION,
        EffectAxis.SELECTION_PROGRESS,
        EffectAxis.AGREEMENT_QUALITY,
    }
    assert AXIS_TRACK[EffectAxis.EXIT_FRICTION] is CareerTrack.EXIT
    assert AXIS_TRACK[EffectAxis.STABILIZATION] is CareerTrack.ENTRY


# ── Kind별 병목 (INV-4) ────────────────────────────────────────────────────


def _vector(**axis_values: float) -> CareerEffectVector:
    contribs = tuple(
        _c(f"EV-{i}", EffectAxis(name), value)
        for i, (name, value) in enumerate(axis_values.items())
    )
    vector, audit = build_effect_vector(contribs)
    assert audit.is_clean and vector is not None
    return vector


def test_bottleneck_uses_minimum_not_average() -> None:
    """초기 단계의 높은 값이 후속 미성립을 덮지 못한다."""
    v = _vector(agreement_quality=0.9, exit_pressure=0.8, entry_realization=0.1)
    a = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert a.bottleneck_gate is CareerGate.ENTRY
    assert a.forecast_completion_readiness == 0.1  # 평균(0.6)이 아니다


def test_resignation_only_needs_exit_alone() -> None:
    """퇴사 단독은 exit만 필수 — entry 부재로 영원히 미완료가 되지 않는다."""
    v = _vector(exit_pressure=0.7)
    a = assess_bottleneck(CareerTransitionKind.RESIGNATION_ONLY, v)
    assert [g.gate for g in a.gate_readiness] == [CareerGate.EXIT]
    assert a.forecast_completion_readiness == 0.7


def test_job_gain_from_unemployed_excludes_exit_gate() -> None:
    """무직 취업은 exit 관문을 요구하지 않는다."""
    gates = REQUIRED_GATES[CareerTransitionKind.JOB_GAIN_FROM_UNEMPLOYED]
    assert CareerGate.EXIT not in gates
    v = _vector(selection_progress=0.6, agreement_quality=0.5, entry_realization=0.8)
    a = assess_bottleneck(CareerTransitionKind.JOB_GAIN_FROM_UNEMPLOYED, v)
    assert a.forecast_completion_readiness == 0.5


def test_internal_transfer_needs_neither_exit_nor_external_entry() -> None:
    """내부 전보는 내부 결정 + 배치 실행만 요구한다."""
    gates = REQUIRED_GATES[CareerTransitionKind.INTERNAL_TRANSFER]
    assert gates == (CareerGate.INTERNAL_DECISION, CareerGate.ASSIGNMENT_EXECUTION)
    assert CareerGate.EXIT not in gates


def test_every_kind_has_required_gates() -> None:
    """모든 Kind가 필수 관문을 갖는다(빈 관문으로 자동 완료되지 않도록)."""
    assert set(REQUIRED_GATES) == set(CareerTransitionKind)
    for kind, gates in REQUIRED_GATES.items():
        assert gates, f"{kind}: required_gates 없음"


def test_forecast_readiness_does_not_create_realization() -> None:
    """예측 여건은 실제 완료를 만들지 않는다(INV-15)."""
    v = _vector(agreement_quality=1.0, exit_pressure=1.0, entry_realization=1.0)
    a = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert a.forecast_completion_readiness == 1.0
    # 완료 상태(realization_status)를 소유하지 않는다.
    assert "realization_status" not in BottleneckAssessment.model_fields


# ── support / blocker ──────────────────────────────────────────────────────


def test_factors_split_by_sign_and_carry_no_score() -> None:
    """support/blocker는 서술 보조이며 점수를 만들지 않는다."""
    v = _vector(opportunity_activation=0.5, exit_friction=-0.3)
    supporting, blocking = split_factors(v)
    assert [f.kind for f in supporting] == [FactorKind.SUPPORTING]
    assert [f.kind for f in blocking] == [FactorKind.BLOCKING]
    assert blocking[0].axis is EffectAxis.EXIT_FRICTION
    assert not hasattr(blocking[0], "value")   # 요인은 값을 갖지 않는다


# ── 감사 계약 ──────────────────────────────────────────────────────────────


def test_audit_dedup_key_matches_ssot_composition() -> None:
    """중복 식별 키가 §15-3 구성과 일치한다."""
    c = _c("EV-1", EffectAxis.AGREEMENT_QUALITY)
    assert c.dedup_key == ("snap-1", "cand-1", "2027", "EV-1", "agreement_quality", "primary")


def test_clean_contributions_produce_vector() -> None:
    """위반이 없으면 벡터가 만들어지고 축 합이 반영된다."""
    contribs = (
        _c("EV-1", EffectAxis.SELECTION_PROGRESS, 0.3),
        _c("EV-2", EffectAxis.SELECTION_PROGRESS, 0.2),   # 다른 evidence — 허용
    )
    audit = audit_contributions(contribs)
    assert audit.is_clean
    vector, _ = build_effect_vector(contribs)
    assert vector is not None
    assert abs(vector.by_axis[EffectAxis.SELECTION_PROGRESS] - 0.5) < 1e-9


def test_missing_required_gate_is_not_evaluable_not_zero() -> None:
    """필수 관문의 축 근거가 없으면 병목을 0이나 1로 추정하지 않는다."""
    v = _vector(agreement_quality=0.9)   # EXTERNAL_MOVE 는 exit·entry 도 필요
    a = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert a.status is BottleneckStatus.NOT_EVALUABLE
    assert a.forecast_completion_readiness is None      # 0 으로 추정 금지
    assert a.bottleneck_gate is None
    assert set(a.missing_gates) == {CareerGate.EXIT, CareerGate.ENTRY}
    assert all(r.readiness is None for r in a.gate_readiness if r.gate in a.missing_gates)


def test_all_gates_present_becomes_evaluable() -> None:
    """모든 필수 관문에 근거가 있어야 병목이 판정된다."""
    v = _vector(agreement_quality=0.9, exit_pressure=0.4, entry_realization=0.6)
    a = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert a.status is BottleneckStatus.EVALUABLE
    assert a.missing_gates == ()
    assert a.forecast_completion_readiness == 0.4


def test_derived_contribution_never_enters_vector_or_sum() -> None:
    """DERIVED 기여는 원시 목록·합산 입력 어디에도 들어가지 못한다."""
    vector, audit = build_effect_vector(
        (_c("EV-1", EffectAxis.SELECTION_PROGRESS, 0.5),
         _c("SUMMARY", EffectAxis.SELECTION_PROGRESS, 9.9, role=ContributionRole.DERIVED))
    )
    assert vector is None and not audit.is_clean       # 벡터 자체가 생성되지 않음
    # DERIVED 를 뺀 입력만 있으면 정상 생성되고 합산에도 9.9 가 섞이지 않는다.
    clean, ok = build_effect_vector((_c("EV-1", EffectAxis.SELECTION_PROGRESS, 0.5),))
    assert ok.is_clean and clean is not None
    assert clean.by_axis[EffectAxis.SELECTION_PROGRESS] == 0.5
    assert all(c.role is ContributionRole.PRIMARY for c in clean.contributions)
