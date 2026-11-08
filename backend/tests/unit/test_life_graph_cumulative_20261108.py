"""인생 그래프 누적 운세선(주식 차트형, docs/10 §3-1, 2026-11-08) — 산술 불변식·추세 라벨·블록."""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import _ReportData
from saju_engines.life_graph import TREND_EPS, cumulative_lines
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    birth_date=date(1980, 5, 17), birth_time=None, birth_place_name="서울", gender="male",
)


def _spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980", end="2070"),
    )


def test_cumulative_is_running_sum_of_year_plus_daewoon() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None and g.years
    band = {}
    for d in g.daewoons:
        for y in range(d.start_year, d.end_year + 1):
            band[y] = d.score
    running = 0.0
    for yr in g.years:
        running += yr.score + band.get(yr.year, 0.0)
        assert abs(yr.cumulative - running) < 0.01, yr.year
    # 점수·마커는 불변(설명용 산술) — 누적은 별도 필드.
    assert all(isinstance(yr.score, float) for yr in g.years)


def test_daewoon_trend_labels_follow_mean_delta() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None
    assert g.daewoons[0].trend == "시작" and g.daewoons[0].trend_delta is None
    prev = g.daewoons[0].mean_total
    for d in g.daewoons[1:]:
        assert d.trend_delta is not None
        assert abs((d.mean_total - prev) - d.trend_delta) < 0.01
        expected = (
            "상승" if d.trend_delta > TREND_EPS
            else "하강" if d.trend_delta < -TREND_EPS
            else "보합"
        )
        assert d.trend == expected, (d.ganji, d.trend, d.trend_delta)
        prev = d.mean_total
    assert g.cumulative_peak_year is not None and g.cumulative_low_year is not None
    assert g.today_cumulative_percentile is not None and 0 <= g.today_cumulative_percentile <= 100


def test_cumulative_block_in_f14_data() -> None:
    data = _ReportData(_BIRTH, _spec(), _TODAY)
    g = data.life_graph
    assert g is not None
    lines = cumulative_lines(g)
    assert lines and lines[0].startswith("[누적 흐름")
    assert any("→ 시작" in ln for ln in lines)
    assert any("누적 최고점" in ln for ln in lines)
    assert any("오늘(2026년)의 누적 수준" in ln for ln in lines)
    block = "\n".join(data.life_graph_block())
    assert "[누적 흐름" in block and "[인생 그래프 데이터" in block
    # 기준선(보통선) 구간·오늘 위치·앞으로의 대운 부호(2026-11-08).
    from saju_engines.life_graph import baseline_phase_lines

    phases = baseline_phase_lines(g)
    assert any("기준선" in ln for ln in phases)
    assert any(ln.startswith("- 오늘(2026년) 누적") for ln in phases)
    assert any(ln.startswith("- 앞으로:") and "대운 평균" in ln for ln in phases)
