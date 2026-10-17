"""용신 배율 품질군 차등 + 십성별 유익형 후보 + 운↔운 충 이동형 보조 가산 (2026-10-15 데굴님 승인).

반례 원칙(2026-10-14 교훈): OFF 불변·중복 곱 금지·후보당 1회 가산·충 없는 달 불변을 전부 고정한다.
실사례: 1980-11-22 09:40 서울 남 — 대운 壬辰 ↔ 2026-10 戊戌월 辰戌충(운↔운), 용신 土=비겁.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import period_v2_config
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.favorable_role_tiering import load_favorable_tiering
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_engines.transit_clash_support import load_transit_clash_rule, transit_clashes
from saju_engines.yongi_quality_engine import YongiQualityEngine
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
    TenGod,
)
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.luck import LuckPillar

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_CASE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)


def _snapshot(cands):
    return [(c.event_key, c.period, c.score, tuple(c.reason_codes)) for c in cands]


def _month_candidates(birth: BirthInput, years: tuple[int, ...], **overrides):
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    assert c2.luck_cycles is not None
    c2.luck_cycles.monthly_luck = [p for y in years for p in luck_months(birth, y)]
    return build_event_engine_v2(_DICTS, **overrides).score(c2, levels={GanjiLevel.MONTH})


def _by_key(cands, period: str):
    return {c.event_key: c for c in cands if c.period == period}


# ── 사전 ─────────────────────────────────────────────────────────────────────

def test_tiering_rule_loads_with_modes_and_extra_events():
    rule = load_favorable_tiering(_DICTS)
    assert rule is not None and rule.rule_id == "YONG_TIERED_MULTIPLIER"
    assert rule.roles == {PolarityRole.YONG, PolarityRole.HEE, PolarityRole.YONG_STRONG}
    assert rule.modes == {"a": 1.10, "b": 1.20}
    assert EventKeyV2.PROMOTION in rule.favorable[TenGod.QISHA]
    assert EventKeyV2.CREATIVE_OUTPUT in rule.favorable[TenGod.PIANYIN]
    assert EventKeyV2.CHILDBIRTH not in rule.favorable[TenGod.SHISHEN]  # 현실 게이트 대상
    assert {(e.incoming, e.event) for e in rule.extra_base_events} == {
        (TenGod.QISHA, EventKeyV2.PROMOTION), (TenGod.PIANYIN, EventKeyV2.CREATIVE_OUTPUT),
    }
    assert rule.is_favorable([TenGod.SHANGGUAN], EventKeyV2.PUBLIC_EXPOSURE)
    assert not rule.is_favorable([TenGod.SHANGGUAN], EventKeyV2.CAREER_CHANGE)


def test_transit_clash_rule_loads():
    rule = load_transit_clash_rule(_DICTS)
    assert rule is not None and rule.bonus == 4
    assert rule.events == {EventKeyV2.CAREER_CHANGE, EventKeyV2.RELOCATION}


# ── OFF 불변 ─────────────────────────────────────────────────────────────────

def test_off_mode_is_byte_identical_to_default():
    base = _month_candidates(_CASE, (2025, 2026))
    off = _month_candidates(
        _CASE, (2025, 2026), yong_tier_mode="off", enable_transit_clash_support=False,
    )
    assert _snapshot(base) == _snapshot(off)
    assert not any(
        r.startswith(("YONG_TIER", "TRANSIT_CLASH")) for c in off for r in c.reason_codes
    )


# ── 품질군 차등 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("mode", "mult"), [("a", 1.10), ("b", 1.20)])
def test_quality_engine_tiered_multiplier_is_exact_and_single(mode, mult):
    """합성 후보로 정확히 검증 — 유익형만 모드 배율, 그 외 1.00, 기존 1.12 와 중복 곱 없음,
    기신 불변."""
    rule = load_favorable_tiering(_DICTS)
    assert rule is not None
    tiered = YongiQualityEngine(_DICTS, tiering=rule, tier_mode=mode)
    legacy = YongiQualityEngine(_DICTS)

    def _c(event: EventKeyV2, role: PolarityRole, gods: list[TenGod]) -> EventCandidateV2:
        return EventCandidateV2(
            event_key=event, period="2026-10", score=80, polarity_role=role, source_ten_gods=gods,
        )

    _fav_in = _c(EventKeyV2.PUBLIC_EXPOSURE, PolarityRole.YONG_STRONG, [TenGod.SHANGGUAN])
    fav = tiered.apply([_fav_in])[0]
    assert fav.score == round(80 * mult) and fav.contributions["yongi"] == round(80 * mult) - 80
    assert "YONG_TIER_FAVORABLE" in fav.reason_codes and "YONG_TIER_FLAT" not in fav.reason_codes
    _flat_in = _c(EventKeyV2.CAREER_CHANGE, PolarityRole.YONG_STRONG, [TenGod.SHANGGUAN])
    flat = tiered.apply([_flat_in])[0]
    assert flat.score == 80 and flat.contributions["yongi"] == 0.0
    assert "YONG_TIER_FLAT" in flat.reason_codes
    # 기존 일괄 배율(강한 용신 1.12)은 이 모드에서 쓰지 않는다 — 90 이 아니라 round(80*mult).
    assert legacy.apply([_fav_in])[0].score == 90
    # 기신 쪽은 모드와 무관하게 동일.
    gi_t = tiered.apply([_c(EventKeyV2.WEALTH_CHANGE, PolarityRole.GI, [TenGod.ZHENGCAI])])[0]
    gi_l = legacy.apply([_c(EventKeyV2.WEALTH_CHANGE, PolarityRole.GI, [TenGod.ZHENGCAI])])[0]
    assert (gi_t.score, gi_t.quality) == (gi_l.score, gi_l.quality)
    assert not any(r.startswith("YONG_TIER") for r in gi_t.reason_codes)


@pytest.mark.parametrize("mode", ["a", "b"])
def test_pipeline_every_yong_candidate_tagged_once_and_flat_has_zero_yongi(mode):
    rule = load_favorable_tiering(_DICTS)
    assert rule is not None
    cands = _month_candidates(_CASE, (2025, 2026), yong_tier_mode=mode)
    yong = [c for c in cands if c.polarity_role in rule.roles]
    assert yong, "용신 역할 달이 있어야 한다(2026-10 戊戌 등)"
    for c in yong:
        tags = [r for r in c.reason_codes if r.startswith("YONG_TIER")]
        assert len(tags) == 1
        if tags[0] == "YONG_TIER_FLAT":
            assert not rule.is_favorable(c.source_ten_gods, c.event_key, c.reason_codes)
            assert c.contributions.get("yongi", 0.0) == 0.0
        else:
            assert rule.is_favorable(c.source_ten_gods, c.event_key, c.reason_codes)
            assert c.contributions.get("yongi", 0.0) > 0.0


def test_real_case_peer_mobility_seed_is_favorable_by_reason_code():
    """비겁 용신 이동 시드는 유익형(2026-10-15 데굴님 확정: 유익·불익은 '이동 뒤 흐름'으로 —
    용신운이라 이동 뒤 기반이 나쁘지 않게 흐를 수 있다). 사건 키가 아니라 근거 코드로 편입된다."""
    rule = load_favorable_tiering(_DICTS)
    assert rule is not None and "PEER_YONGSIN_MOBILITY" in rule.favorable_reason_prefixes
    assert rule.is_favorable([TenGod.JIECAI], EventKeyV2.CAREER_CHANGE, ["PEER_YONGSIN_MOBILITY"])
    assert not rule.is_favorable([TenGod.JIECAI], EventKeyV2.CAREER_CHANGE, ["SINGLE_JIECAI"])
    assert not rule.is_favorable([TenGod.JIECAI], EventKeyV2.CAREER_CHANGE, ["PEER_GISIN_MOBILITY"])
    off = _by_key(_month_candidates(_CASE, (2025, 2026)), "2026-10")
    a = _by_key(_month_candidates(_CASE, (2025, 2026), yong_tier_mode="a"), "2026-10")
    cc = a[EventKeyV2.CAREER_CHANGE]
    assert "PEER_YONGSIN_MOBILITY" in cc.reason_codes and "YONG_TIER_FAVORABLE" in cc.reason_codes
    assert cc.score >= off[EventKeyV2.CAREER_CHANGE].score - 3  # 1.10 vs 종전 1.12 — 순위 2위 유지


def test_extra_base_events_appear_only_when_mode_on():
    """편관 유입 달에 promotion 기본 후보가 모드 ON 일 때만 생긴다(OFF 불변)."""
    years = (2025, 2026, 2027)
    months = [p for y in years for p in luck_months(_CASE, y)]
    qisha = [p.label for p in months if p.stem_ten_god == "편관"]
    assert qisha, "편관 천간 월운이 있어야 한다"
    off = _month_candidates(_CASE, years)
    on = _month_candidates(_CASE, years, yong_tier_mode="a")

    def _promo(cands):
        return [
            c for c in cands
            if c.period in qisha and c.event_key is EventKeyV2.PROMOTION
            and "SINGLE_QISHA" in c.reason_codes
        ]

    assert _promo(on), "편관 달 promotion 기본 후보(SINGLE_QISHA) 가 모드 ON 에서 생겨야 한다"
    assert not _promo(off)


# ── 운↔운 충 보조 가산 ───────────────────────────────────────────────────────

def _pillar(label: str, ganji: str) -> LuckPillar:
    return LuckPillar(
        label=label, period_type="month", ganji=ganji, stem=ganji[0], branch=ganji[1],
        stem_ten_god="", branch_ten_god="",
    )


def test_transit_clashes_only_between_layers():
    stack = [
        (LuckLayer.DAEWOON, _pillar("dw", "壬辰")),
        (LuckLayer.SEWOON, _pillar("2026", "丙午")),
        (LuckLayer.WOLWOON, _pillar("2026-10", "戊戌")),
    ]
    assert [c.code() for c in transit_clashes(stack)] == ["daewoon辰-wolwoon戌"]
    no_clash = [
        (LuckLayer.DAEWOON, _pillar("dw", "壬辰")),
        (LuckLayer.WOLWOON, _pillar("2026-08", "丙申")),
    ]
    assert transit_clashes(no_clash) == []


def test_real_case_clash_support_bonus_once_on_mobility_events_only():
    off = _by_key(_month_candidates(_CASE, (2025, 2026)), "2026-10")
    on = _by_key(
        _month_candidates(_CASE, (2025, 2026), enable_transit_clash_support=True), "2026-10",
    )
    cc = on[EventKeyV2.CAREER_CHANGE]
    codes = [r for r in cc.reason_codes if r.startswith("TRANSIT_CLASH")]
    assert codes == ["TRANSIT_CLASH_daewoon辰-wolwoon戌"]
    assert cc.contributions["transit_clash"] == 4.0
    assert cc.score >= off[EventKeyV2.CAREER_CHANGE].score
    wc = on[EventKeyV2.WEALTH_CHANGE]  # 재물은 충개고 경로만 — 보조 가산 대상 아님
    assert not any(r.startswith("TRANSIT_CLASH") for r in wc.reason_codes)
    assert wc.score == off[EventKeyV2.WEALTH_CHANGE].score


def test_clash_support_leaves_months_without_transit_clash_unchanged():
    off = _month_candidates(_CASE, (2025, 2026))
    on = _month_candidates(_CASE, (2025, 2026), enable_transit_clash_support=True)
    off_m = [x for x in _snapshot(off) if x[1] == "2026-08"]
    on_m = [x for x in _snapshot(on) if x[1] == "2026-08"]
    assert off_m == on_m  # 2026-08 丙申: 대운 辰·세운 午와 충 없음


# ── 설정·직렬화 ───────────────────────────────────────────────────────────────

def test_config_defaults_off_and_rejects_invalid_mode(monkeypatch):
    assert period_v2_config.YONG_TIERED_MULTIPLIER_MODE == "off"
    assert period_v2_config.TRANSIT_CLASH_SUPPORT_ENABLED is False
    monkeypatch.setattr(period_v2_config, "YONG_TIERED_MULTIPLIER_MODE", "c")
    with pytest.raises(period_v2_config.ConfigurationError):
        period_v2_config.validate_flags()


def test_reason_codes_ko_labels_new_prefixes():
    ko = reason_codes_ko(
        ["YONG_TIER_FAVORABLE", "YONG_TIER_FLAT", "TRANSIT_CLASH_daewoon辰-wolwoon戌"]
    )
    assert "용신 유익형 가중(유익한 발현 후보 우선)" in ko
    assert "운끼리 충(변화 보조 근거)" in ko
    assert len(ko) == 2  # FLAT 은 감사용 — 한글 라벨 없음
