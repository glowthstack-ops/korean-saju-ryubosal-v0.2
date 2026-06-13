"""LayerFlowModifier 검증 (이벤트 엔진 재설계 Phase 4).

층위 결합 배율·동일 십성 반복·MIXED·십성 생성/역 흐름 보정을 확인한다(타입 불변).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.layer_flow_modifier import LayerFlowModifier
from saju_engines.ten_god_brancher import TransitSignal
from saju_shared_types.event_engine import EventCandidateV2, LuckLayer, TenGod

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _mod() -> LayerFlowModifier:
    return LayerFlowModifier(_DICTS)


def _cand(event: str, layers: list[LuckLayer], gods: list[TenGod], score: int = 50):
    return EventCandidateV2(
        event_key=event, period="2026", score=score,
        source_layers=layers, source_ten_gods=gods,
    )


def test_layer_combination_multiplier() -> None:
    m = _mod()
    sig = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.DAEWOON, "stem"),
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.SEWOON, "stem"),
    ]
    c = _cand("job_gain", [LuckLayer.DAEWOON, LuckLayer.SEWOON], [TenGod.ZHENGGUAN], 50)
    out = m.apply([c], sig)
    # 대운+세운 결합 ×1.25 + 동일 십성 반복(+8) → 50*1.25=62.5 +8 ≈ 71.
    assert out[0].score > 50
    assert "REPEAT_SAME_TEN_GOD" in out[0].reason_codes


def test_mixed_authority_bonus() -> None:
    m = _mod()
    # 정관+편관 동시 → career_change/job_gain/health_attention 가점.
    sig = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.SEWOON, "stem"),
        TransitSignal(TenGod.QISHA, LuckLayer.SEWOON, "branch_main"),
    ]
    c = _cand("career_change", [LuckLayer.SEWOON], [TenGod.ZHENGGUAN, TenGod.QISHA], 50)
    out = m.apply([c], sig)
    assert out[0].score > 50
    assert "MIXED_TEN_GOD" in out[0].reason_codes


def test_generating_flow_bonus() -> None:
    m = _mod()
    # 대운 식상(output)→세운 재성(wealth)→월운 관성(authority): 생성 흐름 +12.
    sig = [
        TransitSignal(TenGod.SHISHEN, LuckLayer.DAEWOON, "stem"),
        TransitSignal(TenGod.ZHENGCAI, LuckLayer.SEWOON, "stem"),
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.WOLWOON, "stem"),
    ]
    c = _cand("wealth_change", [LuckLayer.SEWOON], [TenGod.ZHENGCAI], 50)
    out = m.apply([c], sig)
    assert "FLOW_GEN" in out[0].reason_codes
    assert out[0].score > 50  # 상생 흐름 보너스가 base(50)를 끌어올림(절대값은 튜닝 변동)


def test_reverse_flow_penalty() -> None:
    m = _mod()
    # 대운 관성→세운 재성→월운 식상: 역흐름 -10.
    sig = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.DAEWOON, "stem"),
        TransitSignal(TenGod.ZHENGCAI, LuckLayer.SEWOON, "stem"),
        TransitSignal(TenGod.SHISHEN, LuckLayer.WOLWOON, "stem"),
    ]
    c = _cand("wealth_change", [LuckLayer.SEWOON], [TenGod.ZHENGCAI], 50)
    out = m.apply([c], sig)
    assert "FLOW_REVERSE" in out[0].reason_codes
    assert out[0].score < 50


def test_no_type_creation() -> None:
    m = _mod()
    sig = [TransitSignal(TenGod.ZHENGCAI, LuckLayer.SEWOON, "stem")]
    out = m.apply([_cand("wealth_change", [LuckLayer.SEWOON], [TenGod.ZHENGCAI])], sig)
    assert {str(c.event_key) for c in out} == {"wealth_change"}
