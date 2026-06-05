"""대운/세운/월운/일운 산출."""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_BASE = dict(birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울")


def test_daewoon_table_forward() -> None:
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    assert lc.direction == "forward"  # 양남(庚=양) → 순행
    assert lc.start_age == 5  # ~15일/3
    assert len(lc.daewoon_table) == 9
    assert lc.daewoon_table[0].ganji == "戊子"  # 월주 丁亥 다음 간지
    assert lc.daewoon_table[1].ganji == "己丑"
    first = lc.daewoon_table[0]
    assert first.first_half_focus == "stem" and first.second_half_focus == "branch"
    assert (first.end_date.year - first.start_date.year) == 10


def test_daewoon_direction_backward_for_yang_year_female() -> None:
    r = calculate(BirthInput(gender="female", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    assert lc.direction == "backward"  # 양녀 → 역행
    assert lc.daewoon_table[0].ganji == "丙戌"  # 丁亥 이전 간지


def test_reference_date_populates_current_and_se_wol_il() -> None:
    r = calculate(BirthInput(gender="male", reference_date="2015-06-15", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    assert lc.current_age == 34
    assert lc.current_daewoon_index == 2  # age 25-35 구간(庚寅)
    assert [p.label for p in lc.yearly_luck] == ["2013", "2014", "2015", "2016", "2017"]
    assert len(lc.monthly_luck) == 12
    assert len(lc.daily_luck) == 30  # 2015-06
    assert lc.yearly_luck[2].ganji == "乙未"  # 2015 = 乙未


def test_no_reference_date_is_deterministic_table_only() -> None:
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    assert lc.current_age is None
    assert lc.yearly_luck == [] and lc.monthly_luck == [] and lc.daily_luck == []


def test_yongsin_alignment_marks_luck() -> None:
    # 용신 土/火, 기신 木/水. 대운 중 용신/기신운이 라벨링된다.
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    labels = {d.yongsin_relation for d in lc.daewoon_table}
    assert "용신운" in labels  # 己丑(土) 대운 등
