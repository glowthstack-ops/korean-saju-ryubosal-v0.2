"""공망 정책 회귀: 분포 유지 / 월지 공망 패격 / 신강약 보정 / 신살 강도·표시."""

from __future__ import annotations

from saju_manse_analysis import analyze_chart

from saju_shared_types.enums import Branch, Stem


def _void_chart(make_pillars):
    # 일주 甲子(旬 공망 戌亥) + 월지 戌 → 월지 공망 케이스.
    return make_pillars(
        (Stem.GYEONG, Branch.O), (Stem.MU, Branch.SUL),
        (Stem.GAP, Branch.JA), (Stem.BYEONG, Branch.IN), Stem.GAP,
    )


def test_gongmang_does_not_remove_element_from_distribution(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    # 旬 공망은 戌亥, 戌(토)가 공망이어도 오행분포에서 토가 제거되지 않는다(정책).
    assert ca.structure.gongmang["empty_branches"] == ["戌", "亥"]
    assert ca.force.five_elements.effective_force["土"] > 0


def test_month_void_marks_geokguk_pae(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    assert "戌" in ca.structure.gongmang["empty_branches"]
    assert "month" in ca.structure.gongmang["affected_positions"]
    assert ca.geokguk.formation_level == "패"
    assert "month_branch_void" in ca.geokguk.stability["reasons"]


def test_void_applies_strength_modifier(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    assert "month_branch_void:-2" in ca.structure.structure_modifier_breakdown


def test_gongmang_listed_as_sinsal_with_context(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    assert ca.traditional.sinsal is not None
    gm = [it for it in ca.traditional.sinsal.full_list if it.name == "공망"]
    assert any(it.position == "month" for it in gm)
    assert all(it.use_for_yongsin_decision is False for it in gm)
