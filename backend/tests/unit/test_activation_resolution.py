"""등급 내부 활성도 해상도 회귀 (CAL-ACTIVATION-RESOLUTION-01b, 2026-08-02).

`ActivationLevel` 은 거친 구간, `operability_anchor` 는 같은 구간 안의 순서다. 두 값은 독립
증거가 아니라 **같은 P2 상태의 두 해상도**라서 더하거나 곱하면 같은 것을 두 번 센다.

`>` 는 좋고 나쁨이 아니라 해당 축의 **작동 정도**가 크다는 뜻이다 — adverse 축에서 크면
불리 작동이 큰 것이다. 가치 방향은 축이, 작동 정도는 anchor 가 결정한다.
"""

from __future__ import annotations

import inspect

import pytest

from saju_engines import activation_resolution as mod
from saju_engines.activation_resolution import (
    ActivationAxis,
    ActivationResolutionError,
    activation_resolution_order_key,
    build_axis_activation_resolution,
    compare_same_axis_resolution,
    narrative_for,
)
from saju_engines.element_operability_grade import (
    OPERABILITY_ANCHOR,
    OperabilityStatus,
)
from saju_engines.role_activation_projection import ActivationLevel

_LEVEL_BY_STATUS = {
    OperabilityStatus.FULLY_OPERABLE: ActivationLevel.HIGH,
    OperabilityStatus.OPERABLE: ActivationLevel.HIGH,
    OperabilityStatus.PARTIALLY_OPERABLE: ActivationLevel.MODERATE,
    OperabilityStatus.WEAKENED: ActivationLevel.LOW,
    OperabilityStatus.SUPPRESSED: ActivationLevel.LOW,
    OperabilityStatus.UNKNOWN: ActivationLevel.UNKNOWN,
}


def _res(status: OperabilityStatus, axis=ActivationAxis.FAVORABLE, level=None):
    return build_axis_activation_resolution(
        axis=axis, level=level or _LEVEL_BY_STATUS[status],
        operability_status=status, operability_anchor=OPERABILITY_ANCHOR[status],
    )


# ── 등급 내부 순서 ───────────────────────────────────────────────────────


def test_fully_outranks_operable_within_high() -> None:
    assert compare_same_axis_resolution(
        _res(OperabilityStatus.FULLY_OPERABLE),
        _res(OperabilityStatus.OPERABLE)) > 0


def test_weakened_outranks_suppressed_within_low() -> None:
    assert compare_same_axis_resolution(
        _res(OperabilityStatus.WEAKENED),
        _res(OperabilityStatus.SUPPRESSED)) > 0


def test_level_is_the_primary_key() -> None:
    """HIGH 는 MODERATE 보다 앞선다 — anchor 가 1차 순서를 뒤집지 못한다."""
    assert compare_same_axis_resolution(
        _res(OperabilityStatus.OPERABLE),              # HIGH  0.75
        _res(OperabilityStatus.PARTIALLY_OPERABLE)) > 0  # MODERATE 0.55


def test_anchor_never_overturns_a_higher_level() -> None:
    """낮은 등급의 높은 anchor 가 높은 등급을 이기지 못한다."""
    high_low_anchor = _res(OperabilityStatus.OPERABLE)            # HIGH 0.75
    moderate = _res(OperabilityStatus.PARTIALLY_OPERABLE)         # MODERATE 0.55
    assert compare_same_axis_resolution(moderate, high_low_anchor) < 0


def test_adverse_axis_orders_by_operation_not_by_valence() -> None:
    """adverse 축에서 크다는 것은 불리 작동이 크다는 뜻이다."""
    assert compare_same_axis_resolution(
        _res(OperabilityStatus.FULLY_OPERABLE, ActivationAxis.ADVERSE),
        _res(OperabilityStatus.OPERABLE, ActivationAxis.ADVERSE)) > 0


# ── 비교 범위 ────────────────────────────────────────────────────────────


def test_cross_axis_comparison_is_rejected() -> None:
    """favorable 과 adverse 를 anchor 하나로 직접 비교하면 안 된다."""
    with pytest.raises(ActivationResolutionError, match="CROSS_AXIS"):
        compare_same_axis_resolution(
            _res(OperabilityStatus.OPERABLE, ActivationAxis.FAVORABLE),
            _res(OperabilityStatus.FULLY_OPERABLE, ActivationAxis.ADVERSE))


