"""용신 검증 루프: 기간 선택 · 질문 생성 · 피드백 점수화 · 판정."""

from __future__ import annotations

from saju_manse_calibration import score_calibration, score_feedback

from saju_api.services.manse_service import calculate, calibrate_feedback
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import (
    CalibrationEventItem,
    CalibrationQuestion,
    FeedbackAnswer,
)
from saju_shared_types.yongsin import AggregatedYongsinResult, YongsinCandidateModel

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
    # 기본 5종(q1~q5) + probe(CAL-P0 교운/성향 + CAL-P1 pair — 추가 문항 총합 ≤3).
    base_qs = [
        q for q in cal.questions
        if not q.id.startswith(("q_transition", "q_trait", "q_pair"))
    ]
    assert len(base_qs) == 5
    # 같은 연도를 중복 질문하지 않는다(성향 질문은 비시간형, pair B는 중복 penalty 허용).
    years = [
        q.year for q in cal.questions
        if q.period_type == "year" and not q.id.startswith("q_pair")
    ]
    assert len(years) == len(set(years))
    # 변별 연도(q1~q3)는 이벤트형(event_list)으로, q4·q5는 탐색형으로 생성된다.
    types = {q.question_type for q in cal.questions}
    assert "event_list" in types
    assert types <= {
        "event_list", "event_domain", "period_detail", "useful", "unfavorable", "contrast",
        "transition_probe", "trait_probe",
        "static_deficiency_probe", "transit_activation_probe",
    }
    # 이벤트형 질문은 그 해의 이벤트와 모델별 기대 극성을 싣는다.
    event_qs = [q for q in cal.questions if q.question_type == "event_list"]
    assert event_qs
    for q in event_qs:
        assert q.events
        for e in q.events:
            assert e.category and e.expected_by_model


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
        FeedbackAnswer(question_id=q.id, overall_rating="positive", selected_events=["직업"])
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
        FeedbackAnswer(question_id=q.id, overall_rating="positive", selected_events=["직업"])
        for q in r.calibration.questions
    ]
    res = calibrate_feedback(b, answers)
    assert r.yongsin_analysis is not None
    primary = {m.model_type for m in r.yongsin_analysis.candidate_models if not m.is_auxiliary}
    assert res.selected_model != "johu"  # 보조 모델 단독 확정 금지
    assert res.selected_model in primary  # primary 모델로 확정


def test_final_selected_auxiliary_model_can_be_calibrated() -> None:
    y = AggregatedYongsinResult(
        status="candidate",
        candidate_models=[
            YongsinCandidateModel(
                model_type="eokbu_normal", label="억부형",
                yongsin="水", heesin="木", gisin="土", gusin="金",
                confidence=0.6,
            ),
            YongsinCandidateModel(
                model_type="johu", label="조후 보조형",
                yongsin="火", heesin="木", gisin="金", gusin="土",
                confidence=0.8, is_auxiliary=True,
            ),
        ],
        final={"selected_model": "johu", "yongsin": "火", "heesin": "木"},
    )
    questions = [
        CalibrationQuestion(
            id=f"q{i}", question_type="useful", period_type="year",
            year=2000 + i, period_label=str(2000 + i),
            target_models=["johu"],
            expected_effect_by_model={"johu": "positive", "eokbu_normal": "negative"},
            ask_domains=["career"], question_text="test", options=[],
        )
        for i in range(4)
    ]
    answers = [
        FeedbackAnswer(question_id=q.id, overall_rating="positive", selected_events=["직업"])
        for q in questions
    ]
    res = score_calibration(questions, answers, y)
    assert res.status == "calibrated"
    assert res.selected_model == "johu"
    assert res.final_yongsin == "火"


def test_event_ratings_select_matching_model() -> None:
    # 이벤트별 긍/부정 응답이 모델별 기대 극성과 대조돼 일치 모델이 선택된다.
    y = AggregatedYongsinResult(
        status="candidate",
        candidate_models=[
            YongsinCandidateModel(
                model_type="eokbu_normal", label="억부형",
                yongsin="水", heesin="木", gisin="土", gusin="金", confidence=0.7,
            ),
            YongsinCandidateModel(
                model_type="eokbu_alt", label="대안형",
                yongsin="火", heesin="土", gisin="水", gusin="木", confidence=0.6,
            ),
        ],
        final={"selected_model": "eokbu_normal", "yongsin": "水", "heesin": "木"},
    )
    cats = ["career", "move", "affection", "money"]
    events = [
        CalibrationEventItem(
            event_key=f"e{i}", category=cats[i], label=f"이벤트{i}",
            # eokbu_normal=positive, eokbu_alt=negative.
            expected_by_model={"eokbu_normal": "positive", "eokbu_alt": "negative"},
        )
        for i in range(4)
    ]
    q = CalibrationQuestion(
        id="q1", question_type="event_list", period_type="year",
        year=2015, period_label="2015", target_models=["eokbu_normal", "eokbu_alt"],
        question_text="…", events=events,
    )
    # 사용자가 모든 이벤트를 '긍정'으로 답함 → eokbu_normal(positive 기대)과 일치.
    ans = FeedbackAnswer(question_id="q1", event_ratings={f"e{i}": "positive" for i in range(4)})
    res = score_calibration([q], [ans], y)
    assert res.selected_model == "eokbu_normal"
    assert res.final_yongsin == "水"
    assert res.evidence_count == 4
    assert res.match_rate == 1.0


