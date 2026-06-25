"""연/월 흐름 블록의 기간 단위어 정합 — 실로그: 연도별 블록이 '달'로 오기되던 결함.

연 단위(period 'YYYY') 블록은 '해', 월 단위(period 'YYYY-MM') 블록은 '달'을 써야 하고,
조사도 '해는/해를', '달은/달을'로 맞아야 한다('달는/달를' 금지).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, GraphIndex, load_event_graph
from saju_engines.context_reducer import build_llm_input, serialize_llm_input
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope
from saju_shared_types.llm_input import MonthOverviewRow

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def scorer() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart, scorer):
    return scorer.score_legacy(chart, levels={GanjiLevel.YEAR})


@pytest.fixture(scope="module")
def bundles():
    graph = load_event_graph(_BACKEND / "compiled" / "event_graph_v1.1.0.json")
    return GraphIndex(graph).retrieve([EventKey.CAREER_CHANGE])


def _intent() -> IntentJson:
    return IntentJson(
        intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.WEALTH,
        time_scope=TimeScope.MID_TERM,
    )


def _row(period: str) -> MonthOverviewRow:
    return MonthOverviewRow(
        period=period, ganji="丙午", top_event_ko="재물 변화", score=80,
        direction="기회·유입", luck_grade="강한 용신운", strength_rank=1,
        transition="대운 교체기", branch_ko="'재물'",
    )


def _text(chart, candidates, bundles, scorer, periods: list[str]) -> str:
    rows = [_row(p) for p in periods]
    payload = build_llm_input(
        "재물 흐름", _intent(), chart, candidates, bundles, scorer,
        today=date(2026, 6, 11), monthly_overview=rows,
    )
    return serialize_llm_input(payload)


def test_yearly_block_uses_hae_not_dal(chart, candidates, bundles, scorer) -> None:
    text = _text(chart, candidates, bundles, scorer, ["2026", "2027", "2028"])
    assert "[연도별 흐름" in text
    assert "기반 최고 해" in text and "이 해에" in text  # 해 단위
    assert "기반 최고 달" not in text and "이 달에" not in text  # 달 오기 없음
    assert "달는" not in text and "달를" not in text  # 조사 오류 없음
    assert "해은" not in text and "해을" not in text  # 해 조사 오류 없음


def test_monthly_block_uses_dal(chart, candidates, bundles, scorer) -> None:
    text = _text(chart, candidates, bundles, scorer, ["2026-06", "2026-07", "2026-08"])
    assert "[월별 요약" in text
    assert "기반 최고 달" in text  # 달 단위
    assert "달는" not in text and "달를" not in text  # '달은/달을' 정상 조사
    assert "기반 최고 해" not in text
