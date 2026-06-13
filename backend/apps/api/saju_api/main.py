"""FastAPI application for the Saju v2 만세력 engine."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from saju_shared_types.constants import ENGINE_VERSION

from .routers import (
    account,
    auth,
    calendar,
    chat,
    health,
    manse,
    past_validation,
    profile,
    report,
    subjects,
)

app = FastAPI(title="류보살 v2 만세력 엔진", version=ENGINE_VERSION)

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
app.include_router(chat.router)
app.include_router(past_validation.router)
app.include_router(report.router)
