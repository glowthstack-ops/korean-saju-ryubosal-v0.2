"""TwelveStageModifier 검증 (이벤트 엔진 재설계 Phase 3).

12운성이 사건 타입을 새로 만들지 않고 후보의 상태(event_phase)·점수만 보정하는지 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.twelve_stage_modifier import TwelveStageModifier
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    TwelveStage,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _mod() -> TwelveStageModifier:
    return TwelveStageModifier(_DICTS)


def _cand(event: str, score: int = 60) -> EventCandidateV2:
    return EventCandidateV2(
        event_key=event, period="2026", score=score, source_layers=[LuckLayer.SEWOON],
    )


def test_does_not_create_new_event_types() -> None:
    m = _mod()
    cands = [_cand("job_gain")]
    out = m.apply(cands, {LuckLayer.SEWOON: TwelveStage.GEONROK})
    assert {str(c.event_key) for c in out} == {"job_gain"}  # 타입 불변


def test_geonrok_boosts_job_gain_and_sets_phase() -> None:
    m = _mod()
    out = m.apply([_cand("job_gain", 60)], {LuckLayer.SEWOON: TwelveStage.GEONROK})
    c = out[0]
    assert c.score > 60  # 건록은 job_gain boost
    assert c.twelve_stage == TwelveStage.GEONROK
    assert c.event_phase == "stabilization"
    assert any(r.startswith("stage:GEONROK") for r in c.reason_codes)


def test_jeol_reduces_job_gain() -> None:
    m = _mod()
    out = m.apply([_cand("job_gain", 60)], {LuckLayer.SEWOON: TwelveStage.JEOL})
    assert out[0].score < 60  # 절은 job_gain reduce(지연·조건 불리)


def test_geonrok_reduces_career_change() -> None:
    # 건록(안정)은 career_change(이직) 감점 — "인성+건록→이직 감점" 취지.
    m = _mod()
    out = m.apply([_cand("career_change", 60)], {LuckLayer.SEWOON: TwelveStage.GEONROK})
    assert out[0].score < 60


def test_layer_stage_combo_bonus() -> None:
    # 대운 seed(절/태/양) + 세운 growth(장생/목욕/관대) → business_start 보너스.
    m = _mod()
    out = m.apply(
        [EventCandidateV2(event_key="business_start", period="2026", score=55,
                          source_layers=[LuckLayer.DAEWOON, LuckLayer.SEWOON])],
        {LuckLayer.DAEWOON: TwelveStage.YANG, LuckLayer.SEWOON: TwelveStage.JANGSAENG},
    )
    # 단계 보정 + DAEWOON_SEED_SEWOON_START 보너스로 상승.
    assert out[0].score > 55


def test_delta_capped() -> None:
    m = _mod()
    out = m.apply([_cand("promotion", 50)], {LuckLayer.SEWOON: TwelveStage.JEWANG})
    assert out[0].score - 50 <= 18  # 단계 보정 한도
