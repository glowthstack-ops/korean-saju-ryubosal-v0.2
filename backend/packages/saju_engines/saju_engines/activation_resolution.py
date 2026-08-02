"""등급 내부 활성도 해상도 (CAL-ACTIVATION-RESOLUTION-01b, 2026-08-02).

`ActivationLevel` 은 거친 작동 구간이고, `operability_anchor` 는 **같은 구간 안의 순서**다.

    1차 키   ActivationLevel   HIGH > MODERATE > LOW > NONE
    2차 키   operability_anchor  같은 축·같은 등급일 때만

두 값은 독립 증거가 아니라 **같은 P2 상태의 두 해상도**다. 그래서 더하거나 곱하면 같은 것을
두 번 센다. 여기서 제공하는 소비 방식은 **정렬 키 하나뿐**이며 산술은 제공하지 않는다.

    금지   score += activation_anchor + operability_anchor
           score *= operability_anchor
    허용   sorted(items, key=lambda x: order_key(x))

`>` 는 좋고 나쁨이 아니라 **해당 축의 작동 정도가 더 큼**을 뜻한다. 가치 방향은 축이
결정하고 anchor 는 작동 정도만 결정한다 — adverse 축에서 크면 불리 작동이 큰 것이다.

`structural_tension` 은 이 계약의 대상이 아니다. 활성도 해상도와 긴장도 해상도를 동시에
바꾸면 원인을 분리할 수 없다.

사용자에게 수치를 노출하지 않는다. 등급에서 파생한 서술만 쓴다(`NARRATIVE_BY_STATUS`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .element_operability_grade import OPERABILITY_ANCHOR, OperabilityStatus
from .role_activation_projection import ActivationLevel


class ActivationAxis(StrEnum):
    """해상도를 적용하는 축. `structural_tension` 은 여기 없다."""

    FAVORABLE = "favorable"
    ADVERSE = "adverse"
    MITIGATION = "mitigation"
    NEUTRAL = "neutral"


#: 1차 키. `UNKNOWN` 은 정렬 대상이 아니라 rank 를 주지 않는다.
LEVEL_RANK: dict[ActivationLevel, int] = {
    ActivationLevel.HIGH: 3,
    ActivationLevel.MODERATE: 2,
    ActivationLevel.LOW: 1,
    ActivationLevel.NONE: 0,
}

#: 등급에서 파생하는 서술. 수치를 문장으로 옮기지 않는다.
NARRATIVE_BY_STATUS: dict[OperabilityStatus, str] = {
    OperabilityStatus.FULLY_OPERABLE: "작동 조건이 충분히 갖춰진 편",
    OperabilityStatus.OPERABLE: "작동 여건이 갖춰진 편",
    OperabilityStatus.PARTIALLY_OPERABLE: "일부 조건에서 작동하는 편",
    OperabilityStatus.WEAKENED: "작동력이 약해진 편",
    OperabilityStatus.SUPPRESSED: "신호는 있으나 작동이 크게 제한된 편",
    OperabilityStatus.UNKNOWN: "현재 근거로 작동 정도를 확정하기 어려움",
}


class ActivationResolutionError(Exception):
    """해상도 소비 계약 위반. 조용히 넘기지 않는다."""


@dataclass(frozen=True)
class ActivationResolutionOrderKey:
    """정렬 전용 키. **산술에 쓰라고 만든 값이 아니다.**"""

    level_rank: int
    within_level_anchor: float | None


@dataclass(frozen=True)
class AxisActivationResolution:
    """축 하나의 해상도. 축을 포함해 교차 비교를 구조적으로 막는다."""

    axis: ActivationAxis
    level: ActivationLevel
    operability_status: OperabilityStatus
    within_level_anchor: float | None


def build_axis_activation_resolution(
    *,
    axis: ActivationAxis,
    level: ActivationLevel,
    operability_status: OperabilityStatus,
    operability_anchor: float | None,
) -> AxisActivationResolution:
    """해상도를 만든다. **상태와 anchor 의 고정 매핑을 검사한다.**

    anchor 가 임의 값으로 들어오면 정렬이 조용히 뒤집힌다. 불일치는 내부 불변식 오류다.

    Raises:
        ActivationResolutionError: 상태–anchor 불일치.
    """
    expected = OPERABILITY_ANCHOR[operability_status]
    if operability_anchor != expected:
        raise ActivationResolutionError(
            f"INVALID_OPERABILITY_ANCHOR_PAIR: {operability_status.value} "
            f"expected={expected} got={operability_anchor}"
        )
    # NONE 축은 애초에 작동이 없다 — 등급 내부 순서를 매길 대상이 아니다.
    anchor = None if level is ActivationLevel.NONE else operability_anchor
    return AxisActivationResolution(axis, level, operability_status, anchor)


def activation_resolution_order_key(
    resolution: AxisActivationResolution,
) -> ActivationResolutionOrderKey | None:
    """정렬 키. `UNKNOWN` 은 키를 만들지 않는다(정렬 대상 제외)."""
    rank = LEVEL_RANK.get(resolution.level)
    if rank is None:
        return None
    return ActivationResolutionOrderKey(rank, resolution.within_level_anchor)


def compare_same_axis_resolution(
    left: AxisActivationResolution, right: AxisActivationResolution,
) -> int:
    """같은 축 안에서만 비교한다. 음수/0/양수.

    favorable 과 adverse 를 anchor 하나로 직접 비교하면 안 된다 — 두 축은 P3 에서도 별도로
    보존해야 하고, 섞으면 "유리함이 불리함보다 크다" 같은 성립하지 않는 문장이 나온다.

    Raises:
        ActivationResolutionError: 축이 다르거나 한쪽이 정렬 대상이 아닌 경우.
    """
    if left.axis is not right.axis:
        raise ActivationResolutionError(
            f"CROSS_AXIS_COMPARISON_PROHIBITED: {left.axis.value} vs {right.axis.value}"
        )
    lk, rk = (activation_resolution_order_key(left),
              activation_resolution_order_key(right))
    if lk is None or rk is None:
        raise ActivationResolutionError("UNKNOWN_LEVEL_IS_NOT_ORDERABLE")
    if lk.level_rank != rk.level_rank:
        # 등급이 다르면 anchor 는 1차 순서를 뒤집지 못한다.
        return -1 if lk.level_rank < rk.level_rank else 1
    la = lk.within_level_anchor if lk.within_level_anchor is not None else -1.0
    ra = rk.within_level_anchor if rk.within_level_anchor is not None else -1.0
    if la == ra:
        return 0
    return -1 if la < ra else 1


def narrative_for(status: OperabilityStatus) -> str:
    """등급 → 서술. **수치를 문장으로 옮기지 않는다.**

    역할과 결합할 때도 단정 강도를 올리지 않는다 — 기신 + FULLY_OPERABLE 은 "매우 강한
    악운" 이 아니라 "불리하게 해석되는 요소가 실제로 작동할 조건은 비교적 갖춰진 편" 이다.
    """
    return NARRATIVE_BY_STATUS[status]
