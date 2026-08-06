"""오늘의 운세 사전생성·export 시각 회귀 (2026-08-02, 2026-08-05 개정).

    21:00 (D-1)  D 보드 생성 — 게시 기준일이 이미 D 라 스레드 파일도 여기서 교체된다
    00:05 (D)    멱등 재확인 — 21시 쓰기가 실패했고 재기동도 없었던 경우의 안전망

2026-08-02 시점에는 생성이 23:50 이었고 export 가드가 '오늘 보드'만 통과시켜, 생성
직후 부르면 언제나 하루 이르러 건너뛰어졌다(8/2 보드가 캐시에 있는데 파일은 8/1 자).
그래서 export 를 자정 뒤로 미뤘다.

2026-08-05 에 게시 기준일을 21시 경계로 옮기면서 그 제약이 사라졌다. 가드를 완화해서가
아니라 **기준일 정의를 옮겨서**다 — 어느 순간에도 통과하는 날짜는 여전히 하나뿐이고,
미래 보드가 게시분 파일을 덮는 사고(2026-08-01)는 그대로 막힌다.

사용자 API 노출 기준일은 옮기지 않았다(자정 유지).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from saju_api.main import daily_fortune_pregen_schedule
from saju_api.services.daily_fortune_export import THREADS_PUBLISH_HOUR

_KST = ZoneInfo("Asia/Seoul")


def _at(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=_KST)


@pytest.mark.parametrize(
    "now",
    [_at(2026, 8, 1, 9, 0), _at(2026, 8, 1, 20, 59), _at(2026, 8, 2, 0, 30)],
)
def test_recheck_export_is_on_the_target_day(now: datetime) -> None:
    """재확인 export 시각은 대상 날짜의 00:05 다 — 생성보다 뒤이고 자정을 넘긴다."""
    run_at, target, export_at = daily_fortune_pregen_schedule(now)
    assert export_at > run_at
    assert export_at.date() == target
    assert (export_at.hour, export_at.minute) == (0, 5)
    assert run_at.date() == target - timedelta(days=1)   # 생성은 전날


def test_generation_is_at_the_publish_hour_of_the_previous_day() -> None:
    """생성 = 전날 21:00. 이 시각부터 스레드 게시 기준일이 대상 날짜로 넘어간다."""
    run_at, target, _export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 9, 0))
    assert (run_at.hour, run_at.minute) == (21, 0)
    assert run_at.date() == date(2026, 8, 1)
    assert target == date(2026, 8, 2)


def test_generation_hour_follows_the_publish_hour_constant() -> None:
    """시각이 두 곳에 따로 박히면 조용히 어긋난다 — 상수 하나를 공유해야 한다."""
    run_at, _target, _export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 9, 0))
    assert run_at.hour == THREADS_PUBLISH_HOUR


def test_target_is_writable_at_generation_time() -> None:
    """생성 시점에 이미 대상 보드가 export 가드를 통과해야 한다(이번 개정의 핵심).

    통과하지 않으면 파일 교체가 다시 자정 뒤로 밀려 '전일 21시 게시'가 성립하지 않는다.
    """
    from saju_api.services.daily_fortune_export import threads_publish_date

    run_at, target, _export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 9, 0))
    assert threads_publish_date(run_at) == target


def test_recheck_export_still_targets_the_same_board() -> None:
    """00:05 재확인도 같은 보드로 통과해야 한다 — 멱등이지 다른 날짜가 아니다."""
    from saju_api.services.daily_fortune_export import threads_publish_date

    _run_at, target, export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 9, 0))
    assert threads_publish_date(export_at) == target


def test_after_the_generation_hour_the_schedule_rolls_forward() -> None:
    """21:00 을 지난 시각에 루프가 돌면 다음 날 주기를 잡는다 — 같은 날을 두 번 만들지 않는다."""
    run_at, target, export_at = daily_fortune_pregen_schedule(_at(2026, 8, 1, 23, 55))
    assert run_at == _at(2026, 8, 2, 21, 0)
    assert target == date(2026, 8, 3)
    assert export_at == _at(2026, 8, 3, 0, 5)


def test_schedule_is_pure_and_deterministic() -> None:
    now = _at(2026, 8, 1, 9, 0)
    assert daily_fortune_pregen_schedule(now) == daily_fortune_pregen_schedule(now)
