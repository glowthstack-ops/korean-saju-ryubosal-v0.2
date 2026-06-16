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


# ── 한신 생(生) 간접 길흉 — 직접 용신·기신보다 약(희신의 ~1/2.6 배율) ──────────────


def test_hansin_gen_good_weak_opportunity() -> None:
    """한신 생(生) 길 — quality None일 때만 약한 기회, 배율 1.015(희신보다 약)."""
    e = _eng()
    out = e.apply([_cand("job_gain", PolarityRole.HAN_GOOD, 50)])
    c = out[0]
    assert c.quality is EventQuality.OPPORTUNITY
    assert c.score == 51  # 50 × 1.015 = 50.75 → 51 (희신 1.04보다 약함)
    assert "HANSIN_GEN_GOOD" in c.reason_codes


def test_hansin_gen_good_preserves_existing_quality() -> None:
    """간접·약신호이므로 십성·게이트가 정한 품질은 보존(성취/지연 등 불변)."""
    e = _eng()
    c = EventCandidateV2(
        event_key="promotion", period="2026", score=50,
        polarity_role=PolarityRole.HAN_GOOD, quality=EventQuality.DELAY,
    )
    assert e.apply([c])[0].quality is EventQuality.DELAY


def test_hansin_gen_bad_weak_pressure() -> None:
    """한신 생(生) 흉 — quality None일 때만 약한 압박(손실/충돌 아님)."""
    e = _eng()
    out = e.apply([_cand("wealth_change", PolarityRole.HAN_BAD, 50)])
    c = out[0]
    assert c.quality is EventQuality.PRESSURE  # 강한 흉(LOSS) 아님
    assert "HANSIN_GEN_BAD" in c.reason_codes


def test_hansin_gen_bad_preserves_existing_quality() -> None:
    e = _eng()
    c = EventCandidateV2(
        event_key="job_gain", period="2026", score=50,
        polarity_role=PolarityRole.HAN_BAD, quality=EventQuality.ACHIEVEMENT,
    )
    assert e.apply([c])[0].quality is EventQuality.ACHIEVEMENT


# ── Part 3 — 직접 용신·희신이 기존 흉을 누그러뜨림(MIXED) ──────────────────────


def test_yong_softens_existing_loss_to_mixed() -> None:
    """불편한 십성도 용신이면 — 기존 흉(LOSS)을 MIXED로 완화."""
    e = _eng()
    c = EventCandidateV2(
        event_key="wealth_change", period="2026", score=50,
        polarity_role=PolarityRole.YONG, quality=EventQuality.LOSS,
    )
    out = e.apply([c])
    assert out[0].quality is EventQuality.MIXED
    assert "YONGGI_SOFTEN" in out[0].reason_codes


def test_yong_does_not_soften_delay() -> None:
    """DELAY는 길흉이 아니라 발현 타이밍 — 용신이 덮지 않는다."""
    e = _eng()
    c = EventCandidateV2(
        event_key="contract_document", period="2026", score=50,
        polarity_role=PolarityRole.YONG, quality=EventQuality.DELAY,
    )
    assert e.apply([c])[0].quality is EventQuality.DELAY
