"""structure_modifier completion and 격국 detection."""

from __future__ import annotations

from saju_manse_analysis import analyze_chart

from saju_shared_types.enums import Branch, Stem


def test_root_clash_handled_by_rooting_not_structure(make_pillars) -> None:
    # 甲 일간, 유일한 뿌리(인성 癸)가 일지 子인데 년지 午가 子午충.
    # (나') 역할 분리: 뿌리 손상은 rooting.reliability에서 처리하고 structure_modifier에서
    # 같은 충을 다시 감산하지 않는다(이중 반영 방지).
    pillars = make_pillars(
        (Stem.MU, Branch.O), (Stem.MU, Branch.SUL),
        (Stem.GAP, Branch.JA), (Stem.GYEONG, Branch.SUL), Stem.GAP,
    )
    ca = analyze_chart(pillars)
    bd = ca.structure.structure_modifier_breakdown
    assert "only_root_damaged:-6" not in bd  # root 충은 structure에서 감산하지 않음
    assert "day_master_root_clashed:-4" not in bd
    assert -10 <= ca.structure.structure_modifier <= 10
    # 충 맞은 뿌리(子)는 통근 reliability(<1.0)로 약화된다.
    clashed = next((r for r in ca.force.rooting.roots if r.branch == "子"), None)
    assert clashed is not None and clashed.reliability < 1.0
    assert "structure_modifier" in ca.force.strength.components


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


def test_transformation_blocked_by_clash(make_pillars) -> None:
    # 寅亥 육합(木) 이지만 寅申 충이 합을 방해 → confirmed=False, blockers 기록.
    # (간지는 실제 60갑자: 乙亥·庚申·甲寅·丙午)
    pillars = make_pillars(
        (Stem.EUL, Branch.HAE), (Stem.GYEONG, Branch.SIN),
        (Stem.GAP, Branch.IN), (Stem.BYEONG, Branch.O), Stem.GAP,
    )
    s = analyze_chart(pillars).structure
    in_hae = [t for t in s.transformed_candidates if set(t.members) == {"寅", "亥"}]
    assert in_hae, "寅亥 육합 변환 후보가 있어야 한다"
    t = in_hae[0]
    assert t.blockers  # 충이 blocker로 잡혀야 한다
    assert t.confirmed is False


def test_geokguk_reason_is_relation_specific(make_pillars) -> None:
    # 1980 fixture: 월지 亥亥 자형 → self_punished 라벨(단순 clashed 아님).
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    g = analyze_chart(pillars).geokguk
    assert "month_branch_self_punished" in g.stability["reasons"]
    assert "month_branch_clashed" not in g.stability["reasons"]


def test_geokguk_special_structure_label(make_pillars) -> None:
    # 월지 본기가 비견이면 건록격으로 표기.
    pillars = make_pillars(
        (Stem.GAP, Branch.JA), (Stem.GAP, Branch.IN),
        (Stem.GAP, Branch.O), (Stem.GAP, Branch.SUL), Stem.GAP,
    )
    g = analyze_chart(pillars).geokguk
    assert g.main_structure in ("건록격", "양인격")
