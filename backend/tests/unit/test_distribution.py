"""오행분포 / 십성분포 layer invariants (five_element_distribution_tests §2)."""

from __future__ import annotations

import pytest
from saju_manse_analysis.distribution.ten_god_distribution import GROUPS

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput, TimeCalculationOptions


@pytest.fixture(scope="module")
def force():
    # Civil chart (hour 己巳) matches the spec distribution-test chart.
    r = calculate(
        BirthInput(
            birth_date="1980-11-22",
            birth_time="09:08",
            birth_place_name="서울",
            gender="male",
            time_options=TimeCalculationOptions(apply_true_solar_time=False),
        )
    )
    return r.force_analysis


def test_raw_visible_has_no_surface_wood(force) -> None:
    # 庚申丁亥己亥己巳: no wood appears on any stem or branch surface ("목 부족").
    assert force.five_elements.raw_visible["木"] == 0.0


def test_hidden_wood_present(force) -> None:
    # Wood lives only in the 亥 hidden stems — raw/effective separation.
    assert force.five_elements.hidden_base["木"] > 0.0
    assert force.five_elements.effective_force["木"] > 0.0


def test_effective_strongest_is_water_and_excessive(force) -> None:
    assert force.five_elements.strongest_element == "水"
    assert "水" in force.five_elements.excessive_elements


def test_effective_percent_normalized(force) -> None:
    assert sum(force.five_elements.effective_percent.values()) == pytest.approx(100, abs=0.1)


def test_ten_god_groups_present(force) -> None:
    groups = force.ten_gods.groups
    assert set(groups) == set(GROUPS)
    # 己 day master with 亥亥 water → wealth (재성 水) is the dominant group.
    assert max(groups, key=lambda g: groups[g]) == "wealth"


def test_ten_god_presence_classification(force) -> None:
    tg = force.ten_gods
    # missing vs hidden_only are disjoint, and a hidden-only god is not "missing".
    assert set(tg.missing_ten_gods).isdisjoint(tg.hidden_only_ten_gods)


def test_element_distribution_trace_records_modifiers(force) -> None:
    trace = force.five_elements.calculation_trace
    for key in (
        "position_weights",
        "hidden_weight",
        "month_main_qi_bonus",
        "non_main_bonus_cap",
        "void_modifier",
        "deferred_modifiers",
    ):
        assert key in trace
    # 합충형파해/병존 보정은 구조작용 단계로 연기됨이 trace에 남는다.
    assert "relation" in trace["deferred_modifiers"]
    # 월령 본기 보정 + 중기/여기 cap.
    assert trace["month_main_qi_bonus"]["factor"] == 1.30
    assert trace["non_main_bonus_cap"] == 1.03


def test_hidden_only_wood_is_amjang(force) -> None:
    # 버그픽스: 표면 木 없음, 亥중甲만 → 암장(hidden-only), 강한 오행 아님.
    fe = force.five_elements
    assert fe.raw_visible["木"] == 0.0
    names = [h["element"] for h in fe.hidden_only_elements]
    assert "木" in names
    wood = next(h for h in fe.hidden_only_elements if h["element"] == "木")
    assert wood["operability"] == "low" and wood["label"] == "암장"
    assert "木" in fe.display_summary["deficient_visible_elements"]
