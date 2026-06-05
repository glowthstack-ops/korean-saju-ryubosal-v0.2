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


def test_effective_strongest_is_water(force) -> None:
    # 재성 水가 최강(자리별 가중치 + 본/중/여 비율 적용 후에도 유지).
    assert force.five_elements.strongest_element == "水"


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


def test_effective_percent_exact_lock(force) -> None:
    # 버그픽스 회귀 고정: 예전 과대 산식(亥중甲 0.6 + 글로벌 계절보정)이 돌아오면 실패해야.
    eff = force.five_elements.effective_percent
    # 자리별 가중치 × 본/중/여 비율(여0.2·중0.2·정0.6 등) 반영 후 고정값.
    assert eff["木"] == pytest.approx(8.80, abs=0.2)
    assert eff["火"] == pytest.approx(18.83, abs=0.2)
    assert eff["土"] == pytest.approx(22.32, abs=0.2)
    assert eff["金"] == pytest.approx(17.36, abs=0.2)
    assert eff["水"] == pytest.approx(32.69, abs=0.2)


def test_visible_is_simple_surface_count_not_weighted(force) -> None:
    # 표시용(visible)은 **단순 표면 글자 수** — 위치가중치 영향 없음.
    # 庚申丁亥己亥己巳: 표면 木0·火2·土2·金2·水2 → 木0·火25·土25·金25·水25.
    vis = force.five_elements.visible_percent
    assert vis["木"] == 0.0
    assert vis["火"] == 25.0 and vis["土"] == 25.0 and vis["金"] == 25.0 and vis["水"] == 25.0
    # 위치가중(effective)과 명확히 다르다(섞이지 않음).
    assert force.five_elements.effective_percent["水"] != vis["水"]
    # 십성 표시용: 정관/편관은 표면 부재(-), 정재는 표면 존재.
    tg = force.ten_gods
    assert tg.visible_percent["정관"] == 0.0 and "정관" in tg.visible_absent
    assert tg.visible_percent["정재"] > 0.0


def test_visible_without_day_master_drops_one_earth(force) -> None:
    # 일간(己=土) 1글자만 제외한 별도 필드.
    wo = force.five_elements.visible_percent_without_day_master
    assert wo["土"] < force.five_elements.visible_percent["土"]
    assert wo["木"] == 0.0


def test_distribution_rates_normalized_and_day_master_handling(force) -> None:
    fe = force.five_elements
    tg = force.ten_gods
    # 세 분포 모두 100%로 정규화.
    assert sum(fe.distribution_total.values()) == pytest.approx(100, abs=0.1)
    assert sum(fe.distribution_environment.values()) == pytest.approx(100, abs=0.1)
    assert sum(tg.distribution.values()) == pytest.approx(100, abs=0.1)
    # 원국(일간 포함)은 일간 己(土)를 포함하므로 환경(일간 제외)보다 土 비중이 높다.
    assert fe.distribution_total["土"] > fe.distribution_environment["土"]
    # 십성 분포(일간 제외): 재성 水 = 정재가 최강, 일간 비견 자동가산 없음.
    assert max(tg.distribution, key=lambda t: tg.distribution[t]) == "정재"


def test_hidden_support_lists_amjang_sources(force) -> None:
    # 표면에도 있는 오행의 지장간 보조도 설명 가능(표면 %에는 섞지 않음).
    hs = force.five_elements.hidden_support
    assert "申여戊" in hs.get("土", []) and "巳여戊" in hs.get("土", [])


def test_visible_normalizes_over_present_chars_when_time_unknown() -> None:
    # 시간 모름 → 시주 제외, 존재하는 6글자(천간3+지지3) 기준으로 정규화.
    r = calculate(
        BirthInput(
            birth_date="1980-11-22",
            birth_time_unknown=True,
            birth_place_name="서울",
            gender="male",
        )
    )
    assert r.force_analysis is not None
    vis = r.force_analysis.five_elements.visible_percent
    assert vis["木"] == 0.0
    assert sum(vis.values()) == pytest.approx(100.0, abs=0.1)
    # 6글자 중 火(丁)·土(己) 각 1 → 16.67%, 金(庚申)·水(亥亥) 각 2 → 33.33%.
    assert vis["火"] == pytest.approx(16.67, abs=0.1)
    assert vis["水"] == pytest.approx(33.33, abs=0.1)


def test_strongest_visible_elements_handles_tie(force) -> None:
    # 표면 개수가 동률(火土金水=2)이면 단일값이 아니라 배열로 표기.
    arr = force.five_elements.display_summary["strongest_visible_elements"]
    assert isinstance(arr, list) and set(arr) == {"火", "土", "金", "水"}


def test_hidden_only_wood_is_amjang(force) -> None:
    # 버그픽스: 표면 木 없음, 亥중甲만 → 암장(hidden-only), 강한 오행 아님.
    fe = force.five_elements
    assert fe.raw_visible["木"] == 0.0
    names = [h["element"] for h in fe.hidden_only_elements]
    assert "木" in names
    wood = next(h for h in fe.hidden_only_elements if h["element"] == "木")
    assert wood["operability"] == "low" and wood["label"] == "암장"
    assert "木" in fe.display_summary["deficient_visible_elements"]
