"""실답 교정 3건(2026-11-08) — ① '저번달/지난달' 파싱·회고 판정 ② 단식 참고 줄 결정론 삽입
③ 후속 확인 중복 제거·'다음에' 보류 키.
"""

from __future__ import annotations

import datetime as dt

from saju_api.services import chat_service
from saju_engines.life_event_followup import (
    FollowupCandidate,
    asked_keys_from_meta,
    exclude_asked,
)
from saju_engines.time_parser import parse_time
from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange
from saju_shared_types.llm_input import LlmInput, PeriodFortune

_TODAY = dt.date(2026, 11, 8)  # 己亥월(11/8 입동 후) — 지난 달 = 2026-10 戊戌월


def _tr(text: str) -> TimeRange | None:
    tr, _scope = parse_time(text, _TODAY, current_month_label="2026-11")
    return tr


# ── ① 지난 달 파싱 ──────────────────────────────────────────────────────────


def test_last_month_expressions_resolve_to_previous_luck_month() -> None:
    for q in ("저번달 운세는 어때?", "지난달 운세는 어땠어?", "지난 달 어땠어", "저번 달은?"):
        tr = _tr(q)
        assert tr is not None, q
        assert (tr.granularity, tr.start, tr.end) == (Granularity.MONTH, "2026-10", "2026-10"), q
    tr = _tr("지지난달은 어땠어?")
    assert tr is not None and (tr.start, tr.end) == ("2026-09", "2026-09")
    # '이번 달'·'다음 달'은 종전 그대로.
    assert _tr("이번 달 운세는 어때?").start == "2026-11"
    assert _tr("다음 달 운세는 어때?").start == "2026-12"


def test_last_month_question_is_retro_even_with_present_tense_verb() -> None:
    """'저번달 운세는 어때?' — 동사는 현재형이지만 창이 과거라 회고 모드(window_past)."""
    intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="relative", granularity=Granularity.MONTH, start="2026-10", end="2026-10",
        ),
    )
    retro, reason = chat_service._question_time_direction_reason(
        "저번달 운세는 어때?", intent, None, _TODAY, "2026-11",
    )
    assert retro and reason == "window_past"
    # 시점 창이 없어도 '저번' 문구만으로 회고.
    assert "저번" in chat_service._PAST_KEYWORDS


# ── ② 단식 참고 줄 결정론 삽입 ──────────────────────────────────────────────


def _payload(line: str) -> LlmInput:
    pf = PeriodFortune(
        fortune_type="monthly", period_label="2026-10", ganji="戊戌", pillar_line="-",
        simple_reading_line=line,
    )
    return LlmInput.model_construct(period_fortune=pf)


def test_simple_reading_line_inserted_after_first_paragraph_when_missing() -> None:
    line = (
        "간단히 봤을 때, 戊戌월은 경(庚) 일간에게 인성(편인·편인) 결이에요. "
        "생각이 깊어지는 달이에요."
    )
    answer = "첫 판정 문단이에요.\n\n둘째 문단이에요."
    fixed = chat_service._ensure_simple_reading_line(answer, _payload(line), "t")
    assert fixed == f"첫 판정 문단이에요.\n\n{line}\n\n둘째 문단이에요."
    # LLM 이 바꿔 쓴 단식 문단은 엔진 문단으로 교체(2026-11-08 실답: '겁재 — 경쟁심·지출'로 변형).
    # 그 다음 문단(개인 판정 '다만 이 명식에서는')은 그대로 남는다.
    present = (
        "첫 문단.\n\n간단히 봤을 때, 다른 표현으로 쓴 문장.\n\n다만 이 명식에서는 다르다.\n\n둘째."
    )
    fixed2 = chat_service._ensure_simple_reading_line(present, _payload(line), "t")
    assert fixed2 == f"첫 문단.\n\n{line}\n\n다만 이 명식에서는 다르다.\n\n둘째."
    # 엔진 문단 그대로면 바이트 불변.
    exact = f"첫 문단.\n\n{line}\n\n둘째."
    assert chat_service._ensure_simple_reading_line(exact, _payload(line), "t") == exact
    # 줄이 없으면(총운 아님) 불변.
    assert chat_service._ensure_simple_reading_line(answer, _payload(""), "t") == answer
    # 한 문단뿐이면 끝에 붙인다.
    one = chat_service._ensure_simple_reading_line("한 문단.", _payload(line), "t")
    assert one == f"한 문단.\n\n{line}"


# ── ③ 후속 확인 중복 제거·보류 키 ──────────────────────────────────────────


def test_exclude_asked_drops_candidates_answered_elsewhere() -> None:
    cands = [
        FollowupCandidate(event_key="wealth_change", event_ko="재물 변화", period="2026-10"),
        FollowupCandidate(event_key="career_change", event_ko="이직", period="2026-10"),
    ]
    asked = {("wealth_change", "2026-10")}
    left = exclude_asked(cands, asked)
    assert [c.event_key for c in left] == ["career_change"]
    assert exclude_asked(cands, set()) == cands


def test_asked_keys_from_meta_reads_answers_and_dismissed_candidates() -> None:
    meta = {
        "followup_answered": {"answers": [
            {"event_key": "wealth_change", "period": "2026-10", "outcome": "confirmed"},
            {"event_key": "contract_document", "period": "2026-10", "outcome": "unknown"},
        ]},
        "followup_dismissed": {"candidates": [{"event_key": "career_change", "period": "2026-10"}]},
    }
    assert asked_keys_from_meta(meta) == {
        ("wealth_change", "2026-10"),
        ("contract_document", "2026-10"),
        ("career_change", "2026-10"),
    }
    assert asked_keys_from_meta({}) == set()
