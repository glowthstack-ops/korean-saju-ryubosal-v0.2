"""현실 신호 캘리브레이션 endpoints (Life Event Inference — 수집 + 계산 보정).

doc/v2_2/LIFE_EVENT_INFERENCE.md §5. 주요 ~10개 연도의 연도별 발생 이벤트를 사용자가 선택하면
LifeEventRow로 적재한다(재제출은 치환 — 수정 모드). 적재 후에는 개인 시그니처(personal_match)로
**계산에 반영**된다 — 본인 확인 신호와 닮은 후보의 점수·확신도를 상한 내 보정하고 정렬을 재정의
(personal_calibration.apply_personal_match). 코호트 보정은 활성 게이트 통과 시 추가.
풀이 프롬프트에 과거 사건을 낭독하지는 않는다(계산 보정이 목적). 접근은 소유자 일치 강제.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from saju_engines.employment_history import (
    entries_from_rows,
    make_month_fingerprint_resolver,
    reference_date_for_label,
    rows_from_history,
    superseded_keys,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.life_event_followup import CalibrationStatus, calibration_status
from saju_engines.life_event_store import LifeEventStore
from saju_engines.reality_calibration import (
    build_reality_calibration,
    month_event_fingerprints,
    pillars_signature,
    prior_answers_from_rows,
    rows_from_submission,
    submission_summary,
)
from saju_engines.subject_store import SubjectStore
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import (
    EmploymentHistorySubmission,
    EmploymentHistorySubmitResult,
    EmploymentHistoryView,
    LifeEventSource,
    RealityCalibrationQuestionSet,
    RealityCalibrationSubmission,
    RealityCalibrationSubmitResult,
    RealityCalibrationYearAnswer,
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
_CALIB_PAYLOAD_VERSION = "calibration_resolution_v1"  # 현실 캘리브레이션 payload 스키마 버전


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


def _prior_answers(
    life_events: LifeEventStore, owner_id: str, subject_id: str,
) -> list[RealityCalibrationYearAnswer]:
    """이전 답변 복원 — 해상도 blob(연 체감·영역·경험) 우선, 없으면 발생 행에서 재구성."""
    blob = life_events.get_reality_payload(owner_id, subject_id)
    if blob and blob.get("answers"):
        return [RealityCalibrationYearAnswer.model_validate(a) for a in blob["answers"]]
    return prior_answers_from_rows(life_events.subject_signature(owner_id, subject_id))


def _refresh_years(prior: list[RealityCalibrationYearAnswer], current_year: int) -> list[int]:
    """갱신 설문 대상 연도 — 마지막으로 답한 해 다음부터 올해까지(답한 적 없으면 빈 목록)."""
    answered = [a.year for a in prior]
    if not answered:
        return []
    return list(range(max(answered) + 1, current_year + 1))


@router.get("/{subject_id}/status", response_model=CalibrationStatus)
def status(
    subject_id: str, owner_id: OwnerId, subjects: Subjects, life_events: LifeEvents,
) -> CalibrationStatus:
    """사건 수집 상태 — 미완료 유도(P2)·연 1회 갱신 권유(P3)의 근거(2026-10-24)."""
    record = subjects.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    rows = life_events.subject_signature(owner_id, subject_id)
    last = life_events.reality_payload_updated_at(owner_id, subject_id)
    return calibration_status(rows, last, date.today())


@router.get("/{subject_id}/questions", response_model=RealityCalibrationQuestionSet)
def questions(
    subject_id: str, owner_id: OwnerId, subjects: Subjects, life_events: LifeEvents,
    mode: Literal["full", "refresh"] = "full",
) -> RealityCalibrationQuestionSet:
    """주요 ~10개 연도의 연도별 발생 이벤트 선택 질문을 생성한다.

    이전 제출이 있으면 prior에 복원해 수정 모드(기존 선택 프리필)로 재진입할 수 있게 한다.
    mode='refresh'(연 1회 갱신, 2026-10-24)는 마지막으로 답한 해 다음부터 올해까지만 묻는다
    (답한 적 없으면 full 과 같다).
    """
    chart = _owned_chart(subjects, subject_id, owner_id)
    prior = _prior_answers(life_events, owner_id, subject_id)
    years: list[int] | None = None
    if mode == "refresh":
        years = _refresh_years(prior, date.today().year) or None
    qset = build_reality_calibration(
        chart, _get_engine(), date.today().year, subject_id=subject_id, years=years,
    )
    if mode == "refresh" and years:
        qset = qset.model_copy(update={
            "note": "마지막 입력 이후의 해만 묻습니다. 실제로 있었던 일만 체크하세요. "
                    "기억이 흐린 해는 비워 두셔도 됩니다.",
        })
    return qset.model_copy(update={"prior": prior})


@router.post("/{subject_id}/submit", response_model=RealityCalibrationSubmitResult)
def submit(
    subject_id: str,
    submission: RealityCalibrationSubmission,
    owner_id: OwnerId,
    subjects: Subjects,
    life_events: LifeEvents,
) -> RealityCalibrationSubmitResult:
    """연도별 선택을 LifeEventRow로 적재한다(수집만). 적재 행 수 + 사용자용 요약을 반환."""
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
    src = str(LifeEventSource.REALITY_SIGNAL_CALIBRATION)
    if submission.mode == "refresh":
        # 갱신 설문(2026-10-24): 묻지 않은 해의 행·답은 보존하고 이번에 답한 해만 치환한다.
        prior = _prior_answers(life_events, owner_id, subject_id)
        years = _refresh_years(prior, date.today().year)
        question = build_reality_calibration(
            chart, _get_engine(), date.today().year, subject_id=subject_id, years=years or None,
        )
        month_fp = _month_fingerprints(record.birth, submission)
        rows = rows_from_submission(submission, question, pillars_signature(chart), month_fp)
        answered_years = sorted({a.year for a in submission.answers})
        life_events.delete_subject_rows_for_years(owner_id, subject_id, src, answered_years)
        stored = life_events.append_rows(rows)
        merged = {a.year: a for a in prior}
        merged.update({a.year: a for a in submission.answers})
        answers_out = [merged[y] for y in sorted(merged)]
    else:
        month_fp = _month_fingerprints(record.birth, submission)
        rows = rows_from_submission(submission, question, pillars_signature(chart), month_fp)
        # 재제출은 치환(수정) — 캘리브레이션 소스 행만 지우고 새로 적재해 선택 해제·중복을
        # 반영한다. 다른 경로(직장 이력)로 적재한 행은 보존한다(F3 교정, 2026-10-22).
        life_events.delete_subject_rows(owner_id, subject_id, source=src)
        stored = life_events.append_rows(rows)
        answers_out = list(submission.answers)
    # 해상도 값(연 체감·영역·사건 경험)은 별도 blob에 답변 원본 그대로 저장(수정 프리필용).
    life_events.save_reality_payload(owner_id, subject_id, {
        "version": _CALIB_PAYLOAD_VERSION,
        "answers": [a.model_dump(mode="json") for a in answers_out],
    })
    return submission_summary(rows, submission, stored)


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
        # 1월 회상(丑월)은 전년 입춘 기준 목록에만 있어 15일 기준일로는 지문이 비던 결함 교정
        # (2026-10-22, employment_history.reference_date_for_label 과 같은 규칙).
        chart = calculate(birth.model_copy(
            update={"reference_date": reference_date_for_label(f"{year}-{month:02d}")},
        ))
        cands = _get_engine().score(chart, levels={GanjiLevel.MONTH})
        fps = month_event_fingerprints(cands, f"{year}-{month:02d}")
        for ek in keys:
            if ek in fps:
                out[(year, month, ek)] = fps[ek]
    return out


# ── 직장 이력(EMPLOYMENT_HISTORY_CALIBRATION.md §4 입력 UI) ────────────────────
@router.get("/{subject_id}/employment-history", response_model=EmploymentHistoryView)
def employment_history(
    subject_id: str, owner_id: OwnerId, subjects: Subjects, life_events: LifeEvents,
) -> EmploymentHistoryView:
    """저장된 직장 이력(프리필). 없으면 빈 목록."""
    record = subjects.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    rows = life_events.subject_signature(owner_id, subject_id)
    return EmploymentHistoryView(subject_id=subject_id, entries=entries_from_rows(rows))


@router.post("/{subject_id}/employment-history", response_model=EmploymentHistorySubmitResult)
def submit_employment_history(
    subject_id: str,
    submission: EmploymentHistorySubmission,
    owner_id: OwnerId,
    subjects: Subjects,
    life_events: LifeEvents,
) -> EmploymentHistorySubmitResult:
    """직장 이력 전체 치환 적재 — 절기월·월운 지문·글자는 엔진이 계산한다(적재 스크립트와 같은
    규칙).

    같은 (event_key, period)의 캘리브레이션 회상 행은 정본에 밀려 삭제된다. 요약에 회사명은 없다.
    """
    if submission.subject_id != subject_id:
        raise HTTPException(status_code=400, detail="subject_id 불일치")
    record = subjects.get(subject_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    chart = _owned_chart(subjects, subject_id, owner_id)
    resolver = make_month_fingerprint_resolver(record.birth, _get_engine(), calculate)
    rows = rows_from_history(
        submission.entries, subject_id, owner_id, pillars_signature(chart), resolver,
    )
    src = str(LifeEventSource.EMPLOYMENT_HISTORY)
    life_events.delete_subject_rows(owner_id, subject_id, source=src)
    superseded = life_events.delete_superseded_rows(
        owner_id, subject_id, superseded_keys(rows), keep_source=src,
    )
    stored = life_events.append_rows(rows)
    n_entry = sum(1 for r in rows if r.event_key == "job_gain")
    n_exit = sum(1 for r in rows if r.event_key == "resignation")
    n_conv = len(rows) - n_entry - n_exit
    summary = [f"입사 {n_entry}건 · 퇴사 {n_exit}건 · 전환 {n_conv}건을 저장했어요."]
    if superseded:
        summary.append(f"같은 달의 이전 회상 기록 {superseded}건은 이력 기준으로 대체됐어요.")
    return EmploymentHistorySubmitResult(
        stored=stored, entries=len(submission.entries), superseded=superseded, summary=summary,
    )
