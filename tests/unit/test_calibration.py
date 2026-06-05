"""용신 검증 루프: 기간 선택 · 질문 생성 · 피드백 점수화 · 판정."""

from __future__ import annotations

from saju_manse_calibration import score_feedback

from saju_api.services.manse_service import calculate, calibrate_feedback
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import FeedbackAnswer

_BASE = dict(birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울", gender="male")


def test_score_feedback_rules() -> None:
    assert score_feedback("positive", 2) == 2
    assert score_feedback("negative", 2) == -2
    assert score_feedback("mixed", 2) == 1.0
    assert score_feedback("neutral", 2) == 0.0
    assert score_feedback("positive", None) == 0.0  # 기억나지 않음 제외


def test_calibration_generated_with_reference_date() -> None:
    r = calculate(BirthInput(reference_date="2015-06-15", **_BASE))
    cal = r.calibration
    assert cal is not None
    assert cal.status == "required"
    assert len(cal.questions) == 5
    # 같은 연도를 중복 질문하지 않는다.
    years = [q.year for q in cal.questions]
    assert len(years) == len(set(years))
    # 질문 유형 5종이 모두 포함된다.
    assert {q.question_type for q in cal.questions} == {
        "useful", "unfavorable", "contrast", "event_domain", "period_detail",
    }


def test_calibration_absent_without_reference_date() -> None:
    r = calculate(BirthInput(**_BASE))
    assert r.calibration is None


def test_feedback_unknown_excluded_yields_uncertain() -> None:
    b = BirthInput(reference_date="2015-06-15", **_BASE)
    r = calculate(b)
    assert r.calibration is not None
    # 모두 '기억나지 않음' → 유효 근거 없음 → uncertain.
    answers = [
        FeedbackAnswer(question_id=q.id, overall_rating="unknown")
        for q in r.calibration.questions
    ]
    res = calibrate_feedback(b, answers)
    assert res.status == "uncertain"
    assert res.evidence_count == 0


def test_feedback_scores_models_and_decides() -> None:
    b = BirthInput(reference_date="2015-06-15", **_BASE)
    r = calculate(b)
    assert r.calibration is not None
    answers = [
        FeedbackAnswer(question_id=q.id, overall_rating="positive", selected_events=["취업"])
        for q in r.calibration.questions
    ]
    res = calibrate_feedback(b, answers)
    assert res.status in ("calibrated", "probable", "uncertain")
    assert res.evidence_count >= 1
    assert res.selected_model in res.model_scores
    if res.status != "uncertain":
        assert res.final_yongsin is not None


def test_auxiliary_johu_cannot_be_solely_calibrated() -> None:
    # 조후(보조 모델)는 raw 점수가 가장 높아도 단독 확정 금지 → primary 모델이 선택돼야.
    b = BirthInput(reference_date="2015-06-15", **_BASE)
    r = calculate(b)
    assert r.calibration is not None
    answers = [
        FeedbackAnswer(question_id=q.id, overall_rating="positive", selected_events=["취업"])
        for q in r.calibration.questions
    ]
    res = calibrate_feedback(b, answers)
    assert res.selected_model != "johu"
    assert res.selected_model == "support_day_master"
    assert res.final_yongsin == "土"  # primary 부일간형 기준 (조후 火 아님)
