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
    assert len(lc.daewoon_table) == 10
    assert lc.daewoon_table[0].ganji == "戊子"  # 월주 丁亥 다음 간지
    assert lc.daewoon_table[1].ganji == "己丑"
    first = lc.daewoon_table[0]
    assert first.first_half_focus == "stem" and first.second_half_focus == "branch"
    assert (first.approx_end_date.year - first.approx_start_date.year) == 10


def test_daewoon_transformed_elements_are_real_elements() -> None:
    # transformed_elements 에는 오행(木火土金水)만 들어가야 한다(쌍 문자열 금지).
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    valid = {"木", "火", "土", "金", "水"}
    for d in lc.daewoon_table:
        assert all(e in valid for e in d.transformed_elements)
    # 정밀 교운일시가 trace에 남는다.
    assert len(lc.trace["exact_jiao_un_dates"]) == 10


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
    assert [p.label for p in lc.yearly_luck] == [
        "2011", "2012", "2013", "2014", "2015", "2016", "2017", "2018", "2019", "2020",
    ]
    assert len(lc.monthly_luck) == 12
    assert len(lc.daily_luck) == 30  # 2015-06
    assert lc.yearly_luck[4].ganji == "乙未"  # 2015 = 乙未 (창 기준연-4 → index 4)
    assert lc.yearly_luck[4].twelve_unseong  # 세운에도 운성이 채워진다


def test_daewoon_gongmang_activation() -> None:
    # 1980 fixture 공망 辰巳 → 壬辰/癸巳 대운에서 공망전실 등 활성이 잡힌다.
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    acts = [a for d in lc.daewoon_table for a in d.gongmang_activation]
    assert any("공망" in a for a in acts)


def test_no_reference_date_is_deterministic_table_only() -> None:
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    assert lc.current_age is None
    assert lc.yearly_luck == [] and lc.monthly_luck == [] and lc.daily_luck == []


def test_yongsin_alignment_marks_luck() -> None:
    # 용신 土/火, 기신 木/水. 대운 중 용신/기신운이 라벨링된다(coarse 호환).
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    labels = {d.yongsin_relation for d in lc.daewoon_table}
    assert "용신운" in labels  # 己丑(土) 대운 등


def test_luck_stem_branch_split_and_labels() -> None:
    # 용신 土/火, 기신 木/水. 천간(드러남)·지지(기반) 분리 평가 + 세분 라벨.
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    by_ganji = {d.ganji: d for d in lc.daewoon_table}
    # 戊子: 천간 戊土(용신) + 지지 子水(기신) → 천간 용신·지지 기신 혼합.
    wuzi = by_ganji["戊子"]
    assert wuzi.stem_effect is not None and wuzi.branch_effect is not None
    assert wuzi.stem_effect.type == "용신" and wuzi.branch_effect.type == "기신"
    assert wuzi.luck_label_code == "mixed_yongsin_surface"
    # 己丑: 천간 己土 + 지지 丑(정기 土) → 강한 용신운.
    assert by_ganji["己丑"].luck_label_code == "pure_yongsin_luck"
    # 甲午: 천간 甲木(기신) + 지지 午(정기 丁火 용신) → 천간 기신·지지 용신 혼합.
    chunwu = by_ganji["甲午"]
    assert chunwu.stem_effect.type == "기신" and chunwu.branch_effect.type == "용신"
    assert chunwu.luck_label_code == "mixed_gisin_surface"


def test_luck_branch_uses_hidden_stem_weighting() -> None:
    # 지지 효과는 지장간(정기 중심) 가중. 巳(戊庚丙)는 火 용신이 정기라 강한 +.
    # (癸巳는 공망+충으로 동태 약화되므로 base_score로 본다.)
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    si = {d.ganji: d for d in lc.daewoon_table}["癸巳"].branch_effect
    assert si is not None
    assert si.element == "火" and (si.base_score or si.score) > 0.5  # 丙火 정기(0.6) 용신
    assert "丙火" in si.detail


def test_daewoon_carries_sewoon() -> None:
    # 각 대운에 그 10년의 세운이 선계산되어 붙는다(대운→세운 연동).
    r = calculate(BirthInput(gender="male", reference_date="2015-06-15", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    for d in lc.daewoon_table:
        assert len(d.sewoon) == 10
        assert d.sewoon[0].twelve_unseong  # 세운에도 운성
    d2 = lc.daewoon_table[2]  # start_age 25 → 첫 세운 = 1980+25
    assert int(d2.sewoon[0].label) == 1980 + d2.start_age


def test_luck_branch_void_clash_dynamics() -> None:
    # 공망 辰巳 → 공망/충이 용신·기신의 발현(실속·사건성)을 바꾼다.
    r = calculate(BirthInput(gender="male", **_BASE))
    lc = r.luck_cycles
    assert lc is not None
    by = {d.ganji: d for d in lc.daewoon_table}
    # 壬辰: 辰 공망 + 지지 용신(土) → 공망 용신운, 작동력 약화·신뢰도↓.
    rz = by["壬辰"].branch_effect
    assert rz is not None and rz.is_void and not rz.has_clash
    assert rz.branch_label.startswith("공망 용신운")
    assert abs(rz.score) < abs(rz.base_score) and rz.reliability < 1.0
    # 癸巳: 巳 공망 + 巳亥충 → 공망충발, 사건성·변동성↑·신뢰도 최저.
    gs = by["癸巳"].branch_effect
    assert gs is not None and gs.is_void and gs.has_clash
    assert "공망충발" in gs.branch_label
    assert gs.event_trigger >= 1.5 and gs.volatility >= 1.5 and gs.reliability <= 0.5
    # 庚寅: 충만(지지 기신) → 충동 기신운(이중 감산 없이 동태만).
    gy = by["庚寅"].branch_effect
    assert gy is not None and gy.has_clash and not gy.is_void
    assert "충동 기신운" in gy.branch_label
