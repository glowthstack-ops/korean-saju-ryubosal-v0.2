"""진입 시기 두 칸 엔진 배정(2026-10-24 실답 web-mvm8zqyr — '내년 4월 취업?' → '최대한 빨리 언제?').

결함 체인: ①같은 사건 키(job_gain)의 후보가 '취업 성사 가능성'(기회·유입)과 '구직·채용 국면'
(압박·부담)으로 갈리는데 두 칸 지시가 "후보 달을 성사 달로"라고만 해 '최대한 빨리' 질문에서 가장
이른 국면 달(2027-02)이 성사 달로 올라감 ②성사 방향 후보 2027-04가 2턴 답에서 통째로 빠짐 ③1턴
답이 두 칸 표지를 안 써 승계 슬롯이 비고, 승계 지시가 명시 시점 후속에만 붙어 '언제' 열린 후속엔
비켜 감.

§4-7(같은 날 저녁): 두 모드(direction/trigger)를 두고 정밀도 측정으로 trigger·95점을 기본으로 정했다
(`scripts/measure_entry_slot_modes.py`). direction 모드 규칙은 비교·회귀용으로 보존한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services import chat_service
from saju_api.services.chat_service import (
    _decision_periods,
    _entry_slot_block,
    _prior_entry_slots_directive,
    _record_entry_slots,
)
from saju_engines import counseling_arbiter as ca
from saju_engines.answer_label_audit import audit_entry_candidate_coverage, month_mentioned
from saju_engines.context_reducer import ASKED_EVENT_STRONG_MIN, asked_event_score_in_period
from saju_engines.entry_slots import (
    COND_ADVERSE,
    COND_SMOOTH,
    DEFAULT_ENTRY_SLOT_MODE,
    ENTRY_DONE_MIN_SCORE,
    ENTRY_SLOT_HEADER,
    NOTE_DELAY,
    assign_entry_slots,
    condition_grade,
    entry_slot_directive,
    is_earliest_question,
    resolve_mode,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import (
    Domain,
    EventKey,
    IntentJson,
    QueryType,
    TimeRange,
)
from saju_shared_types.llm_input import LlmEventCandidate

_TODAY = date(2026, 10, 24)


def _intent(start: str | None, event: EventKey | None = EventKey.JOB_GAIN) -> IntentJson:
    tr = None
    if start is not None:
        tr = TimeRange(type="absolute", start=start, end=start, granularity="month")
    return IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        event_key=event, time_range=tr,
    )


def _cand(
    period: str, score: int, quality: str, *, ganji: str = "", review: bool = False,
    direction: str = "", event: EventKey = EventKey.JOB_GAIN,
) -> LlmEventCandidate:
    return LlmEventCandidate(
        event_key=event, period=period, ganji=ganji, daewoon_context="壬辰", score=score,
        confidence="medium", polarity="positive", quality=quality, review_month=review,
        direction=direction,
    )


# 실답 2턴 Top-5 구성(오전 라벨 기준) — 가장 이른 후보가 국면(pressure), 성사 방향(opportunity)은
# 뒤.
_LIVE_TOP5 = [
    _cand("2027-02", 90, "pressure", ganji="壬寅"),
    _cand("2027-05", 88, "opportunity", ganji="乙巳"),
    _cand("2027-03", 86, "pressure", ganji="癸卯"),
    _cand("2027-04", 87, "opportunity", ganji="甲辰"),
    _cand("2026-12", 60, "pressure", ganji="庚子"),
]
# trigger 모드 반례 — 가장 이른 성사 가능 달은 조건 불리(2027-02), 순조한 성사 달은 뒤(2027-04).
_TRIGGER_SET = [
    _cand("2027-02", 96, "pressure", ganji="壬寅"),
    _cand("2027-05", 95, "opportunity", ganji="乙巳", direction="기회·유입 · 지연"),
    _cand("2027-03", 86, "pressure", ganji="癸卯"),
    _cand("2027-04", 97, "opportunity", ganji="甲辰"),
    _cand("2026-12", 60, "pressure", ganji="庚子"),
    _cand("2026-11", 51, "opportunity", ganji="己亥"),  # 55 미만 — 어느 칸에도 없음
]


def test_default_mode_and_threshold_are_measured_values() -> None:
    assert DEFAULT_ENTRY_SLOT_MODE == "trigger" and ENTRY_DONE_MIN_SCORE == 95
    assert resolve_mode(None) in ("trigger", "direction")
    assert resolve_mode("direction") == "direction" and resolve_mode("nonsense") == "trigger"


# ── A. direction 모드(비교·회귀용) ──────────────────────────────────────────────


def test_direction_mode_splits_by_result_direction() -> None:
    a = assign_entry_slots(_LIVE_TOP5, mode="direction")
    assert a is not None and a.mode == "direction"
    assert a.done_periods == ["2027-04", "2027-05"]
    assert a.move_periods == ["2026-12", "2027-02", "2027-03"]
    assert a.to_state_slots() == {"done": "2027-04", "move": "2027-03"}
    cands = [
        _cand("2027-01", 80, "opportunity", direction="기회·유입 · 지연"),
        _cand("2027-02", 80, "opportunity", review=True),
        _cand("2027-03", 80, "loss"),
        _cand("2027-04", 80, "achievement"),
    ]
    b = assign_entry_slots(cands, mode="direction")
    assert b is not None and b.done_periods == ["2027-04"]
    d = entry_slot_directive(a, event_ko="취업·합격", earliest_asked=True)
    assert "성사 달 후보(결과 방향 긍정): 2027-04·2027-05" in d
    assert "국면 달을 성사 달로 세우지 말 것" in d and "가장 이른 2027-04로 두고" in d


def test_direction_mode_without_done_says_so() -> None:
    a = assign_entry_slots(
        [_cand("2027-02", 90, "pressure"), _cand("2027-03", 86, "pressure")], mode="direction",
    )
    assert a is not None
    d = entry_slot_directive(a, event_ko="취업·합격", earliest_asked=True)
    assert "성사 달 후보 없음" in d and "2027-02·2027-03" in d and "지어내지 말 것" in d


# ── B. trigger 모드(기본) — 점수 하한 + 조건 등급 ───────────────────────────────


def test_trigger_mode_splits_by_score_and_grades_conditions() -> None:
    a = assign_entry_slots(_TRIGGER_SET, mode="trigger", done_min=95)
    assert a is not None and a.mode == "trigger" and a.done_min == 95
    assert a.done_periods == ["2027-02", "2027-04", "2027-05"]
    assert a.move_periods == ["2026-12", "2027-03"]  # 51점(2026-11)은 어느 칸에도 없다
    assert a.conditions["2027-02"] == COND_ADVERSE
    assert a.conditions["2027-04"] == COND_SMOOTH
    assert a.conditions["2027-05"] == f"{COND_SMOOTH} · {NOTE_DELAY}"  # 지연은 제외가 아니라 주석
    assert a.earliest_done == "2027-02" and a.earliest_smooth == "2027-04"
    assert a.to_state_slots() == {"done": "2027-02", "move": "2026-12"}


def test_trigger_mode_threshold_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    # 오전 라벨 세트(최고 90점)는 95 하한에서 성사 가능 달이 없고 전부 움직이는 달이다.
    a = assign_entry_slots(_LIVE_TOP5, mode="trigger")
    assert a is not None and a.done_periods == []
    assert a.move_periods == ["2026-12", "2027-02", "2027-03", "2027-04", "2027-05"]
    monkeypatch.setenv("SAJU_ENTRY_DONE_MIN_SCORE", "85")
    b = assign_entry_slots(_LIVE_TOP5, mode="trigger")
    assert b is not None and b.done_periods == ["2027-02", "2027-03", "2027-04", "2027-05"]
    monkeypatch.setenv("SAJU_ENTRY_SLOT_MODE", "direction")
    assert resolve_mode() == "direction"


def test_condition_grade_translates_direction_not_outcome() -> None:
    assert condition_grade(_cand("2027-02", 96, "pressure")) == COND_ADVERSE
    assert condition_grade(_cand("2027-02", 96, "loss")) == COND_ADVERSE
    assert condition_grade(_cand("2027-02", 96, "mixed")).startswith("완화")
    assert condition_grade(_cand("2027-02", 96, "opportunity", review=True)) == (
        f"{COND_SMOOTH} · 검토월(계약 유지력 낮음)"
    )


def test_trigger_directive_names_earliest_and_smooth_months() -> None:
    a = assign_entry_slots(_TRIGGER_SET, mode="trigger", done_min=95)
    assert a is not None
    d = entry_slot_directive(
        a, event_ko="취업·합격", earliest_asked=True,
        ganji_by_period={"2027-02": "壬寅", "2027-04": "甲辰"},
    )
    assert d.startswith(ENTRY_SLOT_HEADER)
    assert "성사 가능 달(사건 신호 매우 강함" in d
    assert "2027-02(壬寅 · 조건 불리(처우·강도 주의))" in d and "2027-04(甲辰 · 순조)" in d
    assert "움직이는 달(사건 신호는 있으나 성사 기준 미달" in d and "2026-12·2027-03" in d
    assert "가장 이른 성사 가능 달은 2027-02(壬寅)(조건 불리" in d
    assert "조건까지 순조한 가장 이른 달은 2027-04(甲辰)" in d
    assert "불성사·국면으로 격하하지 말 것" in d and "각각 한 번씩 달 이름을 들어" in d
    d2 = entry_slot_directive(a, event_ko="취업·합격")
    assert "가장 이른 성사 가능 달" not in d2


def test_trigger_directive_without_done_says_so() -> None:
    a = assign_entry_slots(_LIVE_TOP5, mode="trigger", done_min=95)
    assert a is not None
    d = entry_slot_directive(a, event_ko="취업·합격", earliest_asked=True)
    assert "성사 가능 달 없음" in d and "성사 기준에 못 미친다" in d and "지어내지 말 것" in d
    assert "2026-12·2027-02·2027-03·2027-04·2027-05" in d


def test_non_entry_or_year_candidates_give_none() -> None:
    assert assign_entry_slots([_cand("2027", 99, "opportunity")]) is None
    assert assign_entry_slots(
        [_cand("2027-04", 99, "opportunity", event=EventKey.RELOCATION)]
    ) is None
    assert assign_entry_slots([]) is None
    assert assign_entry_slots([_cand("2027-04", 40, "opportunity")], mode="trigger") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("최대한 빠르게 취업하려면 언제 가능할가", True),
        ("가장 빠른 취업 시기는?", True),
        ("돈이 없어서 빨리 취업해야해", True),
        ("언제 취업할 수 있을까", False),
        ("", False),
    ],
)
def test_is_earliest_question(text: str, expected: bool) -> None:
    assert is_earliest_question(text) is expected


def test_entry_slot_block_uses_candidate_ganji_and_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAJU_ENTRY_SLOT_MODE", raising=False)
    monkeypatch.delenv("SAJU_ENTRY_DONE_MIN_SCORE", raising=False)
    d, slots = _entry_slot_block(
        _TRIGGER_SET, _intent(None), "최대한 빠르게 취업하려면 언제 가능할가",
    )
    assert d is not None and "2027-02(壬寅 · 조건 불리" in d
    assert "순조한 가장 이른 달은 2027-04(甲辰)" in d
    assert slots == {"done": "2027-02", "move": "2026-12"}
    assert _entry_slot_block(
        [_cand("2027", 90, "opportunity")], _intent(None), "언제",
    ) == (None, {})


# ── C. 승계 — 엔진 배정 우선 저장 + '언제' 열린 후속 주입 ──────────────────────


def test_record_entry_slots_prefers_engine_done_and_answer_move() -> None:
    st = ConversationState(thread_id="t", turn_no=1, last_intent=_intent("2027-04"))
    _record_entry_slots(
        st, "2027년 4월은 성사 가능성이 높습니다.", _TODAY, "t", engine_slots={"done": "2027-04"},
    )
    assert st.entry_slots == {
        "done": "2027-04", "event_key": "job_gain", "turn_no": 1, "source": "engine",
    }
    st2 = ConversationState(thread_id="t2", turn_no=2, last_intent=_intent(None))
    _record_entry_slots(
        st2, "성사 달 2027년 2월·움직이는 달 2026년 12월입니다.", _TODAY, "t2",
        engine_slots={"done": "2027-04", "move": "2027-03"},
    )
    assert st2.entry_slots["done"] == "2027-04" and st2.entry_slots["move"] == "2026-12"
    assert st2.entry_slots["source"] == "engine"
    st3 = ConversationState(thread_id="t3", turn_no=1, last_intent=_intent(None))
    _record_entry_slots(st3, "취업 흐름은 완만합니다.", _TODAY, "t3", engine_slots={})
    assert st3.entry_slots == {}


def test_prior_slots_directive_for_open_when_followup() -> None:
    st = ConversationState(
        thread_id="t", turn_no=2,
        entry_slots={"done": "2027-04", "event_key": "job_gain", "turn_no": 1, "source": "engine"},
    )
    open_when = IntentJson(
        intent_id="i", query_type=QueryType.TIMING_SEARCH, domain=Domain.CAREER,
        event_key=EventKey.JOB_GAIN, time_range=None,
    )
    d = _prior_entry_slots_directive(st, open_when, "2026-10", is_followup=False)
    assert d is not None
    assert "성사 달 2027년 4월" in d and "'언제' 질문" in d and "뒤집어" in d
    d2 = _prior_entry_slots_directive(st, _intent("2027-02"), "2026-10", is_followup=False)
    assert d2 is not None and "2027년 2월" in d2 and "'언제' 질문" not in d2
    assert _prior_entry_slots_directive(
        st, _intent(None, event=EventKey.RELOCATION), "2026-10", is_followup=True,
    ) is None
    year_only = IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        event_key=EventKey.JOB_GAIN,
        time_range=TimeRange(type="absolute", start="2027", end="2027", granularity="year"),
    )
    assert _prior_entry_slots_directive(st, year_only, "2026-10", is_followup=True) is None
    assert _prior_entry_slots_directive(st, open_when, "2027-05", is_followup=True) is None


# ── D. 감사·권유 처리 ─────────────────────────────────────────────────────────────


def test_entry_candidate_coverage_audit() -> None:
    answer = (
        "가장 빠르게 취업의 결실을 맺을 수 있는 시기는 2027년 2월이며 … 2027년 5월 乙巳월에도 "
        "강한 신호가 있습니다. 12월은 준비 달입니다."
    )
    assert audit_entry_candidate_coverage(answer, ["2027-04", "2027-05"]) == ["2027-04"]
    assert month_mentioned("12월은 준비 달입니다.", "2027-02") is False
    assert month_mentioned("4월에 결과를 매듭짓는", "2027-04") is True
    assert audit_entry_candidate_coverage("", ["2027-04"]) == ["2027-04"]


def test_asked_event_score_in_period() -> None:
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", EventKey.JOB_GAIN) == 87
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", "job_gain") == 87
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-01", EventKey.JOB_GAIN) is None
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", EventKey.RELOCATION) is None
    assert asked_event_score_in_period(_LIVE_TOP5, "2027-04", None) is None
    assert ASKED_EVENT_STRONG_MIN == 70


def test_counseling_block_review_periods_line() -> None:
    sem = ca.CounselingSemantics(
        event_key="job_gain", event_ko="취업·합격", period="2027-02",
        activation_band="high", outcome_outlook="adverse",
        summary_stance="PROCEED_WITH_CONDITIONS",
    )
    both = "\n".join(ca.counseling_block_lines(
        sem, allowed_periods=("2027-05", "2027-04"), review_periods=("2027-02", "2027-03"),
    ))
    assert "결정 행동(수락·계약·실행) 허용 시기: 2027-05, 2027-04" in both
    assert "준비·검토 시기(결정 권고 금지): 2027-02, 2027-03" in both
    assert "성사 기준에 못 미치는 달" in both and "국면·압박 후보 달" not in both
    assert both.index("허용 시기") < both.index("준비·검토 시기") < both.index("[상담 서술 계약]")
    only_review = "\n".join(ca.counseling_block_lines(sem, review_periods=("2027-02",)))
    assert "허용 시기: 없음" in only_review
    assert "준비·검토 시기(결정 권고 금지): 2027-02" in only_review
    plain = "\n".join(ca.counseling_block_lines(sem))
    assert "허용 시기" not in plain and "준비·검토 시기" not in plain


# ── E. 실답 명식 회귀(dry-run, 기본 모드 trigger·95) ──────────────────────────────

_FIXTURE = Path(__file__).parent / "fixtures" / "entry_slots_birth_19801122.json"


@pytest.mark.skipif(not _FIXTURE.exists(), reason="실답 명식 픽스처 없음")
def test_live_case_prompts_under_default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAJU_ENTRY_SLOT_MODE", raising=False)
    monkeypatch.delenv("SAJU_ENTRY_DONE_MIN_SCORE", raising=False)
    birth = BirthInput.model_validate(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    r1 = chat_service.chat(birth, "다른 사주에서는 내년 4월에 취업할 수 있을거래. ", _TODAY, True)
    pp1 = r1.prompt_preview or ""
    assert r1.postprocess is not None
    # 1턴(2027-04 한 달 창): 95 하한에 못 미쳐 '성사 가능 달 없음' + 움직이는 달 2027-04.
    assert "성사 가능 달 없음" in pp1 and "움직이는 달 후보: 2027-04(甲辰)" in pp1
    assert r1.postprocess.entry_slots_engine == {}
    # 권유 처리 A: 질문 사건이 그 달의 강한 후보면 '동반 신호로만' 격하 대신 함께 서술.
    assert "최상위 신호는 '계약·문서'이고 질문하신 '취업·합격'도 강한 후보" in pp1
    assert "질문하신 '취업·합격'은(는) 동반 신호로만 서술할 것" not in pp1
    # direction 모드로 같은 후보를 나누면 2027-04 가 성사 방향 후보 — 두 모드의 차이가 바로 이 달.
    d1 = assign_entry_slots(list(r1.postprocess.payload.event_candidates), mode="direction")
    assert d1 is not None and d1.done_periods == ["2027-04"]

    r2 = chat_service.chat(birth, "최대한 빠르게 취업하려면 언제 가능할가", _TODAY, True)
    pp2 = r2.prompt_preview or ""
    assert r2.postprocess is not None
    assert "성사 가능 달(사건 신호 매우 강함" in pp2
    assert "2027-02(壬寅 · 조건 불리(처우·강도 주의))" in pp2
    assert "2026-12(庚子)·2027-03(癸卯)·2027-04(甲辰)·2027-05(乙巳)" in pp2
    assert "가장 이른 성사 가능 달은 2027-02(壬寅)(조건 불리" in pp2
    assert r2.postprocess.entry_slots_engine == {"done": "2027-02", "move": "2026-12"}
    # 권유 처리 B: 결정 행동 허용 시기는 성사 가능 달만, 나머지 월 후보는 준비·검토 시기.
    allowed, review = _decision_periods(r2.postprocess.payload)
    assert allowed == ("2027-02",)
    assert set(review) == {"2027-05", "2027-03", "2027-04", "2026-12"}
    if ca.COUNSELING_SEMANTICS_ENABLED:
        assert "결정 행동(수락·계약·실행) 허용 시기: 2027-02" in pp2
        assert "준비·검토 시기(결정 권고 금지): 2027-05, 2027-03, 2027-04, 2026-12" in pp2
    d2 = assign_entry_slots(list(r2.postprocess.payload.event_candidates), mode="direction")
    assert d2 is not None and d2.done_periods == ["2027-04", "2027-05"]
