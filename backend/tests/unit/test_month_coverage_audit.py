"""P0 월 커버리지 감사(2026-09-18 데굴님 지시) — 전문가 반박 사례 회귀.

실로그: 12개월 이직운 답변이 엔진 지목 '기반 최고 달' 2026-10(강한 용신운)을 건너뛰고,
이직 후보에 없는 2027-01을 '적극 수락·실행' 달로 격상했다. 검사는 결정론, 교정은 엔진
확정 문장 삽입(LLM 재호출 없음), 본문 삭제 없음.
"""

from __future__ import annotations

from saju_engines import counseling_arbiter as ca
from saju_engines.month_coverage_audit import (
    audit_month_coverage,
    best_quality_rows,
    build_coverage_notes,
    patch_month_coverage,
)
from saju_shared_types.llm_input import MonthOverviewRow

# 데굴 차트 2026-09~2027-08 창(엔진 dry_run 실측 등급).
_ROWS = [
    MonthOverviewRow(period="2026-09", ganji="丁酉", luck_grade="용신운(부분)"),
    MonthOverviewRow(period="2026-10", ganji="戊戌", luck_grade="강한 용신운"),
    MonthOverviewRow(period="2026-11", ganji="己亥", luck_grade="천간 용신·지지 기신(혼합)"),
    MonthOverviewRow(period="2026-12", ganji="庚子", luck_grade="기신운(부분)"),
    MonthOverviewRow(period="2027-01", ganji="辛丑", luck_grade="용신운(부분)"),
    MonthOverviewRow(period="2027-02", ganji="壬寅", luck_grade="강한 기신운"),
    MonthOverviewRow(period="2027-03", ganji="癸卯", luck_grade="강한 기신운"),
    MonthOverviewRow(period="2027-04", ganji="甲辰", luck_grade="천간 기신·지지 용신(혼합)"),
    MonthOverviewRow(period="2027-05", ganji="乙巳", luck_grade="천간 기신·지지 용신(혼합)"),
    MonthOverviewRow(period="2027-06", ganji="丙午", luck_grade="강한 용신운"),
    MonthOverviewRow(period="2027-07", ganji="丁未", luck_grade="강한 용신운"),
    MonthOverviewRow(period="2027-08", ganji="戊申", luck_grade="용신운(부분)"),
]
_ALLOWED = ("2027-02", "2027-08", "2027-05", "2027-03", "2026-12")

# 실로그 답변 발췌 — 10월 누락 + 1월 격상.
_BAD_ANSWER = (
    "데굴님, 지금부터 12개월간의 직업적 변화 흐름을 짚어보니 2027년 1월과 2월이 가장 결정적인 "
    "분기점이 될 것으로 보입니다.\n\n"
    "현재 진행 중인 9월은 조짐이 약하게 비치는 정도입니다. 11월에 들어서면 이직에 대한 구상이 "
    "구체화됩니다. 다만 이 시기는 공망의 영향으로 계약의 유지력이 다소 낮을 수 있으니, 실제 도장을 "
    "찍기보다는 조건을 면밀히 따져보는 검토의 시간으로 삼으시길 바랍니다.\n\n"
    "본격적인 변화의 에너지는 12월부터 거세게 몰아칩니다. 2027년 1월 辛丑(신축)월은 나를 돕는 "
    "용신의 기운이 들어와 정체되었던 문서가 움직이기 시작하는 때입니다. 이때 들어오는 처우 합의나 "
    "입사 조건은 적극적으로 수락하여 실행에 옮기셔도 좋습니다.\n\n"
    "주의할 점은 2027년 2월 壬寅(임인)월입니다. 1월에 자발적인 선택으로 움직이지 못하고 2월까지 "
    "상황이 밀려가게 되면 타의에 의한 이동을 마주할 리스크가 있습니다.\n\n"
    "혹시 지금 고려 중인 새로운 직장의 처우에서 절대 양보할 수 없는 우선순위는 무엇인가요?"
)


def test_best_quality_rows_prefers_strong_grade_and_caps_three():
    """강한 용신운이 있으면 그 달만(최대 3), 없으면 용신운(부분)."""
    assert [r.period for r in best_quality_rows(_ROWS)] == ["2026-10", "2027-06", "2027-07"]
    partial_only = [r for r in _ROWS if r.luck_grade != "강한 용신운"]
    assert [r.period for r in best_quality_rows(partial_only)] == [
        "2026-09", "2027-01", "2027-08",
    ]
    assert best_quality_rows([MonthOverviewRow(period="2027-02", ganji="壬寅",
                                               luck_grade="강한 기신운")]) == []


