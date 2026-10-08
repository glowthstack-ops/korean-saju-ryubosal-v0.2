"""기간 블록의 시점 지칭 회귀 (2026-08-06).

관측: '내일 운세를 알려줘' 답변이 "오늘 하루는…" 으로 시작한다.

원인은 모델이 아니라 **프롬프트가 거짓말을 하고 있던 것**이었다. 기간 블록 헤더 라벨이
대상 기간과 무관하게 고정돼 있어서, 내일·다음 달·내년을 물어도 헤더가 이렇게 나갔다.

    내일 운세    [오늘의 운세 — 2026-08-07 …]
    다음 달      [이번 달 총운 — 2026-09 …]
    내년         [올해 총운 — 2027 …]

헤더 뒤에 정확한 기간 라벨이 붙고 [기준 시점] 블록도 오늘을 따로 알려주지만, 상충하는
두 신호 중 LLM 은 앞의 말을 따라갔다. 실측(user→assistant 570쌍): '내일' 질문 17건 중
5건이 답변에서 '오늘'로 지칭.

여기서는 **프롬프트에 거짓 상대 표현이 없는지**만 고정한다. 실제 출력 문장의 지칭이
고쳐졌는지는 라이브 관측 몫이다(LLM 미호출 — 원칙 1).
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta

import pytest

from saju_api.services import chat_service
from saju_shared_types.birth_input import BirthInput

_TODAY = date(2026, 8, 6)
_BIRTH = BirthInput(
    birth_date=date(1985, 11, 20),
    birth_time=time(14, 30),
    birth_place_name="서울",
    timezone="Asia/Seoul",
    gender="male",
    reference_date=_TODAY,
)

#: 기간 블록 헤더가 절대 담아서는 안 되는 상대 표현.
_STALE_HEADER_RE = re.compile(r"\[(?:오늘의 운세|이번 달 총운|올해 총운)")


def _prompt(question: str) -> str:
    resp = chat_service.chat(_BIRTH, question, today=_TODAY, dry_run=True)
    return resp.prompt_preview or ""


# ── 헤더에서 상대 표현 제거 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("question", "header"),
    [
        ("오늘의 운세를 알려줘", "해당 일 운세"),
        ("내일 운세도 알려줘", "해당 일 운세"),
        ("모레 운세 알려줘", "해당 일 운세"),
        ("다음 달 운세 알려줘", "해당 월 총운"),
        ("내년 운세 알려줘", "해당 연 총운"),
    ],
)
def test_period_header_states_the_span_not_its_distance(
    question: str, header: str,
) -> None:
    """헤더는 어느 기간인지만 밝힌다 — 기준 시점과의 거리는 말하지 않는다."""
    text = _prompt(question)
    assert f"[{header} —" in text
    assert not _STALE_HEADER_RE.search(text), "헤더에 고정 상대 표현이 남았다"


def test_today_question_is_not_special_cased() -> None:
    """오늘을 물어도 헤더는 같다 — 지칭은 [기준 시점]과 특정일 지시문이 정한다.

    오늘만 예전 라벨로 되돌리면 라벨이 다시 두 갈래가 되고, '오늘인지'를 헤더 생성부가
    또 판단해야 한다. 판단 지점을 늘리지 않는 것이 이 개정의 요지다.
    """
    assert "[해당 일 운세 —" in _prompt("오늘의 운세를 알려줘")


# ── 특정일 지시문의 상대 표현 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("오늘의 운세를 알려줘", "오늘"),
        ("내일 운세도 알려줘", "내일"),
        ("모레 운세 알려줘", "모레"),
    ],
)
def test_single_day_directive_carries_the_relative_label(
    question: str, expected: str,
) -> None:
    """날짜만 주면 LLM 이 그 날을 '오늘'로 불렀다 — 관계를 계산해 넘긴다."""
    assert f"기준 시점 대비 {expected})" in _prompt(question)


def test_single_day_directive_points_at_a_block_that_exists() -> None:
    """끊어진 참조 회귀 — 예전 지시문은 `[해당 일 일운]` 을 가리켰으나 그런 헤더는 없었다."""
    text = _prompt("내일 운세도 알려줘")
    assert "[해당 일 일운]" not in text
    assert "[해당 일 운세] " in text or "[해당 일 운세]\n" in text


# ── 상대 표현 계산 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("offset", "label"),
    [
        (-2, "그제"), (-1, "어제"), (0, "오늘"), (1, "내일"),
        (2, "모레"), (3, "글피"), (5, "5일 뒤"), (-4, "4일 전"),
    ],
)
def test_relative_day_label(offset: int, label: str) -> None:
    assert chat_service._relative_day_label(_TODAY + timedelta(days=offset), _TODAY) == label


def test_relative_labels_reuse_the_parser_vocabulary() -> None:
    """파싱과 서술이 같은 어휘를 쓴다 — 사용자가 '모레'라 물었는데 '2일 뒤'로 부르면 어긋난다."""
    from saju_engines.time_parser import DAY_WORD_OFFSETS

    for word, offset in DAY_WORD_OFFSETS.items():
        assert chat_service._relative_day_label(
            _TODAY + timedelta(days=offset), _TODAY
        ) == word


# ── 지시문의 블록명이 실제 헤더와 일치 ───────────────────────────────────


@pytest.mark.parametrize(
    ("instruction", "block"),
    [
        ("_DAILY_INSTRUCTION", "[해당 일 운세]"),
        ("_MONTHLY_INSTRUCTION", "[해당 월 총운]"),
        ("_YEARLY_INSTRUCTION", "[해당 연 총운]"),
    ],
)
def test_instructions_reference_real_block_names(instruction: str, block: str) -> None:
    """지시문이 없는 블록을 가리키면 근거 지시가 조용히 무력해진다."""
    from saju_engines import context_reducer

    assert block in getattr(context_reducer, instruction)


def test_daily_instruction_no_longer_says_today() -> None:
    """'오늘 일어난다'는 예시가 다른 날 질문에서 '오늘'을 한 번 더 각인시켰다."""
    from saju_engines import context_reducer

    assert "'오늘 일어난다'" not in context_reducer._DAILY_INSTRUCTION
    assert "'그날 일어난다'" in context_reducer._DAILY_INSTRUCTION
