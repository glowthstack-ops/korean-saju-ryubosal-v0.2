"""Health check."""

from __future__ import annotations

from fastapi import APIRouter

from saju_shared_types.constants import ENGINE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    # async so FastAPI runs it on the event loop instead of dispatching the sync
    # handler to a threadpool (which can hang under restricted sandboxes).
    # 위험 노출 readiness는 서비스 전체와 분리(감수 62차 P1) — 위험 시스템
    # DEGRADED가 일반 풀이 트래픽을 빼지 않도록 status는 항상 서비스 기준.
    out = {"status": "ok", "engine_version": ENGINE_VERSION,
           "service_readiness": "READY"}
    try:
        from ..services.risk_exposure_monitor import risk_readiness_snapshot
        out.update({k: str(v) for k, v in risk_readiness_snapshot().items()
                    if v is not None})
    except Exception:  # noqa: BLE001 — 관측 실패가 health를 막지 않는다
        pass
    return out
