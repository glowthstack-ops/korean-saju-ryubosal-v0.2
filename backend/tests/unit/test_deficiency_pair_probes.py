"""CAL-P1-b — 이원 질문 쌍(A/B) 생성·B 앵커 랭킹·suppress·cap·불변식 검증.

doc/v2_2/CALIBRATION_STATIC_TRANSIT_PROBES.md §1-B·1-C·2·7(기준 1~13 중 P1-b 10종).
불변식: pair 응답은 어떤 값이어도 model_scores·selected_model·final_yongsin 불변,
기본 q1~q5는 probe 미주입(cap 0) 기준선과 동일.
"""

from __future__ import annotations

from saju_manse_calibration import generate_questions, select_validation_periods
from saju_manse_calibration.question_generator import _select_pair_anchor

from saju_api.services.manse_service import (
    _deficiency_pair_candidates,
    calculate,
    calibrate_feedback,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import (
    DeficiencyPairCandidate,
    FeedbackAnswer,
    TraitProbeCandidate,
)

# 사례 명식 — 木 표면 부재 + 관성 표면 부재(병합 축), 현침 보유.
_BIRTH = BirthInput(
    reference_date="2026-07-03", calendar_type="solar", birth_date="1980-11-22",
    birth_time="09:40", birth_place_name="서울", gender="male",
)

_WOOD_PAIR = DeficiencyPairCandidate(
    axis_type="ten_god_group", axis_id="officer", axis_element="木",
    engine_basis=["木 표면 부재", "관성 표면 부재"],
    static_question_text="평소에 기준·규칙·소속을 스스로 잡기 어렵다고 느낀 적이 있나요?",
    transit_question_text="직장, 책임, 규칙, 소속, 평가 압박이 실제로 강해졌나요?",
    suppress_axis_keys=["officer", "wood"],
)


def _period(year: int, stem_el: str, branch_el: str, clean: bool = True) -> dict:
    """synthetic 검증 기간 — B 앵커 랭킹 단위 테스트용 최소 필드."""
    return {
        "year": year, "stem_element": stem_el, "branch_element": branch_el,
        "clean": clean, "score": 1.0, "range_label": "", "disagree": False,
        "expected_by_model": {}, "transition_weight": 0.0,
        "activated_elements": sorted({stem_el, branch_el}),
        "age": year - 1980, "ganji": None,
    }


def _real_setup():
    r = calculate(_BIRTH)
    assert r.yongsin_analysis is not None and r.pillars is not None
    assert r.luck_cycles is not None
    transitions = [d.approx_start_date.year for d in r.luck_cycles.daewoon_table]
    periods = select_validation_periods(
        r.yongsin_analysis, 1980, 2026, pillars=r.pillars, transition_years=transitions,
    )
    return r, periods


# ── 1·2. pair 성립 조건 ──────────────────────────────────────────


def test_no_anchor_means_no_pair_and_no_lone_static() -> None:
    """B 앵커 해가 없으면 A/B 쌍 전체 미생성 — A 단독 생성 금지(기준 1·2)."""
    r, periods = _real_setup()
    no_wood = [p for p in periods if "木" not in p["activated_elements"]]
    qs = generate_questions(
        no_wood, r.yongsin_analysis, gender="male",
        pair_candidates=[_WOOD_PAIR], max_transition_probes=0,
    )
    types = {q.question_type for q in qs.questions}
    assert "static_deficiency_probe" not in types
    assert "transit_activation_probe" not in types


def test_pair_capped_at_one() -> None:
    """후보 축이 여러 개여도 pair는 최대 1쌍(기준 3)."""
    r, periods = _real_setup()
    second = _WOOD_PAIR.model_copy(update={"axis_id": "wealth", "axis_element": "水"})
    qs = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        pair_candidates=[_WOOD_PAIR, second], max_transition_probes=0,
    )
    pair_qs = [q for q in qs.questions if q.pair_id]
    assert len(pair_qs) == 2  # A+B 한 쌍
    assert {q.axis_id for q in pair_qs} == {"officer"}


# ── 4~6. cap·suppress ───────────────────────────────────────────


def test_total_probe_cap_three_prefers_pair_over_trait() -> None:
    """E2E — transition 1 + pair 2 = cap 3 도달 시 trait_probe drop(기준 4)."""
    r = calculate(_BIRTH)
    assert r.calibration is not None
    probes = [
        q for q in r.calibration.questions
        if q.question_type in (
            "transition_probe", "trait_probe",
            "static_deficiency_probe", "transit_activation_probe",
        )
    ]
    assert len(probes) <= 3
    types = [q.question_type for q in probes]
    assert types.count("transition_probe") == 1
    assert types.count("static_deficiency_probe") == 1
    assert types.count("transit_activation_probe") == 1
    assert "trait_probe" not in types  # cap 도달 — pair 우선(§1-C)


def test_same_axis_trait_probe_suppressed_even_with_budget() -> None:
    """pair가 생성된 axis의 trait_probe는 cap 여유가 있어도 suppress(기준 5)."""
    r, periods = _real_setup()
    officer_trait = TraitProbeCandidate(
        target="decision_style", engine_basis=["관성 표면 부재"],
        question_text="규칙보다 흘러가는 대로 움직이는 편인가요?", axis_key="officer",
    )
    qs = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        trait_candidates=[officer_trait], pair_candidates=[_WOOD_PAIR],
        max_transition_probes=0, max_extra_probes=4,
    )
    assert not [q for q in qs.questions if q.question_type == "trait_probe"]