def test_unknown_is_not_orderable() -> None:
    unknown = _res(OperabilityStatus.UNKNOWN)
    assert activation_resolution_order_key(unknown) is None
    with pytest.raises(ActivationResolutionError, match="UNKNOWN"):
        compare_same_axis_resolution(unknown, _res(OperabilityStatus.OPERABLE))


def test_none_axis_does_not_consume_the_anchor() -> None:
    """작동이 없는 축에 등급 내부 순서를 매기지 않는다."""
    res = _res(OperabilityStatus.FULLY_OPERABLE, level=ActivationLevel.NONE)
    assert res.within_level_anchor is None
    key = activation_resolution_order_key(res)
    assert key is not None and key.within_level_anchor is None


# ── 일관성 ───────────────────────────────────────────────────────────────


def test_status_anchor_mismatch_is_rejected() -> None:
    """anchor 가 임의 값으로 들어오면 정렬이 조용히 뒤집힌다."""
    with pytest.raises(ActivationResolutionError, match="INVALID_OPERABILITY_ANCHOR"):
        build_axis_activation_resolution(
            axis=ActivationAxis.FAVORABLE, level=ActivationLevel.HIGH,
            operability_status=OperabilityStatus.OPERABLE, operability_anchor=0.90)


@pytest.mark.parametrize("status", list(OperabilityStatus))
def test_every_status_builds_with_its_canonical_anchor(status) -> None:
    assert _res(status).operability_status is status


# ── 산술 금지 ────────────────────────────────────────────────────────────


def test_module_exposes_no_arithmetic_consumption() -> None:
    """소비 방식은 정렬 키 하나뿐이다 — 합산·곱셈 helper 를 두지 않는다."""
    banned = ("sum", "total", "weight", "combine", "score", "multiply", "add_")
    for name in (n for n in dir(mod) if not n.startswith("_")):
        assert not any(w in name.lower() for w in banned), name


def test_order_key_is_not_a_scalar() -> None:
    """단일 수치로 접히면 곧바로 산술에 쓰인다."""
    key = activation_resolution_order_key(_res(OperabilityStatus.FULLY_OPERABLE))
    assert key is not None
    assert not isinstance(key, (int, float))
    assert (key.level_rank, key.within_level_anchor) == (3, 0.90)


def test_structural_tension_is_out_of_scope() -> None:
    """활성도 해상도와 긴장도 해상도를 동시에 바꾸면 원인을 분리할 수 없다."""
    assert "tension" not in {a.value for a in ActivationAxis}
    assert not any("tension" in n.lower() for n in dir(mod) if not n.startswith("_"))


# ── 사용자 표현 ──────────────────────────────────────────────────────────


def test_narrative_carries_no_numbers() -> None:
    for status in OperabilityStatus:
        text = narrative_for(status)
        assert text and not any(ch.isdigit() for ch in text)
        assert "%" not in text


def test_narrative_does_not_escalate_certainty() -> None:
    """기신 + FULLY 를 '매우 강한 악운' 으로 번역하지 않는다 — 문구는 역할을 모른다."""
    text = narrative_for(OperabilityStatus.FULLY_OPERABLE)
    for word in ("매우", "강한", "악운", "최고", "확실"):
        assert word not in text
    params = inspect.signature(narrative_for).parameters
    assert list(params) == ["status"]        # 역할을 받지 않는다


# ── production 계약 ──────────────────────────────────────────────────────


def test_no_new_user_visible_level_or_tag() -> None:
    """후보 A 의 VERY_HIGH, 후보 C 의 FULL/STANDARD 는 production 에 없다."""
    assert not hasattr(ActivationLevel, "VERY_HIGH")
    assert "very_high" not in {level.value for level in ActivationLevel}
    from saju_engines import role_activation_projection as rap
    source_names = {n for n in dir(rap) if not n.startswith("_")}
    assert "FULL" not in source_names and "STANDARD" not in source_names


def test_role_activation_result_schema_is_unchanged() -> None:
    """해상도는 비직렬화 helper 다 — 응답 스키마에 필드를 더하지 않는다."""
    import dataclasses

    from saju_engines.role_activation_projection import RoleActivationResult
    fields = {f.name for f in dataclasses.fields(RoleActivationResult)}
    assert "within_level_anchor" not in fields
    assert "activation_resolution" not in fields
