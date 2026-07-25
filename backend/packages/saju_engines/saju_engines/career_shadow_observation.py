"""예측 스냅샷 · shadow 관측 side-channel (P0-B 스캐폴드).

§14-5·INV-23: 현실 레이블만으로는 **어느 예측과 비교할지** 알 수 없으므로 예측 시점의
상태를 불변 스냅샷으로 남긴다. 스냅샷은 생성 후 변경되지 않으며, **현재 모델로 재계산한
값을 과거 예측처럼 쓰지 않는다**(`prediction_snapshot_mutation` = 0 허용 지표).

§15-0: 관측 envelope는 지표 분류(`MetricClass`)와 관측 종류(`ObservationKind`)·가드 결과
(`GuardOutcome`)를 **분리**한다 — 안전장치의 정상 작동을 오류로 집계하지 않기 위함
(INV-24).

**P0-B 범위 — side-channel 전용**:
- authoritative store·DB writer를 포함하지 않는다(권위 상태 변경 0).
- 사용자 응답 경로에 배선되지 않는다.
- 컬렉션은 tuple로 두어 실제 불변을 보장한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_transition import (
    CAREER_CONTRACT_VERSION,
    CareerStageRef,
    CareerTrack,
)
from saju_shared_types.event_semantics import SEMANTICS_CONTRACT_VERSION


class MetricClass(StrEnum):
    """지표 분류(§15-0)."""

    SAFETY_OVERCLAIM = "safety_overclaim"
    STATE_INTEGRITY = "state_integrity"
    MODEL_QUALITY = "model_quality"


class ObservationKind(StrEnum):
    """관측 종류 — 지표 측정과 텔레메트리·감사 이벤트를 섞지 않는다."""

    METRIC_MEASUREMENT = "metric_measurement"
    ROLLOUT_TELEMETRY = "rollout_telemetry"
    AUDIT_EVENT = "audit_event"


class GuardOutcome(StrEnum):
    """가드 결과 — `BLOCKED`·`ROLLED_BACK` + 권위 상태 불변은 **보호 성공**이다(INV-24)."""

    NOT_APPLICABLE = "not_applicable"
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ROLLED_BACK = "rolled_back"
    VIOLATION = "violation"


class ObservationContext(StrEnum):
    """관측 맥락 — 의도된 fixture와 실제 트래픽 결함을 구분한다(§15-0)."""

    FIXTURE = "fixture"
    GOLDEN_CORPUS = "golden_corpus"
    SHADOW_TRAFFIC = "shadow_traffic"
    CANARY = "canary"
    BETA = "beta"
    LIVE = "live"


class PredictionSnapshot(BaseModel):
    """불변 예측 스냅샷 — 생성 후 어떤 필드도 변경되지 않는다(INV-23).

    현실 캘리브레이션은 이 스냅샷과 비교하며, 현재 모델 재계산값으로 대체하지 않는다.
    """

    model_config = ConfigDict(frozen=True)

    prediction_snapshot_id: str
    created_at: str
    producer_build_sha: str
    contract_version: str = CAREER_CONTRACT_VERSION
    semantics_contract_version: str = SEMANTICS_CONTRACT_VERSION
    config_snapshot_hash: str | None = None
    episode_id: str | None = None
    track: CareerTrack | None = None
    target_stage: CareerStageRef | None = None
    forecast_window: tuple[str | None, str | None] = (None, None)
    #: 단계 벡터·병목은 P2에서 채운다 — P0-B는 자리 예약(불변 tuple).
    stage_vector: tuple[tuple[str, float], ...] = ()
    bottleneck: str | None = None
    evidence_refs: tuple[str, ...] = ()


class ShadowObservation(BaseModel):
    """shadow 관측 1건 — §15-0 공통 envelope.

    `observation_id`가 안정적으로 생성되면 그것이 기본 멱등 키다(재시도·중복 전송 시
    지표 이중 증가 방지).
    """

    model_config = ConfigDict(frozen=True)

    observation_id: str
    metric_name: str
    metric_class: MetricClass
    observation_kind: ObservationKind
    guard_outcome: GuardOutcome = GuardOutcome.NOT_APPLICABLE
    expected_guard_outcome: GuardOutcome | None = None
    observation_context: ObservationContext = ObservationContext.FIXTURE
    episode_id_hash: str | None = None
    track: CareerTrack | None = None
    stage: CareerStageRef | None = None
    contract_version: str = CAREER_CONTRACT_VERSION
    model_version: str | None = None
    resolution_source: str | None = None
    run_id: str | None = None
    request_id: str | None = None
    build_sha: str | None = None
    config_snapshot_hash: str | None = None
    input_digest: str | None = None
    observed_at: str | None = None
    audit_event: str | None = None
    denominator_eligibility: bool = True
    prediction_snapshot_id: str | None = None

    @property
    def is_violation(self) -> bool:
        """위반 여부 — 정상 가드 작동은 위반이 아니다(INV-24).

        차단 뒤에도 권위 상태가 변경된 경우는 호출자가 별도로 판정해 `VIOLATION`으로
        기록한다(이 속성은 envelope 값만 본다).
        """
        return self.guard_outcome is GuardOutcome.VIOLATION


__all__ = [
    "GuardOutcome",
    "MetricClass",
    "ObservationContext",
    "ObservationKind",
    "PredictionSnapshot",
    "ShadowObservation",
]
