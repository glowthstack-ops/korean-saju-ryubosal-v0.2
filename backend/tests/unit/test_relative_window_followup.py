"""'12개월 내에는 없어?' 후속 단절 회귀 — 2026-07-21 데굴님 베타 실로그.

1턴 이직 타이밍 질문 뒤 2턴 '12개월 내에는 없어?'가 too_broad 안내로 끊기던 3중 결함:
①time_parser C8이 'N개월 내(에)'를 미커버(창 미파싱) ②링커에 상대 창 단답·부정
존재형('없어?') 규칙 부재(NEW로 분류) ③비동기(로그인+스레드) 경로에서 last_offer가
갱신되지 않아 offer-slot 링킹이 사장. 세 교정의 회귀를 고정한다.
"""

from __future__ import annotations

from datetime import date
from typing import cast

from saju_api.services.chat_service import update_thread_offer
from saju_engines.conversation import ConversationEngine
from saju_engines.conversation_store import ConversationStore
from saju_engines.query_parser import parse_message
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    TimeRange,
)

_TODAY = date(2026, 7, 21)


def _career_state(offer: str = "") -> ConversationState:
    last = IntentJson(
        intent_id="t1", query_type=QueryType.TIMING_SEARCH, domain=Domain.CAREER,
        time_range=TimeRange(type="open_when", granularity=Granularity.YEAR),
    )
    return ConversationState(
        thread_id="x", turn_no=1, active_topic=Domain.CAREER,
        last_intent=last, last_offer=offer,
    )


# ── ① time_parser: 'N개월 내(에)' 상대 창 ──────────────────────────────────


def test_parser_covers_months_nae_variant() -> None:
    it = parse_message("12개월 내에는 없어?", _TODAY).intents[0]
    assert it.time_range is not None
    assert it.time_range.end_offset_days == 360


def test_parser_nae_nae_not_mistaken_for_window() -> None:
    # '3년 내내 힘들었지' — '내내'(줄곧)는 상대 창이 아니다(lookahead 가드).
    it = parse_message("3년 내내 힘들었지", _TODAY).intents[0]
    assert not (it.time_range is not None and it.time_range.end_offset_days)


# ── ② 링커: 상대 창 단답·부정 존재형 후속 ──────────────────────────────────


def test_relative_window_short_reply_links_as_followup() -> None:
    engine = ConversationEngine()
    link = engine.link_question(_career_state(), "12개월 내에는 없어?")
    assert link.is_follow_up is True


def test_negative_existential_refine_links_as_followup() -> None:
    engine = ConversationEngine()
    link = engine.link_question(_career_state(), "그 전에는 없을까?")
    assert link.is_follow_up is True


def test_real_log_turn_inherits_domain_and_window() -> None:
    # 실로그 2턴 재현 — career 승계 + 360일 상대 창으로 즉시 분석 가능해야 한다
    # (chat_service의 broad 가드는 is_followup_turn=True면 too_broad를 건너뜀).
    parsed, _ns, _res, link = ConversationEngine().process_turn(
        _career_state(), "12개월 내에는 없어?", _TODAY,
    )
    it = parsed.intents[0]
    assert link.is_follow_up is True
    assert it.domain is Domain.CAREER
    assert it.time_range is not None and it.time_range.end_offset_days == 360


def test_new_domain_question_not_swallowed_as_refine() -> None:
    # 새 도메인이 명시되면 정제 후속이 아니라 도메인 전환/새 질문 경로 — 과승계 가드.
    engine = ConversationEngine()
    link = engine.link_question(_career_state(), "연애운은 언제쯤 풀릴까?")
    assert link.link_kind.value != "constraint_add"


# ── ③ 비동기 경로 last_offer 갱신 ──────────────────────────────────────────


class _FakeStore:
    def __init__(self, state: ConversationState | None) -> None:
        self.state = state
        self.saved: ConversationState | None = None

    def load(self, thread_id: str) -> ConversationState | None:
        return self.state

    def save(self, state: ConversationState, owner_id: str = "default") -> None:
        self.saved = state


def test_update_thread_offer_persists_offer_sentence() -> None:
    fake = _FakeStore(_career_state())
    update_thread_offer(
        "x", "…흐름이에요. 가장 가까운 2027년의 월별 흐름을 먼저 짚어드릴까요?",
        store=cast(ConversationStore, fake),
    )
    assert fake.saved is not None
    assert "짚어드릴까요" in fake.saved.last_offer


def test_update_thread_offer_expires_on_error_answer() -> None:
    fake = _FakeStore(_career_state(offer="이전 제안"))
    update_thread_offer("x", "", store=cast(ConversationStore, fake))
    assert fake.saved is not None
    assert fake.saved.last_offer == ""


def test_update_thread_offer_missing_thread_is_noop() -> None:
    fake = _FakeStore(None)
    update_thread_offer("x", "아무 답변", store=cast(ConversationStore, fake))
    assert fake.saved is None
