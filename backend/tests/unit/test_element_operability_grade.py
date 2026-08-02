"""오행 실현도 등급 회귀 (P2-2, 2026-08-01).

**등급이 SSOT이고 앵커는 보조값이다.** 개별 신호를 감산 누적하지 않는다 — 하나의 卯酉冲이
생조원 교란·합 완성 방해·절각 노출을 동시에 만들 수 있어서, 각각 깎으면 같은 원인을 세 번
센다. `matched_rule_id` 로 최종 규칙 하나를 고정해 구조적으로 막는다.

`ABSENT` 만 무근이다. `DIRECT_TRANSIT_ROOT` 는 유근 분기로 들어가되 `FULLY_OPERABLE` 자격만
갖지 못한다 — 일괄 감점이 아니라 상한 제한이다.
"""

from __future__ import annotations

import inspect

import pytest

from saju_engines import element_operability_grade as mod
from saju_engines.element_operability_grade import (
    OPERABILITY_ANCHOR,
    OperabilityStatus,
    evaluate_element_operability,
)
from saju_engines.element_operability_profile import (
    CutOffStatus,
    ElementOperabilityProfile,
    ObstructionProfile,
    RootDepth,
    RootProfile,
    RootStatus,
    StageApplicability,
    StageModifier,
    SupportProfile,
    SupportStatus,
)


def _profile(
    *, root: RootStatus, support: SupportStatus = SupportStatus.ABSENT,
    cut_off: CutOffStatus = CutOffStatus.CUT_OFF_ABSENT, stage: str | None = None,
    resolved: str | None = "水", evidence: tuple[str, ...] = (),
    depth: str = "main_qi",
) -> ElementOperabilityProfile:
    return ElementOperabilityProfile(
        node_id="sewoon.stem:癸", raw_element="水", resolved_element=resolved,
        root=RootProfile(
            root, strongest_root_depth=RootDepth(depth),
            has_main_qi_root=RootDepth(depth) is RootDepth.MAIN_QI),
        support=SupportProfile(support),
        obstruction=ObstructionProfile(cut_off),
        stage=StageModifier(
            StageApplicability.APPLICABLE, stem="癸", branch="未", stage=stage,
        ) if stage else StageModifier(StageApplicability.NOT_APPLICABLE),
        evidence_ids=evidence,
    )


def _status(**kwargs) -> OperabilityStatus:
    return evaluate_element_operability(_profile(**kwargs)).status


# ── 무근 분류 ────────────────────────────────────────────────────────────


def test_only_absent_counts_as_rootless() -> None:
    """운 뿌리는 무근이 아니다 — 지금 이 시기에는 실제로 기반이 있다."""
    rooted = (RootStatus.DIRECT_NATAL_ROOT, RootStatus.DIRECT_TRANSIT_ROOT,
              RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT)
    for root in rooted:
        rule = evaluate_element_operability(_profile(root=root)).matched_rule_id
        assert "ROOTLESS" not in rule, f"{root.value} 가 무근 분기로 갔다"
    assert "ROOTLESS" in evaluate_element_operability(
        _profile(root=RootStatus.ABSENT)).matched_rule_id


def test_transit_root_enters_the_rooted_branch() -> None:
    rule = evaluate_element_operability(
        _profile(root=RootStatus.DIRECT_TRANSIT_ROOT)).matched_rule_id
    assert rule.startswith("R30_TRANSIT_ROOT")


# ── 운 뿌리 상한 ─────────────────────────────────────────────────────────


def test_transit_root_alone_is_operable() -> None:
    assert _status(root=RootStatus.DIRECT_TRANSIT_ROOT) is OperabilityStatus.OPERABLE


def test_transit_root_with_stable_support_stays_operable() -> None:
    """안정 생조가 있어도 올리지 않는다 — 운에 의존하는 기반이라 최고 등급을 보류한다."""
    assert _status(
        root=RootStatus.DIRECT_TRANSIT_ROOT,
        support=SupportStatus.INDIRECT_GENERATION_STABLE,
    ) is OperabilityStatus.OPERABLE


def test_transit_root_can_never_reach_fully_operable() -> None:
    """상한 제한이 어떤 신호 조합에서도 뚫리지 않는다."""
    for support in SupportStatus:
        for cut_off in CutOffStatus:
            for stage in (None, "묘", "건록"):
                status = _status(
                    root=RootStatus.DIRECT_TRANSIT_ROOT, support=support,
                    cut_off=cut_off, stage=stage)
                assert status is not OperabilityStatus.FULLY_OPERABLE


def test_transit_root_with_cut_off_is_partially_operable() -> None:
    assert _status(
        root=RootStatus.DIRECT_TRANSIT_ROOT, cut_off=CutOffStatus.CUT_OFF_PRESENT,
    ) is OperabilityStatus.PARTIALLY_OPERABLE


