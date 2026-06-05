"""만세력 calculation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.manse_result import ManseV2Result

from ..services import manse_service

router = APIRouter(prefix="/api/v2/manse", tags=["manse"])


@router.post("/calculate", response_model=ManseV2Result)
def calculate(birth: BirthInput) -> ManseV2Result:
    try:
        return manse_service.calculate(birth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
