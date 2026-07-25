"""단계 벡터·병목·support/blocker 산출 — P2 (CAREER_TRANSITION_SYSTEM §4·§9·§15).

순수 함수 모음이며 shadow side-channel 전용이다. 기존 점수·랭킹·직렬화·권위 상태를
읽기만 하고 바꾸지 않는다.

핵심 게이트는 **`double_contribution`**(INV-11): 한 원천 신호는 하나의 축에만 1차
기여하며, 파생 요약값(`process_activation`)이나 legacy 점수를 다시 가산하지 않는다.
위반은 값을 만들지 않고 **감사 결과로 보고**한다(조용한 합산 금지).
"""

from __future__ import annotations

from saju_shared_types.career_effect_vector import (
    GATE_AXIS,
    REQUIRED_GATES,
    BottleneckAssessment,
    BottleneckStatus,
    CareerEffectVector,
    CareerFactor,
    CareerGate,
    ContributionRole,
    EffectAxis,
    EffectContribution,
    FactorKind,
    GateReadiness,
)
from saju_shared_types.career_transition import CareerTransitionKind


class ContributionAudit:
    """기여값 감사 결과 — 위반이 있으면 벡터를 만들지 않는다."""

    __slots__ = ("duplicates", "derived_as_primary", "legacy_mixed")

    def __init__(
        self,
        duplicates: tuple[tuple[str, str], ...] = (),
        derived_as_primary: tuple[str, ...] = (),
        legacy_mixed: tuple[str, ...] = (),
    ) -> None:
        self.duplicates = duplicates
        self.derived_as_primary = derived_as_primary
        self.legacy_mixed = legacy_mixed

    @property
    def is_clean(self) -> bool:
        return not (self.duplicates or self.derived_as_primary or self.legacy_mixed)

    def __repr__(self) -> str:  # pragma: no cover - 디버그 표시
        return (
            f"ContributionAudit(dup={self.duplicates}, "
            f"derived={self.derived_as_primary}, legacy={self.legacy_mixed})"
        )


def audit_contributions(
    contributions: tuple[EffectContribution, ...],
    *,
    legacy_scored_evidence_ids: frozenset[str] = frozenset(),
) -> ContributionAudit:
    """`double_contribution` 감사(INV-11).

    위반 3종:
    - 같은 `evidence_id`가 **같은 축에 중복 가산**
    - `DERIVED` 기여가 1차 가산에 섞임(파생 요약값 재합산)
    - legacy 점수에 이미 반영된 evidence가 신규 adapter에서도 가산

    같은 `signal_ref`가 **서로 다른 evidence_id로 서로 다른 축**에 기여하는 것은 허용된다.
    """
    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    derived: list[str] = []
    legacy: list[str] = []
    for c in contributions:
        if c.role is ContributionRole.DERIVED:
            derived.append(c.evidence_id)
            continue
        key = (c.evidence_id, c.axis.value)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
        if c.evidence_id in legacy_scored_evidence_ids:
            legacy.append(c.evidence_id)
    return ContributionAudit(tuple(duplicates), tuple(derived), tuple(legacy))


def build_effect_vector(
    contributions: tuple[EffectContribution, ...],
    *,
    legacy_scored_evidence_ids: frozenset[str] = frozenset(),
) -> tuple[CareerEffectVector | None, ContributionAudit]:
    """단계 벡터를 만든다. 감사가 깨끗할 때만 벡터를 반환한다(fail-closed).

    Returns:
        `(vector, audit)` — 위반이 있으면 `vector`는 None이다. 위반을 무시하고 값을
        만들면 이중 가산이 조용히 반영되므로 만들지 않는다.
    """
    audit = audit_contributions(
        contributions, legacy_scored_evidence_ids=legacy_scored_evidence_ids
    )
    if not audit.is_clean:
        return None, audit
    totals: dict[EffectAxis, float] = {}
    for c in contributions:
        if c.role is ContributionRole.DERIVED:
            continue
        totals[c.axis] = totals.get(c.axis, 0.0) + c.value
    axes = tuple(sorted(totals.items(), key=lambda kv: kv[0].value))
    return CareerEffectVector(axes=axes, contributions=contributions), audit


def assess_bottleneck(
    kind: CareerTransitionKind, vector: CareerEffectVector
) -> BottleneckAssessment:
    """Kind별 필수 관문의 **병목**으로 예측 여건을 산출한다(§9·INV-4).

    합산이 아니라 최솟값을 쓰므로 초기 단계의 높은 값이 후속 미성립을 덮지 못한다.
    실제 완료(`realization_status`)는 생성하지 않는다(INV-15).
    """
    gates = REQUIRED_GATES[kind]
    by_axis = vector.by_axis
    readiness = tuple(
        GateReadiness(gate=g, axis=GATE_AXIS[g], readiness=by_axis.get(GATE_AXIS[g]))
        for g in gates
    )
    missing = tuple(r.gate for r in readiness if r.readiness is None)
    if missing or not readiness:
        # 근거 없는 관문을 0이나 1로 추정하지 않는다 — 판정 불가로 남긴다.
        return BottleneckAssessment(
            kind=kind,
            status=BottleneckStatus.NOT_EVALUABLE,
            gate_readiness=readiness,
            missing_gates=missing,
        )
    worst = min(readiness, key=lambda r: r.readiness if r.readiness is not None else 0.0)
    return BottleneckAssessment(
        kind=kind,
        status=BottleneckStatus.EVALUABLE,
        gate_readiness=readiness,
        bottleneck_gate=worst.gate,
        forecast_completion_readiness=worst.readiness,
    )


def split_factors(
    vector: CareerEffectVector, *, threshold: float = 0.0
) -> tuple[tuple[CareerFactor, ...], tuple[CareerFactor, ...]]:
    """축 기여를 support/blocker로 나눈다 — **서술 보조이며 점수를 만들지 않는다**.

    Returns:
        `(supporting, blocking)`.
    """
    supporting: list[CareerFactor] = []
    blocking: list[CareerFactor] = []
    for c in vector.contributions:
        if c.role is ContributionRole.DERIVED:
            continue
        factor = CareerFactor(
            kind=FactorKind.SUPPORTING if c.value > threshold else FactorKind.BLOCKING,
            axis=c.axis,
            signal_ref=c.signal_ref,
        )
        (supporting if c.value > threshold else blocking).append(factor)
    return tuple(supporting), tuple(blocking)


__all__ = [
    "CareerGate",
    "ContributionAudit",
    "assess_bottleneck",
    "audit_contributions",
    "build_effect_vector",
    "split_factors",
]
