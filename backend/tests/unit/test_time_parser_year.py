"""축약 연도·미래 롤링 기간 파싱 (2026-06-14 — '이사 시기 질문이 2026만 답' 결함 수정).

NN년 → 20NN(미래 편향), 내후년 → +2년, 향후/앞으로 N년(간) → 현재월부터 N×12개월.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import parse_time

_T = date(2026, 6, 14)


def _tr(q: str):
    return parse_time(q, _T)[0]


def test_short_year_to_2000s() -> None:
    """'27년/28년의 이사운' → 2027/2028(4자리 연도만 인식하던 결함)."""
    for q, y in [("27년의 이사운을 월별로 알려줘", "2027"),
                 ("28년 이사운 알려줘", "2028"),
                 ("29년은 어때", "2029")]:
        tr = _tr(q)
        assert tr.start == tr.end == y, q


def test_naehunyeon() -> None:
    """'내후년' → +2년."""
    tr = _tr("내후년 이사운 어때?")
    assert tr.start == tr.end == "2028"


def test_future_rolling_n_years() -> None:
    """'앞으로 5년간' → 현재월(2026-06)부터 60개월(2031-05)."""
    tr = _tr("앞으로 5년간의 이사운을 월별로 알려줘")
    assert tr.start == "2026-06" and tr.end == "2031-05"
    assert tr.granularity.value == "month"
    tr2 = _tr("향후 3년 직장운")
    assert tr2.start == "2026-06" and tr2.end == "2029-05"


def test_no_regression_full_year_and_relative() -> None:
    """4자리 연도·올해·내년은 기존대로."""
    assert _tr("2028년 이사운").start == "2028"
    assert _tr("올해 이사운").start == "2026"
    assert _tr("내년 이사운").start == "2027"


def test_duration_not_misparsed_as_year() -> None:
    """'10년 후' 같은 기간 어미는 축약 연도로 잡지 않는다(2010 오인 방지)."""
    tr = _tr("10년 후 이사운")
    assert tr is None or tr.start != "2010"
