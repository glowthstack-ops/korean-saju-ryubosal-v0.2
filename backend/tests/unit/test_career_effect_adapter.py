"""기존 신호 → 커리어 효과 기여 어댑터 회귀 (CAREER_TRANSITION_SYSTEM §4·§9).

완료 기준은 "빈 벡터 0건"이 아니다 — 근거가 정말 없는 명식·기간은 빈 벡터가 정상이다.
여기서 고정하는 것은 **기존 엔진에 관련 신호가 있는데 어댑터 누락으로 비는 경우 0**이다.
"""

from __future__ import annotations

import pytest

from saju_engines.career_effect_adapter import (
    SIGNAL_AXIS_MAP,
    build_career_contributions,
)
from saju_engines.career_effect_vector import (
    assess_bottleneck,
    audit_contributions,
    build_effect_vector,
    split_factors,
)
from saju_shared_types.career_effect_vector import (
    REQUIRED_GATES,
    BottleneckStatus,
    ContributionRole,
    EffectAxis,
)
from saju_shared_types.career_transition import CareerTransitionKind
from saju_shared_types.event_engine import EventKeyV2


class _Cand:
    """어댑터가 읽는 최소 후보 형태(EventCandidate / V2 공통 필드)."""

    def __init__(self, event_key, period="2026", score=0, favorability=0.0):
        self.event_key = event_key
        self.period = period
        self.score = score
        self.favorability = favorability


def _external_move_signals():
    """EXTERNAL_MOVE 필수 관문(AGREEMENT·EXIT·ENTRY)을 모두 채우는 최소 신호."""
    return [
        _Cand(EventKeyV2.CAREER_CHANGE, "2026", score=70),
        _Cand(EventKeyV2.JOB_GAIN, "2026", score=55),
        _Cand(EventKeyV2.CONTRACT_DOCUMENT, "2026", favorability=0.4),
    ]


# ── 어댑터가 실제 값을 만든다 ────────────────────────────────────────────


def test_career_signals_produce_non_empty_vector() -> None:
    """관련 신호가 있으면 벡터가 비지 않는다 — P4-1 의 '항상 근거 부족'을 해소한다."""
    contribs = build_career_contributions(_external_move_signals())
    vector, audit = build_effect_vector(contribs)
    assert audit.is_clean
    assert vector is not None and vector.axes


def test_bottleneck_becomes_evaluable_for_external_move() -> None:
    """EXTERNAL_MOVE 필수 관문이 모두 채워지면 병목이 판정 가능해진다."""
    vector, _ = build_effect_vector(build_career_contributions(_external_move_signals()))
    assert vector is not None
    bottleneck = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, vector)
    assert bottleneck.status is BottleneckStatus.EVALUABLE
    assert bottleneck.bottleneck_gate is not None
    assert bottleneck.forecast_completion_readiness is not None


@pytest.mark.parametrize("kind", list(CareerTransitionKind))
def test_every_kind_has_reachable_gate_axes(kind: CareerTransitionKind) -> None:
    """모든 Kind 의 필수 관문 축이 어댑터로 도달 가능해야 한다.

    도달 불가능한 축이 있으면 그 Kind 는 영원히 NOT_EVALUABLE 이 된다 — 누락 탐지.
    """
    from saju_shared_types.career_effect_vector import GATE_AXIS

    reachable = {axis for _key, axis in SIGNAL_AXIS_MAP}
    for gate in REQUIRED_GATES[kind]:
        assert GATE_AXIS[gate] in reachable, f"{kind}: {gate} 축에 도달할 신호가 없다"


# ── 없는 근거를 만들지 않는다 ────────────────────────────────────────────


def test_no_career_signal_yields_empty_vector() -> None:
    """관련 없는 후보만 있으면 빈 tuple — 0 으로 채우지 않는다."""
    contribs = build_career_contributions([
        _Cand(EventKeyV2.CHILDBIRTH, score=90),
        _Cand(EventKeyV2.HEALTH_ATTENTION, score=80),
    ])
    assert contribs == ()


def test_partial_axes_keep_bottleneck_not_evaluable() -> None:
    """일부 축만 있으면 병목을 억지로 만들지 않는다(축별 support/blocker 는 유지)."""
    contribs = build_career_contributions([_Cand(EventKeyV2.CONTRACT_DOCUMENT,
                                                favorability=0.8)])
    vector, _ = build_effect_vector(contribs)
    assert vector is not None and vector.axes
    bottleneck = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, vector)
    assert bottleneck.status is BottleneckStatus.NOT_EVALUABLE
    assert set(bottleneck.missing_gates)          # 빠진 관문이 명시된다
    supporting, _blocking = split_factors(vector)
    assert supporting                              # 있는 축의 근거는 그대로 보여준다


