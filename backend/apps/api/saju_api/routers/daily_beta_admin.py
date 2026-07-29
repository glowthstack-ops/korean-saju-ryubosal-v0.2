"""베타 일운 풀 — 관리자·감사 전용 경로.

미래 날짜 조회(`allow_future`)는 **여기에만** 있다. 공개 라우터에는 query
parameter 로도 헤더로도 이 통로가 없다 — 있으면 선생성한 30일치를 누구나 미리
열 수 있고, "오늘까지만 공개"라는 계약이 사실상 사라진다.

감사 메타데이터도 여기서만 나간다. 사용자 화면에는 대표 선택 이유·손실 같은
내부 지표를 노출하지 않는다.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from saju_engines.daily_beta_pool import BetaPoolError

from ..deps import require_admin
from ..services import daily_fortune_service
from ..services.daily_beta_registry import BetaDailyPoolRegistry
from ..services.daily_beta_registry import render as render_beta

router = APIRouter(prefix="/api/v2/admin/daily-beta", tags=["admin"])

Admin = Annotated[str, Depends(require_admin)]

#: 베타 풀이 이 배포에서 활성이 아니다.
BETA_POOL_NOT_ACTIVE = "BETA_POOL_NOT_ACTIVE"


def _registry() -> BetaDailyPoolRegistry:
    reg = daily_fortune_service.beta_registry()
    if reg is None:
        raise HTTPException(
            status_code=404,
            detail={"code": BETA_POOL_NOT_ACTIVE, "message": "베타 풀 비활성 배포"},
        )
    return reg


@router.get("/pool")
def pool_metadata(_admin: Admin) -> dict:
    """활성 풀의 계약·지문. 카드는 담지 않는다."""
    reg = _registry()
    cfg = reg.config
    return {
        **reg.metadata,
        "audience": cfg.audience,
        "effective_from": cfg.effective_from.isoformat() if cfg.effective_from else None,
        "effective_until": (
            cfg.effective_until.isoformat() if cfg.effective_until else None
        ),
        "renderer_contract_version": cfg.renderer_contract,
        "card_count": len(reg.selections),
    }


@router.get("/day/{fortune_date}")
def day(
    fortune_date: dt.date,
    _admin: Admin,
    include_board: bool = Query(False, description="렌더된 문장까지 포함"),
) -> dict:
    """그 날짜의 선택 결과 — **미래 날짜도 연다**(관리자 전용).

    Args:
        fortune_date: 조회할 운세 날짜.
        include_board: True 면 사용자에게 보이는 문장까지 함께 반환한다.

    Returns:
        감사 메타데이터(+선택 시 보드).
    """
    reg = _registry()
    try:
        board, audit = render_beta(reg, fortune_date, allow_future=True)
    except BetaPoolError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    if include_board:
        audit = {**audit, "board": board.model_dump(mode="json")}
    return audit
