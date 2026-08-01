"""오늘의 운세 사전생성·export 시각 회귀 (2026-08-02).

두 시각이 **자정을 사이에 두고** 갈라져 있어야 한다.

    23:50 (D-1)  D 보드 생성 — write_threads_export 는 여기서 건너뛴다(오늘 보드가 아니다)
    00:05 (D)    이제 D 가 오늘이라 파일이 갱신된다

생성 시점에만 export 를 부르면 사전생성 모델에서는 날짜가 언제나 하루 어긋나 파일이 기동
시점 날짜에 멈춘다. 실제로 8/2 보드가 캐시에 있는데 파일은 8/1 자였다.

가드를 완화해 고치지 않는다 — 미래 보드가 오늘 파일을 덮는 사고(2026-08-01)를 막는 것이
그 가드의 목적이고, 바로잡을 것은 호출 **시점**이다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from saju_api.main import daily_fortune_pregen_schedule

_KST = ZoneInfo("Asia/Seoul")


def _at(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_KST)


@pytest.mark.parametrize(
    "now",
    [_at(2026, 8, 1, 9, 0), _at(2026, 8, 1, 23, 49), _at(2026, 8, 2, 0, 30)],
)
def test_export_happens_after_midnight_of_the_target_day(now: datetime) -> None:
    """export 시각은 대상 날짜의 00:05 다 — 생성 시각보다 뒤이고 자정을 넘긴다."""
    run_at, target, export_at = daily_fortune_pregen_schedule(now)
    assert export_at > run_at
    assert export_at.date() == target
    assert (export_at.hour, export_at.minute) == (0, 5)
    assert run_at.date() == target - timedelta(days=1)   # 생성은 전날


def test_generation_precedes_the_target_day() -> None:
    run_at, target, _export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 9, 0))
    assert (run_at.hour, run_at.minute) == (23, 50)
    assert run_at.date() == date(2026, 8, 1)
    assert target == date(2026, 8, 2)


def test_export_target_is_today_at_export_time() -> None:
    """가드(`board.fortune_date == 오늘`)를 통과하는 유일한 조건이다."""
    _run_at, target, export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 9, 0))
    assert export_at.date() == target


def test_after_the_generation_hour_the_schedule_rolls_forward() -> None:
    """23:50 을 지난 시각에 루프가 돌면 다음 날 주기를 잡는다 — 같은 날을 두 번 만들지 않는다."""
    run_at, target, export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 23, 55))
    assert run_at == _at(2026, 8, 2, 23, 50)
    assert target == date(2026, 8, 3)
    assert export_at == _at(2026, 8, 3, 0, 5)


def test_schedule_is_pure_and_deterministic() -> None:
    now = _at(2026, 8, 1, 9, 0)
    assert daily_fortune_pregen_schedule(now) == daily_fortune_pregen_schedule(now)
