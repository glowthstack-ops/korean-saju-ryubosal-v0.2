"""공망 정책 회귀: 분포 유지 / 월지 공망 패격 / 신강약 보정 / 신살과 분리 표시."""

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
    g = ca.structure.gongmang
    assert g is not None
    # 일공망(旬 戌亥) — canonical 순서 고정. 戌(토)가 공망이어도 토는 분포에서 유지.
    assert g.day_basis_empty_branches == ["戌", "亥"]
    assert ca.force.five_elements.effective_force["土"] > 0


def test_month_void_registered_as_geokguk_damage(make_pillars) -> None:
    # 월지 공망은 자동 '패'가 아니라 격국 파격(void_month_branch)으로 성패에 반영된다(마스터 정책).
    ca = analyze_chart(_void_chart(make_pillars))
    g = ca.structure.gongmang
    assert g is not None
    assert "戌" in g.day_basis_empty_branches
    assert "month" in g.day_affected_positions
    assert "month_branch_void" in ca.geokguk.stability["reasons"]
    assert ca.geokguk.evaluation is not None
    assert "void_month_branch" in ca.geokguk.evaluation.damage_types


def test_void_applies_strength_modifier(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    assert "month_branch_void:-2" in ca.structure.structure_modifier_breakdown


def test_void_modifier_applied_to_effective_distribution(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    trace = ca.force.five_elements.calculation_trace
    # 공망 0.85배가 effective 분포에 반영되고, 더 이상 deferred가 아니다.
    assert trace["void_modifier"]["factor"] == 0.85
    assert "month:戌" in trace["void_modifier"]["applied_to"]
    assert "void" not in trace["deferred_modifiers"]


def test_gongmang_is_separate_layer_not_a_sinsal(make_pillars) -> None:
    ca = analyze_chart(_void_chart(make_pillars))
    # 공망은 신살 목록에 포함되지 않고 별도 레이어로 표시된다.
    assert ca.traditional.sinsal is not None
    assert "공망" not in {it.name for it in ca.traditional.sinsal.full_list}
    # 일공망 중심, 년공망은 참조정보.
    g = ca.structure.gongmang
    assert g is not None
    assert g.primary_basis == "day"
    assert g.day_basis_empty_branches and isinstance(g.year_basis_empty_branches, list)
