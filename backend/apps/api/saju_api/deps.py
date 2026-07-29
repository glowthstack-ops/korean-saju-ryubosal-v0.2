"""API 공용 의존성 (v2.2 프론트 확장 Phase 1).

ID+PIN 경량 인증의 세션 토큰 발급·검증과 owner_id 해석을 한 곳에 격리한다. 추후 OAuth로
대치할 때 본 모듈만 교체하면 라우터는 손대지 않는다. 토큰은 상태 없는 HMAC 서명 방식
(owner_id를 서명) — 낮은 보안 등급의 임시 수단이며, 만료·회수가 필요하면 후속에서 세션
테이블로 승격한다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from collections.abc import Callable

from fastapi import Header, HTTPException

from saju_engines.account_store import AccountSettingsStore
from saju_engines.auth_store import AccountAuthStore
from saju_engines.chat_history_store import ChatHistoryStore
from saju_engines.daily_fortune_cache import DailyFortuneCache, default_cache
from saju_engines.error_store import ErrorStore
from saju_engines.life_event_store import LifeEventStore
from saju_engines.profile_store import ProfileStore
from saju_engines.report_job_store import ReportJobStore
from saju_engines.subject_store import SubjectStore
from saju_engines.usage_store import PricingStore, UsageStore

_SECRET = os.getenv("SAJU_V2_AUTH_SECRET", "dev-insecure-secret-change-me").encode("utf-8")


def _store[StoreT](factory: Callable[[], StoreT]) -> StoreT:
    """DSN 미설정(ValueError)을 503으로 변환해 저장소를 생성한다."""
    try:
        return factory()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="저장소(DB) 미설정") from exc


def get_auth_store() -> AccountAuthStore:
    """accounts 저장소."""
    return _store(AccountAuthStore)


def get_daily_fortune_cache() -> DailyFortuneCache:
    """일주별 오늘의 운세 TTL 캐시 — 미설정(Redis·명시적 InMemory 모두 없음) 시 503."""
    return _store(default_cache)


def get_daily_fortune_cache_or_beta() -> DailyFortuneCache | None:
    """일운 캐시 — **베타 배포에서는 None.**

    베타 경로는 불변 snapshot 만 읽으므로 Redis 가 필요 없다. 그런데도 캐시 dep 이
    먼저 503 을 던지면, 저장소 장애 하나로 스냅샷을 그대로 낼 수 있는 요청까지 함께
    죽는다.
    """
    from .services.daily_fortune_service import beta_enabled

    if beta_enabled():
        return None
    return _store(default_cache)


def get_subject_store() -> SubjectStore:
    """subjects 저장소."""
    return _store(SubjectStore)


def get_subject_store_optional() -> SubjectStore | None:
    """subjects 저장소 — DSN 미설정이면 None(익명·dry-run 채팅이 503에 막히지 않도록)."""
    try:
        return SubjectStore()
    except ValueError:
        return None


def get_life_event_store() -> LifeEventStore:
    """subject_life_events 저장소 (현실 신호 캘리브레이션 수집)."""
    return _store(LifeEventStore)


def get_profile_store() -> ProfileStore:
    """user_profiles 저장소."""
    return _store(ProfileStore)


def get_account_store() -> AccountSettingsStore:
    """account_settings(페르소나) 저장소."""
    return _store(AccountSettingsStore)


def get_report_job_store() -> ReportJobStore:
    """report_jobs 저장소."""
    return _store(ReportJobStore)


def get_chat_history_store() -> ChatHistoryStore:
    """chat_threads/chat_messages 저장소."""
    return _store(ChatHistoryStore)


def get_chat_history_store_optional() -> ChatHistoryStore | None:
    """chat 저장소 — DSN 미설정이면 None(익명·dry-run·정책 채팅이 503에 막히지 않도록)."""
    try:
        return ChatHistoryStore()
    except ValueError:
        return None


def get_usage_store() -> UsageStore:
    """llm_usage(사용량·비용) 저장소 — 관리자 콘솔."""
    return _store(UsageStore)


def get_pricing_store() -> PricingStore:
    """model_pricing/admin_settings(단가·환율) 저장소 — 관리자 콘솔."""
    return _store(PricingStore)


def get_error_store() -> ErrorStore:
    """system_errors(시스템 에러 모니터링) 저장소 — 관리자 콘솔."""
    return _store(ErrorStore)


def _sign(owner_id: str) -> str:
    """owner_id에 대한 HMAC-SHA256 서명(hex)."""
    return hmac.new(_SECRET, owner_id.encode("utf-8"), hashlib.sha256).hexdigest()


def make_token(owner_id: str) -> str:
    """세션 토큰 발급 — base64url(owner_id).signature."""
    encoded = base64.urlsafe_b64encode(owner_id.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.{_sign(owner_id)}"


def parse_token(token: str) -> str | None:
    """토큰 검증 — 유효하면 owner_id, 아니면 None."""
    try:
        encoded, signature = token.split(".", 1)
        padding = "=" * (-len(encoded) % 4)
        owner_id = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(signature, _sign(owner_id)):
        return None
    return owner_id


def _token_from_header(authorization: str | None) -> str | None:
    """Authorization 헤더에서 Bearer 토큰을 추출한다."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def optional_owner(authorization: str | None = Header(default=None)) -> str | None:
    """owner_id를 해석한다(비로그인/무효 토큰이면 None) — 무료 경로용."""
    token = _token_from_header(authorization)
    return parse_token(token) if token else None


def require_owner(authorization: str | None = Header(default=None)) -> str:
    """owner_id를 강제한다(없으면 401) — 유료/소유자 전용 경로용."""
    owner = optional_owner(authorization)
    if owner is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return owner


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """관리자 권한을 강제한다(비로그인 401 / 권한 없음 403) — 운영 콘솔 전용."""
    owner = require_owner(authorization)
    if not get_auth_store().is_admin(owner):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return owner