def test_domain_ratings_drive_model_selection_and_no_signal_excluded() -> None:
    # docs/14 P1 — 영역별 체감이 모델 도메인 기대와 대조돼 일치 모델 선택. 신호 없는 도메인 제외.
    from saju_manse_calibration.question_generator import build_domain_expectations

    y = AggregatedYongsinResult(
        status="candidate",
        candidate_models=[
            YongsinCandidateModel(
                model_type="eokbu_normal", label="억부형",
                yongsin="水", heesin="木", gisin="土", gusin="金", confidence=0.7,
            ),
            YongsinCandidateModel(
                model_type="eokbu_alt", label="대안형",
                yongsin="火", heesin="土", gisin="水", gusin="木", confidence=0.6,
            ),
        ],
        final={"selected_model": "eokbu_normal", "yongsin": "水", "heesin": "木"},
    )
    # 4개 캘리 도메인(career/money/relationship/health) 각각 1개 이벤트.
    cat_by_domain = {"career": "career", "money": "money", "relationship": "affection",
                     "health": "health"}
    events = [
        CalibrationEventItem(
            event_key=f"e_{dom}", category=cat, label=dom,
            expected_by_model={"eokbu_normal": "positive", "eokbu_alt": "negative"},
        )
        for dom, cat in cat_by_domain.items()
    ]
    de = build_domain_expectations(events)
    assert de["eokbu_normal"]["career"].status == "scored"
    polarity = de["eokbu_normal"]["career"].expected_polarity
    assert polarity is not None and polarity > 0

    q = CalibrationQuestion(
        id="q1", question_type="event_list", period_type="year", year=2015,
        period_label="2015", target_models=["eokbu_normal", "eokbu_alt"],
        question_text="…", events=events, domain_expectations=de,
    )
    # 사용자가 4영역 모두 '좋음' + 신호 없는 도메인(study)은 무시돼야 한다.
    ans = FeedbackAnswer(
        question_id="q1",
        domain_ratings={"career": "positive", "money": "positive",
                        "relationship": "positive", "health": "positive"},
    )
    res = score_calibration([q], [ans], y)
    assert res.selected_model == "eokbu_normal"  # positive 기대 모델과 일치
    assert res.evidence_count == 4  # 4도메인만(no_signal/부재 도메인 제외)
    assert res.final_yongsin == "水"


def test_mixed_domain_rating_counts_as_volatility_not_polarity() -> None:
    # 'mixed'(반반)은 극성 0이지만 변동성 신호 — neutral(무던)과 구분.
    from saju_shared_types.calibration import experience_polarity, experience_volatility

    assert experience_polarity("mixed") == 0.0 and experience_volatility("mixed") == 1.0
    assert experience_polarity("neutral") == 0.0 and experience_volatility("neutral") == 0.0
    assert experience_polarity("very_positive") == 2.0
    assert experience_polarity("모름" and "unknown") is None


def test_event_rating_na_is_excluded() -> None:
    y = AggregatedYongsinResult(
        status="candidate",
        candidate_models=[
            YongsinCandidateModel(
                model_type="m", label="m", yongsin="水", gisin="土", confidence=0.7,
            ),
        ],
        final={"selected_model": "m", "yongsin": "水"},
    )
    events = [
        CalibrationEventItem(
            event_key="e0", category="career", label="x",
            expected_by_model={"m": "positive"},
        ),
    ]
    q = CalibrationQuestion(
        id="q1", question_type="event_list", period_type="year",
        year=2015, period_label="2015", question_text="…", events=events,
    )
    ans = FeedbackAnswer(question_id="q1", event_ratings={"e0": "na"})
    res = score_calibration([q], [ans], y)
    assert res.status == "uncertain"  # 유효 근거 0


def test_period_selection_reflects_void_clash() -> None:
    # 운 동태가 검증 기간에 반영: 공망=실속 약화(mixed), 충=사건성(volatile).
    from saju_manse_calibration import select_validation_periods
    from saju_manse_calibration.period_selector import _apply_dynamics

    assert _apply_dynamics("positive", True, False) == "mixed"  # 공망
    assert _apply_dynamics("negative", False, True) == "volatile"  # 충
    assert _apply_dynamics("positive", True, True) == "volatile"  # 공망+충
    assert _apply_dynamics("neutral", True, True) == "neutral"  # 중립은 불변
    # 1980 공망 辰巳 → 세운 지지가 辰/巳인 해는 is_void로 표시.
    r = calculate(BirthInput(reference_date="2015-06-15", **_BASE))
    assert r.yongsin_analysis is not None
    periods = select_validation_periods(r.yongsin_analysis, 1980, 2015, r.pillars)
    voids = [p for p in periods if p["is_void"]]
    assert voids and all(p["ganji"][1] in ("辰", "巳") for p in voids)
    # 깨끗한 해(공망·충 없음)가 검증 우선순위 상위에 온다.
    assert any(p["clean"] for p in periods[:3])


def test_period_selection_keeps_multiple_disease_models_distinct() -> None:
    from saju_manse_calibration import select_validation_periods

    b = BirthInput(
        birth_date="1985-04-18",
        birth_time="16:00",
        birth_place_name="경남 사천",
        latitude=35.0497,
        longitude=128.0377,
        timezone="Asia/Seoul",
        gender="male",
        reference_date="2026-06-11",
        time_options={"apply_equation_of_time": False},
    )
    r = calculate(b)
    assert r.yongsin_analysis is not None
    periods = select_validation_periods(r.yongsin_analysis, 1985, 2026, r.pillars)
    keys = set(periods[0]["expected_by_model"])
    assert "disease_remedy:shangguan_attacks_officer" in keys
    assert "disease_remedy:pyeonin_dosik" in keys
