"""관계 벡터 ↔ legacy 비교 분류 회귀 — P1-7a (RELATIONSHIP_EVENT_SYSTEM 부록 D).

각 comparison class를 구성 벡터·family 관측으로 검증한다. 감사 전용 — 분류는
읽기 전용이며 벡터·후보를 변형하지 않는다(구조 보증: 입력 dataclass는 frozen).
"""

from __future__ import annotations

from saju_api.services.relationship_legacy_comparison import (
    CandidateAbsentSubclass,
    FamilyLegacyObservation,
    LegacyVectorComparisonClass,
    PeriodComparisonInput,
    _delta_bucket,
    classify_period,
)
from saju_api.services.relationship_vector_telemetry import AuditProjectionStatus
from saju_engines.relationship_effect_vector import (
    RelationshipEffectVectorResult,
    RootEffectContribution,
)
from saju_shared_types.relationship_effect import (
    AxisStatus,
    RelationshipAxisValue,
    RelationshipEffectVector,
)

C = LegacyVectorComparisonClass


def _axis(status=AxisStatus.INSUFFICIENT_EVIDENCE, value=None, band=None):
    return RelationshipAxisValue(status=status, value=value, band=band)


def _vector(*, activation=None, stability=None, separation=None,
            roots=0, kinds=("CHUNG",), evidence_count=1, modifiers=None):
    axes = RelationshipEffectVector(
        activation=activation or _axis(),
        stability=stability or _axis(),
        separation_pressure=separation or _axis(),
    )
    contribs = [RootEffectContribution(
        signal_trigger_id=f"sig{i}", evidence_ids=[f"e{i}"],
        kinds=list(kinds)) for i in range(roots)]
    return RelationshipEffectVectorResult(
        axes=axes, root_contributions=contribs,
        independent_root_trigger_count=roots,
        evidence_count=evidence_count,
        modifiers=modifiers or [])


def _fam(name, present=True, delta=None, capped=None):
    return FamilyLegacyObservation(
        event_family=name, candidate_present=present,
        relation_delta=delta, relation_capped=capped)


def _period(vector, families, layer="sewoon"):
    return PeriodComparisonInput(
        vector=vector, period_layer=layer, subject_scope="self",
        vector_run_id="run-abc", audit_status=AuditProjectionStatus.SUCCESS,
        families=families)


def _classes(recs):
    return {r.legacy_event_family: r.comparison_class for r in recs}


# ── 양쪽 활성 ────────────────────────────────────────────────────────────────
def test_aligned():
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 15.0, "moderate"))
    recs = classify_period(_period(v, [_fam("new_relationship", delta=12.0)]))
    assert _classes(recs)["new_relationship"] is C.ALIGNED


def test_cap_saturated():
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 30.0, "strong"))
    recs = classify_period(_period(
        v, [_fam("marriage_signal", delta=22.0, capped=True)]))
    r = recs[0]
    assert r.comparison_class is C.LEGACY_CAP_SATURATED
    assert r.legacy_relation_delta_bucket == "capped_22"


def test_event_key_blind_spot():
    """같은 활성 기간에 한 family는 delta>0인데 new_relationship만 delta 0."""
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 20.0, "strong"))
    recs = classify_period(_period(v, [
        _fam("marriage_signal", delta=14.0),
        _fam("new_relationship", delta=0.0),  # 사각지대
    ]))
    cls = _classes(recs)
    assert cls["marriage_signal"] is C.ALIGNED
    assert cls["new_relationship"] is C.LEGACY_EVENT_KEY_BLIND_SPOT


def test_delta_zero_no_other_positive_is_mixed():
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 10.0, "moderate"))
    recs = classify_period(_period(v, [_fam("relationship_change", delta=0.0)]))
    assert recs[0].comparison_class is C.MIXED


def test_direction_mismatch_conservative():
    """부정 relation(separation 평가) + 결혼 후보 긍정 delta → 보수 review-required."""
    v = _vector(
        activation=_axis(AxisStatus.EVALUATED, 20.0, "strong"),
        stability=_axis(AxisStatus.EVALUATED, -1.0, "weak"),
        separation=_axis(AxisStatus.EVALUATED, 1.0, "strong"))
    recs = classify_period(_period(v, [_fam("marriage_signal", delta=18.0)]))
    assert recs[0].comparison_class is C.REVIEW_REQUIRED_DIRECTION_MISMATCH


def test_negative_on_nonformalization_family_is_aligned():
    """부정 relation이어도 new_relationship(결속 확정 의미 아님)은 mismatch 아님."""
    v = _vector(
        activation=_axis(AxisStatus.EVALUATED, 20.0, "strong"),
        separation=_axis(AxisStatus.EVALUATED, 1.0, "strong"))
    recs = classify_period(_period(v, [_fam("new_relationship", delta=12.0)]))
    assert recs[0].comparison_class is C.ALIGNED


