"""만세력 calculation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.manse_result import ManseV2Result

from ..services import manse_service

router = APIRouter(prefix="/api/v2/manse", tags=["manse"])


@router.post("/calculate", response_model=ManseV2Result)
async def calculate(birth: BirthInput) -> ManseV2Result:
    # async handler: the engine is deterministic CPU work that runs quickly, so we
    # call it inline rather than letting FastAPI hand a sync handler to a
    # threadpool (which can hang under restricted sandboxes).
    try:
        return manse_service.calculate(birth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
