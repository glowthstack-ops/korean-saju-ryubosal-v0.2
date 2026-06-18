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


def test_future_offset_after_n_anchors_start() -> None:
    """'1년 이후부터' → 현재월+N을 미래 시작 앵커로(open_when 과거 오분류 차단, 2026-06-18)."""
    tr = _tr("다음 이사는 1년 이후부터 확인해줘")
    assert tr.type == "relative" and tr.start == "2027-06-01"
    assert tr.granularity.value == "month"
    # 개월 단위 + '후'/'뒤'도 동일하게 미래 앵커.
    assert _tr("6개월 후 이사운").start == "2026-12-01"
    assert _tr("2년 뒤 이사 어때").start == "2028-06-01"
    # '안에/이내'(현재~N 구간)는 기존 의미 유지 — 미래 앵커로 바뀌지 않는다.
    assert _tr("1년 안에 이사").start == _T.isoformat()


def test_multi_month_comparison_spans_both() -> None:
    """'8월과 10월 중 언제가 나아?' → 두 달을 모두 잡아 min~max 구간으로 스팬(2026-06-16)."""
    tr = _tr("이직, 이사와 관련해서 8월과 10월 중 언제가 나아?")
    assert tr.start == "2026-08" and tr.end == "2026-10"
    # 단일 월은 그대로 단일 구간(회귀 없음).
    single = _tr("8월은 이직운 어때?")
    assert single.start == single.end == "2026-08"


def test_remaining_months_of_year_spans_to_december() -> None:
    """'올해 남은 달들' → 당월(2026-06)~연말(2026-12) 스팬.

    '이번달' 단수 규칙이 먼저 잡아 6월만 답하던 결함 수정(2026-06-16 사용자 지적).
    """
    tr = _tr("이번달을 포함해서 올해 남은 달들의 운세를 알려줘")
    assert tr.start == "2026-06" and tr.end == "2026-12"
    assert tr.granularity.value == "month"
    # '연말까지'·'남은 개월' 같은 변형도 동일 스팬.
    assert _tr("연말까지 운세 흐름 알려줘").end == "2026-12"
    assert _tr("올해 남은 개월 직장운").start == "2026-06"
    # '내년'이 붙으면 연 규칙에 양보(남은 달 규칙이 가로채지 않음).
    assert _tr("내년 남은 달은 어때?").start == "2027"
