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

import asyncio
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


# ── 벽시계 보정 내성 (2026-08-06 사고) ──────────────────────────────────────
#
# 실제로 일어난 일: 08:56 기동 → 21:00 발화 예정 → 자는 동안 벽시계가 **50분 28초 뒤로**
# 밀려(monotonic 47,275초 vs 벽시계 44,247초) 태스크가 20:09 에 깨어났다. 그 시각엔 게시
# 기준일이 아직 당일이라 export 가드가 익일 보드를 막았고 21시 게시가 실패했다.
#
# 가드는 설계대로 동작했다 — 어긋난 것은 발화 시각이다. `asyncio.sleep` 은 monotonic
# 타이머인데 남은 시간을 벽시계로 한 번만 계산해 그대로 잤기 때문이다.


class _FakeClock:
    """벽시계와 대기를 분리한 가짜 시계 — 자는 동안의 시계 보정을 주입한다.

    **점프 조건은 경과 시간(monotonic)이지 sleep 횟수가 아니다.** 횟수로 걸면 한 번만
    자는 구현에서는 점프가 아예 발생하지 않아, 결함이 있는 코드도 통과한다(이 파일 초판이
    그랬다). 현실에서 시계 보정은 대기를 몇 조각으로 쪼갰는지와 무관하게 일어난다.
    """

    def __init__(
        self,
        start: datetime,
        *,
        jump_after: timedelta | None = None,
        jump: timedelta | None = None,
    ):
        self.now = start
        self.slept: list[float] = []
        self.elapsed = timedelta(0)      # monotonic 경과(보정의 영향을 받지 않는다)
        self._jump_after = jump_after
        self._jump = jump
        self._jumped = False

    def time(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.elapsed += timedelta(seconds=seconds)
        self.now += timedelta(seconds=seconds)           # 정상 경과
        if (
            not self._jumped
            and self._jump_after is not None
            and self._jump is not None
            and self.elapsed >= self._jump_after
        ):
            self.now += self._jump                       # 시계 보정(점프)
            self._jumped = True


async def _run_sleep_until(clock: _FakeClock, target: datetime, step: float = 60.0):
    from saju_api.main import sleep_until

    await sleep_until(target, step=step, now_fn=clock.time, sleep_fn=clock.sleep)


def test_sleep_until_lands_on_the_wall_clock_target() -> None:
    """정상 시계 — 벽시계가 목표에 닿을 때 반환한다."""
    start = _at(2026, 8, 6, 8, 56)
    clock = _FakeClock(start)
    asyncio.run(_run_sleep_until(clock, _at(2026, 8, 6, 21, 0)))
    assert clock.now >= _at(2026, 8, 6, 21, 0)
    assert clock.now - _at(2026, 8, 6, 21, 0) < timedelta(seconds=60)


def test_backward_clock_jump_does_not_fire_early() -> None:
    """이번 사고의 재현 — 자는 도중 벽시계가 50분 28초 뒤로 밀려도 21:00 전에 깨지 않는다."""
    clock = _FakeClock(
        _at(2026, 8, 6, 8, 56),
        jump_after=timedelta(hours=4),
        jump=timedelta(minutes=-50, seconds=-28),
    )
    asyncio.run(_run_sleep_until(clock, _at(2026, 8, 6, 21, 0)))
    assert clock.now >= _at(2026, 8, 6, 21, 0), "벽시계가 21시에 닿기 전에 깨어났다"


def test_the_fake_clock_actually_reproduces_the_defect() -> None:
    """검사 도구가 결함을 실제로 잡는지 먼저 확인한다.

    옛 구현(남은 시간을 벽시계로 한 번 계산해 그대로 자기)을 같은 시계에 돌려 **20:09 에
    깨어나는지** 본다. 여기서 실패하면 위 회귀는 무의미하다 — 이 파일 초판의 가짜 시계는
    점프를 sleep 횟수로 걸어서, 한 번만 자는 옛 구현에는 점프가 닿지 않았다.
    """
    target = _at(2026, 8, 6, 21, 0)
    clock = _FakeClock(
        _at(2026, 8, 6, 8, 56),
        jump_after=timedelta(hours=4),
        jump=timedelta(minutes=-50, seconds=-28),
    )

    async def _old_style() -> None:
        await clock.sleep((target - clock.time()).total_seconds())

    asyncio.run(_old_style())
    assert clock.now < target, "옛 구현이 조기 발화하지 않았다면 이 시계는 결함을 못 잡는다"
    assert clock.now == _at(2026, 8, 6, 20, 9) + timedelta(seconds=32)


def test_forward_clock_jump_returns_immediately() -> None:
    """앞으로 뛰어 목표를 지나쳤으면 지체 없이 반환한다(반대편 결함 방지)."""
    clock = _FakeClock(
        _at(2026, 8, 6, 20, 0), jump_after=timedelta(seconds=1), jump=timedelta(hours=2),
    )
    asyncio.run(_run_sleep_until(clock, _at(2026, 8, 6, 21, 0)))
    assert len(clock.slept) == 1, "점프 뒤에도 계속 잤다"


def test_already_past_target_does_not_sleep() -> None:
    """이미 지난 시각이면 한 번도 자지 않는다."""
    clock = _FakeClock(_at(2026, 8, 6, 22, 0))
    asyncio.run(_run_sleep_until(clock, _at(2026, 8, 6, 21, 0)))
    assert clock.slept == []


def test_no_single_sleep_exceeds_the_recheck_step() -> None:
    """한 조각이 step 을 넘으면 그만큼 보정을 놓친다 — 오차 상한이 곧 step 이다."""
    from saju_api.main import _CLOCK_RECHECK_STEP

    clock = _FakeClock(_at(2026, 8, 6, 8, 56))
    asyncio.run(_run_sleep_until(clock, _at(2026, 8, 6, 21, 0)))
    assert clock.slept
    assert max(clock.slept) <= _CLOCK_RECHECK_STEP
