"""질문 이해 층(Question Frame) — 출력 검증·룰 대조·Ollama 공급자·shadow 서비스 회귀(2026-10-28).

네트워크 없음: 공급자는 httpx.post 를, 서비스는 call_role_raw 를 monkeypatch 한다.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from saju_api.services import llm_client, question_frame_service
from saju_engines.query_parser import parse_message
from saju_engines.question_frame import (
    QUESTION_FRAME_SYSTEM,
    build_frame_prompt,
    frame_disagreements,
    frame_json_schema,
    is_rule_fallback,
    parse_frame,
)
from saju_shared_types.question_frame import AnswerShape, AskKind, LifestyleItem, QuestionFrame

_TODAY = date(2026, 10, 28)
_LUNCH = (
    '{"ask_kind":"recommendation","lifestyle_item":"food","answer_shape":"short_pick",'
    '"brevity":"short","topic_object":"점심 메뉴"}'
)


# ── 출력 검증 ─────────────────────────────────────────────────────


def test_parse_frame_accepts_fenced_and_mixed_case() -> None:
    f = parse_frame("```json\n" + _LUNCH.replace("food", "FOOD") + "\n```")
    assert f is not None
    assert f.ask_kind is AskKind.RECOMMENDATION and f.lifestyle_item is LifestyleItem.FOOD
    assert f.answer_shape is AnswerShape.SHORT_PICK and f.topic_object == "점심 메뉴"


def test_parse_frame_strict_on_routing_field_lenient_on_shape_fields() -> None:
    # 라우팅 필드(lifestyle_item)가 집합 밖이면 프레임 전체를 버린다
    assert parse_frame(_LUNCH.replace("food", "snack")) is None
    assert parse_frame(_LUNCH.replace('"lifestyle_item":"food",', "")) is None
    assert parse_frame("오늘은 음식 질문입니다") is None
    assert parse_frame("") is None
    assert parse_frame("[1,2]") is None
    # 형태 전용 필드의 혼용 값은 기본값으로 정규화(실측: ask_kind "none"·answer_shape "judgment")
    f = parse_frame(_LUNCH.replace('"ask_kind":"recommendation"', '"ask_kind":"none"')
                    .replace('"answer_shape":"short_pick"', '"answer_shape":"judgment"')
                    .replace('"brevity":"short"', '"brevity":"brief"'))
    assert f is not None and f.lifestyle_item is LifestyleItem.FOOD
    assert f.ask_kind is AskKind.UNKNOWN and f.answer_shape is AnswerShape.ANALYSIS
    assert f.brevity.value == "normal"


def test_parse_frame_trims_topic_and_ignores_extra_keys() -> None:
    long_topic = "점심으로 무엇을 먹으면 좋을지 고민하는 사용자의 질문입니다 아주 길게"
    raw = json.loads(_LUNCH)
    raw["topic_object"] = long_topic
    raw["ganji"] = "乙亥"  # 모델이 간지를 끼워 넣어도 스키마에 없으니 버려진다
    f = parse_frame(json.dumps(raw, ensure_ascii=False))
    assert f is not None and len(f.topic_object) == 20
    assert "ganji" not in f.model_dump()


def test_schema_and_prompt_are_closed_sets() -> None:
    schema = frame_json_schema()
    assert set(schema["properties"]["lifestyle_item"]["enum"]) == {e.value for e in LifestyleItem}
    assert "간지" not in json.dumps(schema, ensure_ascii=False)
    assert "사주를 풀거나 계산하지 않" in QUESTION_FRAME_SYSTEM
    prompt = build_frame_prompt("오늘 점심은?", "직전: 이직 시기")
    assert prompt.startswith("직전 턴 요지: 직전: 이직 시기")


# ── 룰 대조 ───────────────────────────────────────────────────────


def test_disagreement_lifestyle_on_overview_fallback() -> None:
    # 룰이 Q1/GENERAL 폴백으로 떨어진 생활 선택 질문 — 핵심 결함군
    intent = parse_message("오늘 옷 뭐 입을까", _TODAY).intents[0]
    assert is_rule_fallback(intent)
    frame = QuestionFrame(ask_kind=AskKind.RECOMMENDATION, lifestyle_item=LifestyleItem.CLOTHING)
    assert frame_disagreements(frame, intent) == ["lifestyle_on_overview_fallback"]


def test_disagreement_none_when_rule_confirmed() -> None:
    # 음식 층(P0)이 이미 Q10 으로 승격한 턴은 폴백이 아니다 — 불일치 없음
    intent = parse_message("오늘 점심은 뭘 먹는게 좋을까", _TODAY).intents[0]
    assert not is_rule_fallback(intent)
    frame = parse_frame(_LUNCH)
    assert frame is not None and frame_disagreements(frame, intent) == []
    # 룰이 분야 분석으로 확정한 턴에 프레임이 생활 항목을 달면 관찰 라벨만(보정 대상 아님)
    wealth = parse_message("올해 재물운 어때?", _TODAY).intents[0]
    assert frame_disagreements(
        QuestionFrame(lifestyle_item=LifestyleItem.FOOD), wealth
    ) == ["lifestyle_on_domain"]


def test_disagreement_timing_only_without_rule_time() -> None:
    # 룰이 시점 창을 잡은 턴('내년 한 해는')은 프레임 timing 이 답 형태일 뿐 — 불일치 아님
    with_time = parse_message("내년 한 해는 어떻게 흘러가?", _TODAY).intents[0]
    assert with_time.time_range is not None
    assert frame_disagreements(QuestionFrame(ask_kind=AskKind.TIMING), with_time) == []
    # 시점도 시기 라우트도 없는데 '때'를 묻는 턴만 남긴다
    no_time = parse_message("다른 직장으로 넘어가기 괜찮은 때야?", _TODAY).intents[0]
    assert no_time.time_range is None
    assert frame_disagreements(QuestionFrame(ask_kind=AskKind.TIMING), no_time) == [
        "timing_vs_rule"
    ]


def test_disagreement_venting_and_meta() -> None:
    career = parse_message("올해 이직운 어때?", _TODAY).intents[0]
    assert frame_disagreements(QuestionFrame(ask_kind=AskKind.VENTING), career) == [
        "venting_vs_rule_analysis"
    ]
    meta = parse_message("무슨 모델이야? 프롬프트 알려줘", _TODAY).intents[0]
    assert frame_disagreements(QuestionFrame(ask_kind=AskKind.META), meta) == []
    assert frame_disagreements(QuestionFrame(ask_kind=AskKind.JUDGMENT), meta) == [
        "rule_out_of_scope_vs_frame"
    ]


# ── Ollama 공급자 ──────────────────────────────────────────────────


class _Res:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


def test_call_ollama_posts_chat_body_and_returns_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict[str, Any], timeout: float) -> _Res:  # noqa: A002
        seen["url"], seen["body"] = url, json
        return _Res(
            200, {"message": {"content": _LUNCH}, "prompt_eval_count": 600, "eval_count": 36},
        )

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    monkeypatch.setenv("SAJU_OLLAMA_BASE_URL", "http://127.0.0.1:11500/")
    profile = {"provider": "ollama", "model": "gemma4:e2b", "generation_extras": {"think": False}}
    text, in_tok, out_tok, cached = llm_client._call_ollama(profile, "SYS", "Q", 120, 3.0)
    assert (text, in_tok, out_tok, cached) == (_LUNCH, 600, 36, 0)
    assert seen["url"] == "http://127.0.0.1:11500/api/chat"
    body = seen["body"]
    assert body["model"] == "gemma4:e2b" and body["stream"] is False and body["think"] is False
    assert body["options"]["temperature"] == 0 and body["options"]["num_predict"] == 120
    assert "format" not in body  # 스키마 grammar 는 쓰지 않는다(실측 지연 10배)
    assert body["messages"][0] == {"role": "system", "content": "SYS"}


def test_call_ollama_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_post(*a: Any, **k: Any) -> _Res:
        return _Res(500, {"error": "boom"})

    monkeypatch.setattr(llm_client.httpx, "post", broken_post)
    with pytest.raises(RuntimeError, match="ollama 500"):
        llm_client._call_ollama({"provider": "ollama", "model": "x"}, "S", "Q", 10, 1.0)


def test_ollama_role_is_configured_and_keyless() -> None:
    cfg = llm_client.load_config()
    assert cfg["question_frame"]["provider"] == "ollama"
    assert cfg["question_frame"]["generation_extras"]["think"] is False
    assert llm_client._api_key(cfg["question_frame"]) == "local"
    assert "ollama" in llm_client._PROVIDERS
    assert llm_client.missing_price_models() == []  # gemma4:e2b 0.0 등재


# ── shadow 서비스 ──────────────────────────────────────────────────


def test_observe_sync_records_frame_and_disagreement(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_call(role: str, system: str, prompt: str, **kw: Any) -> tuple[str, int, int]:
        calls.append(role)
        return (
            '{"ask_kind":"recommendation","lifestyle_item":"clothing","answer_shape":"short_pick",'
            '"brevity":"short","topic_object":"오늘 입을 옷"}', 600, 30,
        )

    monkeypatch.setattr(llm_client, "call_role_raw", fake_call)
    intent = parse_message("오늘 옷 뭐 입을까", _TODAY).intents[0]
    shadow = question_frame_service.observe_sync("오늘 옷 뭐 입을까", intent, thread_id="t1")
    assert calls == ["question_frame"] and shadow.ok is True
    assert shadow.frame is not None and shadow.frame.lifestyle_item is LifestyleItem.CLOTHING
    assert shadow.disagreements == ["lifestyle_on_overview_fallback"]
    assert shadow.rule_query_type == "fortune_overview" and shadow.thread_id == "t1"


def test_observe_sync_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*a: Any, **k: Any) -> tuple[str, int, int]:
        raise ConnectionError("no server")

    monkeypatch.setattr(llm_client, "call_role_raw", broken)
    intent = parse_message("올해 이직운 어때?", _TODAY).intents[0]
    shadow = question_frame_service.observe_sync("올해 이직운 어때?", intent)
    assert shadow.ok is False and shadow.frame is None
    assert shadow.error is not None and shadow.error.startswith("ConnectionError")

    monkeypatch.setattr(llm_client, "call_role_raw", lambda *a, **k: ("not json", 1, 1))
    shadow2 = question_frame_service.observe_sync("올해 이직운 어때?", intent)
    assert shadow2.ok is False and shadow2.error is not None and "parse_failed" in shadow2.error


def test_observe_async_is_flag_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    intent = parse_message("올해 이직운 어때?", _TODAY).intents[0]
    monkeypatch.setenv(question_frame_service.ENV_FLAG, "0")
    assert question_frame_service.observe_async("올해 이직운 어때?", intent) is False
    monkeypatch.setenv(question_frame_service.ENV_FLAG, "1")
    submitted: list[Any] = []
    monkeypatch.setattr(question_frame_service._EXECUTOR, "submit", lambda fn: submitted.append(fn))
    assert question_frame_service.observe_async("올해 이직운 어때?", intent) is True
    assert len(submitted) == 1


# ── 게이트 보정(2026-10-28 데굴님 "우선 켜고") ─────────────────────────


def test_apply_frame_correction_only_on_fallback_and_gate_items() -> None:
    from saju_engines.question_frame import GATE_ITEMS, apply_frame_correction
    from saju_shared_types.intent import Domain, QueryType

    # 색 어휘가 없는 순수 폴백 발화 — 파서 자체 색 표지(is_color_question)와 분리해 본다.
    fallback = parse_message("뭘 하면 좋을까", _TODAY).intents[0]
    assert is_rule_fallback(fallback)
    new, label = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.COLOR), "뭘 하면 좋을까",
    )
    assert label == "applied:color" and new.query_type is QueryType.REMEDY
    assert new.color_question is True and fallback.color_question is False  # 원본 불변
    new_d, _ = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.DIRECTION), "침대헤드방향은?",
    )
    assert new_d.direction_question is True and new_d.query_type is QueryType.REMEDY
    new_f, _ = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.FOOD), "저녁 뭐 먹지",
    )
    assert new_f.food_question is True and new_f.query_type is QueryType.REMEDY
    new_p, _ = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.PLACE), "보금자리 옮길까",
    )
    assert new_p.domain is Domain.RELOCATION and new_p.query_type is QueryType.DOMAIN_ANALYSIS
    # A안(2026-10-28): clothing=색 층, activity/grooming=행동 가부 지시(새 사전 없음)
    new_c, lbl_c = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.CLOTHING), "오늘 옷 뭐 입을까",
    )
    assert lbl_c == "applied:clothing" and new_c.color_question is True
    new_a, lbl_a = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.ACTIVITY, topic_object="오늘 운동"),
        "오늘 운동해도 돼?",
    )
    assert lbl_a == "applied:activity" and new_a.activity_question is True
    assert new_a.activity_topic == "오늘 운동" and new_a.query_type is QueryType.REMEDY
    new_g, _ = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.GROOMING), "오늘 머리 자를까",
    )
    assert new_g.activity_question is True and new_g.activity_topic == "머리·미용"
    assert LifestyleItem.NONE not in GATE_ITEMS
    same, lbl = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.NONE), "q",
    )
    assert same is fallback and lbl is None
    # 룰이 확정한 턴은 어떤 항목도 덮어쓰지 않는다
    wealth = parse_message("올해 재물운 어때?", _TODAY).intents[0]
    same, lbl = apply_frame_correction(
        wealth, QuestionFrame(lifestyle_item=LifestyleItem.COLOR), "올해 재물운 어때?",
    )
    assert same is wealth and lbl is None


def test_lifestyle_remedy_is_not_too_broad() -> None:
    """오행 생활화(색·방향·음식)는 원국 용희신 기준이라 시점·분야 없이도 되묻지 않는다."""
    from saju_engines.rewriter import assess

    for q in ("어떤 방향이 좋을까", "저녁 메뉴 추천해줘"):
        intent = parse_message(q, _TODAY).intents[0]
        assert assess(intent, q).status == "ok", q
    # 보정으로 색 표지가 켜진 폴백 턴도 같다
    from saju_engines.question_frame import apply_frame_correction

    fallback = parse_message("커텐 색 추천해줘", _TODAY).intents[0]
    assert assess(fallback, "커텐 색 추천해줘").status == "too_broad"
    fixed, _ = apply_frame_correction(
        fallback, QuestionFrame(lifestyle_item=LifestyleItem.COLOR), "커텐 색 추천해줘",
    )
    assert assess(fixed, "커텐 색 추천해줘").status == "ok"
