"""P3 사용자 사실 상속 runtime shadow — CAREER_TRANSITION_SYSTEM §7·§12·§15.

```
parse → 증거 자격 판정 → Episode 해소 → CareerCommand 생성 → P1 reducer → shadow 관측
```

**P3 경계**: 실제 대화 입력을 읽더라도 결과를 다음에 반영하지 않는다 —
`ConversationState` 권위 필드 · 기존 `user_facts` · 기존 EventCandidate 점수 ·
LLM 입력 · report 입력 · 사용자 응답. 상태는 **shadow namespace 전용 store**에만 쌓인다.

Episode 해소는 P1 계약 그대로다: 명시 대상 → 정정 대상 소유 Episode →
ASSERT 한정 유일 open → 나머지 `EPISODE_UNRESOLVED`(추측 금지).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerFactSource,
    RejectionCode,
    TransitionResult,
    TransitionStatus,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    FactSourceRef,
)

from .career_fact_parser import CareerParsedFact, parse_career_fact
from .career_shadow_metrics import observe_career_transition
from .career_shadow_observation import ObservationContext, ShadowObservation
from .career_transition_reducer import reduce_career_command

#: shadow 전용 namespace — production 사실 원장과 섞이지 않는다.
SHADOW_NAMESPACE = "career_shadow"


class CareerShadowRunResult(BaseModel):
    """shadow 실행 1건의 결과 — 권위 상태에 반영되지 않는다."""

    model_config = ConfigDict(frozen=True)

    parsed: CareerParsedFact
    applied: bool = False
    result: TransitionResult | None = None
    observations: tuple[ShadowObservation, ...] = ()
    skip_reason: str | None = None

    @property
    def blocked_as_not_authoritative(self) -> bool:
        """증거 자격 미달로 전이가 차단됐는지 — 정상 차단이며 위반이 아니다."""
        return self.skip_reason == "not_transition_eligible" or (
            self.result is not None
            and self.result.rejection_code is RejectionCode.FACT_NOT_AUTHORITATIVE
        )


def run_career_state_shadow(
    conversation_text: str,
    shadow_store: CareerEpisodeStore,
    *,
    command_id: str,
    source_fact_id: str,
    recorded_at: str,
    target_episode_id: str | None = None,
    occurred_at: str | None = None,
    context: ObservationContext = ObservationContext.SHADOW_TRAFFIC,
) -> CareerShadowRunResult:
    """대화 발화 1건을 shadow 상태 머신에 흘린다(순수 함수).

    전이 자격이 없으면 reducer를 호출하지 않고 `skip_reason`만 남긴다 — 추측·전망이
    권위 경로에 닿지 않게 하기 위함(INV-18).
    """
    parsed = parse_career_fact(conversation_text)
    if not parsed.is_transition_eligible:
        return CareerShadowRunResult(parsed=parsed, skip_reason="not_transition_eligible")

    assert parsed.fact_type is not None  # is_transition_eligible 이 보장
    command = ApplyCareerFactCommand(
        command_id=command_id,
        source_ref=FactSourceRef(
            source_kind=CareerFactSource.USER_CONFIRMED.value,
            source_namespace=SHADOW_NAMESPACE,
            source_fact_id=source_fact_id,
        ),
        source_kind=CareerFactSource.USER_CONFIRMED,
        evidence_class=parsed.evidence_class,
        operation_type=parsed.operation_type,
        fact_type=parsed.fact_type,
        recorded_at=recorded_at,
        occurred_at=occurred_at,
        target_episode_id=target_episode_id or parsed.episode_target_hint,
    )
    result = reduce_career_command(shadow_store, command)
    observations = observe_career_transition(shadow_store, command, result, context)
    return CareerShadowRunResult(
        parsed=parsed,
        applied=result.status
        in {TransitionStatus.APPLIED, TransitionStatus.APPLIED_NO_STATE_CHANGE},
        result=result,
        observations=observations,
    )


__all__ = ["SHADOW_NAMESPACE", "CareerShadowRunResult", "run_career_state_shadow"]
