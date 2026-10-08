"""오늘의 운세 교정 × LLM 서비스 중단 — RAW 유지·재개 대상 선별 (2026-10-06)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_api.services import llm_client, llm_service_state
from saju_engines.daily_fortune_cache import InMemoryDailyFortuneCache
from saju_engines.daily_fortune_v2 import active_content_version
from saju_engines.daily_ilju_fortune import build_day_context, compute_board, load_daily_dicts

_KST = ZoneInfo("Asia/Seoul")
_D = date(2026, 7, 23)
_PREV = _D - timedelta(days=1)


@pytest.fixture(scope="module")
def dicts():
    return load_daily_dicts()


def _board(d: date, dicts):
    return compute_board(build_day_context(d), dicts)


def _echo_response(board) -> str:
    return "\n".join(
        json.dumps({
            "ilju": f.ilju, "headline": f.headline,
            "place_phrase": f.lucky_place.phrase, "lotto": f.lotto_phrase,
        }, ensure_ascii=False)
        for f in board.fortunes
    )


@pytest.fixture(autouse=True)
def _memory_state():
    llm_service_state.use_memory_backend()
    yield
    llm_service_state.use_memory_backend()


def test_suspended_leaves_board_raw_not_failed(dicts, monkeypatch) -> None:
    """중단 예외 → FAILED 로 바꾸지 않고 RAW 유지(재개 시 다시 교정 가능), 저장 없음."""
    cache = InMemoryDailyFortuneCache()
    board = _board(_D, dicts)
    cache.save_board(_D, active_content_version(_D), board, 3600)

    def _suspended(*_a, **_k):
        raise llm_client.LLMServiceSuspended("suspended")

    monkeypatch.setattr(polish.llm_client, "generate_reading", _suspended)
    out = polish.polish_board(cache, _D)
    assert out == {"accepted": 0, "suspended": True}
    assert cache.load_board(_D, active_content_version(_D)).polish_status == "RAW"


def test_generate_and_polish_skips_llm_while_suspended(monkeypatch) -> None:
    """중단 중 선생성 경로 — 보드 생성(엔진)은 하되 교정(LLM)은 부르지 않고, 재개 뒤엔 부른다."""
    cache = InMemoryDailyFortuneCache()
    monkeypatch.setattr(polish.llm_client, "is_available", lambda: True)
    built: list[date] = []
    polished: list[date] = []
    monkeypatch.setattr(polish, "get_board", lambda c, d: built.append(d))
    monkeypatch.setattr(polish, "polish_board", lambda c, d: polished.append(d))
    llm_service_state.suspend("quota_exhausted")
    polish.generate_and_polish(cache, _D)
    assert built == [_D] and polished == []
    llm_service_state.resume("admin", probe=None, still_blocked={}, cooldown_seconds=1)
    polish.generate_and_polish(cache, _D)
    assert polished == [_D]


def test_resume_polishes_only_publish_date_board(dicts, monkeypatch) -> None:
    """재개 — 게시 기준일 보드만 교정, 지난 날짜 RAW 보드는 손대지 않는다."""
    cache = InMemoryDailyFortuneCache()
    today_board = _board(_D, dicts)
    prev_board = _board(_PREV, dicts)
    cache.save_board(_D, active_content_version(_D), today_board, 3600)
    cache.save_board(_PREV, active_content_version(_PREV), prev_board, 3600)
    polished_dates: list[str] = []

    def _gen(payload, **kw):
        polished_dates.append(kw.get("ref_id"))
        return _echo_response(today_board)

    monkeypatch.setattr(polish.llm_client, "generate_reading", _gen)
    now = datetime(_D.year, _D.month, _D.day, 10, 0, tzinfo=_KST)  # 21시 전 → 기준일 = _D
    out = polish.resume_polish_after_suspension(cache, now=now)
    assert out["action"] == "polished" and out["date"] == _D.isoformat()
    assert polished_dates == [_D.isoformat()]
    assert cache.load_board(_D, active_content_version(_D)).polish_status == "POLISHED"
    assert cache.load_board(_PREV, active_content_version(_PREV)).polish_status == "RAW"


def test_resume_skips_when_no_board_or_already_polished(dicts, monkeypatch) -> None:
    cache = InMemoryDailyFortuneCache()
    now = datetime(_D.year, _D.month, _D.day, 10, 0, tzinfo=_KST)
    assert polish.resume_polish_after_suspension(cache, now=now)["action"] == "skipped_no_board"
    board = _board(_D, dicts).model_copy(deep=True)
    board.polish_status = "POLISHED"
    cache.save_board(_D, active_content_version(_D), board, 3600)
    called: list[int] = []
    monkeypatch.setattr(polish.llm_client, "generate_reading", lambda *a, **k: called.append(1))
    out = polish.resume_polish_after_suspension(cache, now=now)
    assert out["action"] == "skipped_status" and out["status"] == "POLISHED" and not called
