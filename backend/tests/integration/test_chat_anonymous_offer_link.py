"""무인증 스레드에서도 되물음 답변이 연결되는지 (2026-08-04, CHAT-OFFER-QUESTION-01).

`_extract_offer` 를 고쳐 질문형 마감을 잡게 해도, **라우터가 직접 답변을 생성하는
경로**(비로그인)는 `chat_service` 의 offer 저장 지점을 지나지 않아 `last_offer` 가
영원히 '' 였다. 그러면 같은 대화가 로그인 여부에 따라 다르게 동작한다(로그인은 연결,
비로그인은 too_broad). 누락된 배선이므로 라우터에서 `update_thread_offer` 를 부른다.

이 파일은 그 경로를 **라우터 레벨**에서 고정한다(서비스 함수 직접 호출이 아니라
실제 HTTP 요청 2턴). LLM 은 호출하지 않고 고정 답변으로 대체한다.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import anyio
import httpx
import pytest
from httpx import ASGITransport

from saju_api.main import app
from saju_api.services import chat_service
from saju_engines.conversation_store import ConversationStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"),
    reason="스레드(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)

_BIRTH = {
    "birth_date": "1979-11-07",
    "birth_time": "03:20",
    "birth_place_name": "서울특별시",
    "gender": "female",
    "calendar_type": "solar",
}
_Q1 = "내게 앞으로 올 연애 이벤트가 있을까?"
_REPLY = "역시 외모지"
# 페르소나 마감 형태 그대로 — 질문 + 말미 고지 줄.
_ANSWER = (
    "올해 하반기에는 새로운 인연의 에너지가 11월 무렵에 뚜렷해집니다.\n"
    "본인이 생각하는 이상적인 배우자의 조건 중 절대 양보할 수 없는 한 가지는 무엇인가요?\n"
    "\n"
    "※ 관계 신호는 시험(beta) 관측치예요."
)


def _post(payload: dict) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=120
        ) as client:
            return await client.post("/api/v2/chat", json=payload)

    return anyio.run(_run)


@pytest.fixture()
def canned_llm(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """LLM 을 고정 답변으로 대체한다(실호출 없음). 반환값은 생성 호출 기록."""
    calls: list[str] = []

    def _generate(prompt: str, **_kw: Any) -> str:
        calls.append(prompt)
        return _ANSWER

    monkeypatch.setattr(chat_service.llm_client, "is_available", lambda: True)
    monkeypatch.setattr(chat_service.llm_client, "generate_reading", _generate)
    return calls


def test_anonymous_thread_links_reply_to_trailing_question(canned_llm) -> None:
    """무인증 2턴: 되물음 답변이 too_broad 로 바운스되지 않는다."""
    thread_id = f"t-anon-{uuid.uuid4().hex[:8]}"

    first = _post({"birth": _BIRTH, "question": _Q1, "thread_id": thread_id})
    assert first.status_code == 200
    assert first.json()["status"] == "answered"

    # ① offer 가 저장됐다(라우터 배선) — 인증 경로와 동일한 해석 결과.
    store = ConversationStore()
    state = store.load(thread_id)
    assert state is not None
    assert state.last_offer == chat_service._extract_offer(_ANSWER)
    assert state.last_offer.endswith("무엇인가요?")
    assert "※" not in state.last_offer

    # ② 다음 턴의 짧은 답변이 직전 질문에 대한 답으로 연결된다.
    second = _post({"birth": _BIRTH, "question": _REPLY, "thread_id": thread_id})
    assert second.status_code == 200
    assert second.json()["status"] != "too_broad", "되물음 답변이 범위 좁히기로 바운스됐다"


def test_offer_update_scoped_to_its_own_thread(canned_llm) -> None:
    """다른 스레드로 기록이 넘어가지 않는다."""
    mine = f"t-anon-{uuid.uuid4().hex[:8]}"
    other = f"t-anon-{uuid.uuid4().hex[:8]}"
    store = ConversationStore()
    store.migrate()

    # 이웃 스레드를 먼저 만들어 둔다(빈 offer 상태).
    _post({"birth": _BIRTH, "question": _Q1, "thread_id": other})
    neighbour_before = store.load(other)
    assert neighbour_before is not None
    store.save(neighbour_before.model_copy(update={"last_offer": ""}))

    _post({"birth": _BIRTH, "question": _Q1, "thread_id": mine})

    assert store.load(mine).last_offer  # 내 스레드만 갱신
    assert store.load(other).last_offer == ""  # 이웃은 그대로


def test_new_domain_question_still_opens_new_context(canned_llm) -> None:
    """새 도메인 질문은 offer 가 있어도 흡수되지 않는다(기존 계약 유지)."""
    thread_id = f"t-anon-{uuid.uuid4().hex[:8]}"
    _post({"birth": _BIRTH, "question": _Q1, "thread_id": thread_id})

    from saju_engines.conversation import ConversationEngine
    from saju_engines.query_parser import _detect_domains
    from saju_shared_types.intent import Domain

    state = ConversationStore().load(thread_id)
    assert state is not None and state.last_offer
    q = "요즘 몸이 계속 나빠지는데 건강 문제부터 봐야 할 것 같아"
    assert Domain.HEALTH in _detect_domains(q)
    assert not ConversationEngine().link_question(state, q).is_follow_up


def test_offer_save_failure_does_not_break_the_answer(
    canned_llm, monkeypatch: pytest.MonkeyPatch
) -> None:
    """offer 갱신이 실패해도 본 답변 전달은 성공한다(링킹만 비활성).

    실패는 `update_thread_offer` 안에서만 나야 한다 — 대화 상태 저장 자체를
    막으면 prep 경로까지 죽어 이 불변식을 검증하지 못한다.
    """
    def _boom(*_a: Any, **_kw: Any) -> str:
        raise RuntimeError("offer extraction down")

    monkeypatch.setattr(chat_service, "_extract_offer", _boom)
    thread_id = f"t-anon-{uuid.uuid4().hex[:8]}"
    res = _post({"birth": _BIRTH, "question": _Q1, "thread_id": thread_id})
    assert res.status_code == 200
    assert res.json()["answer"] == _ANSWER
    # 링킹만 비활성 — 상태는 남고 offer 만 비어 있다.
    state = ConversationStore().load(thread_id)
    assert state is not None and state.last_offer == ""


def test_reply_body_is_not_persisted_as_a_new_fact(canned_llm) -> None:
    """사용자 답변 본문을 새로 영속화하지 않는다 — 저장되는 것은 offer(내 질문)뿐."""
    thread_id = f"t-anon-{uuid.uuid4().hex[:8]}"
    _post({"birth": _BIRTH, "question": _Q1, "thread_id": thread_id})
    _post({"birth": _BIRTH, "question": _REPLY, "thread_id": thread_id})

    state = ConversationStore().load(thread_id)
    assert state is not None
    # last_offer 는 여전히 '내가 던진 질문'이며 사용자의 답이 아니다.
    assert _REPLY not in state.last_offer
