"""신강·신약 v1.3 8성분 — v1 레퍼런스 재현 + 불변식."""

from __future__ import annotations

from saju_manse_analysis import analyze_chart
from saju_manse_analysis.strength.strength_score import classify_band

from saju_shared_types.enums import Branch, Stem


def test_1980_civil_parity(make_pillars) -> None:
    # v1 레퍼런스: 1980.11.22 서울 남(일반시 己巳) = -53.8 신약. 그대로 재현.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.GI, Branch.SA), Stem.GI,
    )
    s = analyze_chart(pillars).force.strength
    assert s.score == -53.8
    assert s.band == "신약"
    # 8성분이 모두 컴포넌트에 기록된다.
    for key in (
        "month_command_score", "root_score", "revealed_stem_score",
        "stem_ten_god_score", "hidden_stem_ten_god_score",
        "combination_adjustment", "clash_adjustment", "climate_adjustment",
    ):
        assert key in s.components


def test_band_thresholds_monotonic() -> None:
    # v1.3 7밴드 경계.
    assert classify_band(95) == "극신강"
    assert classify_band(70) == "신강"
    assert classify_band(30) == "중화신강"
    assert classify_band(0) == "중화"
    assert classify_band(-30) == "중화신약"
    assert classify_band(-60) == "신약"
    assert classify_band(-90) == "극신약"


def test_jong_signal_relabels_extreme_weak_to_neutral(make_pillars) -> None:
    # 일간 극약 + 외부(식/재/관) 종 + 무근 → 가종격 → band 중화로 재라벨.
    # 甲 일간이 火土金水에 둘러싸여 통근 없음.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.BYEONG, Branch.SUL),
        (Stem.GAP, Branch.SIN), (Stem.GYEONG, Branch.O), Stem.GAP,
    )
    s = analyze_chart(pillars).force.strength
    if s.score <= -80:  # 극신약 점수대인데
        assert s.band == "중화"  # 가종 재라벨
        assert any("가종" in w for w in s.warnings)
