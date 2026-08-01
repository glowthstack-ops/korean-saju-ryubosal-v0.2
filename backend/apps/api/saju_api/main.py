"""FastAPI application for the Saju v2 만세력 engine."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import traceback
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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
    daily_beta_admin,
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


_KST = ZoneInfo("Asia/Seoul")


def daily_fortune_pregen_schedule(
    now: datetime,
) -> tuple[datetime, date, datetime]:
    """(생성 시각, 대상 날짜, export 시각). **순수 함수 — 테스트 가능하게 분리한다.**

    두 시각이 자정을 사이에 두고 갈라져 있는 것이 핵심이다. 생성은 전날 23:50 이고
    export 는 그 다음 00:05 다. `write_threads_export` 가 오늘 보드만 쓰므로, 생성
    시점에 부르면 언제나 하루 이르러 건너뛰어진다(2026-08-02 실측).

    대상 날짜는 sleep **전에** 고정한다. 뒤에서 다시 now 를 읽으면 생성이 자정을 넘겨
    끝났을 때 +1 이 하루를 건너뛴 날짜가 된다(2026-08-01 실측).
    """
    run_at = now.replace(hour=23, minute=50, second=0, microsecond=0)
    if run_at <= now:
        run_at += timedelta(days=1)
    target = (run_at + timedelta(days=1)).date()
    export_at = (run_at + timedelta(days=1)).replace(
        hour=0, minute=5, second=0, microsecond=0)
    return run_at, target, export_at


async def _daily_fortune_pregen_loop() -> None:
    """보드를 **사용자 요청과 무관하게** 준비한다 (env SAJU_DAILY_FORTUNE_PREGEN=1 전용).

    23:50 KST 에 익일 보드를 선생성·교정하고, **기동 즉시 당일 누락을 보충**한다.
    23:50 태스크만 두면 그 시각에 서버가 떠 있지 않았던 경우(배포·재기동·신규 환경)
    당일 보드가 비어 첫 사용자가 60건 생성 + LLM 교정을 그대로 기다리게 된다.

    기본 off — 개발·테스트·임시 서버가 자정마다 LLM 을 호출하지 않도록 운영에서만
    명시적으로 켠다. 보충은 멱등이다(보드가 이미 있으면 재생성하지 않고, 교정도
    polish_status 가 RAW 일 때만 수행된다). 실패해도 루프를 유지하며, 최후 보루로
    당일 요청의 lazy 생성이 남는다(무중단).
    """
    from saju_engines.daily_fortune_cache import default_cache

    from .services import (
        daily_fortune_export,
        daily_fortune_polish,
        daily_fortune_service,
    )

    log = logging.getLogger("saju.daily_fortune")

    async def _ensure(target: date) -> None:
        try:
            await asyncio.to_thread(
                daily_fortune_polish.generate_and_polish, default_cache(), target
            )
        except Exception:  # noqa: BLE001 — 루프 유지, 다음 주기 재시도
            log.exception("보드 선생성 실패 date=%s", target)

    async def _export(target: date) -> None:
        """오늘이 된 보드를 스레드용 파일로 내보낸다.

        `write_threads_export` 는 **오늘 보드일 때만** 쓴다. 사전생성은 언제나 전날
        23:50 이라 그 시점의 `now.date()` 는 보드 날짜보다 하루 이르고, 따라서 생성
        경로의 export 는 항상 건너뛰어진다. 자정을 넘긴 뒤 한 번 더 부르는 이 단계가
        없으면 파일이 기동 시점 날짜에 멈춘다(2026-08-02 실측: 8/2 보드는 캐시에
        있는데 파일은 8/1 자였다).

        가드를 완화해 고치지 않는다 — 미래 보드가 오늘 파일을 덮는 사고를 막는 것이
        그 가드의 목적이고, 여기서는 호출 **시점**을 바로잡는다.
        """
        try:
            board = await asyncio.to_thread(
                daily_fortune_service.get_board, default_cache(), target
            )
            if not await asyncio.to_thread(
                daily_fortune_export.write_threads_export, board, today=target
            ):
                log.warning("스레드 export 건너뜀 date=%s", target)
        except Exception:  # noqa: BLE001 — 루프 유지, 다음 주기 재시도
            log.exception("스레드 export 실패 date=%s", target)

    # 기동 즉시 당일 보충 — 지금 접속하는 사용자가 생성을 기다리지 않게 한다.
    today = datetime.now(_KST).date()
    await _ensure(today)
    await _export(today)

    while True:
        now = datetime.now(_KST)
        run_at, target, export_at = daily_fortune_pregen_schedule(now)
        await asyncio.sleep((run_at - now).total_seconds())
        await _ensure(target)
        # 자정을 넘겨 target 이 '오늘' 이 된 뒤 내보낸다. 생성이 오래 걸려 이미 지난
        # 시각이면 즉시 실행된다.
        await asyncio.sleep(
            max(0.0, (export_at - datetime.now(_KST)).total_seconds()))
        await _export(target)


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
    # 베타 일운 풀 preflight — **suppress 하지 않는다.** 검증에 실패하면 예외가 그대로
    # 올라가 이 프로세스는 ready 로 진입하지 못하고, 기존 프로세스도 교체되지 않는다.
    # legacy 로 조용히 내려가면 테스터 일부가 legacy 를 보고 C10 피드백을 준다.
    from .services.daily_fortune_service import beta_enabled, beta_preflight

    beta_preflight()

    pregen_task: asyncio.Task[None] | None = None
    if os.getenv("SAJU_DAILY_FORTUNE_PREGEN") == "1":
        if beta_enabled():
            # legacy 보드를 만들 이유가 없다 — 스냅샷이 SSOT 이고 사후 교정도 돌지 않는다.
            logging.getLogger("saju_api.daily_beta").info(
                "베타 배포 — legacy 선생성 루프와 사후 교정을 기동하지 않는다"
            )
        else:
            pregen_task = asyncio.create_task(_daily_fortune_pregen_loop())
    yield
    if pregen_task is not None:
        pregen_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pregen_task


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
app.include_router(daily_beta_admin.router)
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
