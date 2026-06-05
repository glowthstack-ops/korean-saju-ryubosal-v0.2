"""Golden-fixture regression: 1980-11-22 09:08 Seoul male."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "test_fixtures"
    / "manse"
    / "1980-11-22_seoul_male.json"
)


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result(fixture: dict):
    return calculate(BirthInput(**fixture["input"]))


def test_pillars_match(result, fixture: dict) -> None:
    exp = fixture["expected"]
    assert result.pillars.year.ganji == exp["year_pillar"]
    assert result.pillars.month.ganji == exp["month_pillar"]
    assert result.pillars.day.ganji == exp["day_pillar"]
    assert result.pillars.day_master == exp["day_master"]
    # hour pillar uses true solar time by default
    assert result.pillars.hour.ganji == exp["true_solar_time_hour_pillar"]


def test_true_solar_hour_change_flagged(result, fixture: dict) -> None:
    exp = fixture["expected"]
    tc = result.time_correction
    assert tc.standard_time_hour_pillar == exp["standard_time_hour_pillar"]
    assert tc.true_solar_time_hour_pillar == exp["true_solar_time_hour_pillar"]
    assert tc.hour_pillar_changed_by_true_solar_time is True


def test_solar_term_and_extras(result, fixture: dict) -> None:
    exp = fixture["expected"]
    assert result.solar_term_basis.previous_term_name == exp["month_governing_term"]
    assert sorted(result.pillars.gongmang_branches) == sorted(exp["gongmang_branches"])
    assert result.input_summary["daewoon_direction"] == exp["daewoon_direction"]


def test_ten_gods(result, fixture: dict) -> None:
    tg = fixture["expected"]["ten_gods"]
    assert result.pillars.year.stem_ten_god == tg["year_stem"]
    assert result.pillars.month.stem_ten_god == tg["month_stem"]
    assert result.pillars.month.branch_main_ten_god == tg["month_branch_main"]
    assert result.pillars.hour.stem_ten_god == tg["hour_stem_true_solar"]


def test_metadata_and_trace_present(result) -> None:
    assert result.metadata.engine_version
    assert result.metadata.solar_terms_version
    assert result.metadata.tzdata_version
    assert result.trace.get("absolute_instant_utc")


def test_deterministic(fixture: dict) -> None:
    a = calculate(BirthInput(**fixture["input"]))
    b = calculate(BirthInput(**fixture["input"]))
    assert a.model_dump_json() == b.model_dump_json()
    assert a.chart_id == b.chart_id
