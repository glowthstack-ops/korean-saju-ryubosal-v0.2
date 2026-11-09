"""인생 그래프 추세선·흐름 두 패턴(docs/10 §3-1, 2026-11-08).

데굴님 "누적 운세는 의미가 없어 — 대운별 운세와 조후 운세를 합쳐서 하나의 추세선으로" · "0~5세는
대운도 없는데 태어나면서부터 최대로 그려진다" · "띠 색상·설명이 어려워 — 좋은 흐름/힘든 흐름 두
패턴으로".

- 구간 추세 = 억부·조후 평균(축 없으면 억부 그대로), 첫 대운 전 유년은 월주를 운처럼 본 값.
- 추세 라벨은 직전 구간 대비, 흐름은 추세 부호 두 패턴, 누적선 필드는 더 이상 없다.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.report_service import _ReportData
from saju_engines.life_graph import TREND_EPS, trend_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.life_graph import LifeGraph, LifeGraphDaewoon, LifeGraphYear
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 11, 8)
# 데굴님 명식(亥월 己土 겨울생, 첫 대운 戊子 5세 시작 → 0–4세는 월주 丁亥 구간).
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


def test_pre_daewoon_segment_uses_month_pillar() -> None:
    g = _ReportData(_BIRTH, _spec(), _TODAY).life_graph
    assert g is not None and g.pre_daewoon is not None
    pre = g.pre_daewoon
    assert pre.ganji == "丁亥" and pre.start_age == 0 and pre.end_age == 4
    assert pre.start_year == 1980 and pre.end_year == 1984
    assert pre.climate == pytest.approx(-0.8)  # 亥 — 겨울생에게 추운 지지
    assert pre.trend_score == pytest.approx((pre.score + pre.climate) / 2, abs=0.001)
    assert pre.trend_score < 0 and pre.flow == "hard"  # 유년이 '최대'로 그려지지 않는다
    # 첫 대운 페이지(띠)는 그대로 출생부터 — 마커·페이지 범위 불변.
    assert g.daewoons[0].start_year == 1980 and g.daewoons[0].start_age == 5


def test_trend_is_mean_of_score_and_climate_with_labels() -> None:
    g = _ReportData(_BIRTH, _spec(), _TODAY).life_graph
    assert g is not None
    prev = g.pre_daewoon.trend_score if g.pre_daewoon else None
    for d in g.daewoons:
        assert d.climate is not None
        assert d.trend_score == pytest.approx((d.score + d.climate) / 2, abs=0.001)
        assert d.flow == ("good" if d.trend_score >= 0 else "hard")
        assert d.flow_ko == ("좋은 흐름" if d.flow == "good" else "힘든 흐름")
        if prev is None:
            assert d.trend == "시작" and d.trend_delta is None
        else:
            assert d.trend_delta == pytest.approx(d.trend_score - prev, abs=0.001)
            expected = (
                "상승" if d.trend_delta > TREND_EPS
                else "하강" if d.trend_delta < -TREND_EPS
                else "보합"
            )
            assert d.trend == expected, (d.ganji, d.trend, d.trend_delta)
        prev = d.trend_score
    # 데굴님 궤적: 戊子(−0.4, −1.0) 바닥 → 甲午 부근 최고.
    assert g.trend_low == "戊子" and g.trend_peak in ("甲午", "丁酉")
    assert g.trend_baseline is not None


def test_trend_block_and_no_cumulative_fields() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None
    lines = trend_lines(g)
    assert lines[0].startswith("[추세 흐름")
    assert any(ln.startswith("- 대운 전 丁亥(월주) 0–4세(1980–1984년)") for ln in lines)
    assert any("[힘든 흐름]" in ln and "대운 전" in ln for ln in lines)  # 유년은 힘든 흐름
    assert any("戊子" in ln and "직전 대비" in ln for ln in lines)  # 첫 대운은 유년 대비로 라벨
    assert any(ln.startswith("- 추세 최고") and "보통선(0)" in ln for ln in lines)
    assert any(ln.startswith("- 앞으로:") and "대운 추세" in ln for ln in lines)
    block = "\n".join(data.life_graph_block())
    assert "[추세 흐름" in block and "[누적 흐름" not in block and "[조후 흐름" not in block
    assert "cumulative" not in LifeGraph.model_fields
    assert "cumulative" not in LifeGraphYear.model_fields
    assert "mean_total" not in LifeGraphDaewoon.model_fields


def test_without_pre_daewoon_first_daewoon_starts_trend() -> None:
    """pre_daewoon 없이 만들면 첫 대운이 '시작'(호환), 조후 없으면 추세 = 억부."""
    from saju_engines.life_graph import _attach_trend

    g = LifeGraph(
        birth_year=2000, end_year=2090,
        daewoons=[
            LifeGraphDaewoon(
                index=i, ganji=gj, stem_ten_god="", branch_ten_god="", start_age=3 + 10 * i,
                end_age=12 + 10 * i, start_year=2003 + 10 * i, end_year=2012 + 10 * i,
                score=sc, label="", status="future",
            )
            for i, (gj, sc) in enumerate((("甲子", -0.5), ("乙丑", 0.2), ("丙寅", 0.25)))
        ],
    )
    _attach_trend(g)
    assert [d.trend for d in g.daewoons] == ["시작", "상승", "보합"]
    assert [d.trend_score for d in g.daewoons] == [-0.5, 0.2, 0.25]
    assert [d.flow for d in g.daewoons] == ["hard", "good", "good"]
    assert g.trend_low == "甲子" and g.trend_peak == "丙寅" and g.trend_baseline == "乙丑"