# ── 후보 부재(활성 벡터) ─────────────────────────────────────────────────────
def test_candidate_absent_vector_present():
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 8.0, "weak"), roots=1)
    recs = classify_period(_period(v, [_fam("marriage_signal", present=False)]))
    r = recs[0]
    assert r.comparison_class is C.LEGACY_CANDIDATE_ABSENT
    assert r.candidate_absent_subclass is CandidateAbsentSubclass.VECTOR_PRESENT


def test_candidate_absent_vector_strong():
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 25.0, "strong"), roots=1)
    recs = classify_period(_period(v, [_fam("marriage_signal", present=False)]))
    assert recs[0].candidate_absent_subclass is CandidateAbsentSubclass.VECTOR_STRONG


def test_candidate_absent_multi_root():
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 25.0, "strong"), roots=3)
    recs = classify_period(_period(v, [_fam("new_relationship", present=False)]))
    assert recs[0].candidate_absent_subclass is CandidateAbsentSubclass.MULTI_ROOT


# ── 벡터 미활성 ──────────────────────────────────────────────────────────────
def test_vector_insufficient_when_evidence_but_no_axis():
    """legacy 후보 있고 P1 evidence는 있으나 activation 미평가 → VECTOR_INSUFFICIENT."""
    v = _vector(activation=_axis(AxisStatus.INSUFFICIENT_EVIDENCE), evidence_count=2)
    recs = classify_period(_period(v, [_fam("marriage_signal", delta=10.0)]))
    assert recs[0].comparison_class is C.VECTOR_INSUFFICIENT


def test_legacy_only_signal_when_no_evidence():
    """legacy 후보 있으나 P1 어댑터 대응 evidence 0 → LEGACY_ONLY_SIGNAL."""
    v = _vector(activation=_axis(AxisStatus.INSUFFICIENT_EVIDENCE), evidence_count=0)
    recs = classify_period(_period(v, [_fam("marriage_signal", delta=10.0)]))
    assert recs[0].comparison_class is C.LEGACY_ONLY_SIGNAL


# ── 구조 전용 / 무신호 ───────────────────────────────────────────────────────
def test_vector_only_structure():
    """후보 없음·activation 미평가지만 구조(비활성 evidence) 보존 → 기간 record."""
    v = _vector(activation=_axis(AxisStatus.INSUFFICIENT_EVIDENCE), evidence_count=3)
    recs = classify_period(_period(v, [_fam("marriage_signal", present=False)]))
    assert len(recs) == 1
    r = recs[0]
    assert r.comparison_class is C.VECTOR_ONLY_STRUCTURE
    assert r.legacy_event_family is None


def test_both_quiet_no_record():
    """벡터 미활성·evidence 0·후보 없음 → 기록 안 함(노이즈 방지)."""
    v = _vector(activation=_axis(AxisStatus.INSUFFICIENT_EVIDENCE), evidence_count=0)
    recs = classify_period(_period(v, [_fam("marriage_signal", present=False)]))
    assert recs == []


# ── 미평가 축 0 비교 금지 + 버킷 ─────────────────────────────────────────────
def test_unevaluated_axes_not_bucketed():
    """P1 미평가 축은 bucket None(0으로 비교하지 않음, §1)."""
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 10.0, "moderate"))
    recs = classify_period(_period(v, [_fam("new_relationship", delta=8.0)]))
    r = recs[0]
    assert r.separation_bucket is None          # separation 미평가
    assert r.stability_bucket is None
    assert r.activation_bucket == "moderate"


def test_delta_bucket_boundaries():
    assert _delta_bucket(None) is None
    assert _delta_bucket(0.0) == "zero"
    assert _delta_bucket(5.0) == "low"
    assert _delta_bucket(12.0) == "mid"
    assert _delta_bucket(20.0) == "high"
    assert _delta_bucket(22.0) == "capped_22"


def test_record_allowlist_no_forbidden_fields():
    """직렬화 필드가 §5 allowlist뿐(간지·ID·reason·발화 없음)."""
    v = _vector(activation=_axis(AxisStatus.EVALUATED, 10.0, "moderate"))
    recs = classify_period(_period(v, [_fam("new_relationship", delta=8.0)]))
    dumped = recs[0].model_dump(mode="json")
    allowed = {
        "schema_version", "calibration_version", "vector_run_id",
        "subject_scope_bucket", "period_layer", "comparison_class",
        "candidate_absent_subclass", "activation_status", "activation_bucket",
        "stability_bucket", "separation_status", "separation_bucket",
        "root_count_bucket", "kind_combo", "legacy_candidate_present",
        "legacy_event_family", "legacy_relation_delta_bucket", "legacy_capped",
        "audit_status",
    }
    assert set(dumped.keys()) == allowed