def test_real_log_answer_flags_both_violations():
    """실로그 답변: 10월 누락 + 1월 격상 두 건 모두 잡는다. 11월 '도장보다는' 문장은 유보라 제외."""
    audit = audit_month_coverage(_BAD_ANSWER, _ROWS, _ALLOWED)
    assert audit.violations == ["best_month_missing", "non_candidate_month_promoted"]
    assert [r.period for r in audit.missing_best] == ["2026-10", "2027-06", "2027-07"]
    assert len(audit.promoted) == 1
    assert audit.promoted[0].periods == ("2027-01",)
    assert "수락하여 실행에" in audit.promoted[0].sentence


def test_mention_by_year_month_or_ganji_passes_best_check():
    """'2026년 10월' / '10월' / '戊戌' 어느 표기든 언급으로 인정한다."""
    rows = [r for r in _ROWS if r.period in ("2026-10", "2026-12")]
    for text in ("2026년 10월은 기반이 좋습니다.", "10월에 준비하세요.", "戊戌월은 안정적입니다."):
        assert audit_month_coverage(text, rows, ("2026-12",)).missing_best == []
    missing = audit_month_coverage("12월만 봅니다.", rows, ("2026-12",)).missing_best
    assert [r.period for r in missing] == ["2026-10"]


def test_promotion_requires_decision_verb_and_no_allowed_month_in_sentence():
    """결정 행동어가 없거나, 허용 달을 같은 문장에 언급하면(모호) 위반이 아니다."""
    rows = [r for r in _ROWS if r.period in ("2027-01", "2027-02")]
    ok = "2027년 1월은 문서가 움직이기 시작하는 검토의 달입니다."
    assert audit_month_coverage(ok, rows, ("2027-02",)).promoted == []
    mixed = "1월에 검토하고 2월에 계약을 체결하는 흐름이 자연스럽습니다."
    assert audit_month_coverage(mixed, rows, ("2027-02",)).promoted == []
    bad = "1월에 들어오는 제안은 수락하셔도 좋습니다."
    promoted = audit_month_coverage(bad, rows, ("2027-02",)).promoted
    assert [p.periods for p in promoted] == [("2027-01",)]
    # 후보가 하나도 없는 턴은 검사 ②를 건너뛴다(모든 달을 위반으로 만들지 않는다).
    assert audit_month_coverage(bad, rows, ()).promoted == []


def test_notes_and_patch_insert_before_closing_question_without_deleting_body():
    """교정 문단은 되묻기 앞에 들어가고 본문은 그대로 남는다. 두 번째 실행은 통과한다."""
    audit = audit_month_coverage(_BAD_ANSWER, _ROWS, _ALLOWED)
    notes = build_coverage_notes(audit, _ROWS)
    assert len(notes) == 2
    assert "2026년 10월(戊戌월), 강한 용신운" in notes[0]
    assert "2027년 1월(辛丑월)" in notes[1] and "2027년 2월(壬寅월)" in notes[1]
    patched = patch_month_coverage(_BAD_ANSWER, notes)
    paragraphs = patched.split("\n\n")
    assert paragraphs[-1].endswith("무엇인가요?")
    assert paragraphs[-2] == notes[1] and paragraphs[-3] == notes[0]
    assert "수락하여 실행에 옮기셔도 좋습니다" in patched  # 본문 삭제 없음
    assert audit_month_coverage(patched, _ROWS, _ALLOWED).missing_best == []
    # 위반이 없으면 원문 그대로.
    assert patch_month_coverage("그대로", []) == "그대로"


def test_counseling_block_lists_allowed_periods_only_when_given():
    """허용 시기 줄은 인자가 있을 때만 붙는다(기존 byte 유지)."""
    sem = ca.CounselingSemantics(
        event_key="career_change", event_ko="이직·직업 변화", period="2027-02",
        activation_band="high", outcome_outlook="adverse",
        summary_stance="PROCEED_WITH_CONDITIONS",
    )
    plain = "\n".join(ca.counseling_block_lines(sem))
    assert "허용 시기" not in plain
    with_allowed = "\n".join(ca.counseling_block_lines(sem, allowed_periods=_ALLOWED))
    assert (
        "결정 행동(수락·계약·실행) 허용 시기: 2027-02, 2027-08, 2027-05, 2027-03, 2026-12"
        in with_allowed
    )
    assert with_allowed.index("허용 시기") < with_allowed.index("[상담 서술 계약]")
