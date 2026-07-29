"""일주별 오늘의 운세 — 공개(무인증) 라우터. 오늘 데이터만 제공한다.

휘발성 원칙(docs/17 §0-2): 과거 날짜·history·archive 엔드포인트를 만들지
않는다. 캐시 헤더는 must-revalidate — 자정 이후 어제 운세 노출 방지를 위해
stale-while-revalidate 를 쓰지 않는다.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from saju_engines.daily_beta_pool import BetaPoolError
from saju_engines.daily_fortune_cache import DailyFortuneCache
from saju_shared_types.daily_fortune import DailyFortuneBoard, DailyFortuneSingle

from ..deps import get_daily_fortune_cache_or_beta
from ..services import daily_fortune_polish, daily_fortune_service

router = APIRouter(prefix="/api/v2/daily-fortune", tags=["daily-fortune"])

#: 베타 배포에서는 None — snapshot 경로는 캐시를 쓰지 않는다.
Cache = Annotated[
    DailyFortuneCache | None, Depends(get_daily_fortune_cache_or_beta)
]


def _etag(payload: str) -> str:
    return '"' + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32] + '"'


# 클라이언트 캐시 수명 상한(초) — 교정(RAW→POLISHED)·사전 버전 업이 하루 중에 보드를
# 교체하므로 자정까지 통짜 캐시하면 화면 간 세대 불일치가 생긴다. 5분마다 ETag 재검증
# (304 — 본문 미전송)으로 싸게 동기화하고, 자정 직전에는 남은 시간으로 더 줄인다.
_CLIENT_MAX_AGE = 300


#: 베타 배포에서 snapshot 을 열 수 없을 때. **legacy 로 대체하지 않는다** — 테스터
#: 일부가 legacy 를 보고 C10 피드백을 주면 이번 평가가 통째로 무효가 된다.
_BETA_UNAVAILABLE_STATUS = 503


def _beta_guard(exc: BetaPoolError) -> HTTPException:
    """베타 일운 API 만 차단한다(다른 API 는 영향받지 않는다)."""
    return HTTPException(
        status_code=_BETA_UNAVAILABLE_STATUS,
        detail={"code": exc.code, "message": "일운 베타 풀을 열 수 없습니다"},
        headers={"Cache-Control": "no-store"},
    )


def _set_cache_headers(response: Response, etag: str) -> None:
    max_age = min(_CLIENT_MAX_AGE, daily_fortune_service.seconds_until_next_midnight())
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = f"public, max-age={max_age}, must-revalidate"


@router.get("/today", response_model=DailyFortuneBoard)
async def today(
    request: Request,
    response: Response,
    cache: Cache,
) -> Response | DailyFortuneBoard:
    """오늘의 60일주 보드 — 캐시 미스 시 lazy 생성."""
    # `allow_future` 는 이 경로에 존재하지 않는다 — query parameter·헤더로 미래
    # 날짜를 여는 통로를 만들지 않는다(관리자 라우터에만 있다).
    try:
        board = await asyncio.to_thread(daily_fortune_service.get_board, cache)
    except BetaPoolError as exc:
        raise _beta_guard(exc) from exc
    if cache is not None and board.polish_status == "RAW":
        # lazy 경로 교정 — 응답은 항상 즉시(원문). 베타(cache=None)에서는 하지 않는다:
        # snapshot 은 문장까지 동결돼 있고, 교정이 돌면 테스터가 본 카드가 사후에
        # 바뀐다.
        daily_fortune_polish.maybe_schedule_polish(cache, board.fortune_date)
    etag = _etag(board.model_dump_json())
    if request.headers.get("if-none-match") == etag:
        resp = Response(status_code=304)
        _set_cache_headers(resp, etag)
        return resp
    _set_cache_headers(response, etag)
    return board


@router.get("/today/{ilju}", response_model=DailyFortuneSingle)
async def today_single(
    ilju: str,
    response: Response,
    cache: Cache,
) -> DailyFortuneSingle:
    """일주 단건(메인 카드용) — 한자('甲子')·한글('갑자') 표기 모두 수용."""
    try:
        single = await asyncio.to_thread(daily_fortune_service.get_single, cache, ilju)
    except BetaPoolError as exc:
        raise _beta_guard(exc) from exc
    if single is None:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 일주 표기: {ilju}")
    _set_cache_headers(response, _etag(single.model_dump_json()))
    return single
