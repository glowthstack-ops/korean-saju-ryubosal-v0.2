"""Context Reduction + LLM 입력 계약 검증 (Phase 3 T3.4·T3.5 — docs/03 B5·docs/06)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, GraphIndex, load_event_graph
from saju_engines.context_reducer import (
    SCORE_FLOOR,
    TOP_N_CANDIDATES,
    _clean_evidence_text,
    build_llm_input,
    reduce_candidates,
    serialize_llm_input,
    serialize_with_guard,
    tone_for_score,
)
from saju_engines.llm_guard import TokenBudgetExceeded
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
def scorer() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart, scorer):
    """세운 후보 전체."""
    return scorer.score_legacy(chart, levels={GanjiLevel.YEAR})


@pytest.fixture(scope="module")
def bundles():
    """career graphScope의 EvidenceBundle."""
    graph = load_event_graph(_BACKEND / "compiled" / "event_graph_v1.1.0.json")
    return GraphIndex(graph).retrieve([EventKey.CAREER_CHANGE, EventKey.CONTRACT_DOCUMENT])


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
    assert 0 < tokens <= 12_000
    for section in ("[원국·명식 구조", "[간지달력(압축)]", "[이벤트 후보", "[근거 경로]", "[지시]"):
        assert section in text
    # 이벤트 후보는 점수 확정값이 아니라 '추측 신호'로 고지(항목 10).
    assert "추측 신호" in text


def test_serialize_with_guard_reserve_accounts_overhead(
    chart, candidates, bundles, scorer,
) -> None:
    """reserve_tokens가 후행 오버헤드(시스템·지시문)를 합산 입력으로 반영한다.

    serialize 통과 후 시스템·지시문이 더해져 generate_reading 재검사에서 터지던 회계
    불일치(2026-06-18, 10년 이사 질문 12,098tok)를 막는다.
    """
    payload = build_llm_input("올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer)
    _, base = serialize_with_guard(payload, "chat_single")  # 예약분 없는 기준 토큰
    # 작은 예약분은 합산이 여전히 한도 이내 → payload 변화 없이 통과.
    _, ok = serialize_with_guard(payload, "chat_single", reserve_tokens=100)
    assert ok == base
    # 예약분이 상한 전체를 먹으면 어떤 payload도 못 들어가 축소 후에도 초과 → 전파(차단).
    with pytest.raises(TokenBudgetExceeded, match="Context Reduction"):
        serialize_with_guard(payload, "chat_single", reserve_tokens=12_000)


def test_relocation_reasons_render_in_date_block(
    chart, candidates, bundles, scorer,
) -> None:
    """이사 십성 이유분류가 택일 블록 직렬화에 헤더+라벨 줄로 실린다(R2 surface)."""
    from saju_shared_types.llm_input import DateSelectionBlock

    payload = build_llm_input("이사 좋은 날", _intent(), chart, candidates, bundles, scorer)
    payload.date_selection = DateSelectionBlock(
        purpose_ko="이사", period="2026-07-01 ~ 2026-07-31",
        relocation_reasons=["세운 천간(명분) 편관 → 긴축형_임시거처: 이유 압박 / 집·지역 저가"],
    )
    text = serialize_llm_input(payload)
    assert "이사 이유·집 성격 — 십성 분류" in text
    assert "단정 표현 금지" in text  # 발생 단정 차단 가드 동반
    assert "세운 천간(명분) 편관 → 긴축형_임시거처" in text


def test_clean_evidence_strips_authoring_meta() -> None:
    """근거 경로 정리 — 저작 메타 괄호(표현 제한·당첨 단정 금지 등)는 제거, 의미 괄호는 보존."""
    note = (
        "편재+삼합(재성국 완성)+원국 그릇 강 — 큰 재물이 한 번에 드러날 잠재"
        "(windfall은 표현 제한 — 당첨 단정 금지, 변동성·과몰입 경고)"
    )
    cleaned = _clean_evidence_text(note)
    assert "표현 제한" not in cleaned and "단정 금지" not in cleaned and "과몰입" not in cleaned
    assert "(재성국 완성)" in cleaned  # 의미 있는 괄호는 보존
    assert _clean_evidence_text("횡재(표현 제한)") == "횡재"


def test_monthly_overview_renders_luck_grade(chart, candidates, bundles, scorer) -> None:
    """월별 표에 운 품질 등급〈…〉이 사건명 앞에 노출되고, 길흉 1차 기준 범례가 붙는다."""
    from saju_shared_types.llm_input import MonthOverviewRow

    overview = [
        MonthOverviewRow(period="2026-10", ganji="戊戌", top_event_ko="재물 변화",
                         score=80, polarity="neutral", luck_grade="강한 용신운"),
        MonthOverviewRow(period="2026-12", ganji="庚子", luck_grade="기신운(부분)"),
    ]
    payload = build_llm_input(
        "올해 월별 운 어때?", _intent(), chart, candidates, bundles, scorer,
        monthly_overview=overview,
    )
    text = serialize_llm_input(payload)
    assert "〈강한 용신운〉" in text  # 길흉 1차 기준이 표에 노출
    assert "〈기신운(부분)〉" in text  # 사건 없는 달도 운 품질 표기
    assert "운 품질 등급" in text  # 범례 지시(좋은 달=운 품질 기준)


def test_best_quality_months_named_callout() -> None:
    """기반 최고 달 지목 — 강한 용신운 우선, 없으면 용신운(부분), 흉·혼합은 제외."""
    from saju_engines.context_reducer import _best_quality_months
    from saju_shared_types.llm_input import MonthOverviewRow

    rows = [
        MonthOverviewRow(period="2026-10", ganji="戊戌", luck_grade="강한 용신운"),
        MonthOverviewRow(period="2026-08", ganji="丙申", luck_grade="용신운(부분)"),
        MonthOverviewRow(period="2026-12", ganji="庚子", luck_grade="기신운(부분)"),
    ]
    assert _best_quality_months(rows) == "2026-10(강한 용신운)"  # 최상위만
    # 강한 용신운이 없으면 용신운(부분)로 폴백.
    rows2 = [r for r in rows if r.luck_grade != "강한 용신운"]
    assert _best_quality_months(rows2) == "2026-08(용신운(부분))"
    # 길 등급이 전혀 없으면 빈 문자열(흉·혼합은 '좋은 달'로 지목 안 함).
    assert _best_quality_months([rows[2]]) == ""


def test_monthly_overview_emits_best_month_callout(chart, candidates, bundles, scorer) -> None:
    """월별 블록에 '기반 최고 달' 콜아웃이 이름 박혀 노출된다(intent 질문 누락 방지)."""
    from saju_shared_types.llm_input import MonthOverviewRow

    overview = [
        MonthOverviewRow(period="2026-10", ganji="戊戌", luck_grade="강한 용신운"),
        MonthOverviewRow(period="2026-11", ganji="己亥", top_event_ko="재물 변화",
                         score=70, luck_grade="혼합"),
    ]
    payload = build_llm_input(
        "올해 이직운", _intent(), chart, candidates, bundles, scorer,
        monthly_overview=overview,
    )
    text = serialize_llm_input(payload)
    assert "기반 최고 달" in text and "2026-10(강한 용신운)" in text


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
    assert payload.budget.max_input_tokens == 14_000
