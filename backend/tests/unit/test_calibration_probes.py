"""CAL-P0 — 교운기 우선 배치(transition_probe) + 성향 수집(trait_probe) 검증.

상담 사례 파생(doc/v2_2/cases/1980_1122_job_report_case.md §7, 2026-07-03 데굴님 확정).
불변식: 점수·용신 role·favorability·세운/월운 산출 불변 — probe는 질문 후보 순서와
질문 문구, 축적 레코드에만 관여한다.
"""

from __future__ import annotations

from saju_manse_calibration import (
    generate_questions,
    score_calibration,
    select_validation_periods,
)

from saju_api.services.manse_service import (
    _trait_probe_candidates,
    calculate,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import FeedbackAnswer

# 사례 명식 — 교운 연도 1985/1995/2005/2015/2025…, 현침 보유(trait 후보 1순위).
_BASE = dict(
    birth_date="1980-11-22", birth_time="09:40", birth_place_name="서울", gender="male",
)


def _calibration(reference_date: str = "2026-07-03"):
    r = calculate(BirthInput(reference_date=reference_date, **_BASE))
    assert r.calibration is not None
    return r, r.calibration


# ── 교운기 우선 배치(transition_probe) ──────────────────────────────


def test_transition_probe_present_and_anchored_to_transition_window() -> None:
    """교운기 후보가 질문에 포함되고 교체 연도 ±1년 창에 앵커된다(필수 회귀)."""
    _r, cal = _calibration()
    probes = [q for q in cal.questions if q.question_type == "transition_probe"]
    assert probes, "transition_probe 미생성"
    transition_years = {1985, 1995, 2005, 2015, 2025}
    assert any(abs(probes[0].year - t) <= 1 for t in transition_years)
    # 회상형 문구 — 사건 단정 금지(CAL-P0 금지 조항).
    assert "교운기" in probes[0].question_text
    assert "있었나요" in probes[0].question_text


def test_transition_boost_only_near_transition_years() -> None:
    """교운기 ±3년 밖 연도는 boost 0, 창 안 연도만 transition_weight>0."""
    r, _cal = _calibration()
    assert r.yongsin_analysis is not None and r.pillars is not None
    periods = select_validation_periods(
        r.yongsin_analysis, 1980, 2026, pillars=r.pillars,
        transition_years=[2015],
    )
    by_year = {p["year"]: p for p in periods}
    assert by_year[2015]["transition_weight"] == 1.0
    assert by_year[2014]["transition_weight"] == 0.368
    assert by_year[2018]["transition_weight"] == 0.05
    assert by_year[2020]["transition_weight"] == 0.0  # ±3년 밖 — boost 없음


def test_transition_probe_capped_at_one() -> None:
    """교운기가 여러 번이어도 transition_probe는 최대 1개(cap — 쏠림 방지)."""
    _r, cal = _calibration()
    probes = [q for q in cal.questions if q.question_type == "transition_probe"]
    assert len(probes) <= 1


def test_base_question_types_preserved_and_engine_unchanged() -> None:
    """기존 q1~q5가 유지되고 용신 role·이벤트 기대 등 엔진 판정이 불변이다."""
    r, cal = _calibration()
    base_ids = {
        q.id for q in cal.questions
        if not q.id.startswith(("q_transition", "q_trait", "q_pair"))
    }
    assert base_ids == {"q1", "q2", "q3", "q4", "q5"}
    # 엔진 판정 불변 — 용신 role은 사례 fixture와 동일(boost는 ranking 전용).
    assert r.yongsin_analysis is not None
    roles = r.yongsin_analysis.canonical_roles
    assert roles["yongsin"] == "土" and roles["heesin"] == "火"
    # boost가 expected_by_model(모델 기대 극성)을 바꾸지 않는다.
    assert r.pillars is not None
    with_boost = select_validation_periods(
        r.yongsin_analysis, 1980, 2026, pillars=r.pillars, transition_years=[2015],
    )
    without_boost = select_validation_periods(
        r.yongsin_analysis, 1980, 2026, pillars=r.pillars,
    )
    exp_with = {p["year"]: p["expected_by_model"] for p in with_boost}
    exp_without = {p["year"]: p["expected_by_model"] for p in without_boost}
    assert exp_with == exp_without


def test_transition_probe_does_not_starve_base_questions() -> None:
    """probe가 기본 질문의 유일 후보 해를 선점하지 않는다(QA-P0 F2 회귀).

    1975-03-08 04:30 남성: 갈림(disagree) 해가 2020 하나뿐 — 기본 질문 구성(id, year)이
    probe 유무와 동일해야 하고, probe는 남은 연도에서 골라 표시 순서 맨 앞에 온다.
    """
    b = BirthInput(
        reference_date="2026-07-03", calendar_type="solar", birth_date="1975-03-08",
        birth_time="04:30", birth_place_name="서울", gender="male",
    )
    r = calculate(b)
    assert r.yongsin_analysis is not None and r.pillars is not None
    assert r.luck_cycles is not None
    transitions = [d.approx_start_date.year for d in r.luck_cycles.daewoon_table]
    periods = select_validation_periods(
        r.yongsin_analysis, 1975, 2026, pillars=r.pillars, transition_years=transitions,
    )
    with_probe = generate_questions(periods, r.yongsin_analysis, gender="male")
    without_probe = generate_questions(
        periods, r.yongsin_analysis, gender="male", max_transition_probes=0,
    )

    def base(qs) -> set[tuple[str, int]]:
        return {
            (q.id, q.year) for q in qs.questions
            if not q.id.startswith(("q_transition", "q_trait", "q_pair"))
        }

    assert base(with_probe) == base(without_probe)
    assert with_probe.questions[0].question_type == "transition_probe"
    probe_year = with_probe.questions[0].year
    assert probe_year not in {y for _, y in base(with_probe)}


# ── 성향 수집(trait_probe) ──────────────────────────────────────────
# CAL-P1-b 이후 이 명식의 전체 E2E에서는 cap 우선순위(transition 1 + pair 2 = 3)에 따라
# trait_probe가 의도적으로 drop된다(§1-C — test_deficiency_pair_probes가 고정). trait
# 왕복 자체는 pair·transition을 끈 질문 구성 + score_calibration 직접 경로로 검증한다.


def _trait_setup():
    """trait_probe가 살아있는 질문 구성(pair·transition off) + 용신."""
    r = calculate(BirthInput(reference_date="2026-07-03", **_BASE))
    assert r.yongsin_analysis is not None and r.pillars is not None
    periods = select_validation_periods(
        r.yongsin_analysis, 1980, 2026, pillars=r.pillars,
    )
    qs = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        trait_candidates=_trait_probe_candidates(r),
        max_transition_probes=0,
    )
    return r, qs


