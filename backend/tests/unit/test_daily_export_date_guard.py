"""스레드 업로드용 txt 의 날짜 가드 회귀 (2026-08-01 사고).

`오늘의운세.txt` 는 날짜가 바뀌어도 **같은 경로를 덮어쓴다**. 그런데 이 파일을 쓰는
`write_threads_export` 는 보드 생성·교정 경로에 붙어 있고, `get_board`·`polish_board` 는
임의 날짜로 호출된다(사전생성·관리자 수동 실행·과거 재생).

실제 사고: 2026-08-01(토) 00:02 에 8/2 보드가 이 파일을 덮어 토요일에 일요일 운세가
올라갔다. 원인이 두 겹이었다.

    ① pregen 이 목표 날짜를 sleep **이후** 에 재평가해 자정을 넘기면 +2일이 된다
    ② export 가 날짜를 확인하지 않아 어떤 날짜 보드든 '오늘' 파일을 덮는다

②가 없었다면 ①은 캐시에 미래 보드가 하나 더 생기는 정도로 끝났다. ②가 그것을
사용자에게 보이는 파일로 만들었다.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from saju_api.services.daily_fortune_export import write_threads_export
from saju_shared_types.daily_fortune import DailyFortuneBoard

_TODAY = dt.date(2026, 8, 1)


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
    """오늘 보드는 정상적으로 기록된다 — 가드가 전부를 막으면 안 된다."""
    out = tmp_path / "오늘의운세.txt"
    assert write_threads_export(today_board, out, today=_TODAY) is True
    assert out.is_file()
    assert _TODAY.isoformat() in out.read_text(encoding="utf-8")


def test_future_board_does_not_overwrite(
    tomorrow_board: DailyFortuneBoard, today_board: DailyFortuneBoard, tmp_path: Path
) -> None:
    """미래 보드는 오늘 파일을 덮지 않는다 — 이번 사고의 직접 재현."""
    out = tmp_path / "오늘의운세.txt"
    write_threads_export(today_board, out, today=_TODAY)
    before = out.read_text(encoding="utf-8")

    assert write_threads_export(tomorrow_board, out, today=_TODAY) is False
    assert out.read_text(encoding="utf-8") == before
    assert "2026-08-02" not in out.read_text(encoding="utf-8")


def test_past_board_does_not_overwrite(today_board: DailyFortuneBoard, tmp_path: Path) -> None:
    """과거 재생도 마찬가지다 — 방향이 아니라 '오늘인가'가 기준이다."""
    out = tmp_path / "오늘의운세.txt"
    write_threads_export(today_board, out, today=_TODAY)
    before = out.read_text(encoding="utf-8")
    past = _board(_TODAY - dt.timedelta(days=1))
    assert write_threads_export(past, out, today=_TODAY) is False
    assert out.read_text(encoding="utf-8") == before


def test_no_file_created_when_date_mismatches(
    tomorrow_board: DailyFortuneBoard, tmp_path: Path
) -> None:
    """파일이 아직 없을 때도 미래 보드로 새로 만들지 않는다."""
    out = tmp_path / "오늘의운세.txt"
    assert write_threads_export(tomorrow_board, out, today=_TODAY) is False
    assert not out.exists()


def test_pregen_target_is_pinned_before_sleep() -> None:
    """사전생성 목표 날짜를 sleep 뒤에 다시 계산하면 자정을 넘길 때 하루를 건너뛴다.

    루프 본문을 직접 돌리려면 24시간을 기다려야 하므로 소스 구조로 고정한다 —
    잡아야 할 것은 '언제 날짜를 정하는가' 라는 순서다.
    """
    src = (
        Path(__file__).resolve().parents[2] / "apps" / "api" / "saju_api" / "main.py"
    ).read_text(encoding="utf-8")
    body = src.split("async def _daily_fortune_pregen_loop")[1].split("\nasync def ")[0]
    sleep_at = body.index("await asyncio.sleep(")
    assert "target = " in body[:sleep_at], "목표 날짜가 sleep 이전에 고정돼야 한다"
    assert "datetime.now(_KST) + timedelta(days=1)" not in body[sleep_at:], (
        "sleep 이후 now 를 다시 읽어 +1 하면 자정을 넘길 때 하루를 건너뛴다"
    )
