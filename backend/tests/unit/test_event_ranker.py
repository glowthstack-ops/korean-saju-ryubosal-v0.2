"""EventRanker 검증 (이벤트 엔진 재설계 Phase 6).

증거 등급 confidence_level 산출 + no_event_suppression(소층위 강등) + 충돌 우선순위를 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.event_ranker import EventRanker, RankContext
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    PolarityRole,
    TwelveStage,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _eng() -> EventRanker:
    return EventRanker(_DICTS)


def test_ten_god_only_is_theme_only() -> None:
    e = _eng()
    c = EventCandidateV2(event_key="career_change", period="2026", score=50)
    out = e.rank([c])
    assert out[0].confidence_level is ConfidenceLevel.THEME_ONLY


def test_full_evidence_high_probability() -> None:
    e = _eng()
    c = EventCandidateV2(
        event_key="job_gain", period="2026", score=70,
        source_layers=[LuckLayer.DAEWOON, LuckLayer.SEWOON],
        twelve_stage=TwelveStage.GEONROK, palace=Pillar4.MONTH,
        polarity_role=PolarityRole.YONG,
        reason_codes=["REL_HAP_month_pillar", "PROFILE_x"],
    )
    out = e.rank([c])
    assert out[0].confidence_level is ConfidenceLevel.HIGH_PROBABILITY_EVENT


def test_relation_palace_is_event_candidate() -> None:
    e = _eng()
    c = EventCandidateV2(
        event_key="relocation", period="2026", score=60,
        source_layers=[LuckLayer.SEWOON], palace=Pillar4.DAY,
        reason_codes=["REL_CHUNG_day_pillar"],
    )
    out = e.rank([c])
    assert out[0].confidence_level is ConfidenceLevel.EVENT_CANDIDATE


def test_minor_layer_only_suppressed() -> None:
    e = _eng()
    c = EventCandidateV2(
        event_key="social_conflict", period="2026-08", score=60,
        source_layers=[LuckLayer.ILWOON], twelve_stage=TwelveStage.MOKYOK,
    )
    out = e.rank([c])
    assert out[0].score < 60
    assert "SUPPRESS_minor_layer_only" in out[0].reason_codes


def test_conflict_prefer_over() -> None:
    e = _eng()
    prefer = EventCandidateV2(event_key="relationship_change", period="2026", score=55)
    over = EventCandidateV2(event_key="contract_document", period="2026", score=58)
    ctx = RankContext(flags={
        "day_branch_activated", "wealth_or_authority_signal", "relationship_context_exists",
    })
    out = e.rank([prefer, over], ctx)
    by = {str(c.event_key): c for c in out}
    assert by["relationship_change"].score > by["contract_document"].score
    assert "CONFLICT_prefer_relationship_change" in by["relationship_change"].reason_codes


def test_diffuse_group_flag() -> None:
    e = _eng()
    cs = [
        EventCandidateV2(event_key="career_change", period="2026", score=60),
        EventCandidateV2(event_key="wealth_change", period="2026", score=58),
        EventCandidateV2(event_key="relocation", period="2026", score=57),
    ]
    out = e.rank(cs)
    assert all("DIFFUSE_group" in c.reason_codes for c in out)
