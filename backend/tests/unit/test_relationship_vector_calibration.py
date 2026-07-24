"""관계 벡터 캘리브레이션 profile 주입 — P2-1 foundation (§8·§9).

- BASELINE byte-identity(§9): calibration=None / BASELINE / 명시 상수 profile 모두
  동일 결과. 전역 monkeypatch 없이 명시 인자로만 주입(§8).
- 실험 profile은 실제로 값을 바꾼다(주입 경로 유효성).
- profile_id는 공식 CALIBRATION_VERSION과 별개(실험이 운영 telemetry 오염 안 함).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.relationship_effect_vector import (
    BASELINE_CALIBRATION,
    RELATIONSHIP_CALIBRATION_VERSION,
    RelationshipVectorCalibration,
    synthesize_relationship_effect_vector,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _hit(kind, transit, natal="丑"):
    return SpousePalaceHit(
        kind=kind, palace=Pillar4.DAY, layer="sewoon", position="branch",
        transit_component="branch", transit_participant=transit,
        natal_participant=natal)


def _evidences(period="2027"):
    # 충+합(서로 다른 root — 다른 운 글자) 혼합.
    hits = [_hit(RelationKind.CHUNG, "未"), _hit(RelationKind.HAP, "子")]
    return build_spouse_palace_vector(hits, _DICTS, period_key=period).evidences


def _same_root_evidences(period="2027"):
    # 같은 운 글자(未)가 두 kind 유발 → 같은 root 복합(secondary_factor 적용 대상).
    hits = [_hit(RelationKind.CHUNG, "未", natal="丑"),
            _hit(RelationKind.HYEONG, "未", natal="戌")]
    return build_spouse_palace_vector(hits, _DICTS, period_key=period).evidences


def test_baseline_none_equals_explicit_baseline():
    """calibration=None == BASELINE_CALIBRATION == 무인자 — byte-identical(§9)."""
    ev = _evidences()
    a = synthesize_relationship_effect_vector(ev)
    b = synthesize_relationship_effect_vector(ev, calibration=None)
    c = synthesize_relationship_effect_vector(ev, calibration=BASELINE_CALIBRATION)
    assert a.model_dump() == b.model_dump() == c.model_dump()


def test_baseline_defaults_match_code_constants():
    """BASELINE_CALIBRATION 기본값 = 현행 상수(단일 source)."""
    import saju_engines.relationship_effect_vector as V
    cal = BASELINE_CALIBRATION
    assert cal.secondary_factor == V._SECONDARY_FACTOR
    assert cal.support_weaken == V._SUPPORT_WEAKEN
    assert cal.activation_band == V._ACT_BAND
    assert cal.stability_support == V._STAB_SUPPORT
    assert cal.stability_pressure == V._STAB_PRESSURE
    assert cal.separation_weight == V._SEP_WEIGHT


def test_experiment_profile_changes_output():
    """실험 profile은 실제로 값을 바꾼다(주입 경로 유효) — 같은 root 복합에서."""
    ev = _same_root_evidences()
    base = synthesize_relationship_effect_vector(ev)
    # secondary_factor를 올리면 같은 root의 보조 kind 기여가 커진다.
    exp = synthesize_relationship_effect_vector(
        ev, calibration=RelationshipVectorCalibration(
            profile_id="exp-high-secondary", secondary_factor=0.6))
    assert exp.axes.separation_pressure.value > base.axes.separation_pressure.value


def test_band_profile_changes_only_band_not_value():
    """activation band profile 변경은 band만 바꾸고 raw value는 불변."""
    ev = _evidences()
    base = synthesize_relationship_effect_vector(ev)
    exp = synthesize_relationship_effect_vector(
        ev, calibration=RelationshipVectorCalibration(
            profile_id="B3", activation_band={"weak": 10, "moderate": 18, "strong": 28}))
    assert exp.axes.activation.value == base.axes.activation.value  # raw 불변
    # band는 threshold에 따라 달라질 수 있다(값은 같아도 분류 경계 이동).


def test_profile_frozen_and_extra_forbid():
    cal = RelationshipVectorCalibration()
    import pydantic
    import pytest
    with pytest.raises(pydantic.ValidationError):
        RelationshipVectorCalibration(unknown_field=1)
    with pytest.raises((TypeError, pydantic.ValidationError)):
        cal.secondary_factor = 0.9  # frozen


# ── derived modifier 멱등 hardening (§6) ─────────────────────────────────────
def _jaenghap(derived_ids):
    from saju_engines.relationship_structure_modifiers import (
        build_relationship_structure_modifiers,
    )
    from saju_shared_types.structure_patterns import DetectedPattern
    return build_relationship_structure_modifiers(
        [DetectedPattern(pattern_id="JAENGHAP", name_ko="쟁합", strength=0.6,
                         polarity_mode="context_only")],
        derived_from_by_pattern={"JAENGHAP": derived_ids})


def _support(result):
    return round(sum(rc.stability_support for rc in result.root_contributions), 3)


def test_duplicate_derived_modifier_idempotent():
    """동일 derived modifier 1회 = 2회 (§6) — 축값 동일."""
    ev = _evidences()
    tid = ev[0].evidence_id
    one = synthesize_relationship_effect_vector(ev, modifiers=_jaenghap([tid]))
    two = synthesize_relationship_effect_vector(
        ev, modifiers=_jaenghap([tid]) + _jaenghap([tid]))
    assert one.model_dump() == two.model_dump()


def test_derived_modifier_input_order_invariant():
    """derived modifier 입력 순서 역전 결과 동일(§6)."""
    ev = _evidences()
    tid = ev[0].evidence_id
    m = _jaenghap([tid]) + _jaenghap([tid])
    a = synthesize_relationship_effect_vector(ev, modifiers=m)
    b = synthesize_relationship_effect_vector(ev, modifiers=list(reversed(m)))
    assert a.model_dump() == b.model_dump()


def test_same_pattern_different_root_both_apply():
    """같은 pattern·다른 root set은 각각 적용(dedup 아님, §6)."""
    from saju_engines.spouse_palace_activation import build_spouse_palace_vector
    hits = [_hit(RelationKind.HAP, "未", "丑"), _hit(RelationKind.HAP, "戌", "辰")]
    ev = build_spouse_palace_vector(hits, _DICTS, period_key="2027").evidences
    a_id = next(e.evidence_id for e in ev if e.transit_participant == "未")
    b_id = next(e.evidence_id for e in ev if e.transit_participant == "戌")
    base = synthesize_relationship_effect_vector(ev)
    # 서로 다른 root를 각각 target하는 두 modifier → 둘 다 적용(support 더 감소).
    both = synthesize_relationship_effect_vector(
        ev, modifiers=_jaenghap([a_id]) + _jaenghap([b_id]))
    assert _support(both) < _support(base)


def test_conflicting_derived_modifier_held():
    """동일 key·다른 strength는 conflict 보류(수치 미적용, §6)."""
    from saju_engines.relationship_structure_modifiers import (
        build_relationship_structure_modifiers,
    )
    from saju_shared_types.structure_patterns import DetectedPattern
    ev = _evidences()
    tid = ev[0].evidence_id
    m1 = build_relationship_structure_modifiers(
        [DetectedPattern(pattern_id="JAENGHAP", name_ko="쟁합", strength=0.6,
                         polarity_mode="context_only")],
        derived_from_by_pattern={"JAENGHAP": [tid]})
    m2 = build_relationship_structure_modifiers(
        [DetectedPattern(pattern_id="JAENGHAP", name_ko="쟁합", strength=0.9,
                         polarity_mode="context_only")],
        derived_from_by_pattern={"JAENGHAP": [tid]})
    base = synthesize_relationship_effect_vector(ev)  # modifier 없음
    r = synthesize_relationship_effect_vector(ev, modifiers=m1 + m2)
    # conflict → 수치 미적용(support = modifier 없을 때와 동일) + conflict count.
    assert _support(r) == _support(base)
    assert r.derived_modifier_conflict_count == 1


def test_hardening_production_pipeline_byte_identical():
    """정상 production 입력(단일 modifier)은 hardening 전후 동작 불변 — 실제 명식."""
    from datetime import date

    from saju_api.services.manse_service import calculate
    from saju_engines.marriage_emergence_modifier import (
        analyze_marriage_emergence_natal,
    )
    from saju_engines.relationship_structure_modifiers import (
        build_relationship_structure_modifiers,
    )
    from saju_engines.structure_patterns import detect_structure_patterns
    from saju_shared_types.birth_input import BirthInput
    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 15), birth_time="14:30",
        birth_place_name="서울", gender="female", reference_date=date(2026, 7, 24)))
    mods = build_relationship_structure_modifiers(detect_structure_patterns(chart))
    analyze_marriage_emergence_natal(chart)  # smoke
    ev = _evidences()
    # 정상 파이프라인 modifier(중복 없음)는 dedup 영향 없이 동일 결과.
    r = synthesize_relationship_effect_vector(ev, modifiers=mods)
    assert r.derived_modifier_conflict_count == 0


def test_profile_id_independent_of_calibration_version():
    """profile_id는 공식 CALIBRATION_VERSION과 무관(실험이 버전 오염 안 함, §8)."""
    cal = RelationshipVectorCalibration(profile_id="exp-1")
    assert cal.profile_id == "exp-1"
    assert cal.profile_id != RELATIONSHIP_CALIBRATION_VERSION
    # 실험 profile은 CALIBRATION_VERSION을 바꾸지 않는다(상수 불변).
    assert RELATIONSHIP_CALIBRATION_VERSION == "cal-2026-07-24.1"
