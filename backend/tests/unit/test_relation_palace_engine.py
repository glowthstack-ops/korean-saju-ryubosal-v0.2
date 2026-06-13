"""RelationPalaceEngine 검증 (이벤트 엔진 재설계 Phase 6).

합충형파해 종류 × 궁성 활성으로 사건화 보너스·생활영역(palace) 부여를 확인한다(타입 불변).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.relation_palace_engine import RelationActivation, RelationPalaceEngine
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)

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
