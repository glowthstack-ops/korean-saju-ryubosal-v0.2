"""EventEngineV2 통합 검증 (이벤트 엔진 재설계 Phase 7).

거버닝 스택으로 6계층이 결정론적으로 결합되는지 — 후보 생성, confidence_level 1차 정렬,
궁성·품질 부여, score_years(과거 연도)를 확인한다. reviewed:false 초안 가중이므로 절대
점수가 아니라 구조(사건화 강도 순위·신호 존재)를 고정한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import ConfidenceLevel
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_CONF_ORDER = [
    ConfidenceLevel.THEME_ONLY,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE,
    ConfidenceLevel.EVENT_CANDIDATE,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT,
]


@pytest.fixture(scope="module")
def chart():
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def engine() -> EventEngineV2:
    return EventEngineV2(_DICTS)


def test_year_scoring_produces_candidates(chart, engine: EventEngineV2) -> None:
    cands = engine.score(chart, levels={GanjiLevel.YEAR})
    assert cands, "세운 후보가 생성되어야 한다"
    # 모든 후보는 21키·기간·점수 범위 계약을 지킨다.
    assert all(0 <= c.score <= 100 for c in cands)
    assert all(c.reason_codes for c in cands)


def test_confidence_is_primary_sort_axis(chart, engine: EventEngineV2) -> None:
    cands = engine.score(chart, levels={GanjiLevel.YEAR})
    ranks = [_CONF_ORDER.index(c.confidence_level) for c in cands]
    assert ranks == sorted(ranks, reverse=True), "사건화 강도(confidence_level) 내림차순 정렬"


def test_deterministic(chart, engine: EventEngineV2) -> None:
    a = engine.score(chart, levels={GanjiLevel.YEAR})
    b = engine.score(chart, levels={GanjiLevel.YEAR})
    assert [(c.period, str(c.event_key), c.score) for c in a] == [
        (c.period, str(c.event_key), c.score) for c in b
    ]


def test_strong_candidates_have_palace(chart, engine: EventEngineV2) -> None:
    cands = engine.score(chart, levels={GanjiLevel.YEAR})
    strong = [c for c in cands if c.confidence_level in (
        ConfidenceLevel.STRONG_EVENT_CANDIDATE, ConfidenceLevel.HIGH_PROBABILITY_EVENT,
    )]
    assert strong, "강한 후보가 적어도 일부 있어야 한다"
    # 강한 후보는 관계·궁성 신호를 동반(palace 부여)한다.
    assert all(c.palace is not None for c in strong)


def test_score_years_includes_past(chart, engine: EventEngineV2) -> None:
    # 과거 세운 직접 스코어링(용신 검증 경로) — 윈도 밖 연도도 후보 생성.
    cands = engine.score_years(chart, [2018])
    assert cands
    assert all(c.period == "2018" for c in cands)


def test_profile_gate_optional(chart, engine: EventEngineV2) -> None:
    # 2단계 프로필 미입력이어도 동작해야 한다(규칙11).
    base = engine.score(chart, levels={GanjiLevel.YEAR})
    gated = engine.score(
        chart, levels={GanjiLevel.YEAR},
        occupation_status="employee", relationship_status="married",
    )
    assert base and gated  # 둘 다 정상 산출