def test_transit_root_with_cut_off_and_weak_stage_is_weakened() -> None:
    assert _status(
        root=RootStatus.DIRECT_TRANSIT_ROOT, cut_off=CutOffStatus.CUT_OFF_PRESENT,
        stage="묘",
    ) is OperabilityStatus.WEAKENED


# ── 원국 뿌리 ────────────────────────────────────────────────────────────


def test_natal_root_with_stable_support_is_fully_operable() -> None:
    assert _status(
        root=RootStatus.DIRECT_NATAL_ROOT,
        support=SupportStatus.INDIRECT_GENERATION_STABLE,
    ) is OperabilityStatus.FULLY_OPERABLE


def test_non_main_qi_root_cannot_reach_fully_operable() -> None:
    """중기·여기만으로는 최고 등급 자격이 없다 — 유근 자체는 유지된다(CAL-ROOT-01c)."""
    for root in (RootStatus.DIRECT_NATAL_ROOT,
                 RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT):
        for support in SupportStatus:
            for cut_off in CutOffStatus:
                for stage in (None, "묘"):
                    for depth in ("middle_qi", "residual_qi"):
                        assert _status(
                            root=root, support=support, cut_off=cut_off,
                            stage=stage, depth=depth,
                        ) is not OperabilityStatus.FULLY_OPERABLE


def test_non_main_qi_root_is_still_rooted() -> None:
    """무근 분기로 떨어지지 않는다 — 자격만 제한하고 유근 판정은 그대로다."""
    rule = evaluate_element_operability(_profile(
        root=RootStatus.DIRECT_NATAL_ROOT,
        support=SupportStatus.INDIRECT_GENERATION_STABLE,
        depth="middle_qi")).matched_rule_id
    assert "ROOTLESS" not in rule
    assert rule == "R20_NATAL_NON_MAIN_ROOT_CAP"


def test_non_main_qi_cap_yields_operable_not_lower() -> None:
    """한 단계만 제한한다 — PARTIALLY 로 추가 하향하지 않는다."""
    assert _status(
        root=RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT, depth="middle_qi",
    ) is OperabilityStatus.OPERABLE


def test_natal_root_survives_disrupted_support() -> None:
    """간접 생조원이 흔들렸다고 원국의 직접 뿌리까지 무효로 만들지 않는다."""
    assert _status(
        root=RootStatus.DIRECT_NATAL_ROOT,
        support=SupportStatus.INDIRECT_GENERATION_DISRUPTED,
    ) is OperabilityStatus.OPERABLE


def test_natal_and_transit_root_without_obstruction_is_fully_operable() -> None:
    assert _status(
        root=RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT) is (
        OperabilityStatus.FULLY_OPERABLE)


# ── 무근 ─────────────────────────────────────────────────────────────────


def test_rootless_with_stable_support_is_partially_operable() -> None:
    assert _status(
        root=RootStatus.ABSENT, support=SupportStatus.INDIRECT_GENERATION_STABLE,
    ) is OperabilityStatus.PARTIALLY_OPERABLE


def test_rootless_with_mixed_support_is_partially_operable() -> None:
    """우세 판단을 하지 않는다 — 안정 경로가 하나라도 있으면 전부 교란으로 보지 않는다."""
    assert _status(
        root=RootStatus.ABSENT,
        support=SupportStatus.INDIRECT_GENERATION_PRESENT_MIXED,
    ) is OperabilityStatus.PARTIALLY_OPERABLE


def test_rootless_with_disrupted_support_is_weakened() -> None:
    assert _status(
        root=RootStatus.ABSENT, support=SupportStatus.INDIRECT_GENERATION_DISRUPTED,
    ) is OperabilityStatus.WEAKENED


def test_rootless_cut_off_without_reliable_support_is_suppressed() -> None:
    """첫 버전 SUPPRESSED 의 핵심 성립 규칙."""
    for support in (SupportStatus.INDIRECT_GENERATION_DISRUPTED, SupportStatus.ABSENT):
        assert _status(
            root=RootStatus.ABSENT, cut_off=CutOffStatus.CUT_OFF_PRESENT,
            support=support,
        ) is OperabilityStatus.SUPPRESSED


def test_rootless_cut_off_with_stable_support_is_only_weakened() -> None:
    """안정 생조가 남아 있으면 바로 SUPPRESSED 로 낮추지 않는다."""
    assert _status(
        root=RootStatus.ABSENT, cut_off=CutOffStatus.CUT_OFF_PRESENT,
        support=SupportStatus.INDIRECT_GENERATION_STABLE,
    ) is OperabilityStatus.WEAKENED


# ── 12운성 ───────────────────────────────────────────────────────────────


