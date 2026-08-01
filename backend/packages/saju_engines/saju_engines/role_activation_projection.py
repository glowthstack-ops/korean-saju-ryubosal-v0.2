"""역할 활성도 투영 (P2-3, 2026-08-01).

P2-a(오행 실현도)는 역할을 모른다. 여기서 비로소 용희기구한 역할표를 입력받아 활성도 축에
투영한다. **역할표를 바꿔도 P2-1 프로필과 P2-2 등급은 그대로다** — 그래서 경계 명식의 용신
모델 선택 감수가 실현도 개발을 막지 않는다.

## 억제된 용신은 기신이 아니다

가장 중요한 불변식이다.

    SUPPRESSED 용신  ≠ 기신 전환
                     ≠ adverse activation 발생
                     ≠ favorable quality 반전

"유리한 작용이 충분히 나타나지 않음" 과 "그 오행이 불리하게 뒤집힘" 은 다른 현상이다.
불리한 결과는 기신·구신의 활성이나 완충 실패에서 나와야 한다. 그래서 `effective_quality` 를
만들지 않고 `canonical_quality`(불변) + `operability_status` + 활성도 축으로 나눈다.

## 등급이 SSOT, 수치는 파생

`ActivationLevel` 이 의미론적 SSOT이고 앵커는 등급에 고정된 파생값이다. 두 값을 각각
계산하지 않으며 가감하지도 않는다. `0.25` 를 확률이나 영향력 25% 로 노출하지 않는다.

실현도 앵커와 활성도 앵커는 **다른 축의 고정 지점**이라 한 필드로 합치지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .element_operability_grade import OperabilityEvaluation, OperabilityStatus


class CanonicalRole(StrEnum):
    """용희기구한. 기존 만세 엔진의 한글 어휘를 그대로 쓴다."""

    YONG = "용신"
    HUI = "희신"
    GI = "기신"
    GU = "구신"
    HAN = "한신"


class CanonicalRoleBasis(StrEnum):
    """역할표의 출처. **production 허용 범위가 다르다.**"""

    ENGINE_NATIVE = "engine_native"
    SOURCE_FIXTURE = "source_fixture"
    REVIEWED_OVERRIDE = "reviewed_override"
    CALIBRATION_OVERRIDE = "calibration_override"


#: production 경로에서 허용되는 역할 출처. 0A에서 확정한 대로 출처 역할표는 테스트 전용이며
#: 감수·캘리브레이션 override 는 아직 활성화되지 않았다.
PRODUCTION_ALLOWED_ROLE_BASES: frozenset[CanonicalRoleBasis] = frozenset({
    CanonicalRoleBasis.ENGINE_NATIVE,
})


class ActivationLevel(StrEnum):
    """활성도 등급 — 의미론적 SSOT."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


#: 활성도 앵커. 실현도 앵커(0.90/0.75/0.55/0.35/0.15)와 다른 축이다.
ACTIVATION_ANCHOR: dict[ActivationLevel, float | None] = {
    ActivationLevel.NONE: 0.0,
    ActivationLevel.LOW: 0.25,
    ActivationLevel.MODERATE: 0.50,
    ActivationLevel.HIGH: 0.75,
    ActivationLevel.UNKNOWN: None,
}

#: 실현도 → 역할축 활성도. FULLY/OPERABLE 이 같은 등급을 받아도 정보는 사라지지 않는다 —
#: `operability_status` 와 `operability_anchor` 가 결과에 그대로 남는다.
_OPERABILITY_TO_ACTIVATION: dict[OperabilityStatus, ActivationLevel] = {
    OperabilityStatus.FULLY_OPERABLE: ActivationLevel.HIGH,
    OperabilityStatus.OPERABLE: ActivationLevel.HIGH,
    OperabilityStatus.PARTIALLY_OPERABLE: ActivationLevel.MODERATE,
    OperabilityStatus.WEAKENED: ActivationLevel.LOW,
    OperabilityStatus.SUPPRESSED: ActivationLevel.LOW,
    OperabilityStatus.UNKNOWN: ActivationLevel.UNKNOWN,
}

#: 유리 역할의 구조적 긴장 — 필요한 것이 작동하지 못할수록 커진다.
_TENSION_FAVORABLE: dict[OperabilityStatus, ActivationLevel] = {
    OperabilityStatus.FULLY_OPERABLE: ActivationLevel.NONE,
    OperabilityStatus.OPERABLE: ActivationLevel.NONE,
    OperabilityStatus.PARTIALLY_OPERABLE: ActivationLevel.LOW,
    OperabilityStatus.WEAKENED: ActivationLevel.MODERATE,
    OperabilityStatus.SUPPRESSED: ActivationLevel.HIGH,
    OperabilityStatus.UNKNOWN: ActivationLevel.UNKNOWN,
}

