"""현실 신호 캘리브레이션 endpoints (Life Event Inference — 수집 단계).

doc/v2_2/LIFE_EVENT_INFERENCE.md §5. 주요 ~10개 연도의 연도별 발생 이벤트를 사용자가 선택하면
LifeEventRow로 적재한다. **수집만** — 랭킹 미반영(코호트 활성 게이트는 별도 단계). 모든 접근은
소유자(owner_id) 일치를 강제한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.life_event_store import LifeEventStore
from saju_engines.reality_calibration import (
    build_reality_calibration,
    month_event_fingerprints,
    pillars_signature,
    rows_from_submission,
)
from saju_engines.subject_store import SubjectStore
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import (
    RealityCalibrationQuestionSet,
    RealityCalibrationSubmission,
    SignalFingerprint,
)

from ..deps import get_life_event_store, get_subject_store, require_owner
from ..services.manse_service import calculate

router = APIRouter(prefix="/api/v2/reality-calibration", tags=["reality-calibration"])

OwnerId = Annotated[str, Depends(require_owner)]
Subjects = Annotated[SubjectStore, Depends(get_subject_store)]
LifeEvents = Annotated[LifeEventStore, Depends(get_life_event_store)]

_DICTS = Path(__file__).resolve().parents[4] / "dictionaries"
_engine: EventEngineV2 | None = None


def _get_engine() -> EventEngineV2:
    global _engine
    if _engine is None:
        _engine = EventEngineV2(_DICTS)
    return _engine


def _owned_chart(store: SubjectStore, subject_id: str, owner_id: str):
    """소유 검증 + 그 subject의 차트 계산(오늘 기준)."""
    record = store.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    chart = calculate(record.birth.model_copy(update={"reference_date": date.today()}))
    return chart


@router.get("/{subject_id}/questions", response_model=RealityCalibrationQuestionSet)
def questions(
    subject_id: str, owner_id: OwnerId, subjects: Subjects,
) -> RealityCalibrationQuestionSet:
    """주요 ~10개 연도의 연도별 발생 이벤트 선택 질문을 생성한다."""
    chart = _owned_chart(subjects, subject_id, owner_id)
    return build_reality_calibration(
        chart, _get_engine(), date.today().year, subject_id=subject_id,
    )


@router.post("/{subject_id}/submit")
def submit(
    subject_id: str,
    submission: RealityCalibrationSubmission,
    owner_id: OwnerId,
    subjects: Subjects,
    life_events: LifeEvents,
) -> dict[str, int]:
    """연도별 선택을 LifeEventRow로 적재한다(수집만). 적재 행 수를 반환."""
    if submission.subject_id != subject_id:
        raise HTTPException(status_code=400, detail="subject_id 불일치")
    record = subjects.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    chart = _owned_chart(subjects, subject_id, owner_id)
    # 질문을 결정론적으로 재생성해 신호 지문을 확보(같은 차트·연도 → 같은 질문).
    question = build_reality_calibration(
        chart, _get_engine(), date.today().year, subject_id=subject_id,
    )
    submission = submission.model_copy(update={"owner_id": owner_id})
    month_fp = _month_fingerprints(record.birth, submission)
    rows = rows_from_submission(submission, question, pillars_signature(chart), month_fp)
    return {"stored": life_events.append_rows(rows)}


def _month_fingerprints(
    birth, submission: RealityCalibrationSubmission,
) -> dict[tuple[int, int, str], SignalFingerprint]:
    """발생 월이 지정된 사건만 그 달 월운을 스코어링해 월운 지문을 만든다(발생 건 한정)."""
    wanted: dict[tuple[int, int], set[str]] = {}
    for ans in submission.answers:
        for occ in ans.occurred:
            if occ.month and 1 <= occ.month <= 12:
                wanted.setdefault((ans.year, occ.month), set()).add(occ.event_key)
    out: dict[tuple[int, int, str], SignalFingerprint] = {}
    for (year, month), keys in wanted.items():
        chart = calculate(birth.model_copy(update={"reference_date": date(year, month, 15)}))
        cands = _get_engine().score(chart, levels={GanjiLevel.MONTH})
        fps = month_event_fingerprints(cands, f"{year}-{month:02d}")
        for ek in keys:
            if ek in fps:
                out[(year, month, ek)] = fps[ek]
    return out
