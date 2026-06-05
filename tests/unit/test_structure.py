"""structure_modifier completion and 격국 detection."""

from __future__ import annotations

from saju_manse_analysis import analyze_chart

from saju_shared_types.enums import Branch, Stem


def test_structure_modifier_penalizes_clashed_only_root(make_pillars) -> None:
    # 甲 일간, 유일한 뿌리(인성 癸)가 일지 子인데 년지 午가 子午충 → only_root_damaged.
    pillars = make_pillars(
        (Stem.MU, Branch.O), (Stem.MU, Branch.SUL),
        (Stem.GAP, Branch.JA), (Stem.GYEONG, Branch.SUL), Stem.GAP,
    )
    ca = analyze_chart(pillars)
    sm = ca.structure
    assert "only_root_damaged:-6" in sm.structure_modifier_breakdown
    assert -10 <= sm.structure_modifier <= 10
    assert sm.structure_modifier < 0
    # strength must consume the same modifier.
    assert ca.force.strength.components["structure_modifier"] == sm.structure_modifier


def test_stability_and_volatility_bounds(make_pillars) -> None:
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.GI, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    s = analyze_chart(pillars).structure
    for v in (
        s.stability.yongsin_stability,
        s.stability.geokguk_stability,
        s.stability.root_stability,
    ):
        assert 0.0 <= v <= 1.0
    assert s.volatility_score >= 0.0


def test_geokguk_main_structure_and_aux(make_pillars) -> None:
    # fixture chart 庚申丁亥己亥戊辰 → 월지 亥 정기 壬 = 정재격 (己 일간).
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    g = analyze_chart(pillars).geokguk
    assert g.main_structure == "정재격"
    assert g.basis["main_ten_god"] == "정재"
    assert g.formation_level in ("성", "중성", "패")
    assert any("발현" in a for a in g.auxiliary_structures)


def test_geokguk_special_structure_label(make_pillars) -> None:
    # 월지 본기가 비견이면 건록격으로 표기.
    pillars = make_pillars(
        (Stem.GAP, Branch.JA), (Stem.GAP, Branch.IN),
        (Stem.GAP, Branch.O), (Stem.GAP, Branch.SUL), Stem.GAP,
    )
    g = analyze_chart(pillars).geokguk
    assert g.main_structure in ("건록격", "양인격")
