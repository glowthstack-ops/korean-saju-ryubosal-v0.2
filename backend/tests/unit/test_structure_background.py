"""4번 — 運破格·기신 성국 배경 감점(2026-09-18 데굴님 승인, HAP_MITIGATION 플래그 공유).

favorability만 보정하고 점수·활성·순위는 불변. 運破格은 원국에 구응이 있으면 감점 없이 '경향'
근거 코드만 남긴다(『자평진전』 성패·구응 병행). 데굴 차트는 정재격이라 비겁 운(戊戌 2026-10)에
파격 십성이 들어오지만 원국 庚 상관이 구응이라 '경향'이다. 기신 성국은 2026-12 庚子
(申子 반합 水=구신).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from saju_manse_analysis.structure.luck_geok_break import geok_break

from saju_api.services.manse_service import calculate, luck_months
from saju_engines import EventEngineV2, period_v2_config
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _birth() -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울 구로구", latitude=37.4944, longitude=126.8563,
        timezone="Asia/Seoul", gender="male", reference_date=date(2026, 9, 18),
    )


@pytest.fixture(scope="module")
def chart():
    return calculate(_birth())


def test_geok_break_pure_rules() -> None:
    """격별 파격·구응 표 — 구응 있으면 rescued, 없으면 감점 대상. 미등록 격·None은 빈 목록."""
    hit = geok_break("정재격", ["겁재", "정인"], ["상관", "정인"])
    assert len(hit) == 1 and hit[0].pattern == "비겁쟁재" and hit[0].rescued
    assert hit[0].rescue_evidence == "상관"
    bare = geok_break("정재격", ["비견", "편재"], ["정인", "편인"])
    assert len(bare) == 1 and not bare[0].rescued and bare[0].rescue_evidence == "구응 없음"
    assert len(geok_break("정관격", ["상관", "편관"], [])) == 2
    assert geok_break("정재격", ["정관", "식신"], []) == []
    assert geok_break("건록격", ["겁재"], []) == [] and geok_break(None, ["겁재"], []) == []
    assert geok_break("식신격", ["편인"], ["정재"])[0].rescued


def _score(chart, months, flag, monkeypatch):
    monkeypatch.setattr(period_v2_config, "HAP_MITIGATION_ENABLED", flag)
    c = chart.model_copy(deep=True)
    c.luck_cycles.monthly_luck = months
    return EventEngineV2(_DICTS).score(c, levels={GanjiLevel.MONTH})


def test_background_penalties_only_touch_favorability(chart, monkeypatch) -> None:
    """ON: 2026-12(기신 성국) fav 감점+코드, 2026-10(운 파격 경향) 코드만. 점수·활성 ON/OFF 동일."""
    assert chart.geokguk is not None and chart.geokguk.main_structure == "정재격"
    months = luck_months(_birth(), 2026) + luck_months(_birth(), 2027)
    off = {(c.period, str(c.event_key)): c for c in _score(chart, months, False, monkeypatch)}
    on = {(c.period, str(c.event_key)): c for c in _score(chart, months, True, monkeypatch)}
    assert set(on) == set(off)
    for k in on:
        assert (on[k].score, on[k].raw_score, on[k].activation) == (
            off[k].score, off[k].raw_score, off[k].activation,
        )
    dec = [c for (p, _), c in on.items() if p == "2026-12"]
    assert dec and all("局_기신성국_水" in c.reason_codes for c in dec)
    # favorability는 [−1, 1] 클램프, 시험 대상(job_gain 등)은 fav_adj가 ±0.5로 클램프되므로
    # 시험 대상이 아닌 재물 후보로 −0.2 정확값을 보고 나머지는 단조성만 확인한다.
    wealth = ("2026-12", "wealth_change")
    assert on[wealth].contributions["fav_adj"] == round(
        off[wealth].contributions.get("fav_adj", 0.0) - 0.2, 4
    )
    for k in on:
        if k[0] == "2026-12":
            on_adj = on[k].contributions.get("fav_adj", 0.0)
            assert on_adj <= off[k].contributions.get("fav_adj", 0.0)
            assert on[k].favorability <= off[k].favorability
    octo = [c for (p, _), c in on.items() if p == "2026-10"]
    assert octo and all("格_운파격경향_비겁쟁재" in c.reason_codes for c in octo)
    assert not any("格_운파격_" in r for c in octo for r in c.reason_codes)
    # 구응 있는 경향은 감점하지 않는다 — 10월 fav는 ON/OFF 동일(다른 합 보정도 없는 달).
    assert all(on[k].favorability == off[k].favorability for k in on if k[0] == "2026-10")


def test_month_summary_marks_gisin_local(monkeypatch) -> None:
    """월 등급 요약에 기신 성국 표기(ON만). 점수는 기존 변환 오행 보정 그대로."""
    from saju_manse_analysis.luck import luck_cycles

    monkeypatch.setattr(luck_cycles, "HAP_MITIGATION_ENABLED", True)
    on = next(m for m in luck_months(_birth(), 2026) if m.label == "2026-12")
    assert "기신 성국(局)" in on.luck_summary
    monkeypatch.setattr(luck_cycles, "HAP_MITIGATION_ENABLED", False)
    off = next(m for m in luck_months(_birth(), 2026) if m.label == "2026-12")
    assert "기신 성국" not in off.luck_summary and on.luck_score == off.luck_score
