"""P4-1 chat 소비 파이프라인 — CAREER_TRANSITION_SYSTEM §12.

```
cohort 자격 → visibility → payload → PRE_INPUT_AUDIT → 블록 생성 → LLM
→ claim ledger → POST_OUTPUT_AUDIT → DELIVER | REWRITE | SAFE_FALLBACK | BLOCK
```

**P4-1 최소 cohort만 연다**: `CHAT` + `GENERAL_CAREER` + 단일 본인 + **열린 Episode 정확히
1개** + flag ON. 그 외에는 기존 직업운 경로를 그대로 쓴다(신규 블록 0).

기존 직업운 섹션 축소는 **생성 성공 + 출력 감사 통과 + 최종 응답 실제 포함** 세 조건이
모두 참일 때만 일어난다(INV-29).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_consumer import (
    CareerBlockResult,
    CareerBlockScope,
    CareerConsumerPayload,
    ClaimScope,
    ConsumerClaim,
    ConsumerViolation,
    ConsumerVisibilityDecision,
    InputAuditAction,
    OutputAuditAction,
    StateLabel,
)
from saju_shared_types.career_effect_vector import BottleneckStatus
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    CareerQueryResolution,
    TrackLifecycleStatus,
)

from .career_effect_vector import assess_bottleneck, split_factors

#: 2단 flag — Enabled 는 내부 payload·감사만, Beta expose 가 사용자 노출을 연다.
CAREER_TRANSITION_CHAT_ENABLED = os.getenv(
    "SAJU_CAREER_TRANSITION_CHAT_ENABLED", "false"
).strip().lower() in ("1", "true", "yes")
CAREER_TRANSITION_CHAT_BETA_EXPOSE = os.getenv(
    "SAJU_CAREER_TRANSITION_CHAT_BETA_EXPOSE", "false"
).strip().lower() in ("1", "true", "yes")

#: 출력 금지 표현(§12-2) — 사용자 확인 사실 인용은 별도 예외로 다룬다.
_COMPLETION_OVERCLAIM = re.compile(
    r"(이직이?\s*성사|입사가?\s*확정|합격(이|할)\s*(확정|것)|퇴사하게\s*됩니다"
    r"|곧\s*오퍼가\s*(옵니다|와요|온다))"
)
_COUNTERPARTY_OVERCLAIM = re.compile(
    r"(회사(가|는|도).{0,10}(긍정|좋게|마음에|뽑)|면접관(이|은).{0,10}(좋|평가)"
    r"|채용(이|을)\s*확정|오퍼\s*예정|내부(적으로)?\s*결정(됐|되었))"
)
_FORECAST_AS_FACT = re.compile(r"(확정적으로|틀림없이|반드시)\s*(오퍼|합격|입사|퇴사)")
#: 사실 없는 일반 전망에서 금지 — 진행 중인 절차·특정 회사를 전제하는 표현.
_UNFOUNDED_PROGRESS = re.compile(
    r"(지원(하신|한)\s*(곳|회사)|진행\s*중인\s*(면접|전형|절차)"
    r"|받으신\s*오퍼|그\s*회사|지금\s*다니(시|고)|현재\s*면접)"
)

_PROHIBITED_CLAIMS: tuple[str, ...] = (
    "회사가 긍정적으로 보고 있다",
    "곧 오퍼가 온다",
    "합격 가능성이 높다",
    "이직이 성사된다",
    "퇴사하게 된다",
    "입사가 확정된다",
)


#: 일반 전망에서 추가로 금지되는 주장 — 사실이 없는데 진행 중이라고 말하는 것.
_GENERAL_PROHIBITED_CLAIMS: tuple[str, ...] = (
    "지금 지원한 곳이 있다",
    "면접이 진행 중이다",
    "오퍼를 받은 상태다",
    "이미 정해진 회사가 있다",
    "퇴사가 진행 중이다",
)


def resolve_visibility(*, enabled: bool, beta_expose: bool) -> ConsumerVisibilityDecision:
    """소비 자격을 **직렬화 전에** 확정한다(INV-27)."""
    if not enabled:
        return ConsumerVisibilityDecision.SUPPRESSED
    if not beta_expose:
        return ConsumerVisibilityDecision.INTERNAL_ONLY
    return ConsumerVisibilityDecision.BETA_VISIBLE


def _open_episodes(store: CareerEpisodeStore) -> list:
    return [
        e for e in store.episodes
        if e.opportunity.lifecycle_status is not TrackLifecycleStatus.CLOSED
    ]


def resolve_block_scope(
    store: CareerEpisodeStore,
    *,
    query_resolution: CareerQueryResolution,
    subject_count: int,
) -> tuple[CareerBlockScope, str | None]:
    """서술 범위를 정한다 — 사실 유무로 **무엇을 말할 수 있는지**가 갈린다.

    실제 사용의 상당 부분("이직운 어때?")은 확인된 사실이 없다. 그때 블록을 아예 닫으면
    안전하지만 제품으로는 너무 좁다. 대신 **저장 없는 일반 전망**으로 흐름만 말한다 —
    사실이 없다고 Episode 를 자동 생성하지 않는다.

    ```
    열린 Episode 1개      → 해당 Episode 중심 해석
    0개 + GENERAL_CAREER  → 일시 일반 전망(저장·Episode 생성 없음)
    2개 이상 + 대상 미지정 → 공통 흐름만(회사별 단계·사실 혼합 금지)
    ```
    """
    if query_resolution is not CareerQueryResolution.GENERAL_CAREER:
        return CareerBlockScope.NONE, "query_resolution_not_general"
    if subject_count != 1:
        return CareerBlockScope.NONE, "multi_subject"
    count = len(_open_episodes(store))
    if count == 1:
        return CareerBlockScope.EPISODE_SPECIFIC, None
    if count == 0:
        return CareerBlockScope.GENERAL_FORECAST, None
    return CareerBlockScope.MULTI_EPISODE_OVERVIEW, None


def is_eligible_cohort(
    store: CareerEpisodeStore,
    *,
    query_resolution: CareerQueryResolution,
    subject_count: int,
) -> tuple[bool, str | None]:
    """Episode 확정 서술 자격 — **확인된 사실 기반 단계 서술**에만 쓴다.

    일반 전망 블록은 이 조건을 쓰지 않는다(`resolve_block_scope` 참조).
    """
    scope, reason = resolve_block_scope(
        store, query_resolution=query_resolution, subject_count=subject_count
    )
    if scope is CareerBlockScope.EPISODE_SPECIFIC:
        return True, None
    return False, reason or "open_episode_count_not_one"


def _relative_threshold(vector) -> float:
    """support/blocker 를 가르는 **상대** 기준 — 그 명식 자신의 평균이다.

    절대 0 을 기준으로 하면 축이 대체로 양수인 명식에서 모든 축이 "보조 요인"으로 몰려
    변별력이 사라진다(누구에게나 같은 목록). 어댑터가 넘기는 축 값은 아직 캘리브레이션되지
    않은 상대 지표이므로, 가르는 선도 **자기 자신 대비**로 두는 편이 정직하다.

    평균은 **양수 축만으로** 낸다. 마찰 축은 정의상 음수(막는 힘)라, 함께 평균에 넣으면
    기준선이 끌려 내려가 다시 모든 양수 축이 보조 요인이 된다. 마찰은 기준선과 무관하게
    항상 blocking 으로 남는다.
    """
    values = [v for _axis, v in vector.axes if v > 0.0]
    return sum(values) / len(values) if values else 0.0


def build_general_payload(*, kind, vector, scope: CareerBlockScope) -> CareerConsumerPayload:
    """사실 없는 일반 전망 payload — **확정 단계·Episode 를 만들지 않는다**.

    `resolved_episode_id` 는 None 이고 `confirmed_track_states` 는 비어 있다. 저장도
    하지 않는다(journal 미기록). 진행 중인 절차가 있다고 암시할 근거가 전혀 없으므로,
    말할 수 있는 것은 축의 상대 강약과 병목뿐이다.
    """
    bottleneck = assess_bottleneck(kind, vector)
    supporting, blocking = split_factors(vector, threshold=_relative_threshold(vector))
    not_evaluable = bottleneck.status is BottleneckStatus.NOT_EVALUABLE
    return CareerConsumerPayload(
        query_focus=CareerQueryResolution.GENERAL_CAREER.value,
        resolved_episode_id=None,
        confirmed_track_states=(),
        current_facts=(),
        forecast_stage_candidates=(
            () if not_evaluable
            else ((bottleneck.bottleneck_gate.value, StateLabel.FORECAST),)
            if bottleneck.bottleneck_gate else ()
        ),
        effect_vector=tuple((a.value, v) for a, v in vector.axes),
        bottleneck=None if not_evaluable else (
            bottleneck.bottleneck_gate.value if bottleneck.bottleneck_gate else None
        ),
        bottleneck_not_evaluable=not_evaluable,
        scope=scope,
        blocking_factors=tuple(f.axis.value for f in blocking),
        supporting_factors=tuple(f.axis.value for f in supporting),
        prohibited_claims=_PROHIBITED_CLAIMS + _GENERAL_PROHIBITED_CLAIMS,
    )


def build_payload(
    store: CareerEpisodeStore, *, episode_id: str, kind, vector
) -> CareerConsumerPayload:
    """§12-1 축약본 — confirmed 는 `observed_stages` 기반이며 frontier 가 아니다."""
    episode = store.by_id[episode_id]
    confirmed: list[tuple[str, str, StateLabel]] = []
    for track_state in (episode.opportunity, episode.entry):
        for observed in track_state.observed_stages:
            confirmed.append(
                (observed.stage.track.value, observed.stage.stage.value, StateLabel.CONFIRMED)
            )
    exit_state = store.current_employment.exit_state if store.current_employment else None
    if exit_state is not None:
        for observed in exit_state.observed_stages:
            confirmed.append(
                (observed.stage.track.value, observed.stage.stage.value, StateLabel.CONFIRMED)
            )
    bottleneck = assess_bottleneck(kind, vector)
    supporting, blocking = split_factors(vector, threshold=_relative_threshold(vector))
    not_evaluable = bottleneck.status is BottleneckStatus.NOT_EVALUABLE
    return CareerConsumerPayload(
        query_focus=CareerQueryResolution.GENERAL_CAREER.value,
        resolved_episode_id=episode_id,
        confirmed_track_states=tuple(confirmed),
        current_facts=tuple(f.fact_type for f in store.fact_journal),
        forecast_stage_candidates=(
            () if not_evaluable
            else ((bottleneck.bottleneck_gate.value, StateLabel.FORECAST),)
            if bottleneck.bottleneck_gate else ()
        ),
        effect_vector=tuple((a.value, v) for a, v in vector.axes),
        bottleneck=None if not_evaluable else (
            bottleneck.bottleneck_gate.value if bottleneck.bottleneck_gate else None
        ),
        bottleneck_not_evaluable=not_evaluable,
        scope=CareerBlockScope.EPISODE_SPECIFIC,
        blocking_factors=tuple(f.axis.value for f in blocking),
        supporting_factors=tuple(f.axis.value for f in supporting),
        prohibited_claims=_PROHIBITED_CLAIMS,
    )


def pre_input_audit(
    payload: CareerConsumerPayload, visibility: ConsumerVisibilityDecision
) -> tuple[InputAuditAction, tuple[ConsumerViolation, ...]]:
    """입력 감사 — 실패하면 **필드가 아니라 블록 전체**를 억제한다."""
    if visibility not in {
        ConsumerVisibilityDecision.BETA_VISIBLE, ConsumerVisibilityDecision.LIVE_VISIBLE
    }:
        return InputAuditAction.FALLBACK_TO_LEGACY, (
            ConsumerViolation.CONSUMER_VISIBILITY_VIOLATION,
        )
    if payload.scope is CareerBlockScope.EPISODE_SPECIFIC and (
        payload.resolved_episode_id is None
    ):
        return InputAuditAction.BLOCK_NEW_BLOCK, ()
    if payload.scope is not CareerBlockScope.EPISODE_SPECIFIC and (
        payload.confirmed_track_states or payload.current_facts
    ):
        # 사실 없는 범위인데 확정 단계가 실려 있으면 계약 위반이다.
        return InputAuditAction.BLOCK_NEW_BLOCK, (
            ConsumerViolation.UNFOUNDED_PROGRESS_CLAIM,
        )
    # 다른 Episode 사실 혼입 검사(단일 Episode cohort이므로 교차 자체가 위반).
    bleed = any(
        state[0] not in {"opportunity", "exit", "entry"}
        for state in payload.confirmed_track_states
    )
    if bleed:
        return InputAuditAction.BLOCK_NEW_BLOCK, (
            ConsumerViolation.CROSS_EPISODE_FACT_BLEED,
        )
    return InputAuditAction.ALLOW, ()


#: 축·관문의 사용자 노출 이름 — 영문 enum 값을 그대로 내보내지 않는다.
_AXIS_LABEL: dict[str, str] = {
    "opportunity_activation": "기회·접촉",
    "selection_progress": "평가·선발 진행",
    "agreement_quality": "합의·조건",
    "exit_pressure": "이탈 압력",
    "exit_friction": "퇴사 마찰",
    "entry_realization": "입사·실행",
    "stabilization": "정착",
}
_GATE_LABEL: dict[str, str] = {
    "opportunity": "기회·접촉",
    "selection": "평가·선발",
    "agreement": "합의·조건",
    "exit": "현 직장 정리",
    "entry": "입사·실행",
    "internal_decision": "내부 결정",
    "assignment_execution": "배치 실행",
}


#: 확인된 단계의 사용자 노출 이름.
_STAGE_LABEL: dict[str, str] = {
    "search": "탐색",
    "application": "지원",
    "interview": "면접",
    "offer_received": "오퍼 수령",
    "negotiation": "조건 협의",
    "accepted": "수락",
    "notice_given": "퇴사 통보",
    "handover": "인수인계",
    "separated": "퇴사 완료",
    "joined": "입사",
    "onboarding": "적응",
    "settled": "정착",
}


def _labels(keys: tuple[str, ...], table: dict[str, str]) -> str:
    """노출 이름 목록 — 미등록 키는 원문을 유지한다(조용히 사라지지 않게)."""
    return ", ".join(table.get(k, k) for k in keys)


def build_block_text(payload: CareerConsumerPayload) -> str:
    """§12-2 고정 5단계 서술(엔진이 뼈대를 만들고 LLM은 문체만 손댄다).

    **수치는 내보내지 않는다** — 축 값은 아직 캘리브레이션되지 않은 상대 지표라,
    "0.85" 같은 절대값을 노출하면 성사 확률로 읽힌다(절대원칙 3 단정 금지).
    관문 이름과 상대 순위만 전달한다.
    """
    confirmed = [_STAGE_LABEL.get(s, s) for _t, s, label in payload.confirmed_track_states
                 if label is StateLabel.CONFIRMED]
    head = (
        f"현재 확인된 사실은 {', '.join(confirmed)}까지입니다."
        if confirmed else "현재 확인된 커리어 사실은 없습니다."
    )
    meaning = "절차상 그 단계에 있으며, 이후 단계는 아직 확인된 사실이 아닙니다."
    if payload.bottleneck_not_evaluable:
        flow = "필수 관문을 평가할 근거가 아직 부족해 다음 단계의 상대 활성도는 판단하지 않습니다."
    elif payload.bottleneck:
        flow = (
            f"운의 흐름에서는 {_GATE_LABEL.get(payload.bottleneck, payload.bottleneck)} "
            "쪽이 상대적으로 가장 약한 관문으로 보이며, 이것이 특정 회사의 판단이나 "
            "합격을 뜻하지는 않습니다."
        )
    else:
        flow = "다음 단계의 상대 활성도를 판단할 근거가 충분하지 않습니다."
    strong = _labels(payload.supporting_factors, _AXIS_LABEL) or "없음"
    weak = _labels(payload.blocking_factors, _AXIS_LABEL) or "없음"
    factors = f"상대적으로 힘이 실리는 쪽은 {strong}, 약한 쪽은 {weak}입니다."
    tail = "실제 진행 여부는 연락·면접 일정·서면 통지로 확인해야 합니다."
    return "\n".join([head, meaning, flow, factors, tail])


def build_general_block_text(payload: CareerConsumerPayload) -> str:
    """사실 없는 일반 전망 서술 — 확인된 단계·회사·진행 상황을 말하지 않는다."""
    head = (
        "확인된 지원·면접 사실이 없으므로, 지금 진행 중인 절차가 있다고 전제하지 말 것."
        if payload.scope is CareerBlockScope.GENERAL_FORECAST
        else "여러 건이 함께 진행 중이라 회사별 단계는 섞지 말고 전체 흐름만 말할 것."
    )
    strong = _labels(payload.supporting_factors, _AXIS_LABEL) or "없음"
    weak = _labels(payload.blocking_factors, _AXIS_LABEL) or "없음"
    flow = f"이직 환경에서 상대적으로 힘이 실리는 쪽은 {strong}, 약한 쪽은 {weak}입니다."
    if payload.bottleneck_not_evaluable:
        gate = "관문별 강약을 판단할 근거가 아직 부족합니다."
    elif payload.bottleneck:
        gate = (
            f"관문 중에서는 {_GATE_LABEL.get(payload.bottleneck, payload.bottleneck)} "
            "쪽이 상대적으로 가장 약해 보입니다."
        )
    else:
        gate = "관문별 강약을 판단할 근거가 충분하지 않습니다."
    tail = (
        "실제로 움직이기로 했다면 그때 확인할 것은 조건·처우 합의, 현 직장 정리 일정, "
        "입사 시점의 실행 가능성입니다. 특정 회사·합격 여부는 여기서 말하지 않습니다."
    )
    return "\n".join([head, flow, gate, tail])


def build_claims(payload: CareerConsumerPayload) -> tuple[ConsumerClaim, ...]:
    """claim ledger — 문장별 출처 요구를 기계 검증 가능하게 만든다."""
    claims: list[ConsumerClaim] = []
    for i, (track, stage, _) in enumerate(payload.confirmed_track_states):
        claims.append(
            ConsumerClaim(
                claim_id=f"c{i}", claim_scope=ClaimScope.CONFIRMED_FACT,
                episode_id=payload.resolved_episode_id, track=track, stage=stage,
                source_refs=payload.current_facts,
                visibility_decision=ConsumerVisibilityDecision.BETA_VISIBLE,
            )
        )
    if payload.bottleneck and not payload.bottleneck_not_evaluable:
        claims.append(
            ConsumerClaim(
                claim_id="f0", claim_scope=ClaimScope.FORECAST,
                episode_id=payload.resolved_episode_id, stage=payload.bottleneck,
                source_refs=tuple(a for a, _ in payload.effect_vector),
                visibility_decision=ConsumerVisibilityDecision.BETA_VISIBLE,
            )
        )
    return tuple(claims)


def post_output_audit(
    text: str, claims: tuple[ConsumerClaim, ...], payload: CareerConsumerPayload
) -> tuple[OutputAuditAction, tuple[ConsumerViolation, ...]]:
    """출력 감사 — 감사 전 원문 전달 금지, overclaim 은 fail-closed."""
    violations: list[ConsumerViolation] = []
    if _COMPLETION_OVERCLAIM.search(text):
        violations.append(ConsumerViolation.NARRATIVE_COMPLETION_OVERCLAIM)
    if _COUNTERPARTY_OVERCLAIM.search(text):
        violations.append(ConsumerViolation.COUNTERPARTY_OVERCLAIM)
    if _FORECAST_AS_FACT.search(text):
        violations.append(ConsumerViolation.FACT_FORECAST_LANGUAGE_MIXING)
    # 구조화 값과 서술 불일치 — 병목 판정 불가인데 가능성 언급은 오역이다.
    if payload.bottleneck_not_evaluable and re.search(r"(가능성이?\s*낮|어렵습니다)", text):
        violations.append(ConsumerViolation.STRUCTURED_NARRATIVE_MISMATCH)
    # 출처 없는 상대 의향 claim 금지.
    if any(c.claim_scope is ClaimScope.CONFIRMED_FACT and not c.source_refs for c in claims):
        violations.append(ConsumerViolation.STRUCTURED_NARRATIVE_MISMATCH)
    # 사실이 없는 일반 전망인데 진행 중인 절차가 있는 것처럼 말하면 안 된다.
    if payload.scope is not CareerBlockScope.EPISODE_SPECIFIC and _UNFOUNDED_PROGRESS.search(
        text
    ):
        violations.append(ConsumerViolation.UNFOUNDED_PROGRESS_CLAIM)
    if not violations:
        return OutputAuditAction.DELIVER, ()
    return OutputAuditAction.REWRITE, tuple(violations)


class CareerBlockPreparation(BaseModel):
    """production 훅 1 — prompt 조립 전까지의 결과.

    **LLM을 호출하지 않는다.** 기존 chat 경로의 단일 LLM 호출을 유지하기 위해
    prepare(프롬프트 지시문 생성)와 audit(응답 검사)를 분리한다.
    """

    model_config = ConfigDict(frozen=True)

    eligible: bool = False
    directive: str | None = None
    payload: CareerConsumerPayload | None = None
    claims: tuple[ConsumerClaim, ...] = ()
    input_action: InputAuditAction = InputAuditAction.FALLBACK_TO_LEGACY
    violations: tuple[ConsumerViolation, ...] = ()
    skip_reason: str | None = None


class CareerResponseAudit(BaseModel):
    """production 훅 2 — 기존 단일 응답에 대한 출력 감사 결과."""

    model_config = ConfigDict(frozen=True)

    action: OutputAuditAction = OutputAuditAction.DELIVER
    violations: tuple[ConsumerViolation, ...] = ()

    @property
    def delivered(self) -> bool:
        return self.action is OutputAuditAction.DELIVER

    @property
    def reduce_legacy_section(self) -> bool:
        """기존 직업운 축소 여부 — 전달 확정 시에만 True(INV-29)."""
        return self.delivered


def prepare_career_chat_block(
    store: CareerEpisodeStore,
    *,
    query_resolution: CareerQueryResolution,
    subject_count: int,
    kind,
    vector,
    enabled: bool | None = None,
    beta_expose: bool | None = None,
) -> CareerBlockPreparation:
    """cohort·visibility·payload·PRE_INPUT_AUDIT 까지만 수행한다(LLM 호출 없음)."""
    enabled = CAREER_TRANSITION_CHAT_ENABLED if enabled is None else enabled
    beta_expose = CAREER_TRANSITION_CHAT_BETA_EXPOSE if beta_expose is None else beta_expose
    visibility = resolve_visibility(enabled=enabled, beta_expose=beta_expose)
    if visibility is ConsumerVisibilityDecision.SUPPRESSED:
        return CareerBlockPreparation(skip_reason="flag_off")

    scope, reason = resolve_block_scope(
        store, query_resolution=query_resolution, subject_count=subject_count
    )
    if scope is CareerBlockScope.NONE:
        return CareerBlockPreparation(skip_reason=reason)

    if scope is CareerBlockScope.EPISODE_SPECIFIC:
        episode_id = next(e.episode_id for e in _open_episodes(store))
        payload = build_payload(store, episode_id=episode_id, kind=kind, vector=vector)
    else:
        # 사실 없음·복수 진행 — 저장도 Episode 생성도 하지 않는다(일시 컨텍스트).
        payload = build_general_payload(kind=kind, vector=vector, scope=scope)
    if not payload.effect_vector:
        # 흐름조차 말할 근거가 없으면 기존 경로를 그대로 쓴다(빈 블록 금지).
        return CareerBlockPreparation(payload=payload, skip_reason="no_effect_signal")
    action, violations = pre_input_audit(payload, visibility)
    if action is not InputAuditAction.ALLOW:
        # 필드가 아니라 블록 전체를 억제한다.
        return CareerBlockPreparation(
            payload=payload, input_action=action, violations=violations,
            skip_reason="pre_input_audit",
        )
    directive = (
        build_block_text(payload)
        if payload.scope is CareerBlockScope.EPISODE_SPECIFIC
        else build_general_block_text(payload)
    )
    return CareerBlockPreparation(
        eligible=True, directive=directive, payload=payload,
        claims=build_claims(payload), input_action=action,
    )


def audit_career_chat_response(
    answer: str, preparation: CareerBlockPreparation
) -> CareerResponseAudit:
    """기존 단일 LLM 응답을 검사한다 — 감사 전 원문 전달 금지(INV-28)."""
    if not preparation.eligible or preparation.payload is None:
        return CareerResponseAudit()
    action, violations = post_output_audit(answer, preparation.claims, preparation.payload)
    return CareerResponseAudit(action=action, violations=violations)


def run_career_chat_block(
    store: CareerEpisodeStore,
    *,
    query_resolution: CareerQueryResolution,
    subject_count: int,
    kind,
    vector,
    generate: Callable[[str], str] | None = None,
    enabled: bool | None = None,
    beta_expose: bool | None = None,
    max_rewrites: int = 1,
) -> CareerBlockResult:
    """P4-1 파이프라인 진입점. 자격 미달·감사 실패면 기존 경로로 완전 복귀한다.

    Args:
        generate: LLM 생성기(테스트에서 주입). None이면 엔진 뼈대를 그대로 쓴다.
    """
    enabled = CAREER_TRANSITION_CHAT_ENABLED if enabled is None else enabled
    beta_expose = CAREER_TRANSITION_CHAT_BETA_EXPOSE if beta_expose is None else beta_expose
    visibility = resolve_visibility(enabled=enabled, beta_expose=beta_expose)
    if visibility is ConsumerVisibilityDecision.SUPPRESSED:
        return CareerBlockResult(skip_reason="flag_off")

    ok, reason = is_eligible_cohort(
        store, query_resolution=query_resolution, subject_count=subject_count
    )
    if not ok:
        return CareerBlockResult(skip_reason=reason)

    episode_id = next(
        e.episode_id for e in store.episodes
        if e.opportunity.lifecycle_status is not TrackLifecycleStatus.CLOSED
    )
    payload = build_payload(store, episode_id=episode_id, kind=kind, vector=vector)
    action, violations = pre_input_audit(payload, visibility)
    if action is not InputAuditAction.ALLOW:
        return CareerBlockResult(
            payload=payload, input_action=action, violations=violations,
            skip_reason="pre_input_audit",
        )

    claims = build_claims(payload)
    skeleton = build_block_text(payload)
    text = generate(skeleton) if generate else skeleton
    rewrites = 0
    out_action, out_violations = post_output_audit(text, claims, payload)
    while out_action is OutputAuditAction.REWRITE and rewrites < max_rewrites:
        rewrites += 1
        text = generate(skeleton) if generate else skeleton
        out_action, out_violations = post_output_audit(text, claims, payload)
    if out_action is not OutputAuditAction.DELIVER:
        # 재작성 후에도 실패하면 안전 fallback — 기존 직업운 섹션을 축소하지 않는다.
        return CareerBlockResult(
            payload=payload, claims=claims, input_action=action,
            output_action=OutputAuditAction.SAFE_FALLBACK, violations=out_violations,
            rewrite_count=rewrites, skip_reason="post_output_audit",
        )
    return CareerBlockResult(
        delivered=True, block_text=text, payload=payload, claims=claims,
        input_action=action, output_action=OutputAuditAction.DELIVER,
        rewrite_count=rewrites, legacy_section_reduced=True,
    )


__all__ = [
    "CAREER_TRANSITION_CHAT_BETA_EXPOSE",
    "CareerBlockPreparation",
    "CareerResponseAudit",
    "audit_career_chat_response",
    "prepare_career_chat_block",
    "CAREER_TRANSITION_CHAT_ENABLED",
    "build_block_text",
    "build_claims",
    "build_payload",
    "is_eligible_cohort",
    "post_output_audit",
    "pre_input_audit",
    "resolve_visibility",
    "run_career_chat_block",
]
