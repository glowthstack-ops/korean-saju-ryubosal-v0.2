"""계절 시점어 파싱 C7b (2026-09-23 — '올 겨울 작업 수주가 잘될까?'가 too_broad로 바운스되던 결함).

절기 석 달 기준: 봄=寅卯辰(02~04)·여름=巳午未(05~07)·가을=申酉戌(08~10)·겨울=亥子丑(11~익년01).
연도는 오늘의 절기 달 기준으로 수식어(올/이번/내년/작년/지난/다음/무수식)에 따라 정한다.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import parse_time

_T = date(2026, 9, 23)


def _span(q: str, month_label: str = "2026-09") -> tuple[str, str] | None:
    tr, _ = parse_time(q, _T, current_month_label=month_label)
    return (tr.start, tr.end) if tr is not None else None


def test_this_winter_crosses_year() -> None:
    """9월의 '올 겨울' → 2026-11~2027-01(절기 亥子丑, 연도 경계를 넘는다)."""
    assert _span("올 겨울 작업 수주가 잘될까?") == ("2026-11", "2027-01")
    assert _span("이번 겨울 일감이 많을까?") == ("2026-11", "2027-01")
    assert _span("겨울에 이사해도 될까") == ("2026-11", "2027-01")


def test_this_spring_is_retrospective_when_passed() -> None:
    """'올 봄'은 지났어도 그 해 봄(회고). 무수식 '봄에'는 다가오는 다음 봄."""
    assert _span("올 봄 이직 될까?") == ("2026-02", "2026-04")
    assert _span("봄에 이사") == ("2027-02", "2027-04")
    assert _span("다음 봄에 결혼할 수 있을까") == ("2027-02", "2027-04")


def test_next_last_qualifiers() -> None:
    """내년=+1, 작년=−1, 지난=가장 최근에 끝난 계절."""
    assert _span("내년 여름 이사 어때?") == ("2027-05", "2027-07")
    assert _span("작년 가을에 무슨 일이 있었지") == ("2025-08", "2025-10")
    assert _span("지난 가을에 왜 그랬을까") == ("2025-08", "2025-10")
    assert _span("지난 봄") == ("2026-02", "2026-04")


def test_winter_in_january_belongs_to_previous_start_year() -> None:
    """1월(절기 丑월)의 '올 겨울'은 진행 중인 겨울(전년 11월 시작). '내년 겨울'은 그다음."""
    assert _span("올 겨울 운세", "2026-01") == ("2025-11", "2026-01")
    assert _span("내년 겨울", "2026-01") == ("2026-11", "2027-01")
    assert _span("다음 겨울", "2026-01") == ("2026-11", "2027-01")
    assert _span("지난 겨울", "2026-01") == ("2024-11", "2025-01")


def test_winter_in_november_is_current() -> None:
    """11월(진행 중)의 '올 겨울'=현재 겨울, '다음 겨울'=다음 해."""
    assert _span("올 겨울", "2026-11") == ("2026-11", "2027-01")
    assert _span("다음 겨울", "2026-11") == ("2027-11", "2028-01")


def test_specific_month_wins_over_season() -> None:
    """'겨울 12월에'처럼 특정 월이 함께 오면 더 좁은 월 규칙에 양보한다."""
    assert _span("겨울 12월에 이사해도 될까") == ("2026-12", "2026-12")


def test_bare_bom_verb_form_is_not_season() -> None:
    """'봄' 단독(동사 명사형)은 수식어·조사 없이는 계절로 보지 않는다."""
    assert _span("사주 봄") is None