#: 불리 역할의 구조적 긴장 — 잘 작동할수록 커진다. 억제돼도 NONE 이 아니다(완전 소멸이 아니다).
_TENSION_ADVERSE: dict[OperabilityStatus, ActivationLevel] = {
    OperabilityStatus.FULLY_OPERABLE: ActivationLevel.HIGH,
    OperabilityStatus.OPERABLE: ActivationLevel.HIGH,
    OperabilityStatus.PARTIALLY_OPERABLE: ActivationLevel.MODERATE,
    OperabilityStatus.WEAKENED: ActivationLevel.LOW,
    OperabilityStatus.SUPPRESSED: ActivationLevel.LOW,
    OperabilityStatus.UNKNOWN: ActivationLevel.UNKNOWN,
}

_FAVORABLE_ROLES = frozenset({CanonicalRole.YONG, CanonicalRole.HUI})
_ADVERSE_ROLES = frozenset({CanonicalRole.GI, CanonicalRole.GU})


@dataclass(frozen=True)
class AxisActivation:
    """축 하나의 활성도. 수치는 등급에서 결정적으로 파생된다."""

    level: ActivationLevel
    anchor: float | None


def _axis(level: ActivationLevel) -> AxisActivation:
    return AxisActivation(level, ACTIVATION_ANCHOR[level])


_NONE_AXIS = AxisActivation(ActivationLevel.NONE, 0.0)


@dataclass(frozen=True)
class RoleActivationResult:
    """역할 투영 결과. **canonical_role 은 여기서 바뀌지 않는다.**"""

    node_id: str
    canonical_role: CanonicalRole
    role_basis: CanonicalRoleBasis
    #: 원인 정보 — 활성도로 흡수하지 않고 그대로 보존한다.
    operability_status: OperabilityStatus
    operability_anchor: float | None
    favorable_activation: AxisActivation
    adverse_activation: AxisActivation
    mitigation: AxisActivation
    neutral_activation: AxisActivation
    structural_tension: AxisActivation
    reason_codes: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def project_role_activation(
    *,
    node_id: str,
    canonical_role: CanonicalRole,
    role_basis: CanonicalRoleBasis,
    evaluation: OperabilityEvaluation,
) -> RoleActivationResult:
    """실현도 등급을 역할 활성도 축에 투영한다.

    Args:
        node_id: 대상 자리.
        canonical_role: 용희기구한. **여기서 재선택하지 않는다.**
        role_basis: 역할표 출처. production 허용 여부는 호출부가 확인한다.
        evaluation: P2-2 등급 판정.

    Returns:
        축별 활성도 + 원인 정보. `loss`·`mixed_binding` 축은 만들지 않는다 — 그 둘은 노드
        하나의 작동성이 아니라 결합 결과라서 후속 계층 소관이다.
    """
    status = evaluation.status
    activation = _OPERABILITY_TO_ACTIVATION[status]
    reasons = [f"ROLE_BASIS_{role_basis.name}"]

    favorable = adverse = mitigation = neutral = _NONE_AXIS
    if canonical_role in _FAVORABLE_ROLES:
        favorable = mitigation = _axis(activation)
        tension = _axis(_TENSION_FAVORABLE[status])
        reasons.append("ROLE_PROJECTED_AS_FAVORABLE")
        if status is OperabilityStatus.SUPPRESSED:
            reasons.append("FAVORABLE_ROLE_SUPPRESSED")
        if status in (OperabilityStatus.SUPPRESSED, OperabilityStatus.WEAKENED):
            reasons.append("MITIGATION_LIMITED_BY_OPERABILITY")
    elif canonical_role in _ADVERSE_ROLES:
        adverse = _axis(activation)
        tension = _axis(_TENSION_ADVERSE[status])
        reasons.append("ROLE_PROJECTED_AS_ADVERSE")
        if status in (OperabilityStatus.FULLY_OPERABLE, OperabilityStatus.OPERABLE):
            reasons.append("ADVERSE_ROLE_OPERABLE")
    else:
        # 한신 — 실현도가 낮다고 유리·불리 쪽으로 옮기지 않는다. 관계 충돌에서 오는 긴장은
        # 이 노드의 작동성이 아니라 별도 신호로 들어와야 한다.
        neutral = _axis(activation)
        # 한신의 대상 축은 neutral 하나다. 실현도가 UNKNOWN 이어도 긴장 축까지 오염시키지
        # 않는다 — 한신 자체의 작동성만으로는 구조적 긴장을 만들지 않기 때문이다.
        tension = _NONE_AXIS
        reasons.append("ROLE_PROJECTED_AS_NEUTRAL")

    return RoleActivationResult(
        node_id=node_id, canonical_role=canonical_role, role_basis=role_basis,
        operability_status=status, operability_anchor=evaluation.anchor,
        favorable_activation=favorable, adverse_activation=adverse,
        mitigation=mitigation, neutral_activation=neutral, structural_tension=tension,
        # P2-2 근거를 그대로 전달한다. 여기서 다시 감점하거나 중복 계산하지 않는다.
        reason_codes=tuple(dict.fromkeys([*evaluation.reason_codes, *reasons])),
        evidence_ids=evaluation.evidence_ids,
    )
