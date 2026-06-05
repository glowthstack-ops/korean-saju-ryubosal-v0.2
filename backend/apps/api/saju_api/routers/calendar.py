"""간지달력 endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from saju_shared_types.calendar_view import CalendarMonth

from ..services import calendar_service

router = APIRouter(prefix="/api/v2/calendar", tags=["calendar"])


@router.get("/today", response_model=CalendarMonth)
async def today() -> CalendarMonth:
    return calendar_service.today_month()


@router.get("/{year}/{month}", response_model=CalendarMonth)
async def month(year: int, month: int) -> CalendarMonth:
    try:
        return calendar_service.month(year, month)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
