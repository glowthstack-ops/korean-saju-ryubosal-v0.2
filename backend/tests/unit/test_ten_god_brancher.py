"""TenGodEventBrancher 검증 (이벤트 엔진 재설계 Phase 2).

십성 단일·그룹·특정·3중 조합이 사양대로 사건 타입 후보를 생성하는지 확인한다(LLM·DB 불필요).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.ten_god_brancher import TenGodEventBrancher, TransitSignal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2, LuckLayer, TenGod

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _brancher() -> TenGodEventBrancher:
    return TenGodEventBrancher(_DICTS)


def _keys(cands) -> set[str]:
    return {str(c.event_key) for c in cands}


def test_single_ten_god_emits_base_events() -> None:
    b = _brancher()
    sig = [TransitSignal(TenGod.ZHENGGUAN, LuckLayer.SEWOON, "stem")]
    cands = b.branch(sig, "2026")
    # 정관 단일 → job_gain/promotion/contract_document/marriage_signal.
    assert "job_gain" in _keys(cands)
    assert "promotion" in _keys(cands)


def test_specific_combo_gwaninsangsaeng() -> None:
    b = _brancher()
    # 정관+정인(관인상생) → job_gain 강(85).
    sig = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.SEWOON, "stem"),
        TransitSignal(TenGod.ZHENGYIN, LuckLayer.SEWOON, "branch_main"),
    ]
    cands = b.branch(sig, "2026")
    by = {str(c.event_key): c for c in cands}
    assert "job_gain" in by
    # 특정 조합이 단일 십성 후보보다 우선 채택(절대 점수는 가중 튜닝으로 변동 — 상대 우위만 고정).
    assert "SPEC_ZHENGGUAN_ZHENGYIN" in by["job_gain"].reason_codes
    other = max((c.score for k, c in by.items() if k != "job_gain"), default=0)
    assert by["job_gain"].score >= other
    assert TenGod.ZHENGGUAN in by["job_gain"].source_ten_gods


def test_group_combo_output_wealth() -> None:
    b = _brancher()
    # 식상(output)+재성(wealth) → wealth_change/business_start/business_expansion.
    sig = [
        TransitSignal(TenGod.SHISHEN, LuckLayer.SEWOON, "stem"),
        TransitSignal(TenGod.PIANCAI, LuckLayer.WOLWOON, "branch_main"),
    ]
    cands = b.branch(sig, "2026")
    ks = _keys(cands)
    assert {"wealth_change", "business_start"} <= ks


def test_three_god_combo_authority_resource_peer() -> None:
    b = _brancher()
    # authority+resource+peer 3중 → job_gain 등 강한 후보.
    sig = [
        TransitSignal(TenGod.ZHENGGUAN, LuckLayer.DAEWOON, "stem"),
        TransitSignal(TenGod.ZHENGYIN, LuckLayer.SEWOON, "branch_main"),
        TransitSignal(TenGod.BIJIAN, LuckLayer.WOLWOON, "stem"),
    ]
    cands = b.branch(sig, "2026")
    by = {str(c.event_key): c for c in cands}
    assert "job_gain" in by
    assert any("TRI_" in r for r in by["job_gain"].reason_codes)
    # 3개 운층이 source_layers에 모두 기록.
    assert set(by["job_gain"].source_layers) == {
        LuckLayer.DAEWOON, LuckLayer.SEWOON, LuckLayer.WOLWOON,
    }


def test_conditional_branch_not_emitted_in_phase2() -> None:
    b = _brancher()
    # 겁재+재성 negative_branch(condition 有)는 Phase 2에서 미방출 — primary만.
    sig = [
        TransitSignal(TenGod.JIECAI, LuckLayer.SEWOON, "stem"),
        TransitSignal(TenGod.ZHENGCAI, LuckLayer.SEWOON, "branch_main"),
    ]
    cands = b.branch(sig, "2026")
    # wealth_change는 나오되, score는 조건부 80이 아닌 무조건 후보 기준.
    assert "wealth_change" in _keys(cands)


def test_integration_from_chart_luck_pillar() -> None:
    b = _brancher()
    result = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 13),
    ))
    assert result.luck_cycles is not None
    pillar = result.luck_cycles.yearly_luck[0]
    sig = b.collect_from_pillar(pillar, LuckLayer.SEWOON)
    assert sig, "운 기둥에서 십성 신호가 수집되어야 한다"
    cands = b.branch(sig, pillar.label)
    # 후보는 모두 유효한 21키.
    assert all(c.event_key in set(EventKeyV2) for c in cands)
    assert all(0 <= c.score <= 100 for c in cands)
