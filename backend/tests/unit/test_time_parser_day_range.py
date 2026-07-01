"""상대 일수 범위 파싱 — '이후/앞으로 N일', 'N일 내에' → 오늘부터 N일 롤링 창(C8b).

실로그 결함: '이후 10일 내에 로또 좋은 날'이 시점 미파싱으로 직전 턴의 하루(내일)를 과승계해
택일이 하루만 잡히던 오류 수정. 'N월 N일' 날짜(C5b)와 혼동하지 않아야 한다.
"""

from __future__ import annotations

from datetime import date

from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity

_TODAY = date(2026, 7, 1)


def _tr(q: str):
    return parse_time(q, _TODAY)[0]


def test_next_n_days_range() -> None:
    for q in (
        "이후 10일 내에 로또사기 좋은 날을 추천해줘",
        "앞으로 10일 안에 좋은 날",
        "10일 내에 로또 좋은 날",
        "이후 10일 이내에 좋은 날",
        "앞으로 열흘 안에",
    ):
        tr = _tr(q)
        assert tr is not None, q
        assert tr.granularity is Granularity.DAY
        assert tr.start == "2026-07-01" and tr.end == "2026-07-11", q


def test_seven_day_range() -> None:
    tr = _tr("향후 7일 좋은 날")
    assert tr is not None and tr.start == "2026-07-01" and tr.end == "2026-07-08"


# 'N월 N일' 날짜는 범위가 아니라 그 날짜(C5b) — 오인 금지.
def test_month_day_not_confused_as_range() -> None:
    tr = _tr("7월 10일에 이사")
    assert tr is not None and tr.start == "2026-07-10" and tr.end == "2026-07-10"


# 범위 표지/미래 접두 없는 맨 'N일'은 일-범위로 잡지 않는다(오탐 방지).
def test_bare_day_not_matched() -> None:
    assert _tr("10일 운세") is None
