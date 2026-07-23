"""FastAPI application for the Saju v2 만세력 engine."""

from __future__ import annotations

import contextlib
import logging
import os
import traceback
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from saju_shared_types.constants import ENGINE_VERSION

from .routers import (
    account,
    admin,
    auth,
    calendar,
    chat,
    daily_fortune,
    health,
    manse,
    past_validation,
    profile,
    reality_calibration,
    report,
    subjects,
)
from .services import error_logging, usage_logging

# 앱 로거 콘솔 노출(2026-07-14 관측성) — uvicorn 기본 로깅은 자체(uvicorn.*) 로거만
# 핸들링해 엔진·서비스의 INFO 진단 로그(overview_selection 등)가 침묵한다. 루트가 아니라
# 앱 네임스페이스에만 핸들러를 달아 서드파티 INFO 소음 없이 관측성을 확보한다.
for _log_ns in ("saju_api", "saju_engines"):
    _app_logger = logging.getLogger(_log_ns)
    if not _app_logger.handlers:  # 중복 부착 방지(리로드·다중 임포트)
        _handler = logging.StreamHandler()
        _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s — %(message)s"))
        _app_logger.addHandler(_handler)
        _app_logger.setLevel(logging.INFO)
        _app_logger.propagate = False


def _seed_admins() -> None:
    """env SAJU_ADMIN_LOGIN_IDS(쉼표 구분)의 기존 계정에 관리자 권한을 부여한다."""
    ids = [s.strip() for s in os.getenv("SAJU_ADMIN_LOGIN_IDS", "").split(",") if s.strip()]
    if not ids:
        return
    from saju_engines.auth_store import AccountAuthStore

    store = AccountAuthStore()
    for login_id in ids:
        store.set_admin(login_id, True)


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """기동 시 admin 사용량 로깅 토대(009 마이그레이션·단가 seed·sink)·관리자 시드를 준비한다."""
    with contextlib.suppress(Exception):
        usage_logging.setup()
    with contextlib.suppress(Exception):
        error_logging.setup()  # 010 마이그레이션 + llm 에러 sink 주입
    with contextlib.suppress(Exception):
        _seed_admins()
    with contextlib.suppress(Exception):
        # 위험 노출 adapter startup stamp(감수 61차 §13) — EXPOSE 계열
        # 모드가 아니면 no-op(기존 경로 byte 불변).
        from .services.risk_exposure_bootstrap import (
            bootstrap_risk_exposure,
        )
        bootstrap_risk_exposure()
    yield


app = FastAPI(title="류보살 v2 만세력 엔진", version=ENGINE_VERSION, lifespan=_lifespan)

# 프론트(다른 origin)에서의 호출 허용. 운영 도메인은 env로 제한.
_origins = os.getenv("SAJU_CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(subjects.router)
app.include_router(profile.router)
app.include_router(account.router)
app.include_router(manse.router)
app.include_router(calendar.router)
app.include_router(daily_fortune.router)
app.include_router(chat.router)
app.include_router(past_validation.router)
app.include_router(reality_calibration.router)
app.include_router(report.router)
app.include_router(admin.router)


@app.exception_handler(Exception)
async def _on_unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """미처리 예외(5xx)를 중앙 적재한 뒤 일반화된 500을 반환한다(HTTPException·검증오류는 제외).

    이미 하위 계층(예: llm sink)이 기록한 예외는 중복 적재하지 않는다.
    """
    if not error_logging.is_logged(exc):
        with contextlib.suppress(Exception):
            error_logging.record_error(
                source="http",
                kind=type(exc).__name__,
                message=str(exc) or type(exc).__name__,
                detail="".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )[:8000],
                path=f"{request.method} {request.url.path}",
                exc=exc,
            )
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류"})
