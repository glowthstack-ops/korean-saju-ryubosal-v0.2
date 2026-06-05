"""Health check."""

from __future__ import annotations

from fastapi import APIRouter

from saju_shared_types.constants import ENGINE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    # async so FastAPI runs it on the event loop instead of dispatching the sync
    # handler to a threadpool (which can hang under restricted sandboxes).
    return {"status": "ok", "engine_version": ENGINE_VERSION}