def _answers_with_trait(qs, trait_response: str | None, statement: str | None = None):
    """q1~q5는 긍정 응답, trait 질문엔 지정 응답을 싣는다."""
    answers = []
    for q in qs.questions:
        if q.question_type == "trait_probe":
            answers.append(FeedbackAnswer(
                question_id=q.id, trait_response=trait_response,
                trait_statement=statement,
            ))
        elif q.question_type == "transition_probe":
            continue  # 미응답 — 채점 무관 확인용
        else:
            answers.append(FeedbackAnswer(question_id=q.id, overall_rating="positive"))
    return answers


def test_trait_probe_generated_from_engine_basis() -> None:
    """현침 보유 명식에서 trait_probe(communication_style)가 생성된다."""
    _r, qs = _trait_setup()
    traits = [q for q in qs.questions if q.question_type == "trait_probe"]
    assert len(traits) == 1  # cap 1
    q = traits[0]
    assert q.trait_target == "communication_style"
    assert q.engine_basis == ["현침"]
    assert q.options == ["대체로 그렇다", "상황에 따라 다르다", "그렇지 않다", "잘 모르겠다"]


def test_trait_feedback_agreed_and_denied_accumulated() -> None:
    """동의/반박 응답이 accumulate_only 레코드로 저장된다(필수 회귀)."""
    r, qs = _trait_setup()
    for resp in ("agreed", "denied"):
        res = score_calibration(
            qs.questions,
            _answers_with_trait(qs, resp, "면접에서 말을 잘 못한다"),
            r.yongsin_analysis,
        )
        assert len(res.trait_probe_feedback) == 1
        fb = res.trait_probe_feedback[0]
        assert fb.user_feedback == resp
        assert fb.scoring_effect == "none"
        assert fb.review_status == "accumulate_only"
        assert fb.engine_basis == ["현침"]


def test_trait_feedback_unclear_when_missing_or_unknown() -> None:
    """응답이 없거나 알 수 없는 값이면 unclear로 처리된다."""
    r, qs = _trait_setup()
    res = score_calibration(
        qs.questions, _answers_with_trait(qs, None), r.yongsin_analysis,
    )
    assert res.trait_probe_feedback[0].user_feedback == "unclear"
    res2 = score_calibration(
        qs.questions, _answers_with_trait(qs, "whatever"), r.yongsin_analysis,
    )
    assert res2.trait_probe_feedback[0].user_feedback == "unclear"


def test_trait_probe_never_changes_yongsin_decision() -> None:
    """trait 반박이 있어도 모델 점수·선택·용신 확정이 동일하다(override 금지)."""
    r, qs = _trait_setup()
    # trait 응답 없는 답안(성향 질문 미포함)과 denied 답안을 대조.
    base_answers = [
        FeedbackAnswer(question_id=q.id, overall_rating="positive")
        for q in qs.questions
        if q.question_type not in ("trait_probe", "transition_probe")
    ]
    res_base = score_calibration(qs.questions, base_answers, r.yongsin_analysis)
    res_denied = score_calibration(
        qs.questions, _answers_with_trait(qs, "denied"), r.yongsin_analysis,
    )
    assert res_base.model_scores == res_denied.model_scores
    assert res_base.selected_model == res_denied.selected_model
    assert res_base.final_yongsin == res_denied.final_yongsin


def test_trait_denied_emits_expression_hint_only() -> None:
    """반박 시 LLM 힌트는 '단정 회피·표현 조정'만 지시하고 판정 변경을 금지한다."""
    r, qs = _trait_setup()
    res = score_calibration(
        qs.questions,
        _answers_with_trait(qs, "denied", "면접에서 말을 잘 못한다"),
        r.yongsin_analysis,
    )
    assert len(res.trait_llm_hints) == 1
    hint = res.trait_llm_hints[0]
    assert "단정 서술하지 말고" in hint
    assert "엔진 판정은 변경하지 않는다" in hint
    assert "면접에서 말을 잘 못한다" in hint
    # 동의(agreed)면 힌트 없음.
    res_agreed = score_calibration(
        qs.questions, _answers_with_trait(qs, "agreed"), r.yongsin_analysis,
    )
    assert res_agreed.trait_llm_hints == []
