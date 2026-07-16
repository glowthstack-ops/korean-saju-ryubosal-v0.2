"""CAL-P1-c — A×B 응답 매트릭스 LLM 표현 힌트 + payload 필드 + 주입 직렬화 검증.

doc/v2_2/CALIBRATION_STATIC_TRANSIT_PROBES.md §6-2. 힌트는 서술 조정 전용 — 어떤 조합도
model_scores·selected_model·final_yongsin·event score를 바꾸지 않는다(§5 불변식).
"""

from __future__ import annotations

from typing import Any

from saju_api.services.manse_service import calculate, calibrate_feedback
from saju_api.services.personalization import calibration_hint_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.calibration import FeedbackAnswer

_BIRTH = BirthInput(
    reference_date="2026-07-03", calendar_type="solar", birth_date="1980-11-22",
    birth_time="09:40", birth_place_name="서울", gender="male",
)


def _pair_answers(static: str | None, transit: str | None) -> list[FeedbackAnswer]:
    """FE 제출 payload와 동일 형태 — pair는 전용 필드(static/transit_response)로 전송."""
    r = calculate(_BIRTH)
    assert r.calibration is not None
    out = []
    for q in r.calibration.questions:
        d: dict[str, Any] = {
            "question_id": q.id, "overall_rating": "unknown", "selected_events": [],
             "trait_response": None, "trait_statement": None,
             "static_response": None, "transit_response": None}
        if q.question_type == "static_deficiency_probe":
            d["static_response"] = static
        elif q.question_type == "transit_activation_probe":
            d["transit_response"] = transit
        elif q.question_type != "transition_probe":
            d["overall_rating"] = "positive"
        out.append(FeedbackAnswer.model_validate(d))
    return out


def _hint(static: str | None, transit: str | None):
    res = calibrate_feedback(_BIRTH, _pair_answers(static, transit))
    assert len(res.pair_expression_hints) == (1 if res.deficiency_pair_feedback else 0)
    return res


def test_static_and_transit_responses_sent_via_dedicated_fields() -> None:
    """전용 필드(static_response/transit_response)가 pair 레코드로 왕복된다(기준 1·2·3)."""
    res = _hint("mixed", "partial")
    fb = res.deficiency_pair_feedback[0]
    assert fb.static_response == "mixed"
    assert fb.transit_response == "partial"
    assert fb.pair_id.startswith("pair_officer_")  # A/B 같은 pair_id로 묶임
    assert fb.axis_element == "木"


def test_agreed_strong_makes_dual_narrative_hint() -> None:
    """agreed+strong → 양면 서사(dual) 힌트(기준 4)."""
    res = _hint("agreed", "strong")
    hint = res.pair_expression_hints[0]
    assert hint.narrative_mode == "dual_static_deficiency_and_transit_pressure"
    assert "양면성" in hint.instruction and "분리해" in hint.instruction
    assert "엔진 판정은 변경하지" in hint.instruction  # 불변 조항 내장


def test_denied_none_makes_deemphasize_hint() -> None:
    """denied+none → 축 비중 축소 힌트, 처방식 표현 금지 명시(기준 5)."""
    res = _hint("denied", "none")
    hint = res.pair_expression_hints[0]
    assert hint.narrative_mode == "deemphasize_axis"
    assert "비중을 낮추고" in hint.instruction
    assert "반드시 보완해야 한다' 식의 처방도 금지" in hint.instruction


def test_mixed_partial_makes_conditional_hint() -> None:
    """mixed/partial 계열 → 조건부 발현 힌트(기준 6)."""
    res = _hint("mixed", "partial")
    assert res.pair_expression_hints[0].narrative_mode == "conditional_manifestation"
    res2 = _hint("agreed", "partial")
    assert res2.pair_expression_hints[0].narrative_mode == "conditional_manifestation"


def test_unclear_unknown_makes_hedge_hint() -> None:
    """unclear/unknown 유보 → 단정 회피 힌트(기준 7)."""
    res = _hint("unclear", "strong")
    assert res.pair_expression_hints[0].narrative_mode == "hedge_uncertain"
    res2 = _hint("agreed", "unknown")
    assert res2.pair_expression_hints[0].narrative_mode == "hedge_uncertain"
    assert "확정적으로 말하지" in res2.pair_expression_hints[0].instruction


def test_all_hint_combinations_scoring_invariant() -> None:
    """어떤 조합도 model_scores·selected_model·final_yongsin 불변(기준 8)."""
    decisions = set()
    for static, transit in (
        ("agreed", "strong"), ("agreed", "none"), ("denied", "strong"),
        ("denied", "none"), ("mixed", "partial"), ("unclear", "unknown"),
    ):
        res = _hint(static, transit)
        decisions.add((
            res.final_yongsin, res.selected_model,
            tuple(sorted(res.model_scores.items())),
        ))
    assert len(decisions) == 1


def test_calibration_hint_lines_serializes_stored_blob() -> None:
    """저장 blob → LLM 주입 라인(순수 함수) — pair instruction·trait 힌트·cap(기준: 주입)."""
    res = _hint("agreed", "strong")
    blob = {"answers": {}, "result": res.model_dump()}
    lines = calibration_hint_lines(blob)
    assert lines, "힌트 라인 미생성"
    assert lines[0].startswith("[캘리브레이션 표현 조정 — ")
    assert "木 표면 부재" in lines[0]
    assert str(res.deficiency_pair_feedback[0].transit_year) in lines[0]
    assert "양면성" in lines[0]
    # 방어: 빈/이상 blob은 빈 목록.
    assert calibration_hint_lines(None) == []
    assert calibration_hint_lines({}) == []
    assert calibration_hint_lines({"result": "broken"}) == []
    # cap — 힌트가 많아도 3줄 이내.
    fat = {"result": {"trait_llm_hints": ["h1", "h2", "h3", "h4"]}}
    assert len(calibration_hint_lines(fat)) == 3


def test_unanswered_pair_produces_no_hint() -> None:
    """pair 미응답이면 축적도 힌트도 없다(빈 레코드·빈 힌트 방지)."""
    res = _hint(None, None)
    assert res.deficiency_pair_feedback == []
    assert res.pair_expression_hints == []
