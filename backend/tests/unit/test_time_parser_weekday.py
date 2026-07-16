"""요일 시점 파싱 — '다음주 월요일'은 주 전체가 아니라 단일 일운으로 해석(C3.5).

실로그 결함: '다음주 월요일 운세'가 주 범위(월~일)로 잡혀 월운으로 답한 시점 오류 수정.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity


def _tr(q: str, today: date = date(2026, 6, 14)):  # 2026-06-14 = 일요일
    return parse_time(q, today)[0]


def test_next_week_monday_is_single_day() -> None:
    tr = _tr("다음주 월요일 내 운세")
    assert tr.granularity is Granularity.DAY
    assert tr.start == "2026-06-15" and tr.end == "2026-06-15"  # 다음 주 월요일 = 단일일


def test_this_week_weekday() -> None:
    tr = _tr("이번주 금요일은 어때?")
    assert tr.granularity is Granularity.DAY
    assert tr.start == tr.end == "2026-06-12"  # 이번 주 금요일(명시 — 과거여도 존중)


def test_bare_weekday_picks_upcoming() -> None:
    # 오늘(일)이 지난 이번주 월요일(6/8)보다 뒤 → 다가오는 월요일 6/15.
    tr = _tr("월요일에 좋은 일 있을까")
    assert tr.start == tr.end == "2026-06-15"


def test_bare_next_week_still_full_range() -> None:
    # 요일 없는 '다음주'는 기존대로 주 전체(월~일).
    tr = _tr("다음주 어때?")
    assert tr.start == "2026-06-15" and tr.end == "2026-06-21"


def test_space_variant() -> None:
    assert _tr("다음 주 월요일").start == "2026-06-15"


# C4b 한 주(롤링 7일) — '다음 한주간/일주일/앞으로 한 주'가 '시점 미지정'으로 새던 결함 수정
# (2026-06-20 데굴님: 월운이 지난달 癸巳로 노출 — '다음 한주간'이 '다음 주' 규칙에 안 걸려서).
def test_rolling_one_week_phrases() -> None:
    base = date(2026, 6, 20)  # 토
    for q in ("다음 한주간 로또 사도 될 날", "일주일 안에 좋은 날", "앞으로 한 주 흐름"):
        tr = parse_time(q, base)[0]
        assert tr is not None, q
        assert tr.granularity is Granularity.DAY, q
        assert tr.start == "2026-06-20" and tr.end == "2026-06-26", q  # 오늘~+6일(6월=甲午)


def test_calendar_week_unchanged() -> None:
    base = date(2026, 6, 20)  # 토
    this_w = parse_time("이번 주 어때", base)[0]
    assert this_w is not None
    assert this_w.start == "2026-06-15" and this_w.end == "2026-06-21"  # 월~일 캘린더 주
    next_w = parse_time("다음 주 운세", base)[0]
    assert next_w is not None
    assert next_w.start == "2026-06-22" and next_w.end == "2026-06-28"


def test_past_one_week_not_future() -> None:
    # 과거형 '지난 한 주'는 미래 롤링으로 잡지 않는다(C4b 제외 — 회고 경로 양보).
    tr = parse_time("지난 한 주 어땠어", date(2026, 6, 20))[0]
    assert tr is None or tr.start != "2026-06-20"
