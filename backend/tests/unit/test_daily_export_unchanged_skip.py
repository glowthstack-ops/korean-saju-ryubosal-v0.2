"""스레드 export 동일 내용 생략 회귀 (2026-08-09 데굴님 승인).

00:05 멱등 재확인이 21시 쓰기 성공 여부와 무관하게 매일 같은 내용을 다시 써
mtime 이 갱신됐고, 파일 기록만 보면 불필요한 재생성처럼 보였다(2026-08-09 조사).
수정: `write_threads_export` 가 쓰기 전에 기존 파일 내용과 비교해 동일하면 생략.
비교는 날짜 가드와 같은 이유로 함수 내부에 둔다(호출부가 늘어도 우회 불가).

검증은 mtime_ns·반환값으로 한다 — 앱 로거는 propagate=False 라 caplog 기반
로그 검사는 거짓 통과한다(caplog-propagate 함정).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from saju_api.services.daily_fortune_export import write_threads_export
from saju_shared_types.daily_fortune import DailyFortuneBoard

_TODAY = dt.date(2026, 8, 9)


@pytest.fixture(scope="module")
def board() -> DailyFortuneBoard:
    from saju_api.services import daily_fortune_service as S
    from saju_engines.daily_ilju_fortune import build_day_context, compute_board

    return compute_board(build_day_context(_TODAY), S.load_daily_dicts_for(_TODAY))


def test_identical_content_skips_rewrite(board: DailyFortuneBoard, tmp_path: Path) -> None:
    """같은 보드를 다시 내보내면 파일을 건드리지 않고 True(최신 보장)를 반환한다."""
    out = tmp_path / "오늘의운세.txt"
    assert write_threads_export(board, out, publish_date=_TODAY) is True
    first_mtime = out.stat().st_mtime_ns
    assert write_threads_export(board, out, publish_date=_TODAY) is True  # 00:05 재확인
    assert out.stat().st_mtime_ns == first_mtime  # 재기록 없음 — mtime 불변


def test_changed_content_still_rewrites(board: DailyFortuneBoard, tmp_path: Path) -> None:
    """내용이 다르면(21시 쓰기 실패 후 잔존 파일 등) 정상적으로 다시 쓴다 — 복구 기능 유지."""
    out = tmp_path / "오늘의운세.txt"
    out.write_text("어제 보드 잔존 내용", encoding="utf-8")
    assert write_threads_export(board, out, publish_date=_TODAY) is True
    assert "어제 보드 잔존 내용" not in out.read_text(encoding="utf-8")


def test_missing_file_is_written(board: DailyFortuneBoard, tmp_path: Path) -> None:
    """파일이 없으면(21시 쓰기 자체가 실패) 새로 쓴다 — 재확인의 원래 목적."""
    out = tmp_path / "오늘의운세.txt"
    assert write_threads_export(board, out, publish_date=_TODAY) is True
    assert out.exists() and out.stat().st_size > 0


def test_unreadable_existing_file_is_replaced(board: DailyFortuneBoard, tmp_path: Path) -> None:
    """기존 파일이 UTF-8 로 읽히지 않아도(손상) 비교를 포기하고 새로 쓴다."""
    out = tmp_path / "오늘의운세.txt"
    out.write_bytes(b"\xff\xfe\x00 corrupted")
    assert write_threads_export(board, out, publish_date=_TODAY) is True
    assert out.read_text(encoding="utf-8")  # 정상 UTF-8 로 교체됨
