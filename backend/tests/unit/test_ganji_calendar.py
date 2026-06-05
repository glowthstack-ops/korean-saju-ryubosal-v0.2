"""간지달력 월 그리드 산출."""

from __future__ import annotations

from saju_manse_core.calendar.ganji_calendar import build_month


def test_february_2024_grid_and_terms() -> None:
    m = build_month(2024, 2)
    assert m["year"] == 2024 and m["month"] == 2
    assert len(m["days"]) == 29  # 윤년
    terms = {t["name"]: t["date"].isoformat() for t in m["solar_terms"]}
    assert terms["입춘"] == "2024-02-04"
    assert terms["우수"] == "2024-02-19"


def test_lichun_boundary_changes_year_and_month_ganji() -> None:
    days = {d["date"].day: d for d in build_month(2024, 2)["days"]}
    # 2/4 정오는 입춘 절입(저녁) 이전 → 전년 간지·축월.
    assert days[4]["year_ganji"] == "癸卯"
    assert days[4]["month_ganji"] == "乙丑"
    assert days[4]["solar_term"] == "입춘"
    # 2/5는 입춘 이후 → 甲辰년·寅월(丙寅).
    assert days[5]["year_ganji"] == "甲辰"
    assert days[5]["month_ganji"] == "丙寅"
    # 간지 한글 병기.
    assert days[5]["day_ganji_ko"] and days[5]["year_ganji_ko"] == "갑진"


def test_calendar_enrichment_lunar_naeum_zodiac() -> None:
    d10 = next(d for d in build_month(2024, 2)["days"] if d["date"].day == 10)
    assert d10["lunar_date"] == "2024-01-01"  # 설날
    assert d10["is_leap_month"] is False
    assert d10["naeum"]  # 일주 납음
    assert d10["year_zodiac"] == "용"  # 2024 甲辰년 = 용띠
