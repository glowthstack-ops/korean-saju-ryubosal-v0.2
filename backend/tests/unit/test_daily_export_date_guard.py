"""스레드 업로드용 txt 의 날짜 가드 회귀 (2026-08-01 사고, 2026-08-05 경계 개정).

`오늘의운세.txt` 는 날짜가 바뀌어도 **같은 경로를 덮어쓴다**. 그런데 이 파일을 쓰는
`write_threads_export` 는 보드 생성·교정 경로에 붙어 있고, `get_board`·`polish_board` 는
임의 날짜로 호출된다(사전생성·관리자 수동 실행·과거 재생).

실제 사고: 2026-08-01(토) 00:02 에 8/2 보드가 이 파일을 덮어 토요일에 일요일 운세가
올라갔다. 원인이 두 겹이었다.

    ① pregen 이 목표 날짜를 sleep **이후** 에 재평가해 자정을 넘기면 +2일이 된다
    ② export 가 날짜를 확인하지 않아 어떤 날짜 보드든 '오늘' 파일을 덮는다

②가 없었다면 ①은 캐시에 미래 보드가 하나 더 생기는 정도로 끝났다. ②가 그것을
사용자에게 보이는 파일로 만들었다.

2026-08-05 개정: 기준일이 '오늘'에서 **게시 기준일**(21시부터 익일)로 바뀌었다. 가드를
넓힌 것이 아니라 경계를 옮긴 것이다 — 어느 순간에도 통과하는 날짜는 여전히 정확히
하나이며, 아래 `_allowed_date_is_unique_at_every_hour` 가 그것을 고정한다.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from saju_api.services.daily_fortune_export import (
    THREADS_PUBLISH_HOUR,
    threads_publish_date,
    write_threads_export,
)
from saju_shared_types.daily_fortune import DailyFortuneBoard

_TODAY = dt.date(2026, 8, 1)
_KST = ZoneInfo("Asia/Seoul")


def _board(d: dt.date) -> DailyFortuneBoard:
    from saju_api.services import daily_fortune_service as S
    from saju_engines.daily_ilju_fortune import build_day_context, compute_board

    return compute_board(build_day_context(d), S.load_daily_dicts_for(d))


@pytest.fixture(scope="module")
def today_board() -> DailyFortuneBoard:
    return _board(_TODAY)


@pytest.fixture(scope="module")
def tomorrow_board() -> DailyFortuneBoard:
    return _board(_TODAY + dt.timedelta(days=1))


def test_today_board_is_written(today_board: DailyFortuneBoard, tmp_path: Path) -> None:
    """기준일 보드는 정상적으로 기록된다 — 가드가 전부를 막으면 안 된다."""
    out = tmp_path / "오늘의운세.txt"
    assert write_threads_export(today_board, out, publish_date=_TODAY) is True
    assert out.is_file()
    assert _TODAY.isoformat() in out.read_text(encoding="utf-8")


def test_future_board_does_not_overwrite(
    tomorrow_board: DailyFortuneBoard, today_board: DailyFortuneBoard, tmp_path: Path
) -> None:
    """미래 보드는 기준일 파일을 덮지 않는다 — 이번 사고의 직접 재현."""
    out = tmp_path / "오늘의운세.txt"
    write_threads_export(today_board, out, publish_date=_TODAY)
    before = out.read_text(encoding="utf-8")

    assert write_threads_export(tomorrow_board, out, publish_date=_TODAY) is False
    assert out.read_text(encoding="utf-8") == before
    assert "2026-08-02" not in out.read_text(encoding="utf-8")


def test_past_board_does_not_overwrite(today_board: DailyFortuneBoard, tmp_path: Path) -> None:
    """과거 재생도 마찬가지다 — 방향이 아니라 '게시 기준일인가'가 기준이다."""
    out = tmp_path / "오늘의운세.txt"
    write_threads_export(today_board, out, publish_date=_TODAY)
    before = out.read_text(encoding="utf-8")
    past = _board(_TODAY - dt.timedelta(days=1))
    assert write_threads_export(past, out, publish_date=_TODAY) is False
    assert out.read_text(encoding="utf-8") == before


def test_no_file_created_when_date_mismatches(
    tomorrow_board: DailyFortuneBoard, tmp_path: Path
) -> None:
    """파일이 아직 없을 때도 기준일이 아닌 보드로 새로 만들지 않는다."""
    out = tmp_path / "오늘의운세.txt"
    assert write_threads_export(tomorrow_board, out, publish_date=_TODAY) is False
    assert not out.exists()


# ── 게시 기준일 경계 (2026-08-05) ───────────────────────────────────────────────
# 전일 21시에 익일자 스레드 파일을 올린다는 요구를, 가드를 여는 대신 경계 이동으로 구현했다.


def _at(hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime(2026, 8, 1, hh, mm, tzinfo=_KST)


@pytest.mark.parametrize("hour", [0, 9, 20])
def test_before_the_publish_hour_the_reference_is_today(hour: int) -> None:
    assert threads_publish_date(_at(hour, 59)) == _TODAY


@pytest.mark.parametrize("hour", [21, 22, 23])
def test_from_the_publish_hour_the_reference_is_tomorrow(hour: int) -> None:
    """21시부터 파일은 **내일** 것을 담는다 — 이번 요구의 본체."""
    assert threads_publish_date(_at(hour)) == _TODAY + dt.timedelta(days=1)


def test_the_boundary_is_exact() -> None:
    """20:59:59 는 당일, 21:00:00 은 익일. 경계가 흐려지면 파일 내용이 뒤섞인다."""
    assert threads_publish_date(_at(THREADS_PUBLISH_HOUR - 1, 59)) == _TODAY
    assert (
        threads_publish_date(_at(THREADS_PUBLISH_HOUR))
        == _TODAY + dt.timedelta(days=1)
    )


def test_tomorrow_board_is_written_after_the_publish_hour(
    tomorrow_board: DailyFortuneBoard, tmp_path: Path
) -> None:
    """21시 이후에는 익일 보드가 통과한다 — 전일 저녁 게시가 성립하는 조건."""
    out = tmp_path / "오늘의운세.txt"
    ref = threads_publish_date(_at(21))
    assert write_threads_export(tomorrow_board, out, publish_date=ref) is True
    assert "2026-08-02" in out.read_text(encoding="utf-8")


def test_today_board_cannot_revert_the_file_after_the_publish_hour(
    tomorrow_board: DailyFortuneBoard, today_board: DailyFortuneBoard, tmp_path: Path
) -> None:
    """21시 이후 당일 보드 lazy 재생성이 파일을 어제자로 되돌리지 못한다.

    경계 이동의 대칭 조건이다. 이게 뚫리면 21~24시 사이 사용자 요청 하나로 게시분이
    당일자로 덮여, 저녁에 올릴 내용이 사라진다.
    """
    out = tmp_path / "오늘의운세.txt"
    ref = threads_publish_date(_at(21))
    write_threads_export(tomorrow_board, out, publish_date=ref)
    before = out.read_text(encoding="utf-8")

    assert write_threads_export(today_board, out, publish_date=ref) is False
    assert out.read_text(encoding="utf-8") == before


def test_allowed_date_is_unique_at_every_hour() -> None:
    """어느 시각에도 통과하는 날짜는 정확히 하나다 — 가드가 넓어지지 않았음을 고정한다."""
    candidates = [_TODAY + dt.timedelta(days=n) for n in (-1, 0, 1, 2)]
    for hour in range(24):
        ref = threads_publish_date(_at(hour, 30))
        assert sum(1 for c in candidates if c == ref) == 1
        assert ref in (_TODAY, _TODAY + dt.timedelta(days=1))


def test_pregen_target_is_pinned_before_sleep() -> None:
    """사전생성 목표 날짜를 sleep 뒤에 다시 계산하면 자정을 넘길 때 하루를 건너뛴다.

    루프 본문을 직접 돌리려면 24시간을 기다려야 하므로 소스 구조로 고정한다 —
    잡아야 할 것은 '언제 날짜를 정하는가' 라는 순서다.
    """
    src = (
        Path(__file__).resolve().parents[2] / "apps" / "api" / "saju_api" / "main.py"
    ).read_text(encoding="utf-8")
    body = src.split("async def _daily_fortune_pregen_loop")[1].split("\nasync def ")[0]
    # 대기 표현은 바뀌어 왔다(2026-08-02: 순수 함수 분리 / 2026-08-06: 벽시계 재확인
    # `sleep_until`). 어느 쪽이든 **루프의 첫 대기**가 기준점이다.
    sleep_markers = [
        i
        for pat in ("await asyncio.sleep(", "await sleep_until(")
        if (i := body.find(pat)) != -1
    ]
    assert sleep_markers, "루프에 대기가 없다 — 구조가 바뀌었으면 이 회귀를 갱신할 것"
    sleep_at = min(sleep_markers)
    # 고정할 것은 **순서** 다 — 대상 날짜가 sleep 이전에 정해져야 한다.
    before = body[:sleep_at]
    assert (
        "target = " in before
        or "target, export_at = daily_fortune_pregen_schedule" in before
    ), "목표 날짜가 sleep 이전에 고정돼야 한다"
    assert "datetime.now(_KST) + timedelta(days=1)" not in body[sleep_at:], (
        "sleep 이후 now 를 다시 읽어 +1 하면 자정을 넘길 때 하루를 건너뛴다"
    )
