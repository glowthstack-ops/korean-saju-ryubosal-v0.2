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


def test_activity_directive_is_decisive_and_short() -> None:
    from saju_engines.question_frame import ACTIVITY_JUDGMENT_DIRECTIVE

    text = ACTIVITY_JUDGMENT_DIRECTIVE.format(topic="오늘 운동")
    assert "'오늘 운동'을(를)" in text and "3문장" in text
    assert "확정형 판정" in text and "완곡형 금지" in text
    assert "해도 돼요 / 가볍게 조절해서 하면 돼요 / 오늘은 미루는 게 좋아요" in text


# ── 시제·대상 shadow 필드(2026-10-28 데굴님 "분류 모델 병행은 제외하고 진행") ─────────


def test_parse_frame_shadow_fields_default_and_normalize() -> None:
    from saju_shared_types.question_frame import SubjectFrame, TimeDirection

    # 구 형식 출력(두 키 없음) → 기본값, 라우팅 필드는 그대로
    old = parse_frame(_LUNCH)
    assert old is not None
    assert old.time_direction is TimeDirection.NONE
    assert old.subject_frame is SubjectFrame.UNSPECIFIED and old.mentioned_people == []
    # 집합 밖 값·비목록 지칭은 기본값으로, 목록은 상한·중복 정리
    raw = (
        '{"ask_kind":"judgment","lifestyle_item":"none","answer_shape":"analysis",'
        '"brevity":"normal","topic_object":"x","time_direction":"yesterday",'
        '"subject_frame":"me","mentioned_people":"남편"}'
    )
    f = parse_frame(raw)
    assert f is not None and f.time_direction is TimeDirection.NONE
    assert f.subject_frame is SubjectFrame.UNSPECIFIED and f.mentioned_people == []
    raw2 = raw.replace('"yesterday"', '"wish"').replace('"me"', '"self_explicit"').replace(
        '"남편"', '["남편","남편",3,"아들"," ","a","b","c","d"]'
    )
    f2 = parse_frame(raw2)
    assert f2 is not None and f2.time_direction is TimeDirection.WISH
    assert f2.subject_frame is SubjectFrame.SELF_EXPLICIT
    assert f2.mentioned_people == ["남편", "아들", "a", "b", "c"]


def test_schema_prompt_cover_shadow_fields() -> None:
    from saju_shared_types.question_frame import SubjectFrame, TimeDirection

    schema = frame_json_schema()
    assert set(schema["properties"]["time_direction"]["enum"]) == {e.value for e in TimeDirection}
    assert set(schema["properties"]["subject_frame"]["enum"]) == {e.value for e in SubjectFrame}
    for key in ("time_direction", "subject_frame", "mentioned_people", "wish", "self_explicit"):
        assert key in QUESTION_FRAME_SYSTEM


def test_disagreement_time_direction_vs_rule_retro() -> None:
    from saju_shared_types.question_frame import TimeDirection

    intent = parse_message("그냥 일 적당히 있었으면 좋겠어", _TODAY).intents[0]
    wish = QuestionFrame(time_direction=TimeDirection.WISH)
    # 룰이 회고로 봤는데 프레임은 바람 → 후보 라벨 / 룰이 미래면 라벨 없음 / 대조값 없으면 생략
    assert frame_disagreements(wish, intent, rule_retro=True) == ["time_rule_past_vs_frame_wish"]
    # 창 구조 판정('5월은 어때?' — 오늘이 10월)은 룰이 맞다 → 게이트 후보군과 분리된 라벨
    assert frame_disagreements(
        QuestionFrame(time_direction=TimeDirection.FUTURE), intent,
        rule_retro=True, rule_time_reason="window_past",
    ) == ["time_window_past_vs_frame_future"]
    assert frame_disagreements(
        QuestionFrame(time_direction=TimeDirection.FUTURE), intent,
        rule_retro=True, rule_time_reason="past_phrase",
    ) == ["time_rule_past_vs_frame_future"]
    assert frame_disagreements(wish, intent, rule_retro=False) == []
    assert frame_disagreements(wish, intent) == []
    past = QuestionFrame(time_direction=TimeDirection.PAST)
    assert frame_disagreements(past, intent, rule_retro=False) == ["time_rule_future_vs_frame_past"]
    assert frame_disagreements(past, intent, rule_retro=True) == []


