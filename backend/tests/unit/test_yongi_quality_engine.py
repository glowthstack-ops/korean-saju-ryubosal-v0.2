"""YongiQualityEngine 검증 (이벤트 엔진 재설계 Phase 6).

용신·희신·기신 극성에 따른 점수 배율과 길흉 quality 보정을 확인한다(타입 불변).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.yongi_quality_engine import YongiQualityEngine
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventQuality,
    PolarityRole,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _eng() -> YongiQualityEngine:
    return YongiQualityEngine(_DICTS)


def _cand(event: str, role: PolarityRole, score: int = 50) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score, polarity_role=role)


def test_yong_boosts_and_opportunity() -> None:
    e = _eng()
    out = e.apply([_cand("job_gain", PolarityRole.YONG, 50)])
    c = out[0]
    assert c.score > 50  # ×1.15
    assert c.quality is EventQuality.OPPORTUNITY
    assert "YONGGI_YONG" in c.reason_codes


def test_yong_achievement_event() -> None:
    e = _eng()
    out = e.apply([_cand("promotion", PolarityRole.YONG, 50)])
    assert out[0].quality is EventQuality.ACHIEVEMENT


def test_gi_flips_to_loss_for_wealth() -> None:
    e = _eng()
    out = e.apply([_cand("wealth_change", PolarityRole.GI, 50)])
    c = out[0]
    assert c.quality is EventQuality.LOSS
    assert "YONGGI_GI_flip" in c.reason_codes


def test_gi_pressure_default() -> None:
    e = _eng()
    out = e.apply([_cand("job_gain", PolarityRole.GI, 50)])
    assert out[0].quality is EventQuality.PRESSURE


def test_neutral_unchanged() -> None:
    e = _eng()
    out = e.apply([_cand("wealth_change", PolarityRole.NEUTRAL, 50)])
    assert out[0].score == 50
    assert out[0].quality is None


def test_gi_preserves_delay_quality() -> None:
    e = _eng()
    c = EventCandidateV2(
        event_key="contract_document", period="2026", score=50,
        polarity_role=PolarityRole.GI, quality=EventQuality.DELAY,
    )
    out = e.apply([c])
    assert out[0].quality is EventQuality.DELAY  # 시차 신호 보존
