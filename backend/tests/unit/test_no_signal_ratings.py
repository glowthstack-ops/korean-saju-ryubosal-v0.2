"""CAL-QA — 무신호 응답(no_domain_activity/not_occurred) 데이터 위생 검증 (docs/14 §8).

불변식: 무신호 값은 delta 0·분모 제외·용신/기신 판정 불변이며, raw 응답에는 값
그대로(unknown과 혼합 금지) 남는다. 레거시 'na'는 기존대로 채점 제외 하위호환.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate, calibrate_feedback
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import (
    NO_DOMAIN_ACTIVITY,
    NOT_OCCURRED,
    FeedbackAnswer,
    experience_polarity,
    experience_volatility,
)

_BIRTH = BirthInput(
    reference_date="2026-07-03", calendar_type="solar", birth_date="1980-11-22",
    birth_time="09:40", birth_place_name="서울", gender="male",
)


def _answers(domain_extra: dict[str, str] | None = None,
             event_value: str | None = None) -> list[FeedbackAnswer]:
    """기본 긍정 응답 + (선택) 무신호 도메인/이벤트 응답을 섞는다."""
    r = calculate(_BIRTH)
    assert r.calibration is not None
    out = []
    for q in r.calibration.questions:
        if q.question_type in (
            "transition_probe", "trait_probe",
            "static_deficiency_probe", "transit_activation_probe",
        ):
            continue
        domain_ratings = {"career": "positive"}
        if domain_extra:
            domain_ratings.update(domain_extra)
        event_ratings = {}
        if event_value and q.events:
            event_ratings[q.events[0].event_key] = event_value
        out.append(FeedbackAnswer(
            question_id=q.id, overall_rating="positive",
            domain_ratings=domain_ratings, event_ratings=event_ratings,
        ))
    return out


def test_no_domain_activity_creates_no_delta() -> None:
    """(1) no_domain_activity 도메인 응답은 model_scores에 delta를 만들지 않는다."""
    base = calibrate_feedback(_BIRTH, _answers())
    with_ns = calibrate_feedback(
        _BIRTH, _answers(domain_extra={"money": NO_DOMAIN_ACTIVITY}),
    )
    assert base.model_scores == with_ns.model_scores
    assert base.selected_model == with_ns.selected_model
    assert base.final_yongsin == with_ns.final_yongsin


def test_no_domain_activity_excluded_from_denominator() -> None:
    """(2) no_domain_activity는 분모(evidence/match_rate)에 들어가지 않는다."""
    base = calibrate_feedback(_BIRTH, _answers())
    with_ns = calibrate_feedback(
        _BIRTH, _answers(domain_extra={"money": NO_DOMAIN_ACTIVITY}),
    )
    assert base.evidence_count == with_ns.evidence_count
    assert base.match_rate == with_ns.match_rate
    # 극성/변동성 매핑 자체도 제외값이다.
    assert experience_polarity(NO_DOMAIN_ACTIVITY) is None
    assert experience_volatility(NO_DOMAIN_ACTIVITY) == 0.0


def test_no_signal_values_stored_distinct_from_unknown() -> None:
    """(3) unknown과 무신호 값이 서로 다른 값으로 응답에 남는다(혼합 금지)."""
    ans = FeedbackAnswer.model_validate({
        "question_id": "q1", "overall_rating": "unknown", "selected_events": [],
        "domain_ratings": {"career": NO_DOMAIN_ACTIVITY, "money": "unknown"},
        "event_ratings": {"job_change": NOT_OCCURRED, "promotion": "unknown"},
    })
    dumped = ans.model_dump()
    assert dumped["domain_ratings"]["career"] == "no_domain_activity"
    assert dumped["domain_ratings"]["career"] != dumped["domain_ratings"]["money"]
    assert dumped["event_ratings"]["job_change"] == "not_occurred"
    assert dumped["event_ratings"]["job_change"] != dumped["event_ratings"]["promotion"]


def test_not_occurred_not_scored_for_yongsin() -> None:
    """(4) not_occurred 이벤트 응답은 용신 채점에 반영되지 않는다(발생≠용신 판별 축)."""
    base = calibrate_feedback(_BIRTH, _answers())
    with_no = calibrate_feedback(_BIRTH, _answers(event_value=NOT_OCCURRED))
    assert base.model_scores == with_no.model_scores
    assert base.selected_model == with_no.selected_model
    assert base.final_yongsin == with_no.final_yongsin
    assert base.evidence_count == with_no.evidence_count
    assert experience_polarity(NOT_OCCURRED) is None


def test_not_occurred_survives_in_raw_answer_record() -> None:
    """(5) not_occurred가 raw 응답(blob 저장 원본)에 그대로 남는다 — accumulate_only."""
    answers = _answers(event_value=NOT_OCCURRED)
    with_events = [a for a in answers if a.event_ratings]
    assert with_events, "이벤트형 응답 없음"
    for a in with_events:
        assert NOT_OCCURRED in a.event_ratings.values()
    # 채점 경로를 거쳐도 응답 원본은 변형되지 않는다(스코어러는 읽기 전용).
    calibrate_feedback(_BIRTH, answers)
    for a in with_events:
        assert NOT_OCCURRED in a.event_ratings.values()


def test_legacy_na_still_excluded_backward_compatible() -> None:
    """(6) 레거시 'na'는 기존대로 채점 제외(unknown 계열)로 하위호환 처리된다."""
    assert experience_polarity("na") is None
    assert experience_volatility("na") == 0.0
    base = calibrate_feedback(_BIRTH, _answers())
    with_na = calibrate_feedback(_BIRTH, _answers(event_value="na"))
    assert base.model_scores == with_na.model_scores
    assert base.final_yongsin == with_na.final_yongsin
