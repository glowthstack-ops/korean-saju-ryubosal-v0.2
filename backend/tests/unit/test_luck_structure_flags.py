"""A2 구조 배경 플래그 + A1 신살 7종(2026-09-18 데굴님 승인, 전문가 참고 기준 보완 자료).

A2: 충근·개두·절각(운 기둥 판정, 원국 기둥은 표지)·통관 부재·구응 손상·특수격 역행 — favorability만.
A1: 음양차착·고란살·구교살·원진(元辰)·탕화살·상문·조객 — 통설표, 보조 상징(성별 부재라 연간 음양).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from saju_manse_analysis.luck import luck_cycles
from saju_manse_analysis.sinsal import sinsal_catalog as cat
from saju_manse_analysis.sinsal.sinsal_aggregator import analyze_sinsal
from saju_manse_analysis.structure.luck_structure_flags import resolve_luck_structure_flags

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import EventEngineV2, period_v2_config
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.constants import BRANCH_INDEX
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FAV = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    )


def _flags(chart, stem: str, branch: str, **kw):
    return resolve_luck_structure_flags(
        chart.pillars, _FAV, luck_stem=stem, luck_branch=branch, **kw,
    )


@pytest.fixture(scope="module")
def chart():
    """데굴 차트 庚申 丁亥 己亥 己巳 — 정재격, 일간 己土."""
    return calculate(_birth())


def test_gaedu_jeolgak_only_luck_pillar_is_judged(chart) -> None:
    """壬寅 해당 없음 / 戊子 개두(구신 억제) / 甲辰 개두(용신 억제) / 庚午 절각. 원국은 표지만."""
    none = _flags(chart, "壬", "寅")
    assert not none.luck_gaedu and not none.luck_jeolgak
    mu_ja = _flags(chart, "戊", "子")
    assert mu_ja.luck_gaedu and mu_ja.suppressed_role == "구신"
    gap_jin = _flags(chart, "甲", "辰")
    assert gap_jin.luck_gaedu and gap_jin.suppressed_role == "용신"
    gyeong_o = _flags(chart, "庚", "午")
    assert gyeong_o.luck_jeolgak and gyeong_o.suppressed_role == "한신"
    # 원국 기둥: 己亥(土가 水를 극 → 개두)·丁亥(水가 火를 극 → 절각)·庚申·己巳는 해당 없음.
    assert "일주 개두" in none.natal_gaedu_jeolgak
    assert "월주 절각" in none.natal_gaedu_jeolgak


def test_chunggeun_requires_sole_root_and_reads_role(chart) -> None:
    """운 亥가 巳를 충: 巳 본기 丙(火)은 丁(희신)의 유일한 뿌리 → 기반 손상. 운 巳가 亥를 충: 亥가
    둘이라 다른 뿌리가 남아 충근이 아니다."""
    hae = _flags(chart, "癸", "亥")
    assert hae.chunggeun_useful and any("丁(희신) 뿌리 巳 충" in m for m in hae.chunggeun)
    assert not _flags(chart, "乙", "巳").chunggeun
    pretend = {"火": "기신", "土": "용신", "木": "한신", "水": "희신", "金": "구신"}
    flipped = resolve_luck_structure_flags(chart.pillars, pretend, luck_stem="癸", luck_branch="亥")
    assert flipped.chunggeun_unfavorable and not flipped.chunggeun_useful


def test_tonggwan_and_rescue_damage_are_conservative(chart) -> None:
    """통관: 운 木↔일간 土의 통관 火(丁·巳)가 원국에 있어 부재 아님. 구응 손상: 구응 글자(천간 庚)가
    운 충·합거로 모두 죽을 때만 — 寅이 申을 충해도 천간 庚은 살아 있어 손상 아님(보수적)."""
    assert _flags(chart, "甲", "辰").tonggwan_absent == ""
    no_break = _flags(chart, "乙", "寅", geok_name="정재격", luck_ten_gods=("편관", "정관"))
    assert no_break.rescue_damaged == ()
    tendency = _flags(chart, "戊", "寅", geok_name="정재격", luck_ten_gods=("겁재", "정관"))
    assert tendency.rescue_damaged == ()
    # 운 乙이 庚(구응·상관)을 합거로 묶고 寅이 申(상관 뿌리)을 충하면 구응이 모두 죽는다.
    dead = _flags(chart, "乙", "寅", geok_name="정재격", luck_ten_gods=("겁재", "정관"))
    assert dead.rescue_damaged == ("비겁쟁재",)


def test_special_breach_only_when_special_pattern_overrides(chart) -> None:
    """특수격이 아니면 역행 없음. 종재격(override)은 일간을 돕는 丁 운에, 곡직격은 金 운에 역행."""
    assert _flags(chart, "己", "未").special_breach == ""
    follow = {"name": "종재격", "type": "follow", "override": True, "confidence": 0.7}
    assert "종재격 역행" in _flags(chart, "丁", "未", special_pattern=follow).special_breach
    dominant = {"name": "곡직격", "type": "dominant", "override": True, "confidence": 0.8}
    assert "곡직격 역행" in _flags(chart, "庚", "申", special_pattern=dominant).special_breach
    off = {"name": "곡직격", "type": "dominant", "override": False, "confidence": 0.3}
    assert _flags(chart, "庚", "申", special_pattern=off).special_breach == ""


def test_engine_and_month_apply_structure_background_only_when_flag_on(chart, monkeypatch):
    """ON: 2027-04 甲辰(개두·용신 억제) fav 감점+코드, 점수·활성 불변. 월 등급 요약·점수도 반응."""
    months = luck_months(_birth(), 2026) + luck_months(_birth(), 2027)

    def score(flag):
        monkeypatch.setattr(period_v2_config, "STRUCTURE_BACKGROUND_ENABLED", flag)
        c = chart.model_copy(deep=True)
        c.luck_cycles.monthly_luck = months
        cands = EventEngineV2(_DICTS).score(c, levels={GanjiLevel.MONTH})
        return {(x.period, str(x.event_key)): x for x in cands}

    off, on = score(False), score(True)
    assert set(on) == set(off)
    for k in on:
        assert (on[k].score, on[k].raw_score, on[k].activation) == (
            off[k].score, off[k].raw_score, off[k].activation,
        )
    apr = [c for (p, _), c in on.items() if p == "2027-04"]
    assert apr and all("柱_개두_길신억제" in c.reason_codes for c in apr)
    for k in on:
        if k[0] == "2027-04":
            on_adj = on[k].contributions.get("fav_adj", 0.0)
            assert on_adj < off[k].contributions.get("fav_adj", 0.0)
    monkeypatch.setattr(luck_cycles, "STRUCTURE_BACKGROUND_ENABLED", True)
    m_on = next(m for m in luck_months(_birth(), 2027) if m.label == "2027-04")
    assert "운 기둥 개두" in m_on.luck_summary
    monkeypatch.setattr(luck_cycles, "STRUCTURE_BACKGROUND_ENABLED", False)
    m_off = next(m for m in luck_months(_birth(), 2027) if m.label == "2027-04")
    assert "개두" not in m_off.luck_summary and m_on.luck_score != m_off.luck_score


def test_seven_additional_sinsal_follow_conventional_tables() -> None:
    """통설표 — 일주(음양차착·고란)·일지(탕화)·연지 기준(상문·조객·구교·元辰)을 표와 직접 대조."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1996, 2, 9), birth_time="12:00",
        birth_place_name="서울", gender="male",
    ))
    p = r.pillars
    assert r.structure_analysis is not None
    names = {s.name for s in analyze_sinsal(p, r.structure_analysis).full_list}
    day_gz = (Stem(p.day.stem), Branch(p.day.branch))
    assert ("음양차착" in names) == (day_gz in cat.EUMYANG_CHACHAK)
    assert ("고란살" in names) == (day_gz in cat.GORAN)
    assert ("탕화살" in names) == (Branch(p.day.branch) in cat.TANGHWA_DAY_BRANCHES)
    yb = BRANCH_INDEX[Branch(p.year.branch)]
    others = {Branch(x.branch) for x in (p.month, p.day, p.hour) if x is not None}
    assert ("상문" in names) == (cat.branch_at(yb + cat.SANGMUN_OFFSET) in others)
    assert ("조객" in names) == (cat.branch_at(yb + cat.JOGAEK_OFFSET) in others)
    yang = Stem(p.year.stem) in cat.YANG_STEMS
    yuan = cat.branch_at(yb + (cat.WONJIN_YUAN_OFFSET_YANG if yang else cat.WONJIN_YUAN_OFFSET_YIN))
    assert ("원진(元辰)" in names) == (yuan in others)
    for n in ("음양차착", "고란살", "구교살", "원진(元辰)", "탕화살", "상문", "조객"):
        assert cat.CATALOG_META[n]["polarity"] == "caution"
