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

from saju_engines.daily_fortune_cache import DailyFortuneCache
from saju_shared_types.daily_fortune import DailyFortuneBoard, DailyFortuneSingle

from ..deps import get_daily_fortune_cache
from ..services import daily_fortune_polish, daily_fortune_service

router = APIRouter(prefix="/api/v2/daily-fortune", tags=["daily-fortune"])

Cache = Annotated[DailyFortuneCache, Depends(get_daily_fortune_cache)]


def _etag(payload: str) -> str:
    return '"' + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32] + '"'


def _set_cache_headers(response: Response, etag: str) -> None:
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = (
        f"public, max-age={daily_fortune_service.seconds_until_next_midnight()}, must-revalidate"
    )


@router.get("/today", response_model=DailyFortuneBoard)
async def today(
    request: Request,
    response: Response,
    cache: Cache,
) -> Response | DailyFortuneBoard:
    """오늘의 60일주 보드 — 캐시 미스 시 lazy 생성."""
    board = await asyncio.to_thread(daily_fortune_service.get_board, cache)
    if board.polish_status == "RAW":  # lazy 경로 교정 — 응답은 항상 즉시(원문)
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
    single = await asyncio.to_thread(daily_fortune_service.get_single, cache, ilju)
    if single is None:
        raise HTTPException(status_code=422, detail=f"유효하지 않은 일주 표기: {ilju}")
    _set_cache_headers(response, _etag(single.model_dump_json()))
    return single
