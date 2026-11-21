"""입춘 경계 — 양력 2월은 사주의 해가 바뀌는 달 (2026-11-21 데굴님 승인).

"2월의 경우 해가 바뀌는 부분도 있어서 입춘 전후 모두 설명해 주는 게 맞다 … 민속 방향은 입춘 전후로
모두 풀어 준다." 세운·연간 민속 흉방은 입춘에 바뀌므로, 2월 질문에는 양쪽을 다 싣고, 1월~입춘 전
날짜를 달력 연도로 읽던 기준 연도도 입춘 기준으로 맞춘다.
"""

from __future__ import annotations

from datetime import date

from saju_engines.context_reducer import _avoidance_year, _folk_taboo_lines
from saju_engines.folk_direction import folk_note_for_day
from saju_engines.ipchun_boundary import (
    detect_ipchun_boundary,
    format_ipchun_lines,
    lichun_date,
    sewoon_year_of_day,
)
from saju_engines.query_parser import parse_message
from saju_shared_types.intent import AnchorDate, Granularity, IntentJson, QueryType, TimeRange

_TODAY = date(2026, 11, 21)
_FAV = {"木": "기신", "火": "희신", "土": "용신", "金": "한신", "水": "구신"}


def _month(
    start: str, end: str | None = None, anchor: str | None = None, label: str = "2월 12일"
) -> TimeRange:
    return TimeRange(
        type="absolute", granularity=Granularity.MONTH, start=start, end=end or start,
        anchor_dates=[AnchorDate(label=label, date=anchor)] if anchor else [],
    )


def _day(start: str, end: str | None = None) -> TimeRange:
    return TimeRange(type="absolute", granularity=Granularity.DAY, start=start, end=end or start)


def _relocation_intent(question: str) -> IntentJson:
    return parse_message(question, _TODAY, current_month_label="2026-11").intents[0]


def test_lichun_and_sewoon_year_follow_the_solar_term_table() -> None:
    assert lichun_date(2027) == date(2027, 2, 4)
    assert sewoon_year_of_day(date(2027, 2, 3)) == 2026
    assert sewoon_year_of_day(date(2027, 2, 4)) == 2027
    assert sewoon_year_of_day(date(2027, 1, 20)) == 2026


def test_february_month_window_covers_both_sides() -> None:
    b = detect_ipchun_boundary(_month("2027-02", anchor="2027-02-12"))
    assert b is not None and (b.year, b.lichun, b.side) == (2027, date(2027, 2, 4), "both")
    lines = "\n".join(format_ipchun_lines(b, "己", _FAV))
    assert "[입춘 경계 — 양력 2027년 2월은 사주의 해가 바뀌는 달]" in lines
    assert "사용자가 말한 2월 12일은 입춘 뒤에 든다" in lines
    assert "입춘 전(2월 1일~3일): 세운 丙午" in lines and "월운 辛丑" in lines
    assert "입춘부터(2월 4일~): 세운 丁未" in lines and "월운 壬寅" in lines
    assert "천간 정인·희신" in lines  # 丙 — 己 일간 기준 십성·역할은 엔진 값


def test_approximate_date_before_ipchun_still_gets_the_boundary() -> None:
    """'2월 2일쯤'은 丑월 라벨(01)이지만 말한 날이 양력 2월이라 경계를 싣는다."""
    b = detect_ipchun_boundary(_month("2027-01", anchor="2027-02-02", label="2월 2일"))
    assert b is not None and b.side == "both" and b.stated == date(2027, 2, 2)
    assert "사용자가 말한 2월 2일은 입춘 전에 든다" in "\n".join(
        format_ipchun_lines(b, "己", _FAV)
    )


def test_single_day_gets_only_its_own_side() -> None:
    before = detect_ipchun_boundary(_day("2027-02-02"))
    after = detect_ipchun_boundary(_day("2027-02-12"))
    assert before is not None and before.side == "before"
    assert after is not None and after.side == "after"
    assert "丙午" in "\n".join(format_ipchun_lines(before, "己", _FAV))
    assert "丙午" not in "\n".join(format_ipchun_lines(after, "己", _FAV))
    crossing = detect_ipchun_boundary(_day("2027-02-01", "2027-02-10"))
    assert crossing is not None and crossing.side == "both"


def test_no_boundary_outside_short_february_windows() -> None:
    assert detect_ipchun_boundary(None) is None
    assert detect_ipchun_boundary(_month("2027-03")) is None
    assert detect_ipchun_boundary(_month("2027-01")) is None  # 양력 1월은 전부 입춘 전
    assert detect_ipchun_boundary(_month("2026-11", "2027-10")) is None  # 12개월 흐름
    assert detect_ipchun_boundary(_day("2027-03-05")) is None
    year = TimeRange(type="absolute", granularity=Granularity.YEAR, start="2027", end="2027")
    assert detect_ipchun_boundary(year) is None
    assert format_ipchun_lines(None, "己", _FAV) == []


def test_avoidance_year_uses_the_sewoon_year() -> None:
    def _year(tr: TimeRange | None, today: date = _TODAY) -> int:
        intent = IntentJson(
            intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS, time_range=tr
        )
        return _avoidance_year(intent, today)

    assert _year(_day("2027-01-20")) == 2026  # 입춘 전
    assert _year(_month("2027-01")) == 2026  # 丑월은 전년 세운
    assert _year(_month("2027-02")) == 2027
    assert _year(_day("2027-02-12")) == 2027
    assert _year(None) == 2026
    assert _year(None, date(2027, 1, 15)) == 2026  # 오늘이 입춘 전이면 오늘의 세운 연도


def test_relocation_question_on_february_gets_both_years_of_folk_taboo() -> None:
    q = "2월 12일 정도 이사를 해야해. 방향은 어때?"
    lines = _folk_taboo_lines(_relocation_intent(q), q, _TODAY)
    text = "\n".join(lines)
    assert "[민속 흉방 입춘 경계]" in text
    assert "[민속 흉방 — 2026 丙午년" in text and "[민속 흉방 — 2027 丁未년" in text
    assert text.index("2026 丙午년") < text.index("2027 丁未년")
    # 손방은 말한 날(2/12, 입춘 뒤) 쪽 블록에만, 고지 줄은 한 번만
    assert text.count("- 손방(그날)") == 1 and text.count("- 원거리 고지:") == 1
    assert text.index("- 손방(그날)") > text.index("2027 丁未년")


def test_relocation_question_on_other_month_keeps_single_block_without_todays_son() -> None:
    q = "3월에 이사해도 될까?"
    text = "\n".join(_folk_taboo_lines(_relocation_intent(q), q, _TODAY))
    assert "[민속 흉방 입춘 경계]" not in text and "[민속 흉방 — 2027 丁未년" in text
    assert "- 손방(그날)" not in text  # 달 단위 질문에 오늘 손방을 싣지 않는다
    # 시점 없는 이사 질문은 종전대로 오늘 손방
    q2 = "이사 방향은 어때?"
    assert "- 손방(그날)" in "\n".join(_folk_taboo_lines(_relocation_intent(q2), q2, _TODAY))


def test_folk_note_for_day_before_ipchun_uses_previous_year() -> None:
    assert "丙午년 삼살방 북" in folk_note_for_day(date(2027, 1, 20))
    after = folk_note_for_day(date(2027, 2, 12))
    assert "丁未년" in after and "삼살방 서" in after
