"""월 생략 단일 날짜 파싱 — "28일 오전에 시험", "이번 달 28일" → 그 날짜 일운(C5c).

실로그 결함(2026-08-14): '28일 오전에 필기 시험이 있는데 잘 볼 수 있을까?'가 TIMELESS로
떨어져 시험 도메인 기본 전망 창(내년 상반기)으로 답하던 오류 수정. 날짜 지칭 문맥(조사
에/날/은/이/부터, 오전/오후/아침/저녁)이 뒤따를 때만 잡고, 기간·빈도 용법은 제외한다.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity, TimeScope

_TODAY = date(2026, 8, 14)


def _parse(q: str):
    return parse_time(q, _TODAY)


def test_bare_day_with_time_of_day() -> None:
    """실로그 원 사례 — '28일 오전' 뒤 조사 없이도 시간대 어휘가 날짜 문맥."""
    tr, scope = _parse("28일 오전에 필기 시험이 있는데 공부를 안했어 잘 볼 수 있을까?")
    assert tr is not None
    assert tr.granularity is Granularity.DAY
    assert tr.start == "2026-08-28" and tr.end == "2026-08-28"
    assert scope is TimeScope.SHORT_TERM


def test_this_month_prefix_keeps_day_granularity() -> None:
    """'이번 달 28일'이 월 단위로 뭉개지지 않고 일 단위를 유지한다."""
    tr, _ = _parse("이번 달 28일에 시험 봐")
    assert tr is not None
    assert tr.granularity is Granularity.DAY
    assert tr.start == "2026-08-28"


def test_next_month_prefix() -> None:
    tr, _ = _parse("다음 달 3일부터 출근해")
    assert tr is not None and tr.start == "2026-09-03"


def test_passed_day_rolls_to_next_month() -> None:
    """연도·월 미지정에 이미 지난 날짜면 다음 달로 이월(미래 의도)."""
    tr, _ = _parse("2일에 시험이 있어")
    assert tr is not None and tr.start == "2026-09-02"


def test_past_tense_keeps_current_month() -> None:
    """과거시제 표지('계약했는데')면 이월하지 않고 이번 달 과거 날짜 그대로."""
    tr, _ = _parse("2일에 계약했는데 괜찮았을까")
    assert tr is not None and tr.start == "2026-08-02"


def test_invalid_day_skips_short_month() -> None:
    """짧은 달에 없는 날(9월 31일)은 건너뛰고 다음 유효한 달을 잡는다."""
    tr, _ = _parse("31일에 이사해")  # 8/31 유효(오늘 이후) → 그대로
    assert tr is not None and tr.start == "2026-08-31"
    tr2, _ = parse_time("31일에 이사해", date(2026, 9, 1))  # 9/31 없음 → 10/31
    assert tr2 is not None and tr2.start == "2026-10-31"


def test_duration_and_frequency_not_matched() -> None:
    """기간·빈도 용법은 날짜가 아니다 — 오탐 방지."""
    for q in ("3일 동안 여행 가", "3일에 한 번 운동해", "수능이 100일 남았어", "10일 운세"):
        tr, scope = _parse(q)
        assert scope is TimeScope.TIMELESS, q


def test_neighboring_rules_not_regressed() -> None:
    """C8b(N일 내에)·C5b(N월 N일)·C5(월 단위)는 기존 동작 유지."""
    tr, _ = _parse("10일 내에 로또 좋은 날")
    assert tr is not None and tr.start == "2026-08-14" and tr.end == "2026-08-24"
    tr, _ = _parse("8월 28일 시험")
    assert tr is not None and tr.start == "2026-08-28"
    tr, _ = _parse("5월은 어때?")
    assert tr is not None and tr.granularity is Granularity.MONTH and tr.start == "2026-05"
