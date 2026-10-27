"""연애운 시기 규칙(2026-10-25 외부 강의 4편 대조) — P0 결함 교정 + 실험 플래그 검증.

P0-1 삼합완성·반합성립·방합완성 변환 복구와 HAP 등급 배율, P0-2 편관 토큰(QISHA),
P0-3 new_relationship 일지 편입(플래그), P1-1 여성 편관 시드, P1-2 합 과다 감쇠,
P1-3 배우자성 오행 대운 가산.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import event_engine_v2 as ev
from saju_engines import love_timing as lt
from saju_engines.ganji_calendar import _PREFIX_TO_TYPE
from saju_engines.marriage_flow_modifier import apply_marriage_gender_weight
from saju_engines.relation_palace_engine import RelationActivation, RelationPalaceEngine
from saju_engines.ten_god_brancher import TransitSignal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Element, TenGod
from saju_shared_types.event_engine import (
    EventCandidateV2,
    LuckLayer,
    Pillar4,
    RelationKind,
)
from saju_shared_types.ganji_calendar import RelationType
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(y: int, m: int, d: int, hm: str, gender: str):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(y, m, d), birth_time=hm,
        birth_place_name="서울", gender=gender,
    ))


def _cand(event: str, score: int = 50, reasons: list[str] | None = None) -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period="2026", score=score, reason_codes=reasons or [])


# ── P0-1: 변환기 복구 + 등급 ──────────────────────────────────────────────────


def test_prefix_map_covers_full_and_half_trine() -> None:
    """엔진이 내는 `삼합완성·반합성립·방합완성`이 더는 버려지지 않는다."""
    assert _PREFIX_TO_TYPE["삼합완성"] is RelationType.THREE_HARMONY_FULL
    assert _PREFIX_TO_TYPE["반합성립"] is RelationType.THREE_HARMONY_HALF
    assert _PREFIX_TO_TYPE["방합완성"] is RelationType.DIRECTIONAL_FULL
    for t in (RelationType.THREE_HARMONY_FULL, RelationType.THREE_HARMONY_HALF,
              RelationType.DIRECTIONAL_FULL):
        assert ev._REL_KIND[t] == "HAP"
        assert ev._HAP_SUBTYPE[t] in ("three_harmony", "directional")
    assert ev._HAP_GRADE[RelationType.THREE_HARMONY_FULL] == "full"
    assert ev._HAP_GRADE[RelationType.THREE_HARMONY_HALF] == "half"
    assert ev._HAP_GRADE[RelationType.SIX_COMBINATION] == "six"


def _day_hap(grade: str) -> list[RelationActivation]:
    return [RelationActivation(
        RelationKind.HAP, Pillar4.DAY, LuckLayer.SEWOON, hap_subtype="three_harmony",
        hap_grade=grade,
    )]


def test_half_full_grade_scoped_to_day_relationship() -> None:
    """복구 등급(half·full)은 일지 × 관계 사건에만 가산 — 월주·직업 사건은 종전처럼 0(2차 조정)."""
    e = RelationPalaceEngine(_DICTS)
    month_half = [
        RelationActivation(RelationKind.HAP, Pillar4.MONTH, LuckLayer.SEWOON, hap_grade="half"),
    ]
    assert e.apply([_cand("career_change")], month_half)[0].score == 50
    day_half = _day_hap("half")
    assert e.apply([_cand("relocation")], day_half)[0].score == 50  # 일지라도 관계 사건 아님
    assert e.apply([_cand("marriage_signal")], day_half)[0].score > 50
    # 종전 등급(six·contrib)은 범위 제한 없음.
    month_six = [
        RelationActivation(RelationKind.HAP, Pillar4.MONTH, LuckLayer.SEWOON, hap_grade="six"),
    ]
    assert e.apply([_cand("career_change")], month_six)[0].score > 50


def test_hap_grade_multiplier_full_gt_half_gt_contrib() -> None:
    """일지 HAP 가산: 완성 > 왕지 반합 > 기여(=육합·천간합·종전 7)."""
    e = RelationPalaceEngine(_DICTS)
    scores = {
        g: e.apply([_cand("relationship_change")], _day_hap(g))[0].score
        for g in ("full", "half", "contrib", "six", "")
    }
    assert scores["full"] > scores["half"] > scores["contrib"] > 50
    assert scores["contrib"] == scores["six"] == scores[""]  # 종전 동작 유지


# ── P0-3: new_relationship 일지 편입은 플래그로만 ─────────────────────────────


def test_new_relationship_palace_flag() -> None:
    e = RelationPalaceEngine(_DICTS)
    act = _day_hap("six")
    off = e.apply([_cand("new_relationship")], act)[0]
    assert off.score == 50  # legacy 사각 유지(부록 A-3 #2)
    on = e.apply([_cand("new_relationship")], act, new_relationship_palace=True)[0]
    assert on.score > 50


# ── P1-2: 일지 HAP 감쇠 ────────────────────────────────────────────────────────


def test_day_hap_damping_only_day_palace() -> None:
    e = RelationPalaceEngine(_DICTS)
    base = e.apply([_cand("relationship_change")], _day_hap("six"))[0].score
    damped = e.apply([_cand("relationship_change")], _day_hap("six"), day_hap_damping=0.7)[0].score
    assert damped < base
    month = [RelationActivation(RelationKind.HAP, Pillar4.MONTH, LuckLayer.SEWOON, hap_grade="six")]
    m0 = e.apply([_cand("career_change")], month)[0].score
    m1 = e.apply([_cand("career_change")], month, day_hap_damping=0.7)[0].score
    assert m0 == m1  # 월주는 감쇠 대상 아님


def test_hap_overload_damping_threshold() -> None:
    r = _chart(1980, 11, 22, "10:00", "female")
    n = lt.natal_hap_count(r)
    expected = lt.HAP_OVERLOAD_MULT if n >= lt.HAP_OVERLOAD_THRESHOLD else 1.0
    assert lt.hap_overload_damping(r) == expected


# ── P0-2: 편관 토큰 ───────────────────────────────────────────────────────────


def test_male_qisha_only_downweighted() -> None:
    """종전 'PIANGUAN' 토큰은 어떤 코드와도 맞지 않아 남성 편관 단독이 약화되지 않았다."""
    out = apply_marriage_gender_weight([_cand("marriage_signal", 50, ["SINGLE_QISHA"])], "male")
    assert out[0].score < 50
    # 여성 편관 단독은 관성=배우자성이라 불변.
    out_f = apply_marriage_gender_weight([_cand("marriage_signal", 50, ["SINGLE_QISHA"])], "female")
    assert out_f[0].score == 50


# ── 실험 플래그 해석 ──────────────────────────────────────────────────────────


def test_resolve_love_experiments(monkeypatch: pytest.MonkeyPatch) -> None:
    assert all(v is False for v in lt.resolve_love_experiments([]).values())
    monkeypatch.setenv("SAJU_LOVE_EXPERIMENTS", "female_qisha_partner, hap_overload_damping")
    flags = lt.resolve_love_experiments()
    assert flags["female_qisha_partner"] and flags["hap_overload_damping"]
    assert not flags["new_relationship_palace"] and not flags["partner_element_daewoon"]
    with pytest.raises(ValueError):
        lt.resolve_love_experiments(["nope"])


def test_engine_default_all_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAJU_LOVE_EXPERIMENTS", raising=False)
    eng = ev.EventEngineV2(_DICTS)
    assert not any(eng._love.values())


# ── P1-1: 여성 편관 시드 ──────────────────────────────────────────────────────


def _sig(god: TenGod, layer: LuckLayer, strength: float = 1.0) -> TransitSignal:
    return TransitSignal(god, layer, "stem", strength)


def test_female_qisha_seeds() -> None:
    r = _chart(1990, 5, 5, "08:00", "female")
    seeds = lt.produce_female_qisha_seeds(
        [_sig(TenGod.PYEONGWAN, LuckLayer.SEWOON)], LuckLayer.SEWOON, r, "female", "2026",
    )
    assert {s.event_key.value for s in seeds} == {"new_relationship", "relationship_change"}
    by = {s.event_key.value: s for s in seeds}
    assert by["new_relationship"].score == lt.FEMALE_QISHA_NEW_RELATIONSHIP
    assert by["relationship_change"].score == lt.FEMALE_QISHA_RELATIONSHIP_CHANGE
    assert "LOVE_QISHA_FEMALE_PARTNER" in by["new_relationship"].reason_codes
    assert "LOVE_QISHA_STRONG_INFLOW" in by["new_relationship"].reason_codes
    # 압박 태그는 relationship_change 에만, 원국 관살 조건부.
    pressure = lt._natal_officer_count(r) >= 3 or lt._has_gwansal_honjap(r)
    assert ("LOVE_QISHA_PRESSURE" in by["relationship_change"].reason_codes) is pressure
    assert "LOVE_QISHA_PRESSURE" not in by["new_relationship"].reason_codes


def test_female_qisha_seeds_guards() -> None:
    r = _chart(1990, 5, 5, "08:00", "female")
    sig = [_sig(TenGod.PYEONGWAN, LuckLayer.SEWOON)]
    assert lt.produce_female_qisha_seeds(sig, LuckLayer.SEWOON, r, "male", "2026") == []
    assert lt.produce_female_qisha_seeds(sig, LuckLayer.DAEWOON, r, "female", "2026") == []
    # 정관·다른 층 신호만 있으면 시드 없음.
    assert lt.produce_female_qisha_seeds(
        [_sig(TenGod.JEONGGWAN, LuckLayer.SEWOON), _sig(TenGod.PYEONGWAN, LuckLayer.WOLWOON)],
        LuckLayer.SEWOON, r, "female", "2026",
    ) == []
    weak = lt.produce_female_qisha_seeds(
        [_sig(TenGod.PYEONGWAN, LuckLayer.WOLWOON, 0.9)], LuckLayer.WOLWOON, r, "female", "2026-05",
    )
    assert weak and all("LOVE_QISHA_STRONG_INFLOW" not in s.reason_codes for s in weak)


# ── P1-3: 배우자성 오행 대운 ─────────────────────────────────────────────────


def test_partner_star_element() -> None:
    r = _chart(1984, 3, 1, "12:00", "male")  # 일간 기준 극 관계만 확인
    male = lt.partner_star_element(r, "male")
    female = lt.partner_star_element(r, "female")
    assert male is not None and female is not None and male != female
    assert isinstance(male, Element)
    assert lt.partner_star_element(r, "unknown") is None


def test_partner_element_daewoon_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    import saju_engines.marriage_resource as mr

    r = _chart(1984, 3, 1, "12:00", "female")
    el = lt.partner_star_element(r, "female")
    assert el is not None
    # 대운 지지가 배우자성 오행인 간지 하나 고르기.
    from saju_shared_types.constants import BRANCH_ELEMENT
    branch = next(b for b, e in BRANCH_ELEMENT.items() if e == el)
    dw = LuckPillar(
        label="2020", period_type="daewoon", ganji=f"甲{branch.value}", stem="甲",
        branch=branch.value, stem_ten_god="", branch_ten_god="",
    )
    stack = [(LuckLayer.DAEWOON, dw)]
    cands = [_cand("marriage_signal"), _cand("career_change")]

    class _MR:
        spouse_star_absent = True

    monkeypatch.setattr(mr, "analyze_marriage_resource", lambda *_a, **_k: _MR())
    out = lt.apply_partner_element_daewoon(cands, stack, r, "female")
    assert out[0].score == 50 + lt.PARTNER_ELEMENT_DAEWOON_BONUS
    assert any(c.startswith("LOVE_PARTNER_ELEMENT_DAEWOON_") for c in out[0].reason_codes)
    assert out[1].score == 50
    # 배우자성이 투출돼 있으면 무변경.
    _MR.spouse_star_absent = False
    assert all(c.score == 50 for c in lt.apply_partner_element_daewoon(cands, stack, r, "female"))
