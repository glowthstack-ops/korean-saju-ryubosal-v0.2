"""LLM 서비스 중단 상태 — 전이 규칙·캐시·사용자 안내문 (2026-10-06, 데굴님 승인 설계).

SSOT: doc/v2_2/LLM_SERVICE_SUSPENSION.md

상태 모델
- `active`: 정상. 공급자별로 `providers` 에 소진/쿨다운 기록이 있을 수 있다(메인만 소진 →
  폴백으로 계속 서비스, 메인은 쿨다운 동안 호출하지 않는다).
- `suspended`: 키가 있는 공급자 전부가 **명시 소진 신호**(quota)로 막힌 상태. 모든 LLM 호출은
  네트워크에 닿기 전에 `LLMServiceSuspended` 로 단락된다. 자동 복귀는 없다 — 관리자가 결제 후
  콘솔에서 프로브를 거쳐 `resume()` 한다.

영속화는 `LLMServiceStateStore`(DB 단일 행). DSN 미설정(테스트·무DB 배포)이면 프로세스
메모리에 둔다. 읽기는 5초 캐시 — LLM 호출은 초 단위 작업이라 호출당 DB 1회도 문제없지만,
채팅 라우터가 요청마다 묻기 때문에 짧게 캐시한다. 쓰기는 캐시를 즉시 무효화한다.

이 모듈은 `llm_client` 를 import 하지 않는다(역방향 의존 — llm_client 가 이 모듈을 쓴다).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from saju_engines.llm_service_state_store import LLMServiceStateStore

_logger = logging.getLogger(__name__)

#: 상태 읽기 캐시 TTL(초).
_CACHE_TTL = 5.0

#: 사용자 노출 문구 — 채팅 즉시 응답(중단 중 새 질문).
SUSPENDED_USER_MESSAGE = (
    "풀이 생성이 일시 중단되어 있어요. 서비스가 재개되면 다시 질문해 주세요."
)
#: 사용자 노출 문구 — 중단 시점에 생성 중이던 답변(재개 시 되살리지 않는다).
SUSPENDED_PENDING_MESSAGE = (
    "서비스 일시 중단으로 이 답변을 만들지 못했어요. 재개 후 다시 질문해 주세요."
)
#: 리포트 잡 생성 거부(503 detail).
SUSPENDED_REPORT_DETAIL = (
    "서비스 일시 중단 — 풀이 생성이 잠시 멈춰 있어요. 재개 후 다시 이용해 주세요."
)
#: system_errors 묶음 키를 고정하기 위한 상수 메시지(상세는 detail 로).
SUSPENDED_ERROR_MESSAGE = "LLM 서비스 일시 중단 — 공급자 비용 소진"
SUSPENDED_ERROR_KIND = "llm_service_suspended"
PROVIDER_EXHAUSTED_KIND = "llm_provider_quota_exhausted"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _parse(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass
class ProviderStatus:
    """공급자 1개의 소진/쿨다운 기록."""

    provider: str
    model: str
    kind: str  # 'quota'(명시 소진) | 'cooldown'(애매한 429 — 자동 복귀)
    detail: str
    since: str
    until: str | None  # ISO — 이 시각까지 호출하지 않는다(None=무기한, suspended 전용)

    def blocked_at(self, now: datetime) -> bool:
        """now 시점에 이 공급자를 건너뛰어야 하는가."""
        if self.until is None:
            return True
        until = _parse(self.until)
        return until is not None and until > now


@dataclass
class ServiceState:
    """서비스 전체 상태 스냅샷(불변 취급 — 수정은 모듈 함수로)."""

    state: str = "active"
    reason: str | None = None
    suspended_at: datetime | None = None
    resumed_at: datetime | None = None
    resumed_by: str | None = None
    providers: dict[str, ProviderStatus] = field(default_factory=dict)
    last_probe: dict[str, Any] | None = None

    @property
    def is_suspended(self) -> bool:
        return self.state == "suspended"

    def provider_blocked(self, provider: str, now: datetime | None = None) -> bool:
        """공급자가 소진/쿨다운으로 건너뛰기 대상인가."""
        rec = self.providers.get(provider)
        return rec is not None and rec.blocked_at(now or _now())

    def provider_quota_blocked(self, provider: str, now: datetime | None = None) -> bool:
        """공급자가 **명시 소진(quota)** 으로 막혀 있는가(중단 전이 판정용)."""
        rec = self.providers.get(provider)
        return rec is not None and rec.kind == "quota" and rec.blocked_at(now or _now())

    def snapshot(self, *, public: bool = True) -> dict[str, Any]:
        """JSON 스냅샷. public=True 면 사용자 노출용 최소 필드(비밀 없음)."""
        base: dict[str, Any] = {
            "state": self.state,
            "reason": self.reason,
            "suspended_at": _iso(self.suspended_at),
        }
        if public:
            return base
        base.update({
            "resumed_at": _iso(self.resumed_at),
            "resumed_by": self.resumed_by,
            "providers": {k: asdict(v) for k, v in self.providers.items()},
            "last_probe": self.last_probe,
        })
        return base


# ── 백엔드(DB 또는 메모리) ──────────────────────────────────────────


class _MemoryBackend:
    """DSN 미설정 환경용 — 프로세스 수명 동안만 유지."""

    def __init__(self) -> None:
        self._row: dict[str, Any] = {
            "state": "active", "reason": None, "suspended_at": None,
            "resumed_at": None, "resumed_by": None, "providers": {}, "last_probe": None,
        }

    def load(self) -> dict[str, Any]:
        return dict(self._row)

    def save(self, **fields: Any) -> None:
        self._row.update(fields)


_Backend = LLMServiceStateStore | _MemoryBackend

_lock = threading.RLock()
_backend: _Backend | None = None
_cached: tuple[float, ServiceState] | None = None


def _get_backend() -> _Backend:
    global _backend
    if _backend is None:
        try:
            _backend = LLMServiceStateStore()
        except ValueError:
            _backend = _MemoryBackend()
    return _backend


def setup() -> bool:
    """앱 기동 — 019 마이그레이션 적용. DSN 없으면 메모리 백엔드(False)."""
    global _backend
    try:
        store = LLMServiceStateStore()
    except ValueError:
        _backend = _MemoryBackend()
        return False
    store.migrate()
    _backend = store
    invalidate()
    return True


def use_memory_backend() -> None:
    """테스트 전용 — DB 없이 메모리 상태로 초기화한다."""
    global _backend
    with _lock:
        _backend = _MemoryBackend()
        invalidate()


def invalidate() -> None:
    """읽기 캐시 무효화."""
    global _cached
    with _lock:
        _cached = None


def _from_row(row: dict[str, Any]) -> ServiceState:
    providers: dict[str, ProviderStatus] = {}
    for key, raw in (row.get("providers") or {}).items():
        if not isinstance(raw, dict):
            continue
        try:
            providers[key] = ProviderStatus(
                provider=str(raw.get("provider", key)), model=str(raw.get("model", "")),
                kind=str(raw.get("kind", "quota")), detail=str(raw.get("detail", "")),
                since=str(raw.get("since", "")), until=raw.get("until"),
            )
        except Exception:  # noqa: BLE001 — 손상된 기록 1건이 전체 상태를 막지 않도록
            continue
    return ServiceState(
        state=str(row.get("state") or "active"),
        reason=row.get("reason"),
        suspended_at=_parse(row.get("suspended_at")),
        resumed_at=_parse(row.get("resumed_at")),
        resumed_by=row.get("resumed_by"),
        providers=providers,
        last_probe=row.get("last_probe"),
    )


def current(force: bool = False) -> ServiceState:
    """현재 상태(5초 캐시). 저장소 장애 시 마지막 캐시 또는 active 를 돌려준다(차단 금지)."""
    global _cached
    with _lock:
        now = time.monotonic()
        if not force and _cached is not None and now - _cached[0] < _CACHE_TTL:
            return _cached[1]
        try:
            state = _from_row(_get_backend().load())
        except Exception:  # noqa: BLE001 — 상태 조회 실패가 LLM 호출을 막으면 안 된다
            _logger.warning("llm_service_state 조회 실패 — 직전 캐시/active 로 진행", exc_info=True)
            return _cached[1] if _cached is not None else ServiceState()
        _cached = (now, state)
        return state


def _write(state: ServiceState) -> None:
    with _lock:
        try:
            _get_backend().save(
                state=state.state, reason=state.reason,
                suspended_at=state.suspended_at, resumed_at=state.resumed_at,
                resumed_by=state.resumed_by,
                providers={k: asdict(v) for k, v in state.providers.items()},
                last_probe=state.last_probe,
            )
        except Exception:  # noqa: BLE001 — 영속 실패는 로그만(메모리 캐시엔 반영)
            _logger.error("llm_service_state 저장 실패", exc_info=True)
        global _cached
        _cached = (time.monotonic(), state)


def is_suspended() -> bool:
    """서비스가 일시 중단 상태인가."""
    return current().is_suspended


# ── 전이 ───────────────────────────────────────────────────────────


def mark_provider_exhausted(
    provider: str, model: str, detail: str, *, kind: str = "quota",
    cooldown_seconds: float,
) -> bool:
    """공급자 소진/쿨다운 기록. 새로 막힌 경우에만 True(경고 1건 기록용).

    이미 막혀 있던 공급자를 다시 표시하면 until 만 연장하고 False 를 돌려준다.
    """
    with _lock:
        state = current(force=True)
        now = _now()
        was_blocked = state.provider_blocked(provider, now)
        until = None if state.is_suspended else _iso(now + timedelta(seconds=cooldown_seconds))
        state.providers[provider] = ProviderStatus(
            provider=provider, model=model, kind=kind, detail=detail[:300],
            since=_iso(now) or "", until=until,
        )
        _write(state)
        return not was_blocked


def clear_provider(provider: str) -> None:
    """공급자 기록 해제(프로브 성공 등)."""
    with _lock:
        state = current(force=True)
        if provider in state.providers:
            del state.providers[provider]
            _write(state)


def suspend(reason: str = "quota_exhausted") -> bool:
    """서비스 중단 전이. 이미 중단 상태면 False(중복 기록 방지)."""
    with _lock:
        state = current(force=True)
        if state.is_suspended:
            return False
        state.state = "suspended"
        state.reason = reason
        state.suspended_at = _now()
        state.resumed_at = None
        state.resumed_by = None
        # 중단 중에는 쿨다운 만료로 자동 재시도하지 않는다 — until 을 비운다.
        for rec in state.providers.values():
            rec.until = None
        _write(state)
        _logger.error("LLM 서비스 일시 중단 — reason=%s providers=%s",
                      reason, sorted(state.providers))
        return True


def resume(
    by: str, *, probe: dict[str, Any] | None, still_blocked: dict[str, tuple[str, str]],
    cooldown_seconds: float,
) -> bool:
    """관리자 재개. 프로브를 통과한 공급자 기록은 지우고, 여전히 소진인 공급자는 쿨다운으로 남긴다.

    Args:
        by: 재개한 관리자 owner_id.
        probe: 프로브 결과 요약(콘솔 표시용, last_probe 에 저장).
        still_blocked: 여전히 소진인 공급자 {provider: (model, detail)} — 쿨다운 유지.
        cooldown_seconds: 남는 공급자의 쿨다운 길이.

    Returns:
        상태가 바뀌었으면 True(이미 active 면 False — 단 last_probe 는 갱신한다).
    """
    with _lock:
        state = current(force=True)
        changed = state.is_suspended
        now = _now()
        state.state = "active"
        state.resumed_at = now
        state.resumed_by = by
        state.last_probe = probe
        state.providers = {
            p: ProviderStatus(
                provider=p, model=model, kind="quota", detail=detail[:300],
                since=_iso(now) or "", until=_iso(now + timedelta(seconds=cooldown_seconds)),
            )
            for p, (model, detail) in still_blocked.items()
        }
        _write(state)
        if changed:
            _logger.warning("LLM 서비스 재개 — by=%s still_blocked=%s", by, sorted(still_blocked))
        return changed


def record_probe(probe: dict[str, Any]) -> None:
    """프로브 결과만 갱신(재개 거부 시에도 콘솔에 보이도록)."""
    with _lock:
        state = current(force=True)
        state.last_probe = probe
        _write(state)
