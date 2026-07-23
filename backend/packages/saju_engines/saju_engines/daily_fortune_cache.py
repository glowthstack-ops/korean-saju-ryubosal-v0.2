"""일주별 오늘의 운세 — 휘발성 TTL 캐시 (Redis / 로컬 InMemory).

과거 운세 본문을 저장하지 않는다(docs/17 §0-2 휘발성 불변식). 보드는 하루치
전체(60건)를 하나의 값으로 저장하며, 값 교체(SET)의 원자성으로 부분 저장
문제를 원천 차단한다.

폴백 정책(검토 확정):
- 운영 = Redis 필수(`SAJU_V2_REDIS_URL`). 미설정·연결 실패 시 ValueError →
  API 계층에서 503. 자동 InMemory 폴백 금지(다중 워커 상이 보드 방지).
- 로컬 단일 워커 = `SAJU_DAILY_FORTUNE_MEMORY_CACHE=1` 명시 시에만 InMemory.
- 테스트 = InMemoryDailyFortuneCache 직접 주입.

락 규약: SET lock_key owner_token NX EX ttl — 해제는 Lua 로 현재 값이 자신의
owner_token 일 때만 삭제(타 소유자 락 삭제 방지).
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from datetime import date
from typing import Protocol

from saju_shared_types.daily_fortune import DailyFortuneBoard

_KEY_PREFIX = "daily_fortune"

# Lua: 소유자 토큰이 일치할 때만 락 삭제
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


def _board_key(d: date, content_version: str) -> str:
    return f"{_KEY_PREFIX}:board:{d.isoformat()}:{content_version}"


def _lock_key(kind: str, d: date, content_version: str) -> str:
    return f"{_KEY_PREFIX}:{kind}_lock:{d.isoformat()}:{content_version}"


class DailyFortuneCache(Protocol):
    """보드 TTL 캐시 + 소유권 락 인터페이스."""

    def load_board(self, d: date, content_version: str) -> DailyFortuneBoard | None:
        """오늘자 보드 조회 — 없거나 만료면 None."""
        ...

    def save_board(
        self, d: date, content_version: str, board: DailyFortuneBoard, ttl_seconds: int
    ) -> None:
        """보드 전체를 원자적으로 저장/교체한다(TTL 포함)."""
        ...

    def acquire_lock(
        self, kind: str, d: date, content_version: str, ttl_seconds: int
    ) -> str | None:
        """소유권 락 획득 — 성공 시 owner token, 실패 시 None."""
        ...

    def release_lock(self, kind: str, d: date, content_version: str, token: str) -> None:
        """자신의 token 일 때만 락을 해제한다."""
        ...


class RedisDailyFortuneCache:
    """Redis 구현 — 운영 기본. 값 교체(SET)가 원자적이라 보드 단위 일관성 보장."""

    def __init__(self, url: str | None = None) -> None:
        redis_url = url or os.getenv("SAJU_V2_REDIS_URL")
        if not redis_url:
            raise ValueError("SAJU_V2_REDIS_URL 미설정 — daily fortune 캐시 사용 불가")
        import redis  # 지연 임포트 — 미설치 환경(InMemory 전용)에서도 모듈 로드 가능

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._release = self._client.register_script(_RELEASE_LUA)

    def load_board(self, d: date, content_version: str) -> DailyFortuneBoard | None:
        raw = self._client.get(_board_key(d, content_version))
        if raw is None:
            return None
        return DailyFortuneBoard.model_validate_json(raw)

    def save_board(
        self, d: date, content_version: str, board: DailyFortuneBoard, ttl_seconds: int
    ) -> None:
        self._client.set(
            _board_key(d, content_version), board.model_dump_json(), ex=max(1, ttl_seconds)
        )

    def acquire_lock(
        self, kind: str, d: date, content_version: str, ttl_seconds: int
    ) -> str | None:
        token = secrets.token_hex(16)
        ok = self._client.set(
            _lock_key(kind, d, content_version), token, nx=True, ex=max(1, ttl_seconds)
        )
        return token if ok else None

    def release_lock(self, kind: str, d: date, content_version: str, token: str) -> None:
        self._release(keys=[_lock_key(kind, d, content_version)], args=[token])


class InMemoryDailyFortuneCache:
    """단일 프로세스 전용 구현 — 로컬 개발(명시적 env)·테스트 주입용."""

    def __init__(self) -> None:
        self._boards: dict[str, tuple[float, str]] = {}  # key -> (expire_ts, json)
        self._locks: dict[str, tuple[float, str]] = {}  # key -> (expire_ts, token)
        self._mutex = threading.Lock()

    def load_board(self, d: date, content_version: str) -> DailyFortuneBoard | None:
        with self._mutex:
            entry = self._boards.get(_board_key(d, content_version))
            if entry is None or entry[0] <= time.monotonic():
                return None
            return DailyFortuneBoard.model_validate_json(entry[1])

    def save_board(
        self, d: date, content_version: str, board: DailyFortuneBoard, ttl_seconds: int
    ) -> None:
        with self._mutex:
            self._boards[_board_key(d, content_version)] = (
                time.monotonic() + max(1, ttl_seconds),
                board.model_dump_json(),
            )

    def acquire_lock(
        self, kind: str, d: date, content_version: str, ttl_seconds: int
    ) -> str | None:
        key = _lock_key(kind, d, content_version)
        token = secrets.token_hex(16)
        with self._mutex:
            entry = self._locks.get(key)
            if entry is not None and entry[0] > time.monotonic():
                return None
            self._locks[key] = (time.monotonic() + max(1, ttl_seconds), token)
            return token

    def release_lock(self, kind: str, d: date, content_version: str, token: str) -> None:
        key = _lock_key(kind, d, content_version)
        with self._mutex:
            entry = self._locks.get(key)
            if entry is not None and entry[1] == token:
                del self._locks[key]


_memory_singleton: InMemoryDailyFortuneCache | None = None


def default_cache() -> DailyFortuneCache:
    """환경 기반 캐시 선택 — Redis 우선, 명시적 env 시에만 InMemory.

    둘 다 아니면 ValueError(API 계층에서 503). 운영 자동 InMemory 폴백 금지.
    """
    if os.getenv("SAJU_V2_REDIS_URL"):
        return RedisDailyFortuneCache()
    if os.getenv("SAJU_DAILY_FORTUNE_MEMORY_CACHE") == "1":
        global _memory_singleton
        if _memory_singleton is None:
            _memory_singleton = InMemoryDailyFortuneCache()
        return _memory_singleton
    raise ValueError(
        "daily fortune 캐시 미설정 — SAJU_V2_REDIS_URL 또는 "
        "SAJU_DAILY_FORTUNE_MEMORY_CACHE=1 필요"
    )
