"""RelationPalaceEngine 검증 (이벤트 엔진 재설계 Phase 6).

합충형파해 종류 × 궁성 활성으로 사건화 보너스·생활영역(palace) 부여를 확인한다(타입 불변).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from saju_engines.relation_palace_engine import RelationActivation, RelationPalaceEngine
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _eng() -> RelationPalaceEngine:
    return RelationPalaceEngine(_DICTS)


def _cand(event: str, score: int = 50) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score)


def test_month_palace_activates_career() -> None:
    e = _eng()
    # 세운 충이 월주를 자극 → career_change 발동 가점 + palace=월주.
    act = [RelationActivation(RelationKind.CHUNG, Pillar4.MONTH, LuckLayer.SEWOON)]
    out = e.apply([_cand("career_change", 50)], act)
    c = out[0]
    assert c.score > 50
    assert c.palace is Pillar4.MONTH
    assert any(r.startswith("REL_CHUNG_month_pillar") for r in c.reason_codes)


def test_palace_mismatch_no_bonus() -> None:
    e = _eng()
    # 시주 자극인데 후보는 직업(career_change) → 시주 event_domains에 없으므로 무보정.
    act = [RelationActivation(RelationKind.HAP, Pillar4.HOUR, LuckLayer.SEWOON)]
    out = e.apply([_cand("career_change", 50)], act)
    assert out[0].score == 50
    assert out[0].palace is None


def test_compound_hyeong_chung_bonus() -> None:
    e = _eng()
    act = [
        RelationActivation(RelationKind.HYEONG, Pillar4.MONTH, LuckLayer.SEWOON),
        RelationActivation(RelationKind.CHUNG, Pillar4.MONTH, LuckLayer.SEWOON),
    ]
    out = e.apply([_cand("career_change", 50)], act)
    assert "REL_COMPOUND" in out[0].reason_codes
    assert out[0].score > 60


def test_relation_to_palace_rule_boost() -> None:
    e = _eng()
    # 일주 자극 + relocation: day_pillar event_domains에 relocation 포함 → 가점·palace.
    act = [RelationActivation(RelationKind.CHUNG, Pillar4.DAY, LuckLayer.SEWOON)]
    out = e.apply([_cand("relocation", 50)], act)
    assert out[0].palace is Pillar4.DAY
    assert out[0].score > 50


def test_no_activation_unchanged() -> None:
    e = _eng()
    out = e.apply([_cand("wealth_change", 50)], [])
    assert out[0].score == 50
    assert out[0].palace is None


# Task 2 — 복음(伏吟) 결혼 보조 트리거: 운 지지=원국 일지 → 일지궁 marriage_signal 강화.
def test_bokeum_day_boosts_marriage_signal() -> None:
    e = _eng()
    act = [
        RelationActivation(RelationKind.BOKEUM, Pillar4.DAY, LuckLayer.SEWOON, position="branch"),
    ]
    out = e.apply([_cand("marriage_signal", 50)], act)
    c = out[0]
    assert c.score > 50  # 복음이 결혼 신호를 강화(단독 생성 아님, 기존 후보 가점)
    assert c.palace is Pillar4.DAY
    assert any(r.startswith("REL_BOKEUM_day_pillar") for r in c.reason_codes)


def test_bokeum_weaker_than_clash() -> None:
    e = _eng()
    bok = e.apply(
        [_cand("marriage_signal", 50)],
        [RelationActivation(RelationKind.BOKEUM, Pillar4.DAY, LuckLayer.SEWOON, position="branch")],
    )[0]
    chung = e.apply(
        [_cand("marriage_signal", 50)],
        [RelationActivation(RelationKind.CHUNG, Pillar4.DAY, LuckLayer.SEWOON, position="branch")],
    )[0]
    # 복음(보조 트리거, bonus 5)은 충(bonus 10)보다 약하게 가점된다.
    assert 50 < bok.score <= chung.score


def test_bokeum_activation_detection() -> None:
    """_bokeum_activations — 운 지지가 원국 일지와 같을 때만 BOKEUM/일지 발동(타 지지는 미발동)."""
    from types import SimpleNamespace

    from saju_api.services.manse_service import calculate
    from saju_engines.event_engine_v2 import _bokeum_activations
    from saju_shared_types.birth_input import BirthInput

    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1985-03-15", birth_time="14:30",
        birth_place_name="서울", gender="female",
    ))
    assert r.pillars is not None
    day_branch = r.pillars.day.branch  # 癸丑 → 丑
    # 일지와 같은 지지 → 복음 발동(일지궁).
    acts = _bokeum_activations(
        r, cast("LuckPillar", SimpleNamespace(branch=day_branch)), LuckLayer.SEWOON)
    assert len(acts) == 1
    assert acts[0].kind is RelationKind.BOKEUM and acts[0].palace is Pillar4.DAY
    assert acts[0].position == "branch" and acts[0].layer is LuckLayer.SEWOON
    # 다른 지지 → 미발동.
    other = "寅" if day_branch != "寅" else "卯"
    assert _bokeum_activations(
        r, cast("LuckPillar", SimpleNamespace(branch=other)), LuckLayer.SEWOON) == []


# ── B2 보강(RELATIONSHIP_EVENT_SYSTEM 부록 B) — REL_COMPOUND 고아 방지 불변식 ──────


def test_compound_always_with_constituent_codes() -> None:
    """정상 경로에서 REL_COMPOUND는 반드시 구성 REL 코드와 동반한다(고아 금지).

    구성 코드가 제거되면 출력 가드가 COMPOUND 단독을 보수적 미판정해 방향 누수가
    재발할 수 있으므로, 엔진 산출 불변식으로 고정한다.
    """
    e = _eng()
    act = [
        RelationActivation(RelationKind.CHUNG, Pillar4.DAY, LuckLayer.SEWOON),
        RelationActivation(RelationKind.HAP, Pillar4.DAY, LuckLayer.SEWOON),
    ]
    out = e.apply([_cand("relationship_change", 50)], act)
    codes = out[0].reason_codes
    assert "REL_COMPOUND" in codes  # 합+충 복합 → COMPOUND 발생 전제 확인
    assert any(c.startswith("REL_") and c != "REL_COMPOUND" for c in codes)
