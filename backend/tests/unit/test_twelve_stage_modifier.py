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


# ── P1-b 채널 모델(2026-09-10 사용자 승인) — 사전 SSOT·정합 불변식 ────────────────


def test_channel_model_is_active_and_covers_all_events_and_stages() -> None:
    import json

    m = _mod()
    assert m.channel_model_active
    raw = json.loads((_DICTS / "event_engine" / "twelve_stage_modifier.json").read_text("utf-8"))
    cm = raw["channel_model"]
    branching = json.loads(
        (_DICTS / "event_engine" / "transit_ten_god_branching.json").read_text("utf-8")
    )
    events = set(branching["event_keys"])
    assert set(cm["event_channel_evidence"]) == events  # 21종 전수
    assert set(cm["stage_channels"]) == {s.value for s in TwelveStage}  # 12스테이지 전수
    channels = {ch for v in cm["stage_channels"].values() for ch in v}
    for ev, evidence in cm["event_channel_evidence"].items():
        assert evidence, ev
        for ch, w in evidence.items():
            # 감점·가점 채널은 어떤 스테이지에서든 도달 가능해야 한다(사문 채널 금지 — daily 이식).
            assert ch in channels, (ev, ch)
            assert -0.4 <= w <= 0.4 and w != 0, (ev, ch, w)


def test_channel_delta_matches_formula_and_ignores_legacy_lists() -> None:
    import json

    m = _mod()
    raw = json.loads((_DICTS / "event_engine" / "twelve_stage_modifier.json").read_text("utf-8"))
    cm = raw["channel_model"]
    for ev, evidence in cm["event_channel_evidence"].items():
        for stage_key, chans in cm["stage_channels"].items():
            total = sum(w * chans.get(ch, 0.0) for ch, w in evidence.items())
            expected = round(cm["scale"] * total)
            assert m.channel_delta(ev, TwelveStage(stage_key)) == expected, (ev, stage_key)
    # 구 규칙 목록을 흔들어도 채점은 변하지 않는다(채널 모델이 SSOT).
    before = m.channel_delta("job_gain", TwelveStage.GEONROK)
    m._stage[TwelveStage.GEONROK].good_for.clear()
    m._event_specific["job_gain"].boost_stages.clear()
    assert m.channel_delta("job_gain", TwelveStage.GEONROK) == before
    out = m.apply([_cand("job_gain", 60)], {LuckLayer.SEWOON: TwelveStage.GEONROK})
    assert out[0].contributions["stage"] == float(before) and before > 0


def test_stage_means_are_signed_by_stage_semantics() -> None:
    """사·병·절은 사건 평균이 음수, 제왕·건록·장생은 양수 — 포화 수정(P1-a)+채널화(P1-b)의 목적."""
    import json

    m = _mod()
    branching_path = _DICTS / "event_engine" / "transit_ten_god_branching.json"
    events = json.loads(branching_path.read_text("utf-8"))["event_keys"]
    def mean(stage: TwelveStage) -> float:
        vals = [m.channel_delta(ev, stage) for ev in events]
        return sum(vals) / len(vals)
    assert mean(TwelveStage.JEWANG) > 0 and mean(TwelveStage.GEONROK) > 0
    assert mean(TwelveStage.JANGSAENG) > 0
    assert mean(TwelveStage.BYEONG) < 0 and mean(TwelveStage.JEOL) < 0
    assert all(abs(m.channel_delta(ev, st)) <= 18 for ev in events for st in TwelveStage)

