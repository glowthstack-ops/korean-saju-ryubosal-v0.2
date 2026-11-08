"""조후 흐름선(A안)·조후 점수 블렌드(B안) — 2026-11-08 데굴님 "겨울생이라 바닥에서 서서히 쌓인다".

사전 일치(월지 축 = 조후 용신 사전 climate_axis), 데굴님 명식 대운 조후 궤적(子丑 바닥 → 卯 보통선
→ 午 정점), 중립 월 명식은 선 없음, blend 산술·기본 off 를 고정한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from saju_manse_analysis.luck import climate as CL
from saju_manse_analysis.luck import luck_cycles as LC

from saju_api.services.manse_service import _calculate
from saju_api.services.report_service import _ReportData
from saju_engines.life_graph import trend_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_COMPILED = Path(__file__).resolve().parents[2] / "compiled"
_TODAY = date(2026, 11, 8)
# 데굴님 명식(亥월 己土 겨울생, 대운 순행 戊子→己丑→庚寅→辛卯→壬辰→癸巳→甲午→乙未→丙申→丁酉).
_BIRTH = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40", birth_place_name="서울 구로구",
    gender="male", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
)


def _spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980", end="2070"),
    )


def test_month_axis_matches_johu_dictionary() -> None:
    """월지 조후 축은 조후 용신 사전(최신 compiled)의 climate_axis 와 같다(일간 무관)."""
    latest = sorted(_COMPILED.glob("johu_yongsin_v*.json"))[-1]
    entries = json.loads(latest.read_text(encoding="utf-8"))["entries"]
    seen: dict[str, set[str]] = {}
    for row in entries.values():
        for br, cell in row.items():
            seen.setdefault(br, set()).add(cell["climate_axis"])
    assert {br: next(iter(v)) for br, v in seen.items() if len(v) == 1} == CL.MONTH_CLIMATE_AXIS


def test_degool_daewoon_climate_rises_from_winter_floor() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None and g.climate_axis == "cold" and g.climate_need_ko == "온기(火)"
    by = {d.ganji: d.climate for d in g.daewoons}
    assert by["戊子"] == -1.0 and by["己丑"] == -0.8  # 바닥
    assert by["辛卯"] == 0.0  # 보통선 도달(지난 대운 35–44)
    assert by["甲午"] == 1.0  # 정점
    rising = ("戊子", "己丑", "庚寅", "辛卯", "壬辰", "癸巳", "甲午")
    seq = [d.climate for d in g.daewoons if d.ganji in rising]
    assert seq == sorted(seq)  # 子→午 단조 상승
    assert g.climate_baseline_daewoon == "辛卯" and g.climate_peak_daewoon == "甲午"
    # 연도 조후 = 0.7×대운 + 0.3×세운 지지.
    y2026 = next(y for y in g.years if y.year == 2026)  # 壬辰 대운(+0.3), 丙午(+1.0)
    assert y2026.climate == pytest.approx(0.7 * 0.3 + 0.3 * 1.0, abs=0.001)
    lines = trend_lines(g)
    assert lines[0].startswith("[추세 흐름") and any("한습(겨울)" in ln for ln in lines)
    assert any("辛卯" in ln and "조후 +0.00" in ln for ln in lines)
    assert any("甲午" in ln and "조후 +1.00" in ln for ln in lines)
    assert "[추세 흐름" in "\n".join(data.life_graph_block())
    # 억부 점수·누적선은 불변(설명용 층).
    assert all(isinstance(d.score, float) for d in g.daewoons)


def test_neutral_month_has_no_climate_line() -> None:
    """卯월(중립) 명식은 조후 축이 없어 선·블록이 없다."""
    birth = BirthInput(
        birth_date=date(1985, 3, 20), birth_time=None, birth_place_name="서울", gender="female",
    )
    data = _ReportData(birth, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None and g.climate_axis == ""
    assert all(d.climate is None for d in g.daewoons) and all(y.climate is None for y in g.years)
    # 축이 없으면 추세 점수 = 억부 점수 그대로, 블록에 조후 항 없음.
    assert all(d.trend_score == round(d.score, 3) for d in g.daewoons)
    assert not any("조후" in ln for ln in trend_lines(g)[1:])


def test_climate_score_direction_and_weight() -> None:
    assert CL.climate_score("亥", "午") == 1.0 and CL.climate_score("亥", "子") == -1.0
    # 여름생은 반전, 습·조 월은 절반 가중.
    assert CL.climate_score("午", "子") == 1.0 and CL.climate_score("午", "午") == -1.0
    assert CL.climate_score("辰", "午") == 0.5 and CL.climate_score("戌", "子") == 0.5
    assert CL.climate_score("卯", "午") == 0.0


def test_blend_mode_mixes_climate_into_luck_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """B안: blend 면 세운·대운 점수 = (1−w)×억부 + w×조후. 기본은 off(측정 전)."""
    assert LC.CLIMATE_LUCK_MODE == "off"
    base = _calculate(_BIRTH.model_copy(update={"reference_date": _TODAY}))
    monkeypatch.setattr(LC, "CLIMATE_LUCK_MODE", "blend")
    monkeypatch.setattr(LC, "CLIMATE_LUCK_WEIGHT", 0.3)
    r = _calculate(_BIRTH.model_copy(update={"reference_date": _TODAY}))
    b_dw = {d.ganji: d.luck_score for d in base.luck_cycles.daewoon_table}
    for d in r.luck_cycles.daewoon_table:
        expect = 0.7 * b_dw[d.ganji] + 0.3 * CL.climate_score("亥", d.ganji[-1])
        assert d.luck_score == pytest.approx(expect, abs=0.002), d.ganji
        assert "조후" in d.luck_summary
    b_y = {p.label: p.luck_score for p in base.luck_cycles.yearly_luck}
    for p in r.luck_cycles.yearly_luck:
        expect = 0.7 * b_y[p.label] + 0.3 * CL.climate_score("亥", p.ganji[-1])
        assert p.luck_score == pytest.approx(expect, abs=0.002), p.label
    # 월운·일운은 손대지 않는다.
    b_m = {p.label: p.luck_score for p in base.luck_cycles.monthly_luck}
    assert all(
        p.luck_score == pytest.approx(b_m[p.label], abs=1e-6) for p in r.luck_cycles.monthly_luck
    )
