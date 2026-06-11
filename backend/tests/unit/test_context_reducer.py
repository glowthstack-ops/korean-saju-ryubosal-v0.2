"""Context Reduction + LLM 입력 계약 검증 (Phase 3 T3.4·T3.5 — docs/03 B5·docs/06)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventScorer, GraphIndex, load_event_graph
from saju_engines.context_reducer import (
    SCORE_FLOOR,
    TOP_N_CANDIDATES,
    build_llm_input,
    reduce_candidates,
    serialize_llm_input,
    serialize_with_guard,
    tone_for_score,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    """기준 차트(1980)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def scorer() -> EventScorer:
    return EventScorer(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart, scorer):
    """세운 후보 전체."""
    return scorer.score(chart, levels={GanjiLevel.YEAR})


@pytest.fixture(scope="module")
def bundles():
    """career graphScope의 EvidenceBundle."""
    graph = load_event_graph(_BACKEND / "compiled" / "event_graph_v1.0.0.json")
    return GraphIndex(graph).retrieve([EventKey.CAREER_CHANGE, EventKey.CONTRACT])


def _intent(**over) -> IntentJson:
    base = dict(
        intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS,
        domain=Domain.CAREER, time_scope=TimeScope.MID_TERM,
        event_key=EventKey.CAREER_CHANGE,
    )
    base.update(over)
    return IntentJson(**base)


def test_reduce_top_n_and_floor(candidates) -> None:
    """후보 축소: Top N + 임계값(<40 언급 생략 구간 미전달) + 범위 필터."""
    reduced = reduce_candidates(candidates, [EventKey.CAREER_CHANGE])
    assert len(reduced) <= TOP_N_CANDIDATES
    assert all(c.score >= SCORE_FLOOR for c in reduced)
    assert all(c.event_key is EventKey.CAREER_CHANGE for c in reduced)


def test_candidates_carry_ganji_and_daewoon(chart, candidates, bundles, scorer) -> None:
    """모든 LLM 후보에 간지+대운 맥락 필수(docs/03 B5 규칙 5)."""
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer)
    assert payload.event_candidates
    for c in payload.event_candidates:
        assert c.ganji and c.daewoon_context


def test_calendar_hierarchy_compression(chart, candidates, bundles, scorer) -> None:
    """계층 압축: 선택 세운만, 월운은 선택 세운 내에서만, 일운은 택일에서만."""
    payload = build_llm_input("이직운 봐줘", _intent(), chart, candidates, bundles, scorer)
    cal = payload.calendar_context
    selected_periods = {c.period for c in payload.event_candidates}
    assert {str(y.year) for y in cal.selected_years} <= {p[:4] for p in selected_periods}
    # 비택일 질의 → 일운 미포함.
    assert cal.selected_days == []
    # 세운마다 대운 맥락과 선별 사유 동반.
    assert all(y.daewoon and y.reason_selected for y in cal.selected_years)


def test_serialized_prompt_within_guard(chart, candidates, bundles, scorer) -> None:
    """직렬화 본문이 한도(chat_single 6k) 안에서 통과하고 4요소를 포함한다."""
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer)
    text, tokens = serialize_with_guard(payload, "chat_single")
    assert 0 < tokens <= 6_000
    for section in ("[원국]", "[간지달력(압축)]", "[이벤트 후보", "[근거 경로]", "[지시]"):
        assert section in text
    assert "재계산 금지" in text  # LLM 계산 금지 고지


def test_tone_mapping_table() -> None:
    """docs/06 점수→표현 강도 매핑표."""
    assert tone_for_score(90) == "신호가 매우 강합니다"
    assert tone_for_score(78) == "가능성이 높습니다"
    assert tone_for_score(60) == "흐름이 나타날 수 있습니다"
    assert tone_for_score(45) == "조짐이 약하게 있습니다"
    assert tone_for_score(20) == "뚜렷한 신호는 없습니다"


def test_prohibited_styles_attached(chart, scorer, bundles, candidates) -> None:
    """금기 표현 — 기본 3종 + 이벤트별 금기(windfall 등) 병합."""
    payload = build_llm_input("이직운", _intent(), chart, candidates, bundles, scorer)
    assert "반드시 이직한다" in payload.style_rules.prohibited
    text = serialize_llm_input(payload)
    assert "금기 표현:" in text


def test_budget_from_call_limits(chart, candidates, bundles, scorer) -> None:
    """예산은 docs/09 8장 한도표에서 온다."""
    payload = build_llm_input(
        "이직운", _intent(), chart, candidates, bundles, scorer, call_type="chat_compare",
    )
    assert payload.budget.max_input_tokens == 8_000
