"""대화형 통변 파이프라인 E2E (v2.2 MVP — 단일 질문 → 정확한 풀이).

LLM 실호출 없이 검증한다: dry-run은 직렬화된 LLM 입력 본문을 반환하고, 실호출 경로는
모의 클라이언트로 대체한다. 정책 라우트/too_broad는 엔진·LLM 미호출 즉시 응답.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from saju_api.main import app
from saju_api.services import chat_service, llm_client
from saju_shared_types.birth_input import BirthInput

client = TestClient(app)

_BIRTH = {
    "calendar_type": "solar",
    "birth_date": "1980-11-22",
    "birth_time": "09:08",
    "birth_place_name": "서울",
    "gender": "male",
}


def _post(question: str, **extra):
    return client.post("/api/v2/chat", json={
        "birth": _BIRTH, "question": question, "today": "2026-06-11",
        "dry_run": True, **extra,
    })


# ── 분석 라우트 (dry-run E2E) ────────────────────────────────────


def test_career_question_produces_guarded_prompt() -> None:
    """이직 질문 → 후보·간지·근거가 담긴 LLM 입력이 한도 내로 직렬화된다."""
    res = _post("올해 이직운 어때?")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "dry_run"
    assert body["candidate_count"] >= 1
    assert 0 < body["input_tokens"] <= 12_000  # chat_single 한도(docs/09 8장 v2.2.1)
    preview = body["prompt_preview"]
    for section in ("[원국·명식 구조", "[간지달력(압축)]", "[이벤트 후보", "[근거 경로]", "[지시]"):
        assert section in preview
    # 계산 금지 고지(절대 원칙 1)는 base instruction의 '명리 계산을 시도하지 말 것'에 유지.
    assert "명리 계산을 시도하지 말 것" in preview


def test_intent_metadata_round_trip() -> None:
    """응답에 파싱된 intent(분류·도메인·시점)가 동반된다."""
    res = _post("올해 이직운 어때?")
    intent = res.json()["intents"][0]
    assert intent["query_type"] == "domain_analysis"
    assert intent["domain"] == "career"
    assert intent["time_range"]["start"] == "2026"


# ── 정책 라우트 (T3.8 — 엔진·LLM 미호출) ─────────────────────────


def test_lotto_number_refused_with_alternative() -> None:
    """로또 번호 요청 → 거부 + 날짜·방향 대안 제시(G6)."""
    res = _post("로또번호도 찍어줄 수 있나? ㅋㅋㅋ")
    body = res.json()
    assert body["status"] == "policy"
    assert "로또 번호 생성" in body["answer"] and "날짜" in body["answer"]


def test_emotional_support_routes_empathy() -> None:
    """감정 토로 → 공감 우선, 풀이는 동의 시에만(B13/G1)."""
    res = _post("아빠는 너무 날 혼내 그래서 너무 스트레스야")
    body = res.json()
    assert body["status"] == "policy"
    assert "힘드셨" in body["answer"]


# ── 판정 라우트 (T3.2) ───────────────────────────────────────────


def test_too_broad_returns_suggestions() -> None:
    """무시점·무분야 → too_broad + 실행 가능한 재작성 제안(거절 아님)."""
    res = _post("앞으로 내 운세 알려줘")
    body = res.json()
    assert body["status"] == "too_broad"
    assert "좁혀볼까요" in body["answer"]
    assert len(body["assessment"]["rewrite_suggestions"]) == 3


# ── 실호출 경로 (모의 LLM) ───────────────────────────────────────


def test_answered_with_mocked_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """API 키가 있을 때: 가드 통과 본문으로 LLM 호출 → answered."""
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    captured: dict = {}

    def fake_reading(prompt_text: str, call_type: str = "chat_single", **kw) -> str:
        captured["prompt"] = prompt_text
        captured["call_type"] = call_type
        return "2024년 甲辰년에 직업 변화 에너지가 활성화됩니다(모의 응답)."

    monkeypatch.setattr(llm_client, "generate_reading", fake_reading)

    birth = BirthInput(reference_date="2026-06-11", **_BIRTH)
    res = chat_service.chat(birth, "올해 이직운 어때?", date(2026, 6, 11))
    assert res.status == "answered"
    assert res.answer is not None and "모의 응답" in res.answer
    assert captured["call_type"] == "chat_single"
    assert "[이벤트 후보" in captured["prompt"]  # LLM이 받은 것은 '설명할 결론'


def test_no_api_key_falls_back_to_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """키 미설정이면 dry_run으로 안전 폴백(실호출 시도 없음)."""
    monkeypatch.setattr(llm_client, "is_available", lambda: False)
    birth = BirthInput(reference_date="2026-06-11", **_BIRTH)
    res = chat_service.chat(birth, "올해 이직운 어때?", date(2026, 6, 11))
    assert res.status == "dry_run" and res.prompt_preview is not None


# ── 멀티턴 (Phase 4 연동 — 전용 DB 필요 시 skip) ──────────────────


def _db_available() -> bool:
    from saju_engines.conversation_store import ConversationStore
    from saju_engines.precompute_store import default_dsn

    try:
        ConversationStore(
            default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"
        ).migrate()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_available(), reason="saju-v2-db(5433) 미기동")
def test_multiturn_thread_inherits_domain() -> None:
    """멀티턴: '올해 연애운' → '5월은 어때?'가 연애 도메인을 상속한다(B2/F2)."""
    from saju_engines.conversation_store import ConversationStore
    from saju_engines.precompute_store import default_dsn

    store = ConversationStore(
        default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"
    )
    store.delete("t-e2e")
    birth = BirthInput(reference_date="2026-06-11", **_BIRTH)

    first = chat_service.chat(
        birth, "올해 연애운 어때?", date(2026, 6, 11),
        dry_run=True, thread_id="t-e2e", store=store,
    )
    assert first.thread_id == "t-e2e" and first.turn_no == 1

    second = chat_service.chat(
        birth, "5월은 어때?", date(2026, 6, 11),
        dry_run=True, thread_id="t-e2e", store=store,
    )
    assert second.turn_no == 2
    intent = second.intents[0]
    assert intent.domain.value == "relationship"  # 도메인 상속
    assert intent.time_range is not None and intent.time_range.start == "2026-05"
    store.delete("t-e2e")


@pytest.mark.skipif(not _db_available(), reason="saju-v2-db(5433) 미기동")
def test_multiturn_repeat_flag() -> None:
    """동일 질문 3연속 → repeated=True(다른 각도 제시 신호, F7)."""
    from saju_engines.conversation_store import ConversationStore
    from saju_engines.precompute_store import default_dsn

    store = ConversationStore(
        default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"
    )
    store.delete("t-repeat")
    birth = BirthInput(reference_date="2026-06-11", **_BIRTH)
    last = None
    for _ in range(3):
        last = chat_service.chat(
            birth, "올해 이직운 어때?", date(2026, 6, 11),
            dry_run=True, thread_id="t-repeat", store=store,
        )
    assert last is not None and last.repeated is True
    store.delete("t-repeat")
