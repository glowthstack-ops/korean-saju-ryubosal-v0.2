"""단계별 효과 벡터·병목 계약 — P2 (CAREER_TRANSITION_SYSTEM §4·§9).

기존 `activation`/`favorability`는 **상위 요약값으로만** 유지하고, 출력·전이는 단계 벡터를
쓴다(INV-3). 단계별로 상반된 결과("합격은 원활, 처우는 불리")를 평균으로 뭉개지 않기 위함.

**핵심 절대 게이트 — `double_contribution`(INV-11)**: 한 원천 신호는 **하나의 축에만
1차 기여**한다. `process_activation` 같은 파생 요약값을 다시 원천 기여로 합산하거나,
legacy 점수와 신규 adapter 점수를 동시에 가산하면 위반이다.

**P2 범위**: shadow side-channel 전용. 기존 점수·랭킹·직렬화·권위 상태·LLM/report
payload를 바꾸지 않으며 production에서 import되지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from .career_transition import CareerTrack, CareerTransitionKind

#: 효과 벡터 계약 버전.
EFFECT_VECTOR_CONTRACT_VERSION = "career-effect.v1"


class EffectAxis(StrEnum):
    """단계별 효과 축(§4 산출 책임표) — 트랙마다 소유 축이 다르다."""

    OPPORTUNITY_ACTIVATION = "opportunity_activation"  # A: 기회·접촉 형성
    SELECTION_PROGRESS = "selection_progress"          # A: 서류·면접 절차 진행
    AGREEMENT_QUALITY = "agreement_quality"            # A 후반: 합의 안정도
    EXIT_PRESSURE = "exit_pressure"                    # B: 이탈 압력
    EXIT_FRICTION = "exit_friction"                    # B: 통보·인수인계 마찰
    ENTRY_REALIZATION = "entry_realization"            # C: 실제 입사 현실화
    STABILIZATION = "stabilization"                    # C: 수습·역할 정착


#: 축 → 소유 트랙. 한 축은 정확히 한 트랙이 소유한다.
AXIS_TRACK: Mapping[EffectAxis, CareerTrack] = MappingProxyType(
    {
        EffectAxis.OPPORTUNITY_ACTIVATION: CareerTrack.OPPORTUNITY,
        EffectAxis.SELECTION_PROGRESS: CareerTrack.OPPORTUNITY,
        EffectAxis.AGREEMENT_QUALITY: CareerTrack.OPPORTUNITY,
        EffectAxis.EXIT_PRESSURE: CareerTrack.EXIT,
        EffectAxis.EXIT_FRICTION: CareerTrack.EXIT,
        EffectAxis.ENTRY_REALIZATION: CareerTrack.ENTRY,
        EffectAxis.STABILIZATION: CareerTrack.ENTRY,
    }
)


class ContributionRole(StrEnum):
    """기여 역할 — `DERIVED`는 **가산 대상이 아니다**(파생 요약값의 재합산 금지)."""

    PRIMARY = "primary"
    DERIVED = "derived"


class EffectContribution(BaseModel):
    """축 1개에 대한 기여 1건 — `double_contribution` 감사의 단위.

    중복 식별 키(§15-3): `prediction_snapshot_id + candidate_id + period +
    evidence_id + axis + contribution_role`.
    """

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    signal_ref: str            # 원천 신호(여러 evidence_id가 공유 가능)
    axis: EffectAxis
    role: ContributionRole = ContributionRole.PRIMARY
    value: float = 0.0
    prediction_snapshot_id: str | None = None
    candidate_id: str | None = None
    period: str | None = None

    @property
    def dedup_key(self) -> tuple[str | None, str | None, str | None, str, str, str]:
        return (
            self.prediction_snapshot_id,
            self.candidate_id,
            self.period,
            self.evidence_id,
            self.axis.value,
            self.role.value,
        )


class CareerEffectVector(BaseModel):
    """단계별 효과 벡터(shadow).

    `activation`/`favorability`는 여기 담지 않는다 — 기존 상위 요약값은 엔진이 그대로
    소유하며 이 벡터가 대체하지 않는다(INV-3).
    """

    model_config = ConfigDict(frozen=True)

    axes: tuple[tuple[EffectAxis, float], ...] = ()
    contributions: tuple[EffectContribution, ...] = ()
    contract_version: str = EFFECT_VECTOR_CONTRACT_VERSION

    @property
    def by_axis(self) -> Mapping[EffectAxis, float]:
        """축 → 값(읽기 전용 파생)."""
        return MappingProxyType(dict(self.axes))

    @property
    def process_activation(self) -> float:
        """단계 벡터의 **파생 요약값** — 독립 가점원이 아니다(§10 예약 결정).

        기여로 다시 합산하면 `double_contribution` 위반이다.
        """
        values = [v for _, v in self.axes]
        return sum(values) / len(values) if values else 0.0


class FactorKind(StrEnum):
    """서술용 요인 종류."""

    SUPPORTING = "supporting"
    BLOCKING = "blocking"


class CareerFactor(BaseModel):
    """support/blocker 1건 — 서술 보조이며 점수를 만들지 않는다."""

    model_config = ConfigDict(frozen=True)

    kind: FactorKind
    axis: EffectAxis
    signal_ref: str
    note: str | None = None


# ── 병목 성사도 (§9) ───────────────────────────────────────────────────────


class CareerGate(StrEnum):
    """Kind별 필수 관문."""

    OPPORTUNITY = "opportunity"
    SELECTION = "selection"
    AGREEMENT = "agreement"
    EXIT = "exit"
    ENTRY = "entry"
    INTERNAL_DECISION = "internal_decision"
    ASSIGNMENT_EXECUTION = "assignment_execution"


#: Kind → 필수 관문(§9). 전역 고정 공식이 아니라 Kind별 병목이다 — 퇴사 단독·무직 취업·
#: 내부 전보가 exit/entry 부재로 영원히 미완료가 되지 않도록 한다(INV-4).
REQUIRED_GATES: Mapping[CareerTransitionKind, tuple[CareerGate, ...]] = MappingProxyType(
    {
        CareerTransitionKind.EXTERNAL_MOVE: (
            CareerGate.AGREEMENT, CareerGate.EXIT, CareerGate.ENTRY,
        ),
        CareerTransitionKind.JOB_GAIN_FROM_UNEMPLOYED: (
            CareerGate.SELECTION, CareerGate.AGREEMENT, CareerGate.ENTRY,
        ),
        CareerTransitionKind.RESIGNATION_ONLY: (CareerGate.EXIT,),
        CareerTransitionKind.INTERNAL_TRANSFER: (
            CareerGate.INTERNAL_DECISION, CareerGate.ASSIGNMENT_EXECUTION,
        ),
    }
)

#: 관문 → 여건을 읽어올 축.
GATE_AXIS: Mapping[CareerGate, EffectAxis] = MappingProxyType(
    {
        CareerGate.OPPORTUNITY: EffectAxis.OPPORTUNITY_ACTIVATION,
        CareerGate.SELECTION: EffectAxis.SELECTION_PROGRESS,
        CareerGate.AGREEMENT: EffectAxis.AGREEMENT_QUALITY,
        CareerGate.EXIT: EffectAxis.EXIT_PRESSURE,
        CareerGate.ENTRY: EffectAxis.ENTRY_REALIZATION,
        CareerGate.INTERNAL_DECISION: EffectAxis.AGREEMENT_QUALITY,
        CareerGate.ASSIGNMENT_EXECUTION: EffectAxis.ENTRY_REALIZATION,
    }
)


class BottleneckStatus(StrEnum):
    """병목 판정 가능 여부 — 근거 없는 축을 0이나 1로 추정하지 않는다."""

    EVALUABLE = "evaluable"
    NOT_EVALUABLE = "not_evaluable"   # 필수 관문의 축 기여가 없음


class GateReadiness(BaseModel):
    """관문 1개의 여건. `readiness=None`은 **근거 없음**이며 0이 아니다."""

    model_config = ConfigDict(frozen=True)

    gate: CareerGate
    axis: EffectAxis
    readiness: float | None = None


class BottleneckAssessment(BaseModel):
    """병목 판정 — **예측 여건만** 산출한다.

    `forecast_completion_readiness`는 실제 완료(`realization_status`)를 생성하거나
    취소하지 않는다(INV-15). 초기 단계의 높은 값이 후속 미성립을 덮지 못하도록 합산이
    아니라 병목을 쓴다(INV-4).
    """

    model_config = ConfigDict(frozen=True)

    kind: CareerTransitionKind
    status: BottleneckStatus = BottleneckStatus.NOT_EVALUABLE
    gate_readiness: tuple[GateReadiness, ...] = ()
    missing_gates: tuple[CareerGate, ...] = ()
    bottleneck_gate: CareerGate | None = None
    forecast_completion_readiness: float | None = None


__all__ = [
    "AXIS_TRACK",
    "EFFECT_VECTOR_CONTRACT_VERSION",
    "GATE_AXIS",
    "REQUIRED_GATES",
    "BottleneckAssessment",
    "BottleneckStatus",
    "CareerEffectVector",
    "CareerFactor",
    "CareerGate",
    "ContributionRole",
    "EffectAxis",
    "EffectContribution",
    "FactorKind",
    "GateReadiness",
]
