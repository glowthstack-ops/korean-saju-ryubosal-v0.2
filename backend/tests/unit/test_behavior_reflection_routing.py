"""반복 행동 패턴·과거 행동 회고 질문 라우팅 (2026-09-06 데굴님 조건부 승인).

배경: "나는 왜 끝에 가면 항상 이렇게 하나" / "나는 왜 이랬을까" 가 종합운(Q1)으로 떨어져
시점·분야 없음 → too_broad 안내로 끝나 엔진·LLM 호출이 없었다. 반복 표지+이유 표지 → Q8,
중립 과거 회고 → Q5(assess 통과), '작년/재작년' 연 파싱, 디렉티브 부착을 고정한다.
기존 B13 한탄·대운 흐름 설명·택일·시기 탐색 회귀는 그대로 유지돼야 한다.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from saju_api.services import chat_service
from saju_engines.conversation import ConversationEngine
from saju_engines.query_parser import parse_message
from saju_engines.rewriter import assess
from saju_engines.structural_context import (
    BEHAVIOR_PATTERN_DIRECTIVE,
    MANAGE_NOT_OVERCOME_DIRECTIVE,
    RETRO_BEHAVIOR_DIRECTIVE,
)
from saju_engines.time_parser import parse_time
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.conversation import ConversationState
from saju_shared_types.intent import (
    Domain,
    Granularity,
    IntentJson,
    QueryType,
    TimeRange,
)

_TODAY = date(2026, 9, 6)


def _intent(q: str):  # noqa: ANN202 - 파서 반환 타입은 내부 모델이다
    return parse_message(q, _TODAY).intents[0]


# ── 반복 행동 패턴 → Q8(원국 구조), 시점·분야 없이 실행 ──
@pytest.mark.parametrize("question", [
    "나는 왜 끝에 가면 항상 이렇게 하나",
    "나는 왜 마무리를 항상 이런 식으로 하지",
    "왜 매번 결정 직전에 그러는 걸까",
    "나는 왜 연애 끝에 가면 항상 도망치나",
])
def test_behavior_pattern_routes_to_chart_analysis(question: str) -> None:
    intent = _intent(question)
    assert intent.query_type is QueryType.CHART_ANALYSIS, question
    assert assess(intent, question).status == "ok", question


# ── 중립 과거 회고 → Q5, 시점 없어도 assess 통과(과거 10년 창 앵커링) ──
@pytest.mark.parametrize("question", [
    "나는 왜 이랬을까",
    "내가 그때 왜 그랬을까",
    "작년에 내가 왜 그랬을까",
    "그때 나는 왜 그런 선택을 했을까",
])
def test_neutral_past_routes_to_event_explanation(question: str) -> None:
    intent = _intent(question)
    assert intent.query_type is QueryType.EVENT_EXPLANATION, question
    assert assess(intent, question).status == "ok", question


# ── 기존 회귀 유지: 한탄(B13)·흐름 설명·택일·시기 탐색은 새 규칙에 삼켜지지 않는다 ──
@pytest.mark.parametrize(("question", "expected"), [
    ("나는 왜 이렇게 운이 안 좋지", QueryType.EMOTIONAL_SUPPORT),
    ("내 인생은 왜 이럴까", QueryType.EMOTIONAL_SUPPORT),
    ("작년에 왜 그렇게 힘들었을까?", QueryType.EVENT_EXPLANATION),
    ("마무리는 언제 하지", QueryType.TIMING_SEARCH),
    ("오늘 이사 왜 하지", QueryType.DOMAIN_ANALYSIS),  # '오늘'의 '늘'은 반복 표지가 아니다
    ("이사 마무리 잘 될까", QueryType.DOMAIN_ANALYSIS),
])
def test_existing_routes_untouched(question: str, expected: QueryType) -> None:
    assert _intent(question).query_type is expected, question


def test_daewoon_flow_question_not_swallowed() -> None:
    """'지금 대운은 왜 이렇게 흘러가?'는 반복 표지가 없어 새 규칙과 무관(기존 동작 유지)."""
    assert _intent("지금 대운은 왜 이렇게 흘러가?").query_type is not QueryType.CHART_ANALYSIS


# ── '작년/재작년' 연 단위 파싱 ──
def test_last_year_parsing() -> None:
    tr, _ = parse_time("작년에 내가 왜 그랬을까", _TODAY)
    assert tr is not None and tr.start == tr.end == "2025"
    tr2, _ = parse_time("재작년 이직은 왜 했을까", _TODAY)
    assert tr2 is not None and tr2.start == tr2.end == "2024"


# ── 디렉티브 부착(dry_run 프롬프트) ──
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
    birth_place_name="Seoul", gender="male", reference_date="2026-09-06",
)


def _preview(question: str) -> str:
    return chat_service.chat(_BIRTH, question, _TODAY, dry_run=True).prompt_preview or ""


def test_behavior_pattern_directive_attached() -> None:
    preview = _preview("나는 왜 끝에 가면 항상 이렇게 하나")
    assert BEHAVIOR_PATTERN_DIRECTIVE in preview
    assert MANAGE_NOT_OVERCOME_DIRECTIVE in preview
    assert RETRO_BEHAVIOR_DIRECTIVE not in preview
    assert "시주" in preview  # 궁위별 명식 해석 자료(십성·12운성)가 보조 단서로 들어간다


def test_retro_without_context_is_structural() -> None:
    """맥락 없는 '그때 왜 그랬을까' — 고정 시점 후회·평가 질문이라 흐름표·후보·미래 창을 펼치지
    않고 원국 성향 층 + 확인 질문으로 답한다(2026-09-06 데굴님)."""
    preview = _preview("내가 그때 왜 그랬을까")
    assert RETRO_BEHAVIOR_DIRECTIVE in preview
    assert "[회고 모드" in preview  # 기존 회고 시제 디렉티브와 동반
    assert BEHAVIOR_PATTERN_DIRECTIVE not in preview
    assert "[참고 — 질문 기간 외 흐름" not in preview  # 미래 창 참고 블록 없음
    assert "세운 2026" not in preview and "선별:" not in preview  # 시점 창 이벤트 후보 없음
    assert "연도별" not in preview  # 과거 10년 흐름표도 없음


@pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"),
    reason="2턴 재생은 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)
def test_retro_followup_inherits_prior_period() -> None:
    """후속 턴 '그때 왜 그랬을까' — 직전 턴의 시점·도메인을 승계해 그 시기 배경을 쓴다."""
    import uuid

    thread_id = f"t-{uuid.uuid4().hex[:8]}"
    first = chat_service.chat(
        _BIRTH, "2024년 직장운은 어땠어?", _TODAY, dry_run=True, thread_id=thread_id,
    )
    assert first.status == "dry_run"
    second = chat_service.chat(
        _BIRTH, "내가 그때 왜 그랬을까", _TODAY, dry_run=True, thread_id=thread_id,
    )
    assert second.status == "dry_run"
    it = second.intents[0]
    assert it.query_type is QueryType.EVENT_EXPLANATION
    assert it.time_range is not None and (it.time_range.start or "").startswith("2024")
    preview = second.prompt_preview or ""
    assert RETRO_BEHAVIOR_DIRECTIVE in preview
    assert "2024" in preview  # 승계된 시기의 데이터가 배경 신호로 들어간다


def test_plain_personality_question_has_no_pattern_directive() -> None:
    """일반 성격 질문에는 반복 패턴 디렉티브가 붙지 않는다(과잉 부착 방지)."""
    preview = _preview("저는 어떤 사람인가요?")
    assert BEHAVIOR_PATTERN_DIRECTIVE not in preview
    assert MANAGE_NOT_OVERCOME_DIRECTIVE not in preview


# ── 테스트 대화 재생(2026-09-06 데굴님): 7/4 이사 회고 → '계약금 넣은 건 6월 17일' → '왜 이 집' ──
def _relocation_retro_state(*, last_retro: bool) -> ConversationState:
    last = IntentJson(
        intent_id="t1", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.RELOCATION,
        event_key="relocation",
        time_range=TimeRange(
            type="absolute", granularity=Granularity.DAY, start="2026-07-04", end="2026-07-04",
        ),
    )
    return ConversationState(
        thread_id="x", turn_no=1, active_topic=Domain.RELOCATION, last_intent=last,
        last_retro=last_retro,
    )


def test_past_participle_statement_keeps_this_year() -> None:
    """'넣은 건 6월 17일이야' — 과거 관형형 서술은 택일 미래 편향 없이 올해 과거 날짜."""
    tr, _ = parse_time("생각해보면 결정하고 계약금을 넣은건 6월 17일이야", _TODAY)
    assert tr is not None and tr.start == "2026-06-17"


def test_neutral_contract_event_keeps_relocation_thread() -> None:
    """이사 스레드의 계약금 후속 — 사건 기본 도메인(직업)으로 갈아타지 않고 이사 유지."""
    parsed, _s, _r, link = ConversationEngine().process_turn(
        _relocation_retro_state(last_retro=True),
        "생각해보면 결정하고 계약금을 넣은건 6월 17일이야", _TODAY,
    )
    it = parsed.intents[0]
    assert link.is_follow_up
    assert it.domain is Domain.RELOCATION
    assert it.query_type is QueryType.DOMAIN_ANALYSIS  # 직전 의도 승계(총운 리셋 아님)
    assert it.time_range is not None and it.time_range.start == "2026-06-17"


def test_retro_thread_anchors_bare_date_to_past() -> None:
    """회고 스레드의 연도 없는 단답 날짜('6월 17일') — 미래(내년)가 아니라 올해 과거."""
    parsed, _s, _r, _l = ConversationEngine().process_turn(
        _relocation_retro_state(last_retro=True), "6월 17일", _TODAY,
    )
    assert parsed.intents[0].time_range.start == "2026-06-17"


def test_future_thread_keeps_bare_date_future_bias() -> None:
    """회고 스레드가 아니면 기존 택일 미래 편향 유지(회귀 방지)."""
    parsed, _s, _r, _l = ConversationEngine().process_turn(
        _relocation_retro_state(last_retro=False), "6월 17일", _TODAY,
    )
    assert parsed.intents[0].time_range.start == "2027-06-17"


def test_retro_thread_explicit_next_year_not_anchored() -> None:
    """명시 미래 표지('내년 6월 17일')는 회고 스레드여도 그대로 미래."""
    parsed, _s, _r, _l = ConversationEngine().process_turn(
        _relocation_retro_state(last_retro=True), "내년 6월 17일은?", _TODAY,
    )
    assert parsed.intents[0].time_range.start == "2027-06-17"


def test_dated_why_question_matches_neutral_past() -> None:
    """'왜 지난 7월 4일에 이사하기로 했을까' — 왜와 어미 사이가 길어도 중립 회고로 잡힌다."""
    from saju_engines.query_parser import NEUTRAL_PAST_EXPLANATION_RE

    assert NEUTRAL_PAST_EXPLANATION_RE.search("나는 왜 지난 7월 4일에 이사하기로 했을까?")


@pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"),
    reason="3턴 재생은 thread(대화 엔진) 경로 필요 — 테스트 DB 미구성 시 skip",
)
def test_relocation_retro_three_turn_replay() -> None:
    """실제 테스트 대화 3턴 — 시점·도메인·회고 모드·3층 디렉티브가 끝까지 유지된다."""
    import uuid

    thread_id = f"t-{uuid.uuid4().hex[:8]}"
    turns = [
        "나는 왜 지난 7월 4일에 이사하기로 했을까?",
        "생각해보면 결정하고 계약금을 넣은건 6월 17일이야",
        "난 왜 이 집을 선택하기로 했던걸까?",
    ]
    expect_start = ["2026-07-04", "2026-06-17", "2026-06-17"]
    for q, start in zip(turns, expect_start, strict=True):
        r = chat_service.chat(_BIRTH, q, _TODAY, dry_run=True, thread_id=thread_id)
        assert r.status == "dry_run", q
        it = r.intents[0]
        assert it.domain is Domain.RELOCATION, q
        assert it.time_range is not None and it.time_range.start == start, q
        preview = r.prompt_preview or ""
        assert "[회고 모드" in preview, q  # 미래 서술로 새지 않는다
        assert "2027-06-17" not in preview, q  # 미래로 오인된 계약일 데이터 없음
    assert RETRO_BEHAVIOR_DIRECTIVE in preview  # 마지막 '왜 이 집' 턴에 3층 규칙
