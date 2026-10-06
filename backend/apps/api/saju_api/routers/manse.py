"""만세력 calculation + 용신 검증 피드백 endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import CalibrationResult, FeedbackAnswer
from saju_shared_types.luck import LuckPillar
from saju_shared_types.manse_result import ManseV2Result

from ..services import hour_narrowing, manse_service

router = APIRouter(prefix="/api/v2/manse", tags=["manse"])


class CalibrationFeedbackRequest(BaseModel):
    birth: BirthInput
    answers: list[FeedbackAnswer] = Field(default_factory=list)


class LuckMonthsRequest(BaseModel):
    birth: BirthInput
    year: int


class LuckDaysRequest(BaseModel):
    birth: BirthInput
    year: int
    month: int


@router.post("/calculate", response_model=ManseV2Result)
async def calculate(birth: BirthInput) -> ManseV2Result:
    # async handler: the engine is deterministic CPU work that runs quickly, so we
    # call it inline rather than letting FastAPI hand a sync handler to a
    # threadpool (which can hang under restricted sandboxes).
    try:
        return manse_service.calculate(birth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/calibration/feedback", response_model=CalibrationResult)
async def calibration_feedback(req: CalibrationFeedbackRequest) -> CalibrationResult:
    """Submit past-event feedback; returns calibrated/probable/uncertain decision."""
    try:
        return manse_service.calibrate_feedback(req.birth, req.answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/luck/months", response_model=list[LuckPillar])
async def luck_months(req: LuckMonthsRequest) -> list[LuckPillar]:
    """세운(연도) 선택 시 그 해 월운 12개를 온디맨드로 조회한다."""
    try:
        return manse_service.luck_months(req.birth, req.year)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/luck/days", response_model=list[LuckPillar])
async def luck_days(req: LuckDaysRequest) -> list[LuckPillar]:
    """간지달력에 일운(십성·십이운성·신살)을 오버레이하기 위해 해당 연·월 일운을 조회한다."""
    try:
        return manse_service.luck_days(req.birth, req.year, req.month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class HourTraitsRequest(BaseModel):
    """시주 후보 성향 문장 요청 — 시간 미상 명식(대략 시간대가 있으면 그 범위만)."""

    birth: BirthInput


@router.post("/hour-traits", response_model=hour_narrowing.HourTraitsResponse)
def hour_traits(req: HourTraitsRequest) -> hour_narrowing.HourTraitsResponse:
    """시간 미상 → 후보 시진별 성향 문장(사전 문구). 시간이 있으면 빈 목록(2026-10-06)."""
    return hour_narrowing.trait_candidates(req.birth)


@router.post("/hour-narrow", response_model=hour_narrowing.HourNarrowResponse)
def hour_narrow(req: hour_narrowing.HourNarrowRequest) -> hour_narrowing.HourNarrowResponse:
    """고른 성향 문장으로 후보 순위화 — 결과는 추정(확정 아님)."""
    return hour_narrowing.narrow(req)
