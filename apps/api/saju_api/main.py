"""FastAPI application for the Saju v2 만세력 engine."""

from __future__ import annotations

from fastapi import FastAPI

from saju_shared_types.constants import ENGINE_VERSION

from .routers import health, manse

app = FastAPI(title="류보살 v2 만세력 엔진", version=ENGINE_VERSION)
app.include_router(health.router)
app.include_router(manse.router)
