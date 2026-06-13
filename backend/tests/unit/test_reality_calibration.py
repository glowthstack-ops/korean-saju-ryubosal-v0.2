"""현실 신호 캘리브레이션 검증 (Life Event Inference 2단계 — 수집).

질문 생성(주요 ~10개 연도·연도별 이벤트·신호 지문)과 제출→LifeEventRow 변환을 확인한다.
DB는 쓰지 않는다(수집 로직은 순수 함수). 골든 차트 1980-11-22.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.reality_calibration import (
    build_reality_calibration,
    fingerprint_of,
    pillars_signature,
    rows_from_submission,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventSource,
    OccurredEvent,
    RealityCalibrationSubmission,
    RealityCalibrationYearAnswer,
    SignalFingerprint,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def engine() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def question(chart, engine: EventEngineV2):
    return build_reality_calibration(chart, engine, 2026, subject_id="s1")


def test_question_has_major_years(question) -> None:
    assert question.years, "주요 연도가 생성되어야 한다"
    assert len(question.years) <= 10
    # 성년(1999) 이후 ~ 2026 범위.
    assert all(1999 <= y.year <= 2026 for y in question.years)
    assert question.years == sorted(question.years, key=lambda y: y.year)


def test_year_has_events_with_labels_and_fingerprint(question) -> None:
    y = next(y for y in question.years if y.events)
    ev = y.events[0]
    assert ev.label and ev.label != ev.event_key  # 한글 라벨(내부 키 노출 금지)
    # 신호 지문이 채워진다(십성그룹 등).
    assert ev.fingerprint.ten_god_groups or ev.fingerprint.palace


def test_salience_prefers_strong_or_jiao(question) -> None:
    # salience 최댓값 연도는 0보다 큼(강신호 또는 교운 인접).
    assert max(y.salience for y in question.years) > 0


def test_fingerprint_extracts_groups(chart, engine: EventEngineV2) -> None:
    cands = engine.score(chart, levels={__import__(
        "saju_shared_types.ganji_calendar", fromlist=["GanjiLevel"]).GanjiLevel.YEAR})
    fp = fingerprint_of(cands[0])
    assert isinstance(fp.ten_god_groups, list)


def test_submission_to_rows(chart, question) -> None:
    # 첫 연도에서 한 사건은 발생, 나머지는 미발생.
    y0 = next(y for y in question.years if y.events)
    chosen = y0.events[0].event_key
    sub = RealityCalibrationSubmission(
        subject_id="s1",
        answers=[RealityCalibrationYearAnswer(
            year=y0.year, occurred=[OccurredEvent(event_key=chosen)],
        )],
    )
    rows = rows_from_submission(sub, question, pillars_signature(chart))
    assert rows
    by_key = {r.event_key: r for r in rows if r.period == str(y0.year)}
    assert by_key[chosen].outcome is LifeEventOutcome.CONFIRMED
    others = [r for k, r in by_key.items() if k != chosen]
    assert all(r.outcome is LifeEventOutcome.NOT_HAPPENED for r in others)
    # 코호트 지문(일주+성별) + 소스가 채워진다.
    r = rows[0]
    assert r.pillar_day and r.gender == "male"
    assert r.source is LifeEventSource.REALITY_SIGNAL_CALIBRATION


def test_occurred_month_uses_month_period_and_fingerprint(chart, question) -> None:
    # 발생 월이 있고 월운 지문이 제공되면 period='YYYY-MM' + 월운 지문으로 적재.
    y0 = next(y for y in question.years if y.events)
    chosen = y0.events[0].event_key
    month_fp = SignalFingerprint(ten_god_groups=["wealth"], palace="day_pillar", relation="CHUNG")
    sub = RealityCalibrationSubmission(
        subject_id="s1",
        answers=[RealityCalibrationYearAnswer(
            year=y0.year, occurred=[OccurredEvent(event_key=chosen, month=8)],
        )],
    )
    rows = rows_from_submission(
        sub, question, pillars_signature(chart),
        {(y0.year, 8, chosen): month_fp},
    )
    moved = next(r for r in rows if r.event_key == chosen)
    assert moved.period == f"{y0.year}-08"
    assert moved.outcome is LifeEventOutcome.CONFIRMED
    assert moved.signal_fingerprint.relation == "CHUNG"  # 월운 지문 사용


def test_occurred_month_falls_back_without_fingerprint(chart, question) -> None:
    # 월은 있으나 월운 지문이 없으면 연도 폴백(규칙11).
    y0 = next(y for y in question.years if y.events)
    chosen = y0.events[0].event_key
    sub = RealityCalibrationSubmission(
        subject_id="s1",
        answers=[RealityCalibrationYearAnswer(
            year=y0.year, occurred=[OccurredEvent(event_key=chosen, month=8)],
        )],
    )
    rows = rows_from_submission(sub, question, pillars_signature(chart))  # month_fp 없음
    moved = next(r for r in rows if r.event_key == chosen)
    assert moved.period == str(y0.year)  # 연도 폴백


def test_none_of_them_marks_all_not_happened(chart, question) -> None:
    y0 = next(y for y in question.years if y.events)
    sub = RealityCalibrationSubmission(
        subject_id="s1",
        answers=[RealityCalibrationYearAnswer(year=y0.year, none_of_them=True)],
    )
    rows = [r for r in rows_from_submission(sub, question, pillars_signature(chart))
            if r.period == str(y0.year)]
    assert rows and all(r.outcome is LifeEventOutcome.NOT_HAPPENED for r in rows)
