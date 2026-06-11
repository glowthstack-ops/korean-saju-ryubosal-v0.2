"""Edge paths: unknown time, lunar conversion."""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput


def test_time_unknown_suppresses_hour_pillar() -> None:
    r = calculate(
        BirthInput(
            birth_date="1980-11-22",
            birth_time_unknown=True,
            birth_place_name="서울",
            gender="male",
        )
    )
    assert r.pillars is not None and r.time_correction is not None
    assert r.pillars.hour is None
    assert r.pillars.day.ganji == "己亥"  # date-stable pillars remain valid
    assert r.input_summary["birth_time_unknown"] is True
    assert r.time_correction.standard_time_hour_pillar is None


def test_lunar_conversion_matches_solar_fixture() -> None:
    # 음력 1980-10-15 → 양력 1980-11-22 (same chart as the golden fixture).
    r = calculate(
        BirthInput(
            calendar_type="lunar",
            is_leap_month=False,
            birth_date="1980-10-15",
            birth_time="09:08",
            birth_place_name="서울",
        )
    )
    assert r.time_correction is not None and r.pillars is not None
    converted = r.time_correction.lunar_converted_solar_date
    assert converted is not None and converted.isoformat() == "1980-11-22"
    assert r.pillars.day.ganji == "己亥"
    assert r.pillars.month.ganji == "丁亥"


def test_twin_shift_changes_calculation_basis_and_chart_id() -> None:
    base = BirthInput(
        birth_date="1980-11-22",
        birth_time="00:58",
        birth_place_name="서울",
        gender="male",
    )
    shifted = BirthInput(
        birth_date="1980-11-22",
        birth_time="00:58",
        birth_place_name="서울",
        gender="male",
        chart_variant="twin_adjusted",
        twin_shift=5,
    )
    r1 = calculate(base)
    r2 = calculate(shifted)
    assert r1.chart_id != r2.chart_id
    assert r2.input_summary["chart_variant"] == "twin_adjusted"
    assert r2.trace["twin_adjustment"]["applied"] is True


def test_hour_boundary_sensitive_warning() -> None:
    r = calculate(
        BirthInput(
            birth_date="1980-11-22",
            birth_time="01:00",
            birth_place_name="서울",
            gender="male",
            time_options={"apply_true_solar_time": False},
        )
    )
    assert r.time_correction is not None
    assert any("hour_boundary_sensitive" in w for w in r.time_correction.warnings)
