"""한탄·자조형 감정 토로 인식 (B13 확장, 2026-08-03).

관측된 미스: **"나한테 좋은 운은 왜 하나도 없을까"** 가 `fortune_overview` 로 분류돼
시점·분야가 없다는 이유로 범위 좁히기 메뉴("질문 범위가 넓어요 …")로 빠졌다. 사용자가
원한 것은 선택지가 아니라 "왜" 에 대한 응답이다.

원인은 둘이었다.

    키워드가 좁다      스트레스·힘들[어다]·고장나서·우울 뿐 — 한탄 어법이 없다
                       활용형도 놓친다("힘들지" 는 `힘들[어다]` 에 안 걸린다)
    물음표로 갈랐다     `"?" not in text` — docs/08 B13 은 "질문 없이 서사만 있는 경우
                       **포함**" 이라 질문이 있으면 B13 이 아니라는 뜻이 아니다

넓히면서 삼키지 말아야 할 것이 두 종류 있다. 그래서 한탄 어법은 **도메인·명리 용어가
없을 때만** 적용한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_engines.query_parser import parse_message
from saju_engines.rewriter import assess
from saju_shared_types.intent import QueryType

_TODAY = date(2026, 8, 3)


def _intent(question: str):  # noqa: ANN202 - 파서 반환 타입은 내부 모델이다
    return parse_message(question, _TODAY).intents[0]


# ── 한탄·자조 → 공감 우선 ────────────────────────────────────────────────


@pytest.mark.parametrize("question", [
    "나한테 좋은 운은 왜 하나도 없을까",   # 관측된 원 사례
    "왜 나는 되는 일이 없을까",
    "내 인생은 왜 이럴까",
    "나는 왜 이렇게 운이 안 좋지",         # '나 → 왜' 어순
    "좋은 운이 하나도 없어요",
    "뭐 하나 제대로 되는 게 없어",
])
def test_lament_is_emotional_support(question: str) -> None:
    """도메인 없는 한탄은 B13 이다 — 범위 좁히기 메뉴로 빠지지 않는다."""
    assert _intent(question).query_type is QueryType.EMOTIONAL_SUPPORT
    assert assess(_intent(question), question).status == "ok"


@pytest.mark.parametrize("question", [
    "요즘 왜 이렇게 힘들지",   # 활용형 — `힘들[어다]` 로는 안 걸렸다
    "너무 힘들어",
    "사는 게 너무 힘들다",
    "너무 지치네요",
    "요즘 사는 게 버겁다",
])
def test_emotion_word_inflections_are_covered(question: str) -> None:
    assert _intent(question).query_type is QueryType.EMOTIONAL_SUPPORT


@pytest.mark.parametrize("question", [
    "작년에 왜 그렇게 힘들었을까?",
    "내가 무직에 취직도 안되어서 힘들때가 있었는데 언제인지 맞춰봐",
])
def test_past_tense_narrative_is_not_emotional_support(question: str) -> None:
    """과거형·관형형은 감정 토로가 아니다 — 과거 사건 설명·시점 되짚기다.

    어미를 열거하지 않고 어간 `힘들` 을 그대로 넣었더니 이 둘을 삼켜 기존 회귀가
    깨졌다(실측). 넓히기의 경계를 여기서 고정한다.
    """
    assert _intent(question).query_type is QueryType.EVENT_EXPLANATION


@pytest.mark.parametrize("question", [
    # 2026-09-11 실로그 — 변화 예측('힘들어질까·힘들어지면')은 감정 토로가 아니라 분석 질문이다.
    "아 내 위의 리더가 다른팀으로가는데 그럼 나의업무 방향은 더 힘들어질까? 10월부터",
    "앞으로 더 힘들어지면 어떡하지",
])
def test_change_prediction_is_not_emotional_support(question: str) -> None:
    assert _intent(question).query_type is not QueryType.EMOTIONAL_SUPPORT


def test_question_mark_does_not_flip_the_classification() -> None:
    """물음표 하나로 판정이 뒤집히지 않는다.

    이전에는 `"?" not in text` 라서 같은 문장이 물음표 유무로 공감/메뉴로 갈렸다.
    """
    without = _intent("너무 스트레스야")
    with_mark = _intent("너무 스트레스야 어떻게 해야 할까?")
    assert without.query_type is QueryType.EMOTIONAL_SUPPORT
    assert with_mark.query_type is QueryType.EMOTIONAL_SUPPORT


# ── 삼키면 안 되는 것 ────────────────────────────────────────────────────


@pytest.mark.parametrize(("question", "expected"), [
    ("왜 나는 연애운이 없을까", QueryType.DOMAIN_ANALYSIS),
    ("이직이 왜 이렇게 안 될까", QueryType.DOMAIN_ANALYSIS),
    ("왜 이렇게 돈이 안 모일까", QueryType.DOMAIN_ANALYSIS),
])
def test_domain_bearing_lament_stays_domain_analysis(
    question: str, expected: QueryType,
) -> None:
    """분야를 지목한 한탄은 사용자가 이미 연결한 것이다.

    B13 파생 규칙이 "도메인 연결은 사용자가 원할 때만" 이므로, 분야가 있으면 공감으로
    대체하지 않고 기존 분야 분석(기본 기간 적용)을 유지한다.
    """
    assert _intent(question).query_type is expected
    assert assess(_intent(question), question).status == "apply_default_period"


@pytest.mark.parametrize("question", [
    "내 대운은 왜 이렇게 안 좋아?",
    "지금 대운은 왜 이렇게 흘러가?",
    "내 용신은 왜 힘을 못 쓰지?",
    "내 격국은 왜 이렇게 판정됐어?",
])
def test_chart_term_questions_are_not_swallowed(question: str) -> None:
    """명리 용어가 있으면 명식 구조 질문이다 — 공감으로 대체하면 안 된다."""
    assert _intent(question).query_type is not QueryType.EMOTIONAL_SUPPORT


@pytest.mark.parametrize("question", [
    "앞으로 내 운세 알려줘",   # 범위 없는 일반 요청 — 메뉴가 맞다
    "언제쯤 좋아질까?",        # 시점 질문
    "올해 운은 어때?",
])
def test_ordinary_requests_keep_their_routes(question: str) -> None:
    """한탄이 아닌 요청은 그대로 둔다 — too_broad 메뉴 자체는 유효한 계약이다."""
    assert _intent(question).query_type is not QueryType.EMOTIONAL_SUPPORT
