"""감사 전용 ablation overlay (CAL-ROOT-01a, 2026-08-01).

**production 모듈은 이 파일을 import 하지 않는다.** 여기 있는 것은 코드를 바꾸기 전에
영향 범위를 재기 위한 overlay 이고, 확정되면 P2-1/P2-2 로 옮긴다(CAL-ROOT-01b/01c).

01a 는 규칙표를 다시 구현하지 않는다. baseline 결과에 **한 가지 상한만** 덧씌운다.

    baseline 이 FULLY_OPERABLE 이고 MAIN_QI 뿌리가 없다 → OPERABLE
    그 외                                              → baseline 그대로

중기·여기 차등 감점, 뿌리 개수 승격, OPERABLE 추가 하향, 절각·생조·12운성 재계산은 하지
않는다. 그렇게 하면 무엇이 이동을 일으켰는지 분리할 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from saju_engines.element_operability_grade import (
    OPERABILITY_ANCHOR,
    OperabilityStatus,
)

#: 이름 있는 ablation. boolean 플래그로 두면 나중에 다른 정책과 결과를 구별할 수 없다.
ROOT_DEPTH_MAIN_QI_FULLY_CAP_V1 = "root-depth-main-qi-fully-cap-v1"
KNOWN_ABLATIONS = (ROOT_DEPTH_MAIN_QI_FULLY_CAP_V1,)


class RootDepth(StrEnum):
    """직접 뿌리의 지장간 깊이. `INDIRECT_GENERATION` 은 여기 포함되지 않는다."""

    MAIN_QI = "main_qi"
    MIDDLE_QI = "middle_qi"
    RESIDUAL_QI = "residual_qi"
    NONE = "none"
    UNKNOWN = "unknown"


_ORDER = {
    RootDepth.MAIN_QI: 3, RootDepth.MIDDLE_QI: 2,
    RootDepth.RESIDUAL_QI: 1, RootDepth.NONE: 0, RootDepth.UNKNOWN: -1,
}
_BY_TYPE = {
    "main": RootDepth.MAIN_QI, "middle": RootDepth.MIDDLE_QI,
    "residual": RootDepth.RESIDUAL_QI,
}


class AblationReason(StrEnum):
    FULLY_CAPPED_WITHOUT_MAIN_QI_ROOT = "FULLY_CAPPED_WITHOUT_MAIN_QI_ROOT"
    NO_ABLATION_CHANGE = "NO_ABLATION_CHANGE"


@dataclass(frozen=True)
class RootDepthProfile:
    natal_root_depth: RootDepth
    transit_root_depth: RootDepth
    strongest_root_depth: RootDepth
    has_main_qi_root: bool


def _deepest(depths: list[RootDepth]) -> RootDepth:
    return max(depths, key=lambda d: _ORDER[d]) if depths else RootDepth.NONE


def derive_root_depth_for_audit(profile: Any) -> RootDepthProfile:
    """뿌리 인스턴스에서 깊이를 뽑는다. 여러 뿌리면 **가장 깊은 자격**을 대표로 쓴다."""
    if profile.resolved_element is None:
        return RootDepthProfile(
            RootDepth.UNKNOWN, RootDepth.UNKNOWN, RootDepth.UNKNOWN, False)
    natal, transit = [], []
    for instance in profile.root.instances:
        depth = _BY_TYPE.get(instance.hidden_stem_type)
        if depth is None:
            continue
        (natal if instance.layer == "natal" else transit).append(depth)
    natal_depth, transit_depth = _deepest(natal), _deepest(transit)
    strongest = _deepest([natal_depth, transit_depth])
    return RootDepthProfile(
        natal_root_depth=natal_depth, transit_root_depth=transit_depth,
        strongest_root_depth=strongest,
        has_main_qi_root=strongest is RootDepth.MAIN_QI,
    )


def apply_root_depth_ablation(
    *, status: OperabilityStatus, has_main_qi_root: bool,
) -> tuple[OperabilityStatus, AblationReason]:
    """상한 하나만 덧씌운다. **후보가 baseline 보다 상향되는 경로는 없다.**"""
    if status is OperabilityStatus.FULLY_OPERABLE and not has_main_qi_root:
        return (OperabilityStatus.OPERABLE,
                AblationReason.FULLY_CAPPED_WITHOUT_MAIN_QI_ROOT)
    return status, AblationReason.NO_ABLATION_CHANGE


#: 허용 전이. 이 밖의 이동이 나오면 overlay 가 규칙표를 건드린 것이다.
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("fully_operable", "fully_operable"), ("fully_operable", "operable"),
    ("operable", "operable"), ("partially_operable", "partially_operable"),
    ("weakened", "weakened"), ("suppressed", "suppressed"),
    ("unknown", "unknown"),
})


def anchor_for(status: OperabilityStatus) -> float | None:
    return OPERABILITY_ANCHOR[status]