def test_weak_stage_alone_never_changes_the_grade() -> None:
    """12운성은 독립 판정자가 아니라 보조 조정자다."""
    for root in RootStatus:
        for support in SupportStatus:
            plain = _status(root=root, support=support)
            with_tomb = _status(root=root, support=support, stage="묘")
            assert plain is with_tomb, f"{root.value}/{support.value} 에서 묘가 단독 작용"


def test_weak_stage_alone_never_creates_suppression() -> None:
    assert _status(
        root=RootStatus.ABSENT, support=SupportStatus.ABSENT, stage="묘",
    ) is not OperabilityStatus.SUPPRESSED


# ── UNKNOWN ──────────────────────────────────────────────────────────────


def test_unresolved_element_is_unknown() -> None:
    """resolved_element 가 없으면 나머지 신호를 억지로 조합하지 않는다."""
    result = evaluate_element_operability(
        _profile(root=RootStatus.DIRECT_NATAL_ROOT, resolved=None))
    assert result.status is OperabilityStatus.UNKNOWN
    assert result.anchor is None


def test_unknown_root_is_unknown() -> None:
    assert _status(root=RootStatus.UNKNOWN) is OperabilityStatus.UNKNOWN


# ── 앵커·규칙 ────────────────────────────────────────────────────────────


def test_anchor_comes_from_the_grade_not_from_signal_arithmetic() -> None:
    """앵커는 등급에서 결정된다 — 개별 신호 가감으로 만들어지지 않는다."""
    assert OPERABILITY_ANCHOR == {
        OperabilityStatus.FULLY_OPERABLE: 0.90,
        OperabilityStatus.OPERABLE: 0.75,
        OperabilityStatus.PARTIALLY_OPERABLE: 0.55,
        OperabilityStatus.WEAKENED: 0.35,
        OperabilityStatus.SUPPRESSED: 0.15,
        OperabilityStatus.UNKNOWN: None,
    }
    for root in RootStatus:
        for support in SupportStatus:
            result = evaluate_element_operability(_profile(root=root, support=support))
            assert result.anchor == OPERABILITY_ANCHOR[result.status]


def test_exactly_one_rule_is_matched() -> None:
    """규칙이 하나뿐이라 같은 evidence 로 두 번 감점하는 것이 구조적으로 불가능하다."""
    result = evaluate_element_operability(_profile(
        root=RootStatus.ABSENT, cut_off=CutOffStatus.CUT_OFF_PRESENT,
        support=SupportStatus.INDIRECT_GENERATION_DISRUPTED, stage="묘",
        evidence=("clash:卯酉@natal.year.branch:卯+daewoon.branch:酉",) * 2,
    ))
    assert result.matched_rule_id == "R40_ROOTLESS_CUT_OFF_NO_RELIABLE_SUPPORT"
    assert len(result.evidence_ids) == 1          # 발생 1건
    assert len(result.reason_codes) == len(set(result.reason_codes))


def test_evaluation_is_deterministic() -> None:
    args = dict(root=RootStatus.ABSENT, cut_off=CutOffStatus.CUT_OFF_PRESENT,
                support=SupportStatus.ABSENT, stage="묘")
    assert evaluate_element_operability(_profile(**args)) == (
        evaluate_element_operability(_profile(**args)))


# ── 역할 중립 ────────────────────────────────────────────────────────────


_FORBIDDEN = ("role", "yong", "favorable", "adverse", "canonical", "activation",
              "mitigation", "quality")


def test_module_exposes_no_role_symbol() -> None:
    """역할표를 바꿔도 등급·앵커가 같으려면 애초에 역할을 몰라야 한다."""
    for name in (n for n in dir(mod) if not n.startswith("_")):
        assert not any(w in name.lower() for w in _FORBIDDEN), name
    params = inspect.signature(evaluate_element_operability).parameters
    assert list(params) == ["profile"]


def test_output_carries_no_activation_axis() -> None:
    result = evaluate_element_operability(_profile(root=RootStatus.ABSENT))
    for field in vars(result):
        assert not any(w in field.lower() for w in _FORBIDDEN), field


@pytest.mark.parametrize("depth", ["none", "unknown"])
def test_missing_depth_is_not_treated_as_a_non_main_cap(depth: str) -> None:
    """`has_main_qi_root=False` 는 중기·여기뿐 아니라 NONE·UNKNOWN 에서도 나온다.

    직접 뿌리가 있는데 깊이가 NONE·UNKNOWN 인 것은 프로필 불변식 위반이다. 조용히
    OPERABLE 로 낮추면 그 모순이 정상 결과로 흡수된다.
    """
    assert _status(
        root=RootStatus.DIRECT_NATAL_AND_TRANSIT_ROOT, depth=depth,
    ) is OperabilityStatus.FULLY_OPERABLE