def test_different_axis_hyeonchim_trait_kept_with_budget() -> None:
    """P1 axis와 다른 현침 trait_probe는 cap 여유가 있을 때 유지(기준 6)."""
    r, periods = _real_setup()
    hyeonchim = TraitProbeCandidate(
        target="communication_style", engine_basis=["현침"],
        question_text="말·글 전달이 편한 편인가요?", axis_key=None,
    )
    qs = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        trait_candidates=[hyeonchim], pair_candidates=[_WOOD_PAIR],
        max_transition_probes=0,  # transition 없음 → pair 2 + trait 1 = 3
    )
    assert [q for q in qs.questions if q.question_type == "trait_probe"]


# ── 7·8. B 앵커 교운 회피·예외 문구 ─────────────────────────────


def test_anchor_avoids_transition_year_when_alternative_exists() -> None:
    """q_transition과 같은 해는 다른 후보가 있으면 회피(기준 7)."""
    periods = [
        _period(2023, "水", "木"),  # 축 활성(지지)
        _period(2025, "木", "火"),  # 축 활성(천간)이지만 교운 앵커와 동일
    ]
    anchor = _select_pair_anchor(
        periods, "木", base_years=set(), transition_year=2025, daewoon_years=set(),
    )
    assert anchor is not None and anchor["year"] == 2023


def test_sole_transition_overlap_generates_with_caution_note() -> None:
    """유일 후보가 q_transition과 겹치면 생성하되 교운 중첩 안내 문구 부착(기준 8)."""
    r, _ = _real_setup()
    periods = [_period(2025, "木", "火"), _period(2020, "金", "土")]  # 木 활성은 2025뿐
    qs = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        pair_candidates=[_WOOD_PAIR], max_transition_probes=0,
    )
    transit = next(
        q for q in qs.questions if q.question_type == "transit_activation_probe"
    )
    # transition_probe가 없으므로 문구 없음이 정상 — 직접 transition_year 주입 케이스:
    from saju_manse_calibration.question_generator import _make_pair_questions
    pair = _make_pair_questions(_WOOD_PAIR, periods[0], 2026, transition_year=2025)
    assert "대운 전환감도 함께 있었을 수 있어요" in pair[1].question_text
    assert transit.year == 2025  # 유일 후보 사용 자체는 허용


# ── 9·10. 기준선·채점 불변식 ────────────────────────────────────


def test_base_questions_identical_to_cap_zero_baseline() -> None:
    """기본 q1~q5 (id, year)가 probe 전부 끈 기준선과 동일(기준 9)."""
    r, periods = _real_setup()
    full = generate_questions(
        periods, r.yongsin_analysis, gender="male",
        trait_candidates=[TraitProbeCandidate(
            target="communication_style", engine_basis=["현침"], question_text="q",
        )],
        pair_candidates=_deficiency_pair_candidates(r),
    )
    baseline = generate_questions(
        periods, r.yongsin_analysis, gender="male", max_extra_probes=0,
    )

    def base(qs) -> set[tuple[str, int]]:
        return {
            (q.id, q.year) for q in qs.questions
            if not q.id.startswith(("q_transition", "q_trait", "q_pair"))
        }

    assert base(full) == base(baseline)


def test_pair_responses_never_change_scoring_and_are_accumulated() -> None:
    """pair 응답 전 조합이 판정을 바꾸지 않고 accumulate_only로 축적된다(기준 10)."""
    r = calculate(_BIRTH)
    assert r.calibration is not None
    qs = r.calibration.questions

    def answers(static: str | None, transit: str | None) -> list[FeedbackAnswer]:
        out = []
        for q in qs:
            if q.question_type == "static_deficiency_probe":
                out.append(FeedbackAnswer(
                    question_id=q.id, trait_response=static,
                    trait_statement="예전에는 규칙이 버거웠어요" if static else None,
                ))
            elif q.question_type == "transit_activation_probe":
                out.append(FeedbackAnswer(question_id=q.id, transit_response=transit))
            elif q.question_type == "transition_probe":
                continue
            else:
                out.append(FeedbackAnswer(question_id=q.id, overall_rating="positive"))
        return out

    base_res = calibrate_feedback(
        _BIRTH,
        [a for a in answers(None, None) if not a.question_id.startswith("q_pair")],
    )
    decisions = set()
    for static, transit in (
        ("agreed", "strong"), ("denied", "none"), ("mixed", "partial"),
        ("unclear", "unknown"),
    ):
        res = calibrate_feedback(_BIRTH, answers(static, transit))
        decisions.add((
            res.final_yongsin, res.selected_model,
            tuple(sorted(res.model_scores.items())),
        ))
        fb = res.deficiency_pair_feedback[0]
        assert fb.scoring_effect == "none"
        assert fb.review_status == "accumulate_only"
        assert fb.static_response == static
        assert fb.transit_response == transit
        assert fb.transit_year is not None
        assert fb.axis_id == "officer"
        if static == "denied":
            assert fb.static_denial_kind == "temporal"  # '예전 회사에서는' 룰 태깅
    assert len(decisions) == 1
    assert (
        base_res.final_yongsin,
        base_res.selected_model,
        tuple(sorted(base_res.model_scores.items())),
    ) in decisions
