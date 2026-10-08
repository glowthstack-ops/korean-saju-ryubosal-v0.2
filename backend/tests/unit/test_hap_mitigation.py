"""P1 합 완화·관운 강화(2026-09-18 데굴님 지시, 전문가 취지 "기신 억제 + 관운 강화 · 지병 완화").

기준 사례: 데굴 차트(1980-11-22 09:40 서울 구로구 남 · 己土 신약 · 용신 土 · 기신 木 · 구신 水)
2027-02 壬寅월 — 엔진 관계 층은 丁壬合 합화 확정·化木, 寅亥合 합반·합거·壬 구신 boon·甲 기신
boon으로 판정하지만 월 등급은 '강한 기신운', 이직 후보 결과 유불리는 '불리'였다. 전문가:
1월(辛丑)은 좋다고 보기 어렵고, 2월은 기신(亥水) 작용이 합으로 눌리며 관운이 강해진다.

플래그 OFF(기본)는 byte 불변, ON일 때만 완화·관운 강화가 붙는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from saju_manse_analysis.luck import luck_cycles
from saju_manse_analysis.relations.hap_mitigation import officer_element, resolve_hap_mitigation

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import EventEngineV2, period_v2_config
from saju_engines import context_reducer as cr
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FAV = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    )


@pytest.fixture(scope="module")
def chart():
    return calculate(_birth())


def test_resolver_flags_2027_02_and_not_2027_01(chart) -> None:
    """壬寅: 지지 寅亥 합거 완화 + 관(木) 강화 재료. 辛丑·庚子·戊戌: 해당 없음."""
    assert officer_element(chart.pillars.day_master) == "木"
    m = resolve_hap_mitigation(chart.pillars, _FAV, luck_stem="壬", luck_branch="寅")
    assert m.branch_mitigated and not m.stem_mitigated  # 丁壬은 化(합화)라 묶임이 아니다
    assert m.officer_elements == ("木",)
    assert any("寅" in n and "완화" in n for n in m.notes)
    for stem, branch in (("辛", "丑"), ("庚", "子"), ("戊", "戌")):
        quiet = resolve_hap_mitigation(chart.pillars, _FAV, luck_stem=stem, luck_branch=branch)
        assert not quiet.any
    # luck_cycles식 2역할(용신/기신) 맵으로도 같은 판정.
    two = {"土": "용신", "火": "용신", "木": "기신", "水": "기신"}
    m2 = resolve_hap_mitigation(chart.pillars, two, luck_stem="壬", luck_branch="寅")
    assert m2.branch_mitigated


def _month(label: str, months):
    return next(m for m in months if m.label == label)


def test_month_grade_mitigated_only_when_flag_on(monkeypatch) -> None:
    """OFF: 2027-02 '강한 기신운' 그대로. ON: '기신운(합거 완화)'·지지 점수 절반·방향 유지."""
    monkeypatch.setattr(luck_cycles, "HAP_MITIGATION_ENABLED", False)
    off = _month("2027-02", luck_months(_birth(), 2027))
    assert off.luck_label == "강한 기신운" and off.luck_label_code == "pure_gisin_luck"
    monkeypatch.setattr(luck_cycles, "HAP_MITIGATION_ENABLED", True)
    on = _month("2027-02", luck_months(_birth(), 2027))
    assert on.luck_label == "기신운(합거 완화)" and on.luck_label_code == "gisin_mitigated"
    assert on.yongsin_alignment == "기신운"  # 방향 유지(제거 아님)
    assert on.branch_effect is not None and off.branch_effect is not None
    assert on.branch_effect.type == "기신"
    assert on.branch_effect.score == round(off.branch_effect.score * 0.5, 4)
    assert "합거 완화" in on.branch_effect.branch_label
    assert on.luck_score > off.luck_score
    # 1월(辛丑)은 완화 대상이 아니라 ON/OFF 동일. (2027-01은 2026 절기년의 마지막 달이다.)
    jan_on = _month("2027-01", luck_months(_birth(), 2026))
    monkeypatch.setattr(luck_cycles, "HAP_MITIGATION_ENABLED", False)
    jan_off = _month("2027-01", luck_months(_birth(), 2026))
    assert jan_on.model_dump() == jan_off.model_dump()
    assert jan_off.luck_label == "용신운(부분)"


def _score_months(chart, months):
    chart = chart.model_copy(deep=True)
    chart.luck_cycles.monthly_luck = months
    return EventEngineV2(_DICTS).score(chart, levels={GanjiLevel.MONTH})


def test_event_favorability_mitigated_scores_unchanged(chart, monkeypatch) -> None:
    """ON: 2027-02 이직 후보 결과 유불리 불리→중립(완화+관운 강화), 점수·순위·사건 종류는 불변."""
    months = luck_months(_birth(), 2026) + luck_months(_birth(), 2027)
    monkeypatch.setattr(period_v2_config, "HAP_MITIGATION_ENABLED", False)
    off = _score_months(chart, months)
    monkeypatch.setattr(period_v2_config, "HAP_MITIGATION_ENABLED", True)
    on = _score_months(chart, months)

    def pick(cands, key):
        return next(c for c in cands if c.period == "2027-02" and c.event_key is key)

    off_c = pick(off, EventKeyV2.CAREER_CHANGE)
    on_c = pick(on, EventKeyV2.CAREER_CHANGE)
    assert off_c.favorability <= -0.2  # 원래 '불리' 밴드
    assert -0.2 < on_c.favorability < 0.2  # 완화 + 관운 강화 → 중립 밴드(유리 단정 아님)
    assert on_c.score == off_c.score and on_c.raw_score == off_c.raw_score  # 점수 불변
    assert on_c.polarity_role == off_c.polarity_role  # 극성 evidence 원값 유지
    assert "制_합거_흉완화" in on_c.reason_codes and "化_관운강화" in on_c.reason_codes
    # 관 계열이 아닌 후보는 관운 강화 없이 완화만(여전히 불리 밴드).
    non_career = [c for c in on if c.period == "2027-02" and c.event_key not in (
        EventKeyV2.CAREER_CHANGE, EventKeyV2.JOB_GAIN, EventKeyV2.PROMOTION,
    )]
    assert non_career, "2027-02에 관 계열 외 후보가 있어야 비교 가능"
    for c in non_career:
        assert "化_관운강화" not in c.reason_codes
        assert "制_합거_흉완화" in c.reason_codes
        assert c.favorability <= -0.2
    # 전체 후보의 점수·활성은 ON/OFF 동일(길흉 채널만 바뀐다). 동점 후보의 나열 순서는
    # favorability를 보조 키로 쓰는 정렬 단계에서 바뀔 수 있어 집합으로 비교한다.
    def table(cands):
        return {(c.period, str(c.event_key)): (c.score, c.raw_score, c.activation) for c in cands}

    assert table(on) == table(off)


def test_candidate_hap_notes_and_legend_follow_flag(chart, monkeypatch) -> None:
    """ON: 후보에 합 작용 줄(흉 '완화' 표현) + 월별 범례에 합거 완화 읽는 법. OFF: 둘 다 없음."""
    monkeypatch.setattr(period_v2_config, "HAP_MITIGATION_ENABLED", False)
    assert cr._candidate_hap_notes(chart, "壬寅") == []
    monkeypatch.setattr(period_v2_config, "HAP_MITIGATION_ENABLED", True)
    notes = cr._candidate_hap_notes(chart, "壬寅")
    assert notes and all(n.startswith("운 ") for n in notes)
    joined = " / ".join(notes)
    assert "亥寅合" in joined and "합거" in joined
    assert "흉 완화" in joined and "흉 제거" not in joined
    # 辛丑은 巳丑 반합 줄만 있고 합거는 없다(완화 대상 아님).
    assert all("합거" not in n for n in cr._candidate_hap_notes(chart, "辛丑"))
    assert cr._candidate_hap_notes(None, "壬寅") == []
