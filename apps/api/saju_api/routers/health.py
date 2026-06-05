"""Health check."""

from __future__ import annotations

from fastapi import APIRouter

from saju_shared_types.constants import ENGINE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_version": ENGINE_VERSION}
