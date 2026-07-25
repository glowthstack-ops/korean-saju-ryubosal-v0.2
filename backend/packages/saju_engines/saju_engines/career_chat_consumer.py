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

from saju_shared_types.career_consumer import (
    CareerBlockResult,
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

_PROHIBITED_CLAIMS: tuple[str, ...] = (
    "회사가 긍정적으로 보고 있다",
    "곧 오퍼가 온다",
    "합격 가능성이 높다",
    "이직이 성사된다",
    "퇴사하게 된다",
    "입사가 확정된다",
)


def resolve_visibility(*, enabled: bool, beta_expose: bool) -> ConsumerVisibilityDecision:
    """소비 자격을 **직렬화 전에** 확정한다(INV-27)."""
    if not enabled:
        return ConsumerVisibilityDecision.SUPPRESSED
    if not beta_expose:
        return ConsumerVisibilityDecision.INTERNAL_ONLY
    return ConsumerVisibilityDecision.BETA_VISIBLE


def is_eligible_cohort(
    store: CareerEpisodeStore,
    *,
    query_resolution: CareerQueryResolution,
    subject_count: int,
) -> tuple[bool, str | None]:
    """P4-1 최소 cohort 자격. 실패 사유를 함께 돌려준다."""
    if query_resolution is not CareerQueryResolution.GENERAL_CAREER:
        return False, "query_resolution_not_general"
    if subject_count != 1:
        return False, "multi_subject"
    open_eps = [
        e for e in store.episodes
        if e.opportunity.lifecycle_status is not TrackLifecycleStatus.CLOSED
    ]
    if len(open_eps) != 1:
        # 0개·2개 이상이면 일반 흐름 합산을 열지 않고 기존 경로만 쓴다.
        return False, "open_episode_count_not_one"
    return True, None


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
    supporting, blocking = split_factors(vector)
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
    if payload.resolved_episode_id is None:
        return InputAuditAction.BLOCK_NEW_BLOCK, ()
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


def build_block_text(payload: CareerConsumerPayload) -> str:
    """§12-2 고정 5단계 서술(엔진이 뼈대를 만들고 LLM은 문체만 손댄다)."""
    confirmed = [f"{t}/{s}" for t, s, label in payload.confirmed_track_states
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
            f"운의 흐름에서는 {payload.bottleneck} 쪽이 상대적으로 병목으로 보이며, "
            "이것이 특정 회사의 판단이나 합격을 뜻하지는 않습니다."
        )
    else:
        flow = "다음 단계의 상대 활성도를 판단할 근거가 충분하지 않습니다."
    factors = (
        f"보조 요인은 {', '.join(payload.supporting_factors) or '없음'}, "
        f"부담 요인은 {', '.join(payload.blocking_factors) or '없음'}입니다."
    )
    tail = "실제 진행 여부는 연락·면접 일정·서면 통지로 확인해야 합니다."
    return "\n".join([head, meaning, flow, factors, tail])


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
    if not violations:
        return OutputAuditAction.DELIVER, ()
    return OutputAuditAction.REWRITE, tuple(violations)


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
