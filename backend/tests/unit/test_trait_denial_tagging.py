"""CAL-P1 P1-a — trait_denial_kind 룰 태깅 + 스키마 호환 검증.

doc/v2_2/CALIBRATION_STATIC_TRANSIT_PROBES.md §4·§6-1. 태깅은 채점 절대 비반영 —
review 축적·LLM 표현 힌트 전용(§5 불변식은 test_calibration_probes가 함께 고정).
"""

from __future__ import annotations

from saju_manse_calibration import (
    classify_trait_denial_kind,
    generate_questions,
    score_calibration,
    select_validation_periods,
)

from saju_api.services.manse_service import _trait_probe_candidates, calculate
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import (
    TRAIT_DENIAL_KINDS,
    DeficiencyPairFeedback,
    FeedbackAnswer,
)


def test_situational_statements() -> None:
    """특정 상황 한정 표지 → situational."""
    assert classify_trait_denial_kind("글로는 괜찮은데 면접에서는 말을 못해요") == "situational"
    assert classify_trait_denial_kind("사람들 앞에서 발표할 때만 얼어붙어요") == "situational"


def test_temporal_statements() -> None:
    """시기 변화 표지 → temporal."""
    assert classify_trait_denial_kind("예전에는 못했는데 요즘은 좀 나아졌어요") == "temporal"
    assert classify_trait_denial_kind("어릴 때는 그랬는데 지금은 아니에요") == "temporal"


def test_absolute_statements() -> None:
    """강부정 표지(상황·시기 표지 없음) → absolute."""
    assert classify_trait_denial_kind("저는 외로움을 전혀 못 느껴요") == "absolute"
    assert classify_trait_denial_kind("아예 그런 성격이 아니에요") == "absolute"


def test_mixed_when_both_situational_and_temporal() -> None:
    """상황+시기 표지가 함께 있으면 mixed(우선순위 확정 규칙)."""
    assert (
        classify_trait_denial_kind("평소엔 괜찮은데 예전 면접에서는 너무 힘들었어요")
        == "mixed"
    )


def test_unclear_and_empty() -> None:
    """표지가 없으면 unclear, 빈 진술은 None(정보 없음 ≠ 분류 실패)."""
    assert classify_trait_denial_kind("그냥 그런 것 같기도 해요") == "unclear"
    assert classify_trait_denial_kind("") is None
    assert classify_trait_denial_kind("   ") is None
    assert classify_trait_denial_kind(None) is None


def test_all_kinds_are_registered() -> None:
    """분류 결과값이 TRAIT_DENIAL_KINDS 등록값 안에 있다."""
    for stmt in ("면접에서는", "요즘은", "전혀", "모르겠어요"):
        kind = classify_trait_denial_kind(stmt)
        assert kind in TRAIT_DENIAL_KINDS


def test_denial_kind_flows_into_trait_feedback() -> None:
    """채점 경로에서 trait 축적 레코드에 denial_kind가 실린다.

    trait_probe가 살아있는 구성(pair·transition off — 전체 E2E에서는 cap 우선순위로
    trait가 drop됨, CAL-P1-b §1-C)으로 score_calibration을 직접 검증한다.
    """
    b = BirthInput(
        reference_date="2026-07-03", calendar_type="solar", birth_date="1980-11-22",
        birth_time="09:40", birth_place_name="서울", gender="male",
    )
    r = calculate(b)
    assert r.yongsin_analysis is not None and r.pillars is not None
    periods = select_validation_periods(
        r.yongsin_analysis, 1980, 2026, pillars=r.pillars,
    )
    qs = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        trait_candidates=_trait_probe_candidates(r), max_transition_probes=0,
    )
    answers = []
    for q in qs.questions:
        if q.question_type == "trait_probe":
            answers.append(FeedbackAnswer(
                question_id=q.id, trait_response="denied",
                trait_statement="글로는 괜찮은데 면접에서는 말을 못해요",
            ))
        elif q.question_type != "transition_probe":
            answers.append(FeedbackAnswer(question_id=q.id, overall_rating="positive"))
    res = score_calibration(qs.questions, answers, r.yongsin_analysis)
    fb = res.trait_probe_feedback[0]
    assert fb.denial_kind == "situational"
    assert fb.scoring_effect == "none"
    # 진술 없는 응답은 denial_kind None.
    answers2 = [
        a.model_copy(update={"trait_statement": None}) if a.trait_response else a
        for a in answers
    ]
    res2 = score_calibration(qs.questions, answers2, r.yongsin_analysis)
    assert res2.trait_probe_feedback[0].denial_kind is None
    # 태깅은 판정 비개입 — 진술 유무와 무관하게 용신 확정 동일.
    assert res.final_yongsin == res2.final_yongsin
    assert res.model_scores == res2.model_scores


def test_deficiency_pair_feedback_schema_defaults() -> None:
    """P1-a 스키마 — pair 레코드 기본값(scoring_effect=none, accumulate_only) 고정."""
    fb = DeficiencyPairFeedback(
        pair_id="pair_wood_officer", axis_type="element", axis_id="wood",
        engine_basis=["木 부재", "관성 표면 부재"],
        static_response="agreed", transit_year=2016, transit_response="strong",
    )
    assert fb.type == "deficiency_pair_feedback"
    assert fb.scoring_effect == "none"
    assert fb.review_status == "accumulate_only"
    assert fb.static_denial_kind is None


def test_feedback_answer_accepts_transit_fields() -> None:
    """FeedbackAnswer가 transit 응답 필드를 하위호환으로 수용한다(P1-a 스키마)."""
    a = FeedbackAnswer.model_validate({
        "question_id": "q_pair_b", "overall_rating": "unknown", "selected_events": [],
        "transit_response": "partial", "transit_statement": "그 해 이직 고민이 있었어요",
    })
    assert a.transit_response == "partial"
    # 기존 payload(신규 필드 없음)도 그대로 통과.
    legacy = FeedbackAnswer.model_validate(
        {"question_id": "q1", "overall_rating": "positive", "selected_events": []}
    )
    assert legacy.transit_response is None
