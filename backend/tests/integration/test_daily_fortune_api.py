"""일주별 오늘의 운세 — 서비스·API 통합 테스트 (InMemory 캐시 주입).

DB 불필요(휘발성 캐시 전용 기능). TestClient + dependency_overrides 로
Redis 없이 전체 경로를 검증한다.
"""

from __future__ import annotations

import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient

from saju_api.deps import get_daily_fortune_cache
from saju_api.main import app
from saju_api.services import daily_fortune_service
from saju_engines.daily_fortune_cache import InMemoryDailyFortuneCache
from saju_shared_types.daily_fortune import CONTENT_VERSION

_D = date(2026, 7, 23)


@pytest.fixture()
def cache():
    return InMemoryDailyFortuneCache()


@pytest.fixture()
def client(cache):
    app.dependency_overrides[get_daily_fortune_cache] = lambda: cache
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_daily_fortune_cache, None)


# ── 서비스 계층 ─────────────────────────────────────────────────────────


def test_lazy_generation_and_cache_hit(cache) -> None:
    assert cache.load_board(_D, CONTENT_VERSION) is None
    board = daily_fortune_service.get_board(cache, _D)
    assert len(board.fortunes) == 60
    # 2회차는 캐시 히트 — 동일 객체 내용
    again = daily_fortune_service.get_board(cache, _D)
    assert again.model_dump() == board.model_dump()
    assert cache.load_board(_D, CONTENT_VERSION) is not None


def test_concurrent_requests_generate_once(cache) -> None:
    """동시 요청 — 락 경합에도 결과는 동일 보드(결정론)."""
    results = []

    def _run() -> None:
        results.append(daily_fortune_service.get_board(cache, _D))

    threads = [threading.Thread(target=_run) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 6
    first = results[0].model_dump()
    assert all(r.model_dump() == first for r in results[1:])


def test_content_version_change_generates_new_board(cache) -> None:
    board = daily_fortune_service.get_board(cache, _D)
    assert cache.load_board(_D, "other.version") is None  # 버전별 독립 키
    assert cache.load_board(_D, CONTENT_VERSION) is not None
    assert board.content_version == CONTENT_VERSION


def test_single_lookup_normalization(cache) -> None:
    hanja = daily_fortune_service.get_single(cache, "甲子", _D)
    hangul = daily_fortune_service.get_single(cache, "갑자", _D)
    assert hanja is not None and hangul is not None
    assert hanja.fortune.ilju == hangul.fortune.ilju == "甲子"
    assert daily_fortune_service.get_single(cache, "없는일주", _D) is None


def test_ttl_positive(cache) -> None:
    assert daily_fortune_service.board_ttl_seconds(daily_fortune_service.kst_today()) > 0
    assert 1 <= daily_fortune_service.seconds_until_next_midnight() <= 86400


def test_lock_owner_token_semantics(cache) -> None:
    token = cache.acquire_lock("generate", _D, CONTENT_VERSION, 30)
    assert token is not None
    assert cache.acquire_lock("generate", _D, CONTENT_VERSION, 30) is None
    cache.release_lock("generate", _D, CONTENT_VERSION, "타인토큰")  # 무시되어야 함
    assert cache.acquire_lock("generate", _D, CONTENT_VERSION, 30) is None
    cache.release_lock("generate", _D, CONTENT_VERSION, token)
    assert cache.acquire_lock("generate", _D, CONTENT_VERSION, 30) is not None


# ── API 계층 ────────────────────────────────────────────────────────────


def test_today_endpoint_and_headers(client) -> None:
    res = client.get("/api/v2/daily-fortune/today")
    assert res.status_code == 200
    body = res.json()
    assert len(body["fortunes"]) == 60
    assert set(body["top5"].keys()) == {"money", "love", "news"}
    cc = res.headers["cache-control"]
    assert "must-revalidate" in cc and "public" in cc
    assert "stale-while-revalidate" not in cc
    etag = res.headers["etag"]
    # ETag 재검증 — 304
    res2 = client.get("/api/v2/daily-fortune/today", headers={"If-None-Match": etag})
    assert res2.status_code == 304


def test_today_single_endpoint(client) -> None:
    res = client.get("/api/v2/daily-fortune/today/갑자")
    assert res.status_code == 200
    assert res.json()["fortune"]["ilju"] == "甲子"
    bad = client.get("/api/v2/daily-fortune/today/모름")
    assert bad.status_code == 422


def test_no_cache_configured_returns_503(monkeypatch) -> None:
    monkeypatch.delenv("SAJU_V2_REDIS_URL", raising=False)
    monkeypatch.delenv("SAJU_DAILY_FORTUNE_MEMORY_CACHE", raising=False)
    with TestClient(app) as c:
        res = c.get("/api/v2/daily-fortune/today")
        assert res.status_code == 503