def test_disagreement_subject_frame_vs_rule() -> None:
    from saju_engines.question_frame import rule_subject_frame
    from saju_shared_types.intent import SubjectKind, SubjectMode, SubjectRef
    from saju_shared_types.question_frame import SubjectFrame

    base = parse_message("2027년 내가 이직을 하게 된다면 어느 쪽 회사가 좋아?", _TODAY).intents[0]
    assert rule_subject_frame(base) == "self"
    hus = SubjectRef(kind=SubjectKind.COMPANION, label="남편", companion_id="h1")
    me = SubjectRef(kind=SubjectKind.SELF, label="본인")
    inherited = base.model_copy(update={"subjects": [hus]})
    assert rule_subject_frame(inherited) == "companion_single"
    frame = QuestionFrame(subject_frame=SubjectFrame.SELF_EXPLICIT)
    # 룰이 직전 동반자를 상속한 턴에 프레임이 1인칭 명시 → 본인 복귀 놓침 후보 두 라벨
    assert frame_disagreements(frame, inherited, rule_subject_inherited=True) == [
        "subject_frame_self_vs_rule_companion_single", "subject_self_on_inherited",
    ]
    assert frame_disagreements(frame, inherited, rule_subject_inherited=False) == [
        "subject_frame_self_vs_rule_companion_single",
    ]
    assert frame_disagreements(frame, base) == []
    # 프레임이 동반자군인데 룰은 본인 → 미등록 지칭 후보
    assert frame_disagreements(QuestionFrame(subject_frame=SubjectFrame.COMPANIONS_ONLY), base) == [
        "subject_frame_companions_only_vs_rule_self",
    ]
    # 본인 포함/제외 모양 불일치
    pair = base.model_copy(update={"subjects": [me, hus], "subject_mode": SubjectMode.PAIRWISE})
    assert rule_subject_frame(pair) == "self_with_companions"
    assert frame_disagreements(QuestionFrame(subject_frame=SubjectFrame.COMPANIONS_ONLY), pair) == [
        "subject_frame_companions_only_vs_rule_self_with_companions",
    ]
    excl = base.model_copy(update={
        "subjects": [hus, SubjectRef(kind=SubjectKind.COMPANION, label="아들", companion_id="s1")],
        "subject_mode": SubjectMode.COMPARE_EXCLUDE_SELF,
    })
    assert rule_subject_frame(excl) == "companions_only"
    only = QuestionFrame(subject_frame=SubjectFrame.COMPANIONS_ONLY)
    assert frame_disagreements(only, excl) == []
    assert frame_disagreements(QuestionFrame(subject_frame=SubjectFrame.UNSPECIFIED), excl) == []


def test_resolution_inherited_flag() -> None:
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState
    from saju_shared_types.intent import SubjectKind, SubjectRef

    eng = ConversationEngine()
    fresh = eng.resolve_subjects(ConversationState(thread_id="t"), "내년 재물운 어때?", _TODAY)
    assert fresh.inherited is False  # 직전 대상 없음 → 본인 기본값(상속 아님)
    st = ConversationState(
        thread_id="t",
        active_subjects=[SubjectRef(kind=SubjectKind.COMPANION, label="남편", companion_id="h1")],
    )
    assert eng.resolve_subjects(st, "내년 재물운 어때?", _TODAY).inherited is True
    assert eng.resolve_subjects(st, "내가 내년에 이직할까?", _TODAY).inherited is False


def test_observe_sync_carries_rule_contrast_values(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(role: str, system: str, prompt: str, **kw: Any) -> tuple[str, int, int]:
        return (
            '{"ask_kind":"venting","lifestyle_item":"none","answer_shape":"empathy_first",'
            '"brevity":"normal","topic_object":"업무량","time_direction":"wish",'
            '"subject_frame":"unspecified","mentioned_people":[]}', 600, 40,
        )

    monkeypatch.setattr(llm_client, "call_role_raw", fake_call)
    q = "그냥 일 적당히 있었으면 좋겠어"
    intent = parse_message(q, _TODAY).intents[0]
    shadow = question_frame_service.observe_sync(
        q, intent, rule_retro=True, rule_subject_inherited=False,
    )
    assert shadow.ok and shadow.rule_time_direction == "past"
    assert shadow.rule_subject_frame == "self"
    assert shadow.rule_subject_inherited is False
    assert "time_rule_past_vs_frame_wish" in shadow.disagreements
    none = question_frame_service.observe_sync(q, intent)
    assert none.rule_time_direction is None and none.rule_subject_inherited is None


def test_time_direction_reason_labels() -> None:
    from saju_api.services.chat_service import _question_time_direction_reason as reason

    i = parse_message("5월은 어때?", _TODAY).intents[0]
    assert reason("5월은 어때?", i, None, _TODAY) == (True, "window_past")
    i = parse_message("작년에 왜 힘들었을까", _TODAY).intents[0]
    assert reason("작년에 왜 힘들었을까", i, None, _TODAY)[1] in (
        "window_past", "past_phrase", "event_explanation",
    )
    i = parse_message("몸이 예전 같지 않은데 괜찮아질까?", _TODAY).intents[0]
    assert reason("몸이 예전 같지 않은데 괜찮아질까?", i, None, _TODAY) == (True, "past_phrase")
    i = parse_message("그냥 일 적당히 있었으면 좋겠어", _TODAY).intents[0]
    assert reason("그냥 일 적당히 있었으면 좋겠어", i, None, _TODAY)[0] is False
    i = parse_message("이직 제안 언제쯤 들어올까?", _TODAY).intents[0]
    assert reason("이직 제안 언제쯤 들어올까?", i, None, _TODAY) == (False, "future_phrase")
