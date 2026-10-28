"""2026-10-28 실답 교정 — 소원형 회고 제외 · 되물음 답 개방형 시점 승계 · 1인칭 본인 복귀.

실로그 두 스레드:
- web-mvrs11fx: "아니 새롭게 하고싶은건 없고 그냥 일 적당히 있었으면 좋겠어"의 '있었'이
  `_PAST_KEYWORDS`에 걸려 회고 모드가 되고 2022~2024년을 되짚었다. 직전 '언제 줄어들까'의
  개방형 시점도 잇지 못했다(약한 후속 규칙이 유형만 먼저 승계).
- web-mvrtgkza: "남편과의 2027년 관계" 뒤 "2027년 내가 이직을 하게 된다면 …"이 직전 동반자
  (남편)를 상속해 남편 풀이로 나갔다(docs/03 A0 3단계 1인칭 복귀 보강).
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.chat_service import _question_time_direction
from saju_engines.companion_alias import build_companion_alias_index
from saju_engines.conversation import ConversationEngine
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import (
    IntentJson,
    QueryType,
    SubjectKind,
    SubjectRef,
    TimeRange,
)
from saju_shared_types.subject import SubjectRecord

_TODAY = date(2026, 10, 28)


def _intent(tr: TimeRange | None = None, qt: QueryType = QueryType.TIMING_SEARCH) -> IntentJson:
    return IntentJson(intent_id="i1", query_type=qt, time_range=tr)


# ── A-1 소원형 '~었으면' 은 회고가 아니다 ──────────────────────────────────────────


@pytest.mark.parametrize("q", [
    "아니 새롭게 하고싶은건 없고 그냥 일 적당히 있었으면 좋겠어",
    "일이 좀 줄었으면 좋겠어",
    "내년엔 이직을 했으면 해",
    "돈이 좀 모였으면 싶은데 언제쯤 될까",
])
def test_wish_conditional_is_not_retro(q: str) -> None:
    assert _question_time_direction(q, _intent(), None, _TODAY) is False


@pytest.mark.parametrize("q", [
    "그때 갔었으면 어땠을까",          # 반사실 회고 — '어땠' 이 남는다
    "작년에 일이 많았는데 왜 그랬을까",  # 과거 표지 '작년' 유지
    "7월에 무슨 일 있었어?",            # '있었' 단독(소원형 아님)은 그대로 회고
])
def test_real_retro_still_detected(q: str) -> None:
    assert _question_time_direction(q, _intent(), None, _TODAY) is True


# ── A-2 되물음 답이 유형만 먼저 승계해도 개방형 시점을 잇는다 ──────────────────────


def test_offer_answer_inherits_open_when_after_type_inheritance() -> None:
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = eng.process_turn(
        state, "이미 이직해서 적응중인데 일이 많아 일이 언제줄어들거 같아?", today=_TODAY,
    )
    assert state.last_intent is not None
    assert state.last_intent.query_type is QueryType.TIMING_SEARCH
    assert state.last_intent.time_range is not None
    assert state.last_intent.time_range.type == "open_when"
    state.last_offer = "혹시 업무 외적으로 새롭게 관심을 두게 된 자기 계발 계획이 있으신가요?"
    parsed, state, _, link = eng.process_turn(
        state, "아니 새롭게 하고싶은건 없고 그냥 일 적당히 있었으면 좋겠어", today=_TODAY,
    )
    it = parsed.intents[0]
    assert link.is_follow_up
    assert it.query_type is QueryType.TIMING_SEARCH
    assert it.time_range is not None and it.time_range.type == "open_when"
    assert it.event_key is None


def test_offer_answer_with_own_time_not_overridden() -> None:
    eng = ConversationEngine()
    state = ConversationState(thread_id="t")
    _, state, _, _ = eng.process_turn(state, "일이 언제쯤 줄어들까?", today=_TODAY)
    state.last_offer = "업무량 때문인지 관계 때문인지 어느 쪽이 더 힘드신가요?"
    parsed, state, _, _ = eng.process_turn(state, "2027년 상반기는 어때?", today=_TODAY)
    tr = parsed.intents[0].time_range
    assert tr is not None and tr.type != "open_when" and tr.start is not None


# ── B 1인칭 표지 → 본인 복귀(동반자 지칭 없을 때) ──────────────────────────────────

_B = BirthInput(birth_date="1990-01-01", birth_place_name="서울")


def _records() -> list[SubjectRecord]:
    return [
        SubjectRecord(subject_id="self1", owner_id="u", kind="self", label="윤정",
                      aliases=[], relation_to_user=None, birth=_B),
        SubjectRecord(subject_id="hus1", owner_id="u", kind="companion", label="남편",
                      aliases=[], relation_to_user="husband", birth=_B),
    ]


def _engine_with_husband_active() -> tuple[ConversationEngine, ConversationState]:
    eng = ConversationEngine(
        alias_index=build_companion_alias_index(_records(), base_subject_id="self1"),
    )
    state = ConversationState(thread_id="t")
    _, state, res, _ = eng.process_turn(
        state, "남편과의 2027년 관계는 어떤 사이가 될까?", today=_TODAY,
    )
    assert any(s.kind is SubjectKind.COMPANION for s in state.active_subjects)
    return eng, state


@pytest.mark.parametrize("q", [
    "2027년 내가 이직을 하게 된다면 집 기준으로 어느쪽 방향회사로 이사하는게 좋아?",
    "나는 내년 재물운이 어때?",
    "난 올해 건강 괜찮아?",
    "제가 내년에 승진할 수 있을까요?",
    "내 사주는 어떤 편이야?",
])
def test_first_person_returns_to_self(q: str) -> None:
    eng, state = _engine_with_husband_active()
    res = eng.resolve_subjects(state, q, _TODAY)
    assert res.subjects == [SubjectRef(kind=SubjectKind.SELF, label="본인")]
    assert not res.unresolved


@pytest.mark.parametrize("q", [
    "내가 남편한테 어떻게 해주면 좋을까?",   # 동반자 지칭 있음 → 남편 유지(관계·대상 규칙 그대로)
    "내가 보기엔 성실한 편이야",             # 관점 표현 — 되물음 답, 대상 전환 아님
    "제 생각엔 요즘 많이 지쳐 보여요",        # 관점 표현
    "우리가 내년에 주의할 점은?",             # 1인칭 복수 — 기존 규칙(상속)
    "하나는 잘 풀리는데 다른 건 어때?",        # '하나는' — '나는' 오매칭 금지
    "난리 났던 그 달은 어땠어?",               # '난리' — '난' 오매칭 금지
])
def test_first_person_exceptions_keep_previous_subject(q: str) -> None:
    eng, state = _engine_with_husband_active()
    res = eng.resolve_subjects(state, q, _TODAY)
    assert all(s.kind is SubjectKind.COMPANION for s in res.subjects)
    assert res.subjects[0].label == "남편"


def test_first_person_without_active_companion_is_self_as_before() -> None:
    eng = ConversationEngine()
    res = eng.resolve_subjects(ConversationState(thread_id="t"), "내가 내년에 이직할까?", _TODAY)
    assert res.subjects == [SubjectRef(kind=SubjectKind.SELF, label="본인")]
