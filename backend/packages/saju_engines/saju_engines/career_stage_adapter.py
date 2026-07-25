"""CareerStageAdapter — 단계 투영 어댑터 **인터페이스** (P0-B 스캐폴드).

`PredictionEngines`의 범용 단계 모델(awareness→exploration→action→decision→completion)은
이직에 그대로 노출하기엔 추상적이다(`action`이 지원인지 면접인지 퇴사 통보인지 불명확).
따라서 그것을 **시간창·진행도 계산 코어로만** 재사용하고, 그 위에 트랙별 커리어 단계로
번역하는 어댑터를 둔다.

**P0-B 범위 — 인터페이스만**:
- 구현체·singleton·registry 등록을 만들지 않는다.
- `EventEngineV2`·service 계층을 import하지 않으며, production 경로에서 호출되지 않는다.
- silent no-op 구현체를 두지 않는다 — 실수로 배선돼도 "후보 없음"처럼 보이면 안 되므로
  `NotImplementedError`로 실패한다.

`PredictionEngines`는 **재사용 확정 자산이 아니라 이 어댑터 뒤에서 shadow 적합성을
검증할 대상**이다(INV-9·§17 ③).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_transition import CareerStageRef, CareerTrack


class CareerStageProjection(BaseModel):
    """단계 투영 결과(shadow) — 권위 상태가 아니다.

    엔진 신호를 트랙·단계 공간으로 투영한 **전망**이며, 사용자의 지원·오퍼·퇴사·입사
    사실을 생성하지 않는다(INV-18). 실제 효과 벡터·병목은 P2에서 채운다.
    """

    model_config = ConfigDict(frozen=True)

    track: CareerTrack
    forecast_stage: CareerStageRef | None = None
    #: 단계 벡터·병목은 P2 범위 — P0-B에서는 자리만 예약한다(값 없음).
    notes: tuple[str, ...] = ()


class CareerStageAdapter(ABC):
    """엔진 신호 → 커리어 단계 투영 어댑터.

    P0-B에서는 구현체를 만들지 않는다. 하위 클래스가 생기더라도 production 배선은
    §16 승격 게이트를 통과한 뒤에만 허용된다.
    """

    @abstractmethod
    def project(self, track: CareerTrack) -> CareerStageProjection:
        """트랙 1개의 단계 투영을 산출한다(shadow 전용).

        Raises:
            NotImplementedError: P0-B에는 구현체가 없다.
        """
        raise NotImplementedError


__all__ = ["CareerStageAdapter", "CareerStageProjection"]
