"""LifeFitRanker 검증 (Life Event Inference 3단계).

개인 시그니처(personal_match)·현실 맥락(life_fit)·누락 사건 시드와 LEI 정렬축을 확인한다.
입력이 비면 EventEngineV2 정렬과 동치(life_fit·personal_match=0). 순수 단위(DB 미사용).
"""

from __future__ import annotations

from saju_engines.life_fit_ranker import LifeFitRanker
from saju_engines.reality_context import RealityContext
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    Pillar4,
    TenGod,
    TwelveStage,
)
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_WEALTH_DAY_FP = SignalFingerprint(
    ten_god_groups=["wealth"], palace="day_pillar", relation="CHUNG", twelve_stage="JEOL",
)


def _cand(event: str, period: str, conf: ConfidenceLevel, score: int = 50) -> EventCandidateV2:
    return EventCandidateV2(
        event_key=event, period=period, score=score, confidence_level=conf,
    )


def _wealth_day_cand(event: str, period: str, conf: ConfidenceLevel) -> EventCandidateV2:
    # 지문이 _WEALTH_DAY_FP와 일치하도록 구성.
    return EventCandidateV2(
        event_key=event, period=period, score=50, confidence_level=conf,
        source_ten_gods=[TenGod.ZHENGCAI], palace=Pillar4.DAY,
        twelve_stage=TwelveStage.JEOL, reason_codes=["REL_CHUNG_day_pillar"],
    )


def _row(event: str, period: str, outcome: LifeEventOutcome,
         fp: SignalFingerprint = _WEALTH_DAY_FP) -> LifeEventRow:
    return LifeEventRow(
        event_row_id=f"r:{period}:{event}", subject_id="s1",
        pillar_year="庚申", pillar_month="丁亥", pillar_day="己亥", gender="male",
        event_key=event, period=period, signal_fingerprint=fp,
        outcome=outcome, source=LifeEventSource.REALITY_SIGNAL_CALIBRATION,
    )


def test_empty_inputs_preserve_confidence_order() -> None:
    r = LifeFitRanker()
    cs = [
        _cand("wealth_change", "2026", ConfidenceLevel.WEAK_EVENT_CANDIDATE),
        _cand("career_change", "2026", ConfidenceLevel.STRONG_EVENT_CANDIDATE),
    ]
    out = r.rank(cs)
    assert [str(c.event_key) for c in out] == ["career_change", "wealth_change"]


def test_personal_match_boosts_matching() -> None:
    r = LifeFitRanker()
    sig = [_row("wealth_change", "2018", LifeEventOutcome.CONFIRMED)]
    matching = _wealth_day_cand("wealth_change", "2026", ConfidenceLevel.EVENT_CANDIDATE)
    other = _cand("career_change", "2026", ConfidenceLevel.EVENT_CANDIDATE)
    out = r.rank([other, matching], signature=sig)
    assert out[0].event_key == matching.event_key
    assert out[0].personal_match > 0


def test_failed_prediction_penalty() -> None:
    r = LifeFitRanker()
    sig = [_row("wealth_change", "2018", LifeEventOutcome.NOT_HAPPENED)]
    c = _wealth_day_cand("wealth_change", "2026", ConfidenceLevel.EVENT_CANDIDATE)
    out = r.rank([c], signature=sig)
    assert out[0].personal_match < 0


def test_seed_missing_relocation() -> None:
    # relocation이 2025·2026 확정(반복) — 후보에 없으면 시드.
    r = LifeFitRanker()
    sig = [
        _row("relocation", "2024", LifeEventOutcome.CONFIRMED),
        _row("relocation", "2025", LifeEventOutcome.CONFIRMED),
    ]
    cs = [_cand("career_change", "2026", ConfidenceLevel.STRONG_EVENT_CANDIDATE)]
    out = r.rank(cs, signature=sig)
    seeded = [c for c in out if str(c.event_key) == "relocation" and c.period == "2026"]
    assert seeded and "PERSONAL_SEED" in seeded[0].reason_codes
    assert seeded[0].personal_match > 0


def test_life_fit_is_top_axis() -> None:
    # life_fit이 confidence보다 위 — 맥락 맞는 약신호가 강신호를 앞선다.
    r = LifeFitRanker()
    weak_relocate = _cand("relocation", "2026", ConfidenceLevel.WEAK_EVENT_CANDIDATE)
    strong_career = _cand("career_change", "2026", ConfidenceLevel.STRONG_EVENT_CANDIDATE)
    ctx = RealityContext(relocation_planned=True)
    out = r.rank([strong_career, weak_relocate], reality_context=ctx)
    assert out[0].event_key == weak_relocate.event_key
    assert out[0].life_fit > 0


def test_empty_context_no_life_fit() -> None:
    r = LifeFitRanker()
    cs = [_cand("relocation", "2026", ConfidenceLevel.WEAK_EVENT_CANDIDATE)]
    out = r.rank(cs, reality_context=RealityContext())  # 전부 미입력
    assert out[0].life_fit == 0.0
