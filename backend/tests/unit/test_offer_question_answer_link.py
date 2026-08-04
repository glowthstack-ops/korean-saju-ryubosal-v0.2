"""질문형 마감 뒤 사용자의 답이 끊기던 결함 (2026-08-04 실로그).

관측된 미스:

    시스템  "… 절대 양보할 수 없는 한 가지는 무엇인가요?"
            "※ 관계 신호는 시험(beta) 관측치예요."
    사용자  "역시 외모지"
    시스템  "질문 범위가 넓어요. 이렇게 좁혀볼까요? — 향후 6개월 연애운 / 올해 연애운"

원인은 링킹 규칙이 없어서가 아니다. offer-answer 규칙(2026-07-22)은 이미 있었지만
그 입력인 `last_offer` 가 비어 있었다: `_extract_offer` 가 제안 어구 **키워드 목록**
(`짚어드릴까요`·`궁금해요` 등)으로만 offer 를 뽑아, 페르소나가 사용자에게 직접 묻고
끝낸 질문형 마감("… 무엇인가요?")을 하나도 잡지 못했다. 그래서

    last_offer='' → offer-slot·offer-answer 둘 다 건너뜀 → LinkKind.NEW → too_broad

같은 원인으로 `_OFFER_CONTINUE_DIRECTIVE` 도 죽어 있었다(LLM 이 사용자가 무슨 질문에
답한 것인지 모른 채 답변을 생성).

마커를 늘리는 대신 **마지막 문장이 물음표로 끝나면 대기 질문으로 인정**한다. 마지막
문장으로 한정하는 이유는 본문 중간 수사의문문을 제안으로 오인하지 않기 위해서다.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from saju_api.services.chat_service import (
    _extract_offer,
    _offer_is_question,
)
from saju_engines.conversation import ConversationEngine
from saju_engines.query_parser import _detect_domains
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import Domain

_T = date(2026, 8, 4)
_Q1 = "내게 앞으로 올 연애 이벤트가 있을까?"
_ANSWER_WITH_QUESTION = (
    "올해 하반기에 만나는 인연은 데굴님의 현실적인 생활 방식에 변화를 줄 가능성이 큰데, "
    "본인이 생각하는 이상적인 배우자의 조건 중 절대 양보할 수 없는 한 가지는 무엇인가요?\n"
    "\n"
    "※ 관계 신호는 시험(beta) 관측치예요."
)
_USER_REPLY = "역시 외모지"


# ── ① offer 추출 — 질문형 마감 ───────────────────────────────


def test_trailing_question_is_extracted_as_offer() -> None:
    """실로그 원 사례: 질문형 마감 + 고지 줄."""
    offer = _extract_offer(_ANSWER_WITH_QUESTION)
    assert offer.endswith("무엇인가요?")
    assert "※" not in offer
    assert _offer_is_question(offer)


def test_notice_lines_do_not_push_question_out_of_tail() -> None:
    """고지가 여러 줄이어도 질문을 찾는다(tail 계산에서 고지 제외)."""
    answer = (
        "어떤 조건을 가장 중요하게 보세요?\n"
        "\n"
        "※ 관계 신호는 시험(beta) 관측치예요.\n"
        "※ 관계 주의 신호는 시험(beta) 관측치예요."
    )
    assert _extract_offer(answer) == "어떤 조건을 가장 중요하게 보세요?"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("12월 흐름을 더 짚어드릴까요?", "12월 흐름을 더 짚어드릴까요?"),
        ("제품형인지 서비스형인지 궁금해요.", "제품형인지 서비스형인지 궁금해요."),
    ],
)
def test_existing_offer_markers_unchanged(answer: str, expected: str) -> None:
    """기존 제안·되물음 추출은 그대로다(회귀 없음)."""
    assert _extract_offer(answer) == expected


@pytest.mark.parametrize(
    "answer",
    [
        "천천히 주변을 살펴나가는 여유를 가져보셨으면 좋겠어요.",
        # 본문 중간 수사의문문 + 평서문 마감 — 제안이 아니다(오탐 금지).
        "이 시기가 정말 좋을까요? 결론적으로는 준비를 갖추는 편이 낫습니다.",
        "",
    ],
)
def test_statement_ending_is_not_an_offer(answer: str) -> None:
    assert _extract_offer(answer) == ""


def test_offer_is_question_distinguishes_acceptance_offer() -> None:
    """수락형 제안과 되물음을 구분한다(지시문 선택 기준)."""
    assert _offer_is_question("어떤 조건을 가장 중요하게 보세요?")
    assert not _offer_is_question("이어서 12월 흐름을 봐드릴게요.")


# ── ② 링킹 — 사용자의 답이 새 질문으로 끊기지 않는다 ─────────


def test_reply_to_trailing_question_links_to_thread() -> None:
    """실로그 재현: '역시 외모지' 가 NEW 로 끊기지 않는다."""
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q1, _T, birth_year=1980)
    assert st.last_intent is not None
    st.last_offer = _extract_offer(_ANSWER_WITH_QUESTION)
    assert st.last_offer  # 추출 실패 시 아래 링킹은 의미가 없다

    link = eng.link_question(st, _USER_REPLY)
    assert link.is_follow_up


def test_reply_domain_is_not_hijacked() -> None:
    """'외모' 는 도메인 키워드가 아니므로 직전 연애 맥락을 그대로 잇는다."""
    assert _detect_domains(_USER_REPLY) == []


def test_new_domain_reply_still_opens_new_thread() -> None:
    """되물음이 있어도 새 도메인을 들고 온 질문은 흡수하지 않는다(기존 계약)."""
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, _Q1, _T, birth_year=1980)
    st.last_offer = _extract_offer(_ANSWER_WITH_QUESTION)
    q = "요즘 몸이 계속 나빠지는데 건강 문제부터 봐야 할 것 같아"
    assert Domain.HEALTH in _detect_domains(q)
    assert not eng.link_question(st, q).is_follow_up


# ── ③ end-to-end — too_broad 로 바운스되지 않는다 ────────────


def _birth():  # noqa: ANN202 - 테스트 픽스처 타입은 내부 모델이다
    from saju_shared_types.birth_input import BirthInput

    return BirthInput(
        birth_date=date(1988, 3, 15), birth_time="14:30",
        birth_place_name="서울특별시", gender="male", calendar_type="solar",
    )


@pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"),
    reason="2턴 재생은 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)
def test_reply_to_trailing_question_is_not_bounced_as_too_broad() -> None:
    """실로그 2턴 재생: 되물음에 답한 턴이 범위 좁히기 메뉴로 빠지지 않는다.

    dry_run 이라 LLM 은 호출되지 않는다. 운영에서는 답변 생성 직후
    `state.last_offer = _extract_offer(answer)` 가 실행되므로, 그 지점을
    동일하게 재현해 다음 턴의 링킹을 본다.
    """
    import uuid

    from saju_api.services.chat_service import ConversationStore, chat

    thread_id = f"t-{uuid.uuid4().hex[:8]}"
    birth = _birth()
    first = chat(birth, _Q1, today=_T, dry_run=True, thread_id=thread_id)
    assert first.status == "dry_run"  # 1턴은 정상 진행(범위 안내 아님)

    store = ConversationStore()
    store.migrate()
    state = store.load(thread_id)
    assert state is not None
    state.last_offer = _extract_offer(_ANSWER_WITH_QUESTION)
    assert state.last_offer
    store.save(state)

    second = chat(birth, _USER_REPLY, today=_T, dry_run=True, thread_id=thread_id)
    assert second.status != "too_broad", "되물음 답변이 범위 좁히기로 바운스됐다"


def test_answer_directive_replaces_acceptance_wording() -> None:
    """되물음 답변 턴에는 '수락' 문구가 아니라 답변용 지시문이 실린다."""
    from saju_api.services.chat_service import (
        _OFFER_ANSWER_DIRECTIVE,
        _OFFER_CONTINUE_DIRECTIVE,
    )

    offer = _extract_offer(_ANSWER_WITH_QUESTION)
    # 되물음(질문형) + 수락어 아님 → 답변용 지시문
    assert _offer_is_question(offer)
    assert "그 질문에 대한 답이다" in _OFFER_ANSWER_DIRECTIVE
    assert "짧은 수락" in _OFFER_CONTINUE_DIRECTIVE
    assert _OFFER_ANSWER_DIRECTIVE.format(offer=offer).endswith("무엇인가요?」")
