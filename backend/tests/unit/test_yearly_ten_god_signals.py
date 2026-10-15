"""세운 육신별 사건 신호 5계열(2026-10-15, 외부 교재 6장 대조 — 데굴님 '적용 후 감수')."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate, luck_months, luck_years
from saju_engines import period_v2_config
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_engines.yearly_ten_god_signals import load_yearly_signal_rules
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2, LuckLayer
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_YONG = BirthInput(  # 己亥 — 원국·대운에 관살 없음(관성 木 천간·본기 없음, 대운 壬辰)
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
_GISIN = BirthInput(  # 己未 — 년간 乙(편관) → 관살 존재
    birth_date=date(1985, 5, 20), birth_time="10:00:00", birth_place_name="서울", gender="male",
)


def _months(birth: BirthInput, year: int, **kw):
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    assert c2.luck_cycles is not None
    c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
    return build_event_engine_v2(_DICTS, **kw).score(c2, levels={GanjiLevel.MONTH})


def _years(birth: BirthInput, **kw):
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    assert c2.luck_cycles is not None
    c2.luck_cycles.yearly_luck = luck_years(birth, list(range(2022, 2032)))  # 관성·식상 해 포함
    return build_event_engine_v2(_DICTS, **kw).score(c2, levels={GanjiLevel.YEAR})


def test_rules_load_with_five_families_and_defaults_on():
    rules = load_yearly_signal_rules(_DICTS)
    ids = {r.rule_id for r in rules}
    assert {
        "JIECAI_RESTRAINED_BY_OFFICER", "SAME_GOD_HAP_PEER", "SAME_GOD_HAP_AUTHORITY",
        "SAME_GOD_HAP_WEALTH", "RESOURCE_WEALTH_HAP_SPECULATION", "OFFICER_YEAR_RELOCATION",
        "OUTPUT_YEAR_RELATIONSHIP_CHANGE",
    } <= ids
    seeds = [r for r in rules if r.effect == "seed_if_absent"]
    assert all(r.layers == {LuckLayer.SEWOON} for r in seeds)  # 세운 전용
    assert period_v2_config.YEARLY_TEN_GOD_SIGNALS_ENABLED is True


def test_off_is_byte_identical():
    on = _months(_GISIN, 2026)
    off = _months(_GISIN, 2026, enable_yearly_ten_god_signals=False)
    snap = lambda cs: [(c.event_key, c.period, c.score, tuple(c.reason_codes)) for c in cs]  # noqa: E731
    assert snap(on) != snap(off) or not on  # 켜면 어딘가는 달라진다(1985 명식 2026-10 겁재 완화)
    prefixes = ("JIECAI_RESTRAINED", "SAME_GOD_HAP", "RESOURCE_WEALTH_HAP", "OFFICER_YEAR",
                "OUTPUT_YEAR")
    assert not any(r.startswith(prefixes) for c in off for r in c.reason_codes)


def test_jiecai_restrained_only_when_officer_present():
    """2026-10 戊戌(겁재): 관살 있는 명식은 겁재 분쟁·손재 후보가 0.85배, 없는 명식은 불변."""
    g = {c.event_key: c for c in _months(_GISIN, 2026) if c.period == "2026-10"}
    g_off = {c.event_key: c for c in _months(_GISIN, 2026, enable_yearly_ten_god_signals=False)
             if c.period == "2026-10"}
    restrained = [k for k, c in g.items() if "JIECAI_RESTRAINED_BY_OFFICER" in c.reason_codes]
    assert restrained and set(restrained) <= {EventKeyV2.SOCIAL_CONFLICT, EventKeyV2.WEALTH_CHANGE}
    for k in restrained:
        assert g[k].score <= g_off[k].score
    y = {c.event_key: c for c in _months(_YONG, 2026) if c.period == "2026-10"}
    assert not any("JIECAI_RESTRAINED_BY_OFFICER" in c.reason_codes for c in y.values())


def test_authority_stem_hap_adds_marriage_signal_bonus():
    """2026-07 乙未: 乙(편관) ↔ 원국 庚 천간합 → 관합 가중(결혼 신호·관계 변화 +2, 측정 후 하향)."""
    on = {c.event_key: c for c in _months(_YONG, 2026) if c.period == "2026-07"}
    off = {c.event_key: c for c in _months(_YONG, 2026, enable_yearly_ten_god_signals=False)
           if c.period == "2026-07"}
    hit = [c for c in on.values() if "SAME_GOD_HAP_AUTHORITY" in c.reason_codes]
    allowed = (EventKeyV2.MARRIAGE_SIGNAL, EventKeyV2.RELATIONSHIP_CHANGE)
    assert hit and all(c.event_key in allowed for c in hit)
    for c in hit:
        assert c.contributions.get("yearly_signal") == 2.0 and c.score >= off[c.event_key].score


def test_sewoon_seeds_only_when_absent_and_officer_or_output_year():
    on = _years(_YONG)
    off = _years(_YONG, enable_yearly_ten_god_signals=False)
    seed_ids = ("OFFICER_YEAR_RELOCATION", "OUTPUT_YEAR_RELATIONSHIP_CHANGE")
    seeded = [c for c in on if any(r in seed_ids for r in c.reason_codes)]
    assert seeded, "세운 범위에 관성·식상 천간 해가 있어야 한다"
    for c in seeded:
        assert c.source_ten_gods and c.candidate_source_layers == ["sewoon"]
        # 없을 때만 시드.
        assert not any(o.period == c.period and o.event_key is c.event_key for o in off)


def test_reason_codes_ko_labels():
    ko = reason_codes_ko(
        ["JIECAI_RESTRAINED_BY_OFFICER", "SAME_GOD_HAP_AUTHORITY", "OFFICER_YEAR_RELOCATION"]
    )
    assert "관살이 겁재를 제어(분쟁·손재 완화)" in ko
    assert "운 천간이 원국과 합(그 십성 사건 강화)" in ko
    assert "관성 해의 장소 변경(사무실 이전 등)" in ko
