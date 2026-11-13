"""'이 해'·'지난 해' 표기 변형의 연 단위 파싱 (2026-11-11 실답 결함).

실답: "올한해 난 힘든 운이었을까?" 가 시점 미파싱 → 무시점·무분야 → 범위 좁히기 메뉴로
반려됐다. 연 단위 규칙(C6)이 '올해'·'금년' 두 낱말만 이 해로 읽었기 때문이다.

- 올해로 읽는 표기: 올 한 해(띄어쓰기 무관)·올핸·이번 해·이번 년도/연도
- 작년으로 읽는 표기: 지난해·지난 한 해
- 반례: '이번 해고 통보'·'이번 해외여행'·'지난 해외여행'·'다가올 한 해'·수식 없는 '한 해'
"""

from __future__ import annotations

from datetime import date

import pytest

import saju_api.services.chat_service as cs
from saju_engines.conversation import ConversationEngine
from saju_engines.query_parser import parse_message
from saju_engines.rewriter import assess
from saju_engines.time_parser import extract_time_constraints, parse_time
from saju_shared_types.conversation import ConversationState, LinkKind
from saju_shared_types.intent import Domain, Granularity, QueryType, TimeConstraintRole

_T = date(2026, 11, 11)
_MONTH = "2026-11"


def _year(q: str) -> str | None:
    """질문에서 파싱된 연 단위 시점(YYYY) — 연 단위가 아니거나 시점이 없으면 None."""
    tr = parse_time(q, _T, current_month_label=_MONTH)[0]
    if tr is None or tr.granularity is not Granularity.YEAR:
        return None
    assert tr.start == tr.end
    return tr.start


@pytest.mark.parametrize(
    "q",
    [
        "올한해 난 힘든 운이었을까?",
        "올 한 해 난 힘든 운이었을까?",
        "올 한해 운세 어때?",
        "올 한해동안 난 어땠어?",
        "올핸 어땠어?",
        "이번 해 운세",
        "이번 해는 어때?",
        "이번 해",
        "이번 년도 운세 알려줘",
        "이번년도 운세",
        "이번 연도 운세",
        # 기존 표기(회귀)
        "올해 난 힘든 운이었을까?",
        "금년 한 해 어땠어?",
    ],
)
def test_this_year_variants_parse_as_current_year(q: str) -> None:
    assert _year(q) == "2026", q


@pytest.mark.parametrize(
    "q",
    ["지난해 운세 어땠어?", "지난 한 해 어땠어?", "지난 한해 난 힘들었을까?", "작년 한해 어땠어?"],
)
def test_last_year_variants_parse_as_previous_year(q: str) -> None:
    assert _year(q) == "2025", q


@pytest.mark.parametrize(
    "q",
    [
        "이번 해고 통보 어떻게 될까",  # 해고 — '이번 해'가 아니다
        "이번 해외여행 괜찮을까",
        "이번 해도 될까",  # '해도'(하다) — 조사 '도'는 인정하지 않는다
        "지난 해외여행은 왜 그랬을까",
        "지지난해 운세 어땠어?",  # 재작년 — 작년으로 읽으면 안 된다
        "다가올 한 해 운세",  # 앞날을 꾸미는 말 — 올해가 아니다
        "돌아올 한해 어때",
        "한 해 동안 힘들었을까?",  # 수식 없는 '한 해' — 어느 해인지 알 수 없다
        "한해 운세 봐줘",
    ],
)
def test_lookalikes_are_not_read_as_a_year(q: str) -> None:
    assert _year(q) is None, q


def test_reported_question_runs_as_this_year_overview() -> None:
    """붙여 받은 실답 질문 원문 — 범위 좁히기 메뉴가 아니라 2026년 종합운으로 실행된다."""
    q = "올한해 난 힘든 운이었을까?"
    it = parse_message(q, _T, current_month_label=_MONTH).intents[0]
    assert assess(it, q).status == "ok"
    assert it.query_type is QueryType.FORTUNE_OVERVIEW
    assert it.time_range is not None
    assert (it.time_range.granularity, it.time_range.start) == (Granularity.YEAR, "2026")
    # '~이었을까' — 지나온 흐름을 되짚는 회고 방향으로 답한다.
    assert cs._question_time_direction_reason(q, it, None, _T, _MONTH) == (True, "past_phrase")


def test_unqualified_year_question_still_asks_to_narrow() -> None:
    """수식 없는 '한 해'는 종전대로 되묻는다(어느 해인지 추측하지 않는다)."""
    q = "한해 운세 봐줘"
    it = parse_message(q, _T, current_month_label=_MONTH).intents[0]
    assert assess(it, q).status == "too_broad"


def test_exclusion_phrase_uses_the_same_this_year_spelling() -> None:
    """'올 한 해 말고 내년은?' — 배제·정정 추출도 같은 표기 정의를 쓴다."""
    q = "올 한 해 말고 내년은?"
    items = extract_time_constraints(q, _T)
    roles = {(it.role, it.start_year) for it in items}
    assert (TimeConstraintRole.EXCLUDED, 2026) in roles
    it = parse_message(q, _T, current_month_label=_MONTH).intents[0]
    assert it.time_range is not None and it.time_range.start == "2027"


def test_short_followup_with_this_year_variant_shifts_time_only() -> None:
    """'올한해는?' 단답 — 직전 주제(직업운)를 잇고 시점만 올해로 바꾼다.

    수정 전에는 새 질문(일반 종합운)으로 끊기고 시점은 직전의 2027년이 그대로 남았다.
    """
    eng = ConversationEngine()
    st = ConversationState(thread_id="t")
    _, st, _, _ = eng.process_turn(st, "내년 직업운 어때?", _T)
    p, _, _, link = eng.process_turn(st, "올한해는?", _T)
    assert link.link_kind is LinkKind.TIME_SHIFT
    it = p.intents[0]
    assert it.domain is Domain.CAREER
    assert it.time_range is not None and it.time_range.start == "2026"
