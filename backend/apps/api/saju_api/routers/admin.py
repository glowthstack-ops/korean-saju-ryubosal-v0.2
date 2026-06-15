"""운영 관리자 콘솔 API (v2.2 — Phase C). 모든 경로는 require_admin 가드.

LLM 사용량·비용(USD·KRW 병기)·서버 이벤트(리포트 잡)·관리자 등록 단가/환율을 제공한다.
BI는 추후 — 본 API는 집계·운영 지표와 단가 관리에 집중한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from saju_engines.error_store import ErrorStore
from saju_engines.report_job_store import ReportJobStore
from saju_engines.usage_store import PricingStore, UsageStore

from ..deps import (
    get_error_store,
    get_pricing_store,
    get_report_job_store,
    get_usage_store,
    require_admin,
)

router = APIRouter(prefix="/api/v2/admin", tags=["admin"])

Admin = Annotated[str, Depends(require_admin)]
Usage = Annotated[UsageStore, Depends(get_usage_store)]
Pricing = Annotated[PricingStore, Depends(get_pricing_store)]
Jobs = Annotated[ReportJobStore, Depends(get_report_job_store)]
Errors = Annotated[ErrorStore, Depends(get_error_store)]


def _krw(usd: float, rate: float) -> int:
    return round(usd * rate)


_KST = ZoneInfo("Asia/Seoul")


def _window(days: int) -> str:
    """KST 기준 days일 전 자정(tz-aware ISO) — 사용량 범위 시작(UTC 경계로 끊지 않음)."""
    midnight = datetime.now(_KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - timedelta(days=days)).isoformat()


class PricingIn(BaseModel):
    """모델 단가 등록(USD / 1M tokens)."""

    input_per_1m: float = Field(ge=0)
    output_per_1m: float = Field(ge=0)
    cached_per_1m: float = Field(ge=0, default=0.0)


class RateIn(BaseModel):
    usd_krw: float = Field(gt=0)


@router.get("/overview")
def overview(_admin: Admin, usage: Usage, pricing: Pricing, jobs: Jobs, errors: Errors) -> dict:
    """KPI — 오늘/7일/30일 토큰·비용(USD·KRW), 월 예상, 단위 비용, 잡 상태, 미해결 에러."""
    rate = pricing.usd_krw()
    today = usage.totals(start=_window(0))
    w7 = usage.totals(start=_window(7))
    w30 = usage.totals(start=_window(30))
    daily_avg_usd = w30["cost_usd"] / 30
    # 30일 surface별 단위 비용(호출당) — '채팅 1질의', '리포트 1섹션' 평균.
    surf30 = {s["key"]: s for s in usage.summary(start=_window(30), group_by="surface")}

    def _unit(key: str) -> float:
        s = surf30.get(key, {})
        return round(s.get("cost_usd", 0.0) / s["calls"], 6) if s.get("calls") else 0.0

    return {
        "exchange_rate_usd_krw": rate,
        "today": _with_krw(today, rate),
        "last_7d": _with_krw(w7, rate),
        "last_30d": _with_krw(w30, rate),
        "projection_month_usd": round(daily_avg_usd * 30, 4),
        "projection_month_krw": _krw(daily_avg_usd * 30, rate),
        "unit_cost_chat_usd": _unit("chat"),
        "unit_cost_report_section_usd": _unit("report"),
        "job_status_counts": jobs.status_counts(),
        "unresolved_errors": _unresolved_errors(errors),
    }


def _unresolved_errors(errors: ErrorStore) -> int:
    """미해결 에러 수 — 010 미적용 등 조회 실패 시 0(개요가 깨지지 않도록)."""
    try:
        return errors.unresolved_total()
    except Exception:  # noqa: BLE001 — KPI 1개가 개요 전체를 막지 않도록
        return 0


def _with_krw(totals: dict, rate: float) -> dict:
    return {**totals, "cost_krw": _krw(totals.get("cost_usd", 0.0), rate)}


@router.get("/usage/summary")
def usage_summary(
    _admin: Admin, usage: Usage, pricing: Pricing,
    start: str | None = None, end: str | None = None,
    group_by: str = Query("day", pattern="^(day|surface|product|model|owner)$"),
) -> dict:
    """기간 사용량 집계(group_by) — 토큰·비용(USD·KRW)."""
    rate = pricing.usd_krw()
    rows = usage.summary(start=start, end=end, group_by=group_by)
    for r in rows:
        r["cost_krw"] = _krw(r["cost_usd"], rate)
    return {"exchange_rate_usd_krw": rate, "group_by": group_by, "rows": rows}


@router.get("/usage/timeseries")
def usage_timeseries(
    _admin: Admin, usage: Usage, pricing: Pricing, days: int = Query(30, ge=1, le=365),
) -> dict:
    """일별 토큰·비용 추세(기본 30일)."""
    rate = pricing.usd_krw()
    rows = usage.summary(start=_window(days), group_by="day")
    for r in rows:
        r["cost_krw"] = _krw(r["cost_usd"], rate)
    return {"exchange_rate_usd_krw": rate, "rows": rows}


@router.get("/events")
def events(
    _admin: Admin, jobs: Jobs,
    status: str | None = None, limit: int = Query(100, ge=1, le=500),
) -> dict:
    """서버 이벤트 — 리포트(테마사주) 잡 목록(상태 필터)."""
    return {"jobs": jobs.list_recent(status=status, limit=limit)}


@router.get("/pricing")
def get_pricing(_admin: Admin, pricing: Pricing) -> dict:
    """등록 단가 + 환율."""
    return {"pricing": pricing.list_pricing(), "usd_krw": pricing.usd_krw()}


@router.put("/pricing/{model}")
def put_pricing(model: str, body: PricingIn, admin: Admin, pricing: Pricing) -> dict:
    """모델 단가 등록·수정."""
    pricing.upsert_pricing(
        model, body.input_per_1m, body.output_per_1m, body.cached_per_1m, updated_by=admin,
    )
    return {"ok": True, "model": model}


@router.put("/settings/usd_krw")
def put_rate(body: RateIn, _admin: Admin, pricing: Pricing) -> dict:
    """환율(USD→KRW) 등록."""
    pricing.set_setting("usd_krw", str(body.usd_krw))
    return {"ok": True, "usd_krw": body.usd_krw}


class ResolveIn(BaseModel):
    """에러 해결 처리 — id 목록 또는 fingerprint(묶음) 단위."""

    ids: list[int] | None = None
    fingerprint: str | None = None


@router.get("/errors/groups")
def error_groups(
    _admin: Admin, errors: Errors,
    days: int = Query(7, ge=1, le=90), unresolved: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """시스템 에러 — fingerprint 묶음(발생 횟수·미해결 수·최초/최종) + 기간 집계."""
    return {
        "groups": errors.group_summary(days=days, unresolved_only=unresolved, limit=limit),
        "counts": errors.counts(days=days),
    }


@router.get("/errors")
def error_list(
    _admin: Admin, errors: Errors,
    source: str | None = None, severity: str | None = None,
    fingerprint: str | None = None, unresolved: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """시스템 에러 개별 목록(필터: 출처·심각도·fingerprint·미해결)."""
    return {
        "errors": errors.list_recent(
            source=source, severity=severity, fingerprint=fingerprint,
            unresolved_only=unresolved, limit=limit,
        )
    }


@router.post("/errors/resolve")
def resolve_errors(body: ResolveIn, _admin: Admin, errors: Errors) -> dict:
    """에러 해결 처리(id 목록 또는 fingerprint 단위) — 처리 건수 반환."""
    n = errors.resolve(ids=body.ids, fingerprint=body.fingerprint)
    return {"ok": True, "resolved": n}