# ── double_contribution (INV-11) ────────────────────────────────────────


def test_one_contribution_per_axis() -> None:
    """축당 기여는 정확히 1건 — 여러 기간 후보를 합산하지 않는다."""
    contribs = build_career_contributions([
        _Cand(EventKeyV2.CAREER_CHANGE, "2026", score=40),
        _Cand(EventKeyV2.CAREER_CHANGE, "2027", score=90),
        _Cand(EventKeyV2.CAREER_CHANGE, "2028", score=60),
    ])
    axes = [c.axis for c in contribs]
    assert len(axes) == len(set(axes))


def test_strongest_signal_wins_not_the_sum() -> None:
    """축 값은 합이 아니라 최댓값 — 합산하면 1.0 을 넘겨 병목 비교가 무의미해진다."""
    contribs = build_career_contributions([
        _Cand(EventKeyV2.CAREER_CHANGE, "2026", score=40),
        _Cand(EventKeyV2.CAREER_CHANGE, "2027", score=90),
    ])
    by_axis = {c.axis: c.value for c in contribs}
    assert by_axis[EffectAxis.OPPORTUNITY_ACTIVATION] == pytest.approx(0.9)


def test_same_signal_on_multiple_axes_has_distinct_evidence_and_rationale() -> None:
    """한 신호가 여러 축에 들어가면 축별 evidence_id·근거가 따로 남는다."""
    contribs = build_career_contributions([_Cand(EventKeyV2.CAREER_CHANGE, score=70)])
    axes = {c.axis for c in contribs}
    assert axes == {EffectAxis.OPPORTUNITY_ACTIVATION, EffectAxis.EXIT_PRESSURE}
    assert len({c.evidence_id for c in contribs}) == 2
    assert len({c.signal_ref for c in contribs}) == 2   # 축별 근거가 다르다
    assert audit_contributions(contribs).is_clean


def test_adapter_emits_no_derived_role() -> None:
    """파생 요약값을 기여로 만들지 않는다(재합산 금지)."""
    contribs = build_career_contributions(_external_move_signals())
    assert all(c.role is ContributionRole.PRIMARY for c in contribs)


def test_legacy_scored_evidence_is_not_double_counted() -> None:
    """기존 점수에 반영된 evidence 를 신규 기여로도 가산하면 감사가 잡는다."""
    contribs = build_career_contributions(_external_move_signals())
    legacy = frozenset({contribs[0].evidence_id})
    vector, audit = build_effect_vector(contribs, legacy_scored_evidence_ids=legacy)
    assert vector is None and audit.legacy_mixed


# ── 마찰은 support 가 아니다 ─────────────────────────────────────────────


def test_friction_signals_are_blocking_not_supporting() -> None:
    """지연·갈등은 막는 힘이므로 support 로 뒤집히면 안 된다."""
    contribs = build_career_contributions([
        _Cand(EventKeyV2.PREPARATION_DELAY, score=80),
        _Cand(EventKeyV2.CAREER_CHANGE, score=60),
    ])
    vector, _ = build_effect_vector(contribs)
    assert vector is not None
    _supporting, blocking = split_factors(vector)
    assert any(f.axis is EffectAxis.EXIT_FRICTION for f in blocking)
    assert vector.by_axis[EffectAxis.EXIT_FRICTION] < 0


def test_exit_friction_does_not_change_bottleneck() -> None:
    """마찰 축은 필수 관문이 아니므로 병목 판정을 바꾸지 않는다(서술 보조)."""
    base = build_career_contributions(_external_move_signals())
    with_friction = build_career_contributions(
        [*_external_move_signals(), _Cand(EventKeyV2.PREPARATION_DELAY, score=95)]
    )
    v1, _ = build_effect_vector(base)
    v2, _ = build_effect_vector(with_friction)
    assert v1 is not None and v2 is not None
    b1 = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v1)
    b2 = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v2)
    assert b1.bottleneck_gate == b2.bottleneck_gate
    assert b1.forecast_completion_readiness == b2.forecast_completion_readiness


# ── 결정론·범위 ──────────────────────────────────────────────────────────


def test_values_stay_within_unit_range() -> None:
    """축 값은 −1~1 을 벗어나지 않는다(병목 비교가 성립하려면 스케일이 같아야 한다)."""
    contribs = build_career_contributions([
        _Cand(EventKeyV2.CAREER_CHANGE, score=100000),      # soft_cap 전 raw 유입 방어
        _Cand(EventKeyV2.CONTRACT_DOCUMENT, favorability=-5.0),
        _Cand(EventKeyV2.PREPARATION_DELAY, score=100000),
    ])
    assert all(-1.0 <= c.value <= 1.0 for c in contribs)


