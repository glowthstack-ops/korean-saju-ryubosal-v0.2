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


def test_dual_channel_activation_and_favorability() -> None:
    # 활성/길흉 이중 채널 — _apply_soft_cap이 contributions·극성에서 파생값을 확정.
    from saju_engines.event_engine_v2 import _apply_soft_cap
    from saju_shared_types.event_engine import EventCandidateV2, PolarityRole

    # 용신(YONG) + yongi 기여 → favorability>0, activation은 길흉(yongi) 제외.
    yong = _apply_soft_cap(EventCandidateV2(
        event_key="job_gain", period="2026", score=70,
        polarity_role=PolarityRole.YONG, contributions={"base": 64.0, "yongi": 6.0},
    ))
    assert yong.favorability > 0
    assert yong.activation == 64.0  # 70(raw) - 6(yongi)

    # 기신(GI) → favorability<0.
    gi = _apply_soft_cap(EventCandidateV2(
        event_key="career_change", period="2026", score=60,
        polarity_role=PolarityRole.GI, contributions={"base": 60.0},
    ))
    assert gi.favorability < 0

    # fav_adj(시험 불합격 패턴 보정)가 극성 기준값에 합산되고 [-1,1]로 클램프.
    adj = _apply_soft_cap(EventCandidateV2(
        event_key="education_admission", period="2026", score=60,
        polarity_role=PolarityRole.NEUTRAL, contributions={"fav_adj": -0.3},
    ))
    assert adj.favorability == -0.3


def test_jobchange_classification_label() -> None:
    # 이직 분류(자료 12) — career_change 최종 favorability로 압박성/기회성 라벨.
    from saju_engines.event_engine_v2 import _apply_soft_cap
    from saju_shared_types.event_engine import EventCandidateV2, PolarityRole

    pressure = _apply_soft_cap(EventCandidateV2(
        event_key="career_change", period="2026", score=60,
        polarity_role=PolarityRole.GI, contributions={"base": 60.0},
    ))
    assert pressure.favorability < 0
    assert "JOBCHANGE_PRESSURE_DRIVEN" in pressure.reason_codes

    opportunity = _apply_soft_cap(EventCandidateV2(
        event_key="career_change", period="2026", score=60,
        polarity_role=PolarityRole.YONG, contributions={"base": 60.0},
    ))
    assert opportunity.favorability > 0
    assert "JOBCHANGE_OPPORTUNITY" in opportunity.reason_codes
