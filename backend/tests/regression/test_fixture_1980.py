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


def test_force_analysis_strength_band(result) -> None:
    # 표준 지장간(亥=戊甲壬 등) 교정 후 己 일간이 亥戊·巳戊로 뿌리가 강해져 중화신약으로 상향.
    f = result.force_analysis
    assert f is not None
    assert f.strength.band == "중화신약"
    assert 34 <= f.strength.score <= 42
    assert f.strength.requires_validation in (True, False)


def test_force_analysis_distribution_invariants(result) -> None:
    fe = result.force_analysis.five_elements
    assert fe.strongest_element == "水"  # 재성 수 최강
    assert fe.raw_visible["木"] == 0.0  # 목 표면 부족
    assert fe.hidden_base["木"] > 0.0  # 지장간 목 존재
    # 공망 지지가 분포에서 제거되지 않는다 (정책)
    assert sum(fe.effective_force.values()) > 0


def test_force_analysis_rootedness_vs_strong_gate(result) -> None:
    s = result.force_analysis.strength
    # 신왕(rootedness)과 신강(gate)은 분리된다.
    assert "label" in s.rootedness
    assert set(s.strong_chart_gate) == {
        "month_or_day_branch_ally",
        "another_ally_position_exists",
        "passed",
    }


def test_structure_analysis(result) -> None:
    sa = result.structure_analysis
    assert sa is not None
    rel_types = {i.relation_type for i in sa.interactions}
    # 申亥 해 + 亥亥 자형
    assert "harm" in rel_types
    assert "self_punishment" in rel_types
    amp_types = {a.relation_type for a in sa.amplifiers}
    assert "gan_yeo_ji_dong" in amp_types  # 庚申, 戊辰
    assert "branch_duplication" in amp_types  # 亥亥
    assert -10 <= sa.structure_modifier <= 10
    for v in (sa.stability.yongsin_stability, sa.stability.root_stability):
        assert 0.0 <= v <= 1.0


def test_geokguk(result) -> None:
    g = result.geokguk
    assert g is not None
    assert g.main_structure == "정재격"  # v1 reference 격국
    assert g.basis["month_branch"] == "亥"
    assert any("발현" in a for a in g.auxiliary_structures)


def test_yongsin_candidates(result) -> None:
    y = result.yongsin_analysis
    assert y is not None
    assert y.status == "candidate"
    assert y.requires_validation is True
    # v1 reference: 용신 토 · 희신 화 · 기신 목 · 구신 수
    assert y.final["yongsin"] == "土"
    assert y.final["heesin"] == "火"
    assert y.final["gisin"] == "木"
    assert y.final["gusin"] == "水"
    assert y.final["selected_model"] == "support_day_master"


def test_luck_cycles(result) -> None:
    lc = result.luck_cycles
    assert lc is not None
    assert lc.direction == "forward"  # 양남(庚) 순행
    assert lc.start_age == 5
    assert lc.daewoon_table[0].ganji == "戊子"  # 월주 丁亥 다음
    assert len(lc.daewoon_table) == 9
    # reference_date 없는 fixture → 세운/월운/일운은 비어 있고 대운표만.
    assert lc.yearly_luck == []


def test_deterministic(fixture: dict) -> None:
    a = calculate(BirthInput(**fixture["input"]))
    b = calculate(BirthInput(**fixture["input"]))
    assert a.model_dump_json() == b.model_dump_json()
    assert a.chart_id == b.chart_id
