"""진입 시기 두 칸의 턴 간 정합(2026-10-23 실답 web-mvkqiip3 — '11월은 어때?').

결함 체인: ①한 달 창에서 '1/1위'·'유력 달 1위'가 붙어 '가장 유력'으로 번역 ②두 칸 지시가 약한
검토월 후보를 성사 달로 세움 ③직전 답(성사 달 2027년 2월·움직이는 달 2026년 12월)이 후속에
전달되지 않음 ④'조짐이 약하게'→'강하게' 과장을 잡는 감사 없음. 네 층을 반례로 고정한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import chat_service
from saju_api.services.chat_service import (
    _entry_window_weak_note,
    _prior_entry_slots_directive,
    _record_entry_slots,
)
from saju_engines.answer_label_audit import audit_intensity_claims, extract_entry_slots
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

_TODAY = date(2026, 10, 23)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1984-08-19", birth_time="10:15",
    birth_place_name="서울", gender="male",
)


def _intent(start: str | None, event: EventKey | None = EventKey.JOB_GAIN) -> IntentJson:
    tr = None
    if start is not None:
        tr = TimeRange(type="absolute", start=start, end=start, granularity="month")
    return IntentJson(
        intent_id="i", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        event_key=event, time_range=tr,
    )


def _cand(period: str, score: int, *, review: bool = False,
          event: EventKey = EventKey.JOB_GAIN) -> LlmEventCandidate:
    return LlmEventCandidate(
        event_key=event, period=period, ganji="己亥", daewoon_context="壬辰", score=score,
        confidence="medium", polarity="positive", review_month=review,
    )


# ── A. 단일 달 창의 상대 순위 라벨 억제 ────────────────────────────────────────


def test_single_month_window_has_no_relative_rank_labels() -> None:
    p = chat_service.chat(_BIRTH, "2026년 12월 이직 운 어때?", date(2026, 8, 21), True)
    pp = p.prompt_preview or ""
    assert "1/1위" not in pp and "★기간 내 강도 1위" not in pp
    assert "[유력 달 종합" not in pp
    # 후보가 있으면 상대 순위 대신 '절대 강도만 따르라'는 줄·종합 머리가 온다.
    if p.candidate_count:
        assert "상대 순위 없음" in pp or "[질문 달 종합" in pp


def test_multi_month_window_keeps_relative_rank_labels() -> None:
    pp = chat_service.chat(
        _BIRTH, "2026년 10월부터 2027년 3월까지 이직 운 어때?", date(2026, 8, 21), True
    ).prompt_preview or ""
    assert "강도 맥락: 기간 내 상대 " in pp
    assert "[유력 달 종합" in pp
    assert "상대 순위 없음" not in pp


# ── B. 두 칸 지시 예외(약함·검토월) ────────────────────────────────────────────


def test_weak_review_candidate_triggers_exception_note() -> None:
    note = _entry_window_weak_note([_cand("2026-11", 48, review=True)], _intent("2026-11"))
    assert note is not None
    assert "조짐이 약하게 있습니다" in note and "검토월" in note and "성사 달로 두지" in note


def test_strong_candidate_keeps_default_directive() -> None:
    cands = [_cand("2026-11", 48, review=True), _cand("2027-02", 90)]
    assert _entry_window_weak_note(cands, _intent("2026-11")) is None


def test_non_entry_or_year_candidates_ignored() -> None:
    # 연 후보·다른 사건은 판정 대상이 아니다 — 월 진입 후보가 없으면 None.
    cands = [_cand("2026", 40), _cand("2026-11", 40, event=EventKey.RELOCATION)]
    assert _entry_window_weak_note(cands, _intent("2026-11")) is None


# ── C. 직전 두 칸 승계 ────────────────────────────────────────────────────────


def test_extract_entry_slots_both_word_orders_and_year_inference() -> None:
    # 달→라벨 어순(실답 첫 문단 그대로).
    first = (
        "2027년 2월이 입사나 계약이 가시화될 수 있는 성사 달이며 이를 위해 2026년 12월부터 "
        "본격적으로 움직이는 준비가 뒷받침되어야 합니다.\n\n둘째 문단은 무시."
    )
    assert extract_entry_slots(first, _TODAY) == {"done": "2027-02", "move": "2026-12"}
    # 라벨→달 어순 + 연도 없는 달은 오늘 기준 다가오는 달(2월<10월 → 내년).
    assert extract_entry_slots("성사 달 2월·움직이는 달 12월로 보세요.", _TODAY) == {
        "done": "2027-02", "move": "2026-12",
    }
    assert extract_entry_slots("취업 흐름은 완만합니다.", _TODAY) == {}


def test_record_entry_slots_only_for_entry_events() -> None:
    st = ConversationState(thread_id="t", turn_no=4, last_intent=_intent(None))
    _record_entry_slots(st, "성사 달 2027년 2월·움직이는 달 2026년 12월입니다.", _TODAY, "t")
    assert st.entry_slots == {
        "done": "2027-02", "move": "2026-12", "event_key": "job_gain", "turn_no": 4,
        "source": "answer",  # 엔진 배정 없이 답 파싱만으로 저장된 경우(2026-10-24)
    }
    other = ConversationState(
        thread_id="t2", turn_no=1, last_intent=_intent(None, event=EventKey.RELOCATION),
    )
    _record_entry_slots(other, "성사 달 2027년 2월입니다.", _TODAY, "t2")
    assert other.entry_slots == {}


def test_prior_slots_directive_conditions() -> None:
    st = ConversationState(
        thread_id="t", turn_no=5,
        entry_slots={"done": "2027-02", "move": "2026-12", "event_key": "job_gain", "turn_no": 4},
    )
    d = _prior_entry_slots_directive(st, _intent("2026-11"), "2026-10", is_followup=True)
    assert d is not None
    assert "성사 달 2027년 2월" in d and "움직이는 달 2026년 12월" in d and "2026년 11월" in d
    # 2026-10-24 개정: 링크 판정이 NEW 여도 같은 진입 사건이면 주입(실답 '최대한 빨리 언제'가 NEW 로
    # 끊겨 승계가 비켜 간 결함) / 시점 미명시('언제')는 열린 질문 문안으로 주입.
    assert _prior_entry_slots_directive(
        st, _intent("2026-11"), "2026-10", is_followup=False,
    ) is not None
    d_open = _prior_entry_slots_directive(st, _intent(None), "2026-10", is_followup=True)
    assert d_open is not None and "'언제' 질문" in d_open
    # 다른 사건 / 두 달이 모두 지남 → 미주입.
    assert _prior_entry_slots_directive(
        st, _intent("2026-11", event=EventKey.RELOCATION), "2026-10", is_followup=True,
    ) is None
    assert _prior_entry_slots_directive(st, _intent("2027-05"), "2027-03", is_followup=True) is None


# ── D. 강도 충실 감사(로그 전용) ──────────────────────────────────────────────


def test_intensity_audit_flags_inflated_weak_month() -> None:
    answer = (
        "2026년 11월은 취업의 기운이 강하게 움직이는 성사 달입니다. 12월은 준비 달입니다. "
        "취업과 합격의 기운은 2026년 11월에 가장 유력하게 활성화됩니다."
    )
    hits = audit_intensity_claims(answer, ["2026-11"])
    assert [h[0] for h in hits] == ["2026-11", "2026-11"]
    # 과장 어휘가 없는 서술·다른 달 언급은 잡지 않는다('12월' 안의 '2월' 오탐 포함).
    assert audit_intensity_claims(
        "2026년 11월은 조짐이 약하게 있어 검토 달입니다.", ["2026-11"],
    ) == []
    assert audit_intensity_claims("12월은 가장 강한 달입니다.", ["2027-02"]) == []