def test_output_is_deterministic_across_input_order() -> None:
    """입력 순서가 달라도 같은 기여가 나온다(동률 tie-break 포함)."""
    a = _Cand(EventKeyV2.CAREER_CHANGE, "2026", score=70)
    b = _Cand(EventKeyV2.CAREER_CHANGE, "2027", score=70)   # 동률
    forward = build_career_contributions([a, b])
    backward = build_career_contributions([b, a])
    assert [c.model_dump() for c in forward] == [c.model_dump() for c in backward]


def test_unknown_event_key_is_ignored_not_crashed() -> None:
    """알 수 없는 키는 무시한다 — 어댑터가 채팅을 깨뜨리면 안 된다."""
    class _Weird:
        event_key = "not_a_real_key"
        period = "2026"
        score = 50
        favorability = 0.0

    assert build_career_contributions([_Weird(), *_external_move_signals()])


# ── 병목 간격 가드 (2026-07-26) ──────────────────────────────────────────


def _gate_vector(**gate_values: float):
    """필수 관문 축을 직접 지정한 벡터(간격 시나리오 구성용)."""
    from saju_shared_types.career_effect_vector import ContributionRole, EffectContribution

    contribs = tuple(
        EffectContribution(
            evidence_id=f"ev-{name}", signal_ref=name, axis=EffectAxis(name),
            value=v, role=ContributionRole.PRIMARY,
        )
        for name, v in gate_values.items()
    )
    vector, audit = build_effect_vector(contribs)
    assert audit.is_clean and vector is not None
    return vector


def test_wide_margin_is_distinct_bottleneck() -> None:
    """간격이 충분하면 단일 병목으로 말해도 된다."""
    from saju_shared_types.career_effect_vector import BottleneckSharpness

    v = _gate_vector(agreement_quality=0.5, exit_pressure=0.9, entry_realization=0.95)
    b = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert b.sharpness is BottleneckSharpness.DISTINCT
    assert b.bottleneck_margin == pytest.approx(0.4)


def test_narrow_margin_reports_tied_gates() -> None:
    """하위 두 관문이 비슷하면 병렬로 남긴다 — 단일 병목 단정 금지."""
    from saju_shared_types.career_effect_vector import BottleneckSharpness

    v = _gate_vector(agreement_quality=0.86, exit_pressure=0.91, entry_realization=0.95)
    b = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert b.sharpness is BottleneckSharpness.NARROW
    assert len(b.tied_gates) >= 2


def test_flat_margin_denies_single_bottleneck() -> None:
    """차이가 사실상 없으면 뚜렷한 병목이 아니다."""
    from saju_shared_types.career_effect_vector import BottleneckSharpness

    v = _gate_vector(agreement_quality=0.96, exit_pressure=0.97, entry_realization=0.98)
    b = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert b.sharpness is BottleneckSharpness.FLAT


def test_sharpness_does_not_change_the_verdict() -> None:
    """서술 강도만 바뀔 뿐 병목 판정 자체는 그대로다."""
    v = _gate_vector(agreement_quality=0.96, exit_pressure=0.97, entry_realization=0.98)
    b = assess_bottleneck(CareerTransitionKind.EXTERNAL_MOVE, v)
    assert b.status is BottleneckStatus.EVALUABLE
    assert b.bottleneck_gate is not None
    assert b.forecast_completion_readiness == pytest.approx(0.96)


def test_single_gate_kind_has_unknown_sharpness() -> None:
    """관문이 1개면 비교할 대상이 없다 — 간격을 지어내지 않는다."""
    from saju_shared_types.career_effect_vector import BottleneckSharpness

    v = _gate_vector(exit_pressure=0.7)
    b = assess_bottleneck(CareerTransitionKind.RESIGNATION_ONLY, v)
    assert b.sharpness is BottleneckSharpness.UNKNOWN
    assert b.bottleneck_margin is None


def test_axis_saturation_rate_reports_compression() -> None:
    """포화율은 adapter 매핑·표시 점수 압축 문제를 드러내는 관측값이다."""
    from saju_engines.career_effect_vector import axis_saturation_rate

    saturated = _gate_vector(agreement_quality=0.96, exit_pressure=0.97,
                             entry_realization=0.99)
    spread = _gate_vector(agreement_quality=0.2, exit_pressure=0.5,
                          entry_realization=0.95)
    assert axis_saturation_rate(saturated) == pytest.approx(1.0)
    assert axis_saturation_rate(spread) == pytest.approx(1 / 3)
