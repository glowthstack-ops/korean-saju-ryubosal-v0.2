"""Past Validation 엔드포인트 (v2.2 Phase 6 T6.4 — 온보딩 신뢰 형성 플로우).

흐름(docs/01): 사주 입력 → 과거 검증 후보 제시 → 사용자 확인 → 신뢰도 계산 →
(이후 미래 예측 표현 강도에 반영). 프론트 온보딩은 미래 예측 전에 이 단계를 노출한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from saju_engines import EventScorer
from saju_engines.cases_store import CaseRow, CasesStore
from saju_engines.past_validation import calibrate_confidence, generate_past_candidates
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.past_validation import (
    CalibrationOutcome,
    PastFeedbackItem,
    PastValidationResult,
)

from ..services.manse_service import calculate

router = APIRouter(prefix="/api/v2/past-validation", tags=["past-validation"])

_BACKEND = Path(__file__).resolve().parents[4]
_scorer: EventScorer | None = None


def _get_scorer() -> EventScorer:
    global _scorer
    if _scorer is None:
        _scorer = EventScorer(_BACKEND / "dictionaries")
    return _scorer


class PastValidationRequest(BaseModel):
    """과거 검증 후보 요청 — 기간 미지정 시 성년(만 19세)~작년."""

    birth: BirthInput
    start_year: int | None = None
    end_year: int | None = None


class FeedbackRequest(BaseModel):
    """사용자 확인 제출 — cases.jsonl 적재 + 신뢰도 산출."""

    birth: BirthInput
    feedback: list[PastFeedbackItem] = Field(min_length=1)


@router.post("", response_model=PastValidationResult)
def candidates(req: PastValidationRequest) -> PastValidationResult:
    """과거 이벤트 후보 생성(연도당 ≤2건, 근거 경로 동반 — 콜드리딩 금지)."""
    birth_year = req.birth.birth_date.year
    ref_year = (
        req.birth.reference_date.year if req.birth.reference_date else birth_year + 46
    )
    start = req.start_year or birth_year + 19
    end = req.end_year or ref_year - 1
    return generate_past_candidates(
        req.birth, _get_scorer(), calculate, start, end,
    )


@router.post("/feedback", response_model=CalibrationOutcome)
def feedback(req: FeedbackRequest) -> CalibrationOutcome:
    """확인 결과 적재(cases.jsonl) + 신뢰도/표현 강도 산출(T6.2·T6.3)."""
    store = CasesStore()
    for item in req.feedback:
        store.append(CaseRow(
            case_id=store.next_case_id(),
            signals=[],  # 후보 신호 상세는 후속(후보 ID 연동 시 채움)
            predicted_event=str(item.event_key),
            actual_event=item.actual_event,
            time=item.year_range,
            matched=item.matched,
            notes=item.notes,
        ))
    return calibrate_confidence(req.feedback)
