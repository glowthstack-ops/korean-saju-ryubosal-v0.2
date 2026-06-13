"""Phase 5 예측 엔진군 검증 (T5.1~T5.7 — docs/02 E3~E8·E12·E13)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_engines.prediction import PredictionEngines
from saju_engines.relations_engines import CompatibilityEngine, CompetitionEngine
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def chart():
    """기준 차트 A (1980, 일간 己)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def chart_b():
    """비교 차트 B (1985, 일간 丁 — 시각 있음)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1985, 4, 18), birth_time="16:00",
        birth_place_name="서울", gender="female", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def engines() -> PredictionEngines:
    return PredictionEngines(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart):
    """세운+월운 후보."""
    return EventEngineV2(_DICTS).score_legacy(
        chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH}
    )


# ── T5.1 Timeline (E4) ───────────────────────────────────────────


def test_timeline_activation_window_and_stages(engines, candidates) -> None:
    """월운 신호 → 단계 매핑 + Activation Window(Trigger ≠ Execution)."""
    timeline = engines.build_timeline(EventKey.CAREER_CHANGE, candidates)
    assert timeline is not None
    assert timeline.activation_window.start <= timeline.activation_window.end
    valid = {"awareness", "exploration", "action", "decision", "completion"}
    assert all(p.stage in valid for p in timeline.phases)
    s = timeline.scores
    assert all(0 <= v <= 100 for v in (s.interest, s.action, s.completion))


def test_timeline_none_without_monthly(engines, chart) -> None:
    """월 단위 후보가 없으면 None(연 단위만으로 단계 생성 금지)."""
    yearly_only = EventEngineV2(_DICTS).score_legacy(chart, levels={GanjiLevel.YEAR})
    monthly = [c for c in yearly_only if len(c.period) == 7]
    assert not monthly
    assert engines.build_timeline(EventKey.CAREER_CHANGE, yearly_only) is None


# ── T5.2 Event Form (E3) ─────────────────────────────────────────


def test_event_forms_prob_sum_le_one(engines, chart) -> None:
    """발현 형태 prob 합 ≤ 1.0 (프로파일 보정 후에도 유지)."""
    profile = engines.self_profile(chart)
    for key in (EventKey.CAREER_CHANGE, EventKey.RELOCATION):
        result = engines.event_forms(key, profile)
        assert result.forms
        assert sum(f.prob for f in result.forms) <= 1.0 + 1e-9


# ── T5.3 Self Profile (E5) ───────────────────────────────────────


def test_self_profile_with_evidence(engines, chart) -> None:
    """프로파일 4축 + 모든 축 근거 첨부(성격검사화 금지 — 보정 목적 한정)."""
    p = engines.self_profile(chart)
    assert p.decision_style in ("impulsive", "deliberate", "avoidant", "consensus")
    assert 0 <= p.risk_tolerance <= 100 and 0 <= p.execution_power <= 100
    assert set(p.axes) == {"relationship", "money", "work", "stress"}
    assert p.evidence  # 근거 노드 첨부
    assert p.manifestation_tendency


# ── T5.4 Manifestation (E6) ──────────────────────────────────────


def test_manifestation_without_context_is_safe(engines, chart, candidates) -> None:
    """Reality Context 부재 → modifier 0 + confidence 하향(차단·오류 금지)."""
    profile = engines.self_profile(chart)
    career = next(c for c in candidates if c.event_key is EventKey.CAREER_CHANGE)
    m = engines.manifestation(career, profile, reality_context=None)
    assert m.context_modifier == 0
    assert m.confidence == "medium_low"
    assert 0 <= m.realization_score <= 100
    assert m.likely_forms  # E3 연동


def test_manifestation_with_context_raises_confidence(engines, chart, candidates) -> None:
    profile = engines.self_profile(chart)
    career = next(c for c in candidates if c.event_key is EventKey.CAREER_CHANGE)
    m = engines.manifestation(career, profile, reality_context={"career_change": 8})
    assert m.context_modifier == 8 and m.confidence == "medium_high"


# ── T5.5 Advice (E8 + remedy 6분기) ──────────────────────────────


def test_advice_follows_timeline_stages(engines, candidates) -> None:
    """타임라인 단계별 행동 조언 + 주의(remedy 사전)."""
    timeline = engines.build_timeline(EventKey.CAREER_CHANGE, candidates)
    advice = engines.advice(EventKey.CAREER_CHANGE, timeline)
    assert advice.advice and len(advice.advice) == len(timeline.phases)
    assert advice.cautions  # remedy 시기회피/주의행동 분기


def test_advice_disclaimers_fixed(engines) -> None:
    """의료·투자 고지 문구는 템플릿 레벨 고정(docs/07 리스크 6)."""
    health = engines.advice(EventKey.HEALTH_ATTENTION, None)
    assert any("의료" in d for d in health.disclaimers)
    windfall = engines.advice(EventKey.WINDFALL, None)
    assert any("투자" in d for d in windfall.disclaimers)


# ── T5.6 Compatibility (E13) ─────────────────────────────────────


def test_compatibility_axes_by_relation_type(chart, chart_b) -> None:
    """관계 유형별로 축 구성이 달라진다(relation_profiles 사전)."""
    engine = CompatibilityEngine(_DICTS)
    lover = engine.analyze(chart, chart_b, "lover")
    parent = engine.analyze(chart, chart_b, "parent_child")
    assert 0 <= lover.overall <= 100
    assert {a.axis for a in lover.axes} != {a.axis for a in parent.axes}
    assert all(a.notes for a in lover.axes)  # 축마다 근거


def test_compatibility_deterministic(chart, chart_b) -> None:
    engine = CompatibilityEngine(_DICTS)
    a = engine.analyze(chart, chart_b, "spouse")
    b = engine.analyze(chart, chart_b, "spouse")
    assert a.model_dump() == b.model_dump()


# ── T5.7 Competition (E12 — 당락 단정 금지·no_hour) ──────────────


def test_competition_prohibitions_and_gap(chart, chart_b, candidates) -> None:
    """상대 우열 + 근거까지만 — 당락 단정 금지 문구 고정 첨부."""
    engine = CompetitionEngine()
    cands_b = EventEngineV2(_DICTS).score_legacy(chart_b, levels={GanjiLevel.YEAR})
    result = engine.compare(
        [("후보1", chart, candidates), ("후보2", chart_b, cands_b)],
        anchor_date="2026-06-03",  # 투표일(C11 앵커)
        event_key=EventKey.EDUCATION_ADMISSION,
    )
    assert result.relative_gap in ("clear", "narrow", "inconclusive")
    assert any("단정" in p for p in result.prohibitions)
    assert all(0 <= c.strength_score <= 100 for c in result.candidates)
    # 점수 내림차순 + 근거 경로 동반.
    scores = [c.strength_score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(c.evidence_path for c in result.candidates)


def test_competition_no_hour_mode() -> None:
    """시각 미상(공인 일반) → no_hour 품질 표시 + 비교는 계속 지원."""
    chart_no_hour = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1970, 3, 5),
        birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))
    engine = CompetitionEngine()
    result = engine.compare(
        [("공인A", chart_no_hour, [])], anchor_date="2026-06-03",
    )
    assert result.candidates[0].data_quality == "no_hour"
