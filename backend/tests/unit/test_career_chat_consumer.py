"""P4-1 chat 소비 회귀 — CAREER_TRANSITION_SYSTEM §12.

필수 12 fixture: flag 단계별 동작 · cohort 자격 · 사실/전망 언어 분리 ·
`NOT_EVALUABLE` 오역 금지 · overclaim 차단 · rewrite→fallback · 원자적 소유권 이전.
"""

from __future__ import annotations

from saju_engines.career_chat_consumer import (
    post_output_audit,
    resolve_visibility,
    run_career_chat_block,
)
from saju_engines.career_effect_vector import build_effect_vector
from saju_engines.career_transition_reducer import reduce_career_command
from saju_shared_types.career_commands import (
    ApplyCareerFactCommand,
    CareerFactSource,
    CareerFactType,
    CreateEpisodeCommand,
    FactEvidenceClass,
)
from saju_shared_types.career_consumer import (
    ConsumerViolation,
    ConsumerVisibilityDecision,
    InputAuditAction,
    OutputAuditAction,
    StateLabel,
)
from saju_shared_types.career_effect_vector import (
    ContributionRole,
    EffectAxis,
    EffectContribution,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    CareerQueryResolution,
    CareerTransitionKind,
    FactOperationType,
    FactSourceRef,
)

UC = CareerFactSource.USER_CONFIRMED
GENERAL = CareerQueryResolution.GENERAL_CAREER
KIND = CareerTransitionKind.EXTERNAL_MOVE


def _vector(**axes: float):
    contribs = tuple(
        EffectContribution(
            evidence_id=f"EV{i}", signal_ref=f"SIG{i}", axis=EffectAxis(name),
            value=v, role=ContributionRole.PRIMARY,
        )
        for i, (name, v) in enumerate(axes.items())
    )
    vector, audit = build_effect_vector(contribs)
    assert audit.is_clean and vector is not None
    return vector


def _full_vector():
    return _vector(agreement_quality=0.6, exit_pressure=0.3, entry_realization=0.5)


def _store(*episode_ids: str, facts: tuple[tuple[str, CareerFactType], ...] = ()):
    store = CareerEpisodeStore()
    for i, eid in enumerate(episode_ids):
        store = reduce_career_command(
            store,
            CreateEpisodeCommand(
                command_id=f"mk{i}", episode_id=eid, recorded_at="t0", source_kind=UC
            ),
        ).store
    for j, (eid, ftype) in enumerate(facts):
        store = reduce_career_command(
            store,
            ApplyCareerFactCommand(
                command_id=f"f{j}",
                source_ref=FactSourceRef(
                    source_kind="user_confirmed", source_namespace="chat",
                    source_fact_id=f"sf{j}",
                ),
                source_kind=UC, evidence_class=FactEvidenceClass.OBSERVABLE_HARD_FACT,
                operation_type=FactOperationType.ASSERT, fact_type=ftype,
                recorded_at="t1", target_episode_id=eid,
            ),
        ).store
    return store


def _run(store, **kw):
    params = dict(
        query_resolution=GENERAL, subject_count=1, kind=KIND, vector=_full_vector(),
        enabled=True, beta_expose=True,
    )
    params.update(kw)
    return run_career_chat_block(store, **params)  # type: ignore[arg-type]


# ── 1~2. flag 단계 ─────────────────────────────────────────────────────────


def test_flag_off_produces_no_block() -> None:
    """flag OFF → 신규 블록 0(기존 응답 byte 불변)."""
    r = _run(_store("ep-a"), enabled=False, beta_expose=False)
    assert not r.delivered and r.block_text is None
    assert r.skip_reason == "flag_off"
    assert not r.legacy_section_reduced


def test_enabled_without_expose_keeps_user_output_unchanged() -> None:
    """enabled ON + expose OFF → 내부 감사만, 사용자 출력 불변."""
    r = _run(_store("ep-a"), enabled=True, beta_expose=False)
    assert not r.delivered and r.block_text is None
    assert r.input_action is InputAuditAction.FALLBACK_TO_LEGACY
    assert ConsumerViolation.CONSUMER_VISIBILITY_VIOLATION in r.violations
    assert not r.legacy_section_reduced
    assert resolve_visibility(enabled=True, beta_expose=False) is (
        ConsumerVisibilityDecision.INTERNAL_ONLY
    )


# ── 3~5. cohort 자격 ───────────────────────────────────────────────────────


def test_single_episode_general_career_produces_block() -> None:
    r = _run(_store("ep-a", facts=(("ep-a", CareerFactType.APPLICATION_SUBMITTED),)))
    assert r.delivered and r.block_text
    assert r.payload is not None and r.payload.resolved_episode_id == "ep-a"
    assert r.legacy_section_reduced


def test_multiple_open_episodes_fall_back_to_legacy() -> None:
    r = _run(_store("ep-a", "ep-b"))
    assert not r.delivered
    assert r.skip_reason == "open_episode_count_not_one"
    assert not r.legacy_section_reduced


def test_episode_specific_resolution_is_out_of_this_cohort() -> None:
    """이번 슬라이스는 GENERAL_CAREER만 연다."""
    r = _run(_store("ep-a"), query_resolution=CareerQueryResolution.EPISODE_SPECIFIC_RESOLVED)
    assert not r.delivered
    assert r.skip_reason == "query_resolution_not_general"


# ── 6~7. 사실/전망 언어 분리 ───────────────────────────────────────────────


def test_confirmed_and_forecast_are_labelled_separately() -> None:
    """confirmed APPLICATION + forecast 병목이 서로 다른 표식을 갖는다."""
    r = _run(_store("ep-a", facts=(("ep-a", CareerFactType.APPLICATION_SUBMITTED),)))
    assert r.payload is not None
    assert all(s[2] is StateLabel.CONFIRMED for s in r.payload.confirmed_track_states)
    assert all(f[1] is StateLabel.FORECAST for f in r.payload.forecast_stage_candidates)


def test_confirmed_states_come_from_observed_not_frontier() -> None:
    """frontier 가 JOINED 여도 확정 표현은 observed 기반이다."""
    store = _store("ep-a", facts=(("ep-a", CareerFactType.APPLICATION_SUBMITTED),))
    r = _run(store)
    assert r.payload is not None
    stages = {s[1] for s in r.payload.confirmed_track_states}
    assert stages == {"application"}       # JOINED 를 확정으로 올리지 않는다
    assert "joined" not in (r.block_text or "")


# ── 8. NOT_EVALUABLE 오역 금지 ─────────────────────────────────────────────


def test_not_evaluable_bottleneck_is_not_translated_as_low_chance() -> None:
    partial = _vector(agreement_quality=0.9)   # exit·entry 근거 없음
    r = _run(_store("ep-a"), vector=partial)
    assert r.delivered and r.payload is not None
    assert r.payload.bottleneck_not_evaluable
    assert r.payload.bottleneck is None
    assert "근거가 아직 부족" in (r.block_text or "")
    assert "가능성이 낮" not in (r.block_text or "")


def test_low_chance_wording_on_not_evaluable_is_audited() -> None:
    """구조화 값과 서술이 어긋나면 출력 감사가 잡는다."""
    partial = _vector(agreement_quality=0.9)
    r = _run(_store("ep-a"), vector=partial, generate=lambda _: "진행 가능성이 낮습니다.")
    assert not r.delivered
    assert ConsumerViolation.STRUCTURED_NARRATIVE_MISMATCH in r.violations


# ── 9~11. overclaim 차단 · rewrite · fallback ──────────────────────────────


def test_counterparty_overclaim_is_blocked() -> None:
    r = _run(_store("ep-a"), generate=lambda _: "회사가 긍정적으로 보고 있습니다.")
    assert not r.delivered
    assert ConsumerViolation.COUNTERPARTY_OVERCLAIM in r.violations
    assert r.output_action is OutputAuditAction.SAFE_FALLBACK


def test_completion_overclaim_triggers_rewrite_then_passes() -> None:
    """1회 재작성 후 통과하면 전달된다."""
    calls = {"n": 0}

    def gen(skeleton: str) -> str:
        calls["n"] += 1
        return "이직이 성사됩니다." if calls["n"] == 1 else skeleton

    r = _run(_store("ep-a"), generate=gen)
    assert r.rewrite_count == 1
    assert r.delivered and r.output_action is OutputAuditAction.DELIVER


def test_rewrite_failure_falls_back_safely() -> None:
    """재작성 후에도 실패하면 안전 fallback."""
    r = _run(_store("ep-a"), generate=lambda _: "곧 오퍼가 옵니다.")
    assert not r.delivered
    assert r.rewrite_count == 1
    assert r.output_action is OutputAuditAction.SAFE_FALLBACK
    assert ConsumerViolation.NARRATIVE_COMPLETION_OVERCLAIM in r.violations


# ── 12. 원자적 소유권 이전 ─────────────────────────────────────────────────


def test_legacy_section_is_not_reduced_when_block_fails() -> None:
    """신규 블록이 실패한 모든 경로에서 기존 직업운 축소는 일어나지 않는다(INV-29)."""
    failures = [
        _run(_store("ep-a"), enabled=False),                              # flag OFF
        _run(_store("ep-a"), beta_expose=False),                          # expose OFF
        _run(_store("ep-a", "ep-b")),                                     # cohort 미충족
        _run(_store("ep-a"), generate=lambda _: "곧 오퍼가 옵니다."),        # 출력 감사 실패
    ]
    for r in failures:
        assert not r.delivered
        assert not r.legacy_section_reduced
        assert r.block_text is None


def test_legacy_section_reduced_only_on_delivered_block() -> None:
    r = _run(_store("ep-a", facts=(("ep-a", CareerFactType.INTERVIEW_COMPLETED),)))
    assert r.delivered and r.legacy_section_reduced


# ── 감사 단위 ──────────────────────────────────────────────────────────────


def test_user_confirmed_official_notice_is_not_counterparty_overclaim() -> None:
    """사용자가 서면 통지를 받았다고 확인한 사실을 그대로 말하는 것은 위반이 아니다."""
    r = _run(_store("ep-a", facts=(("ep-a", CareerFactType.WRITTEN_OFFER_RECEIVED),)))
    assert r.delivered
    assert ConsumerViolation.COUNTERPARTY_OVERCLAIM not in r.violations


def test_prohibited_claims_are_carried_in_payload() -> None:
    r = _run(_store("ep-a"))
    assert r.payload is not None
    assert "곧 오퍼가 온다" in r.payload.prohibited_claims


def test_claims_require_sources_for_confirmed_facts() -> None:
    """CONFIRMED_FACT claim 은 출처를 반드시 갖는다."""
    r = _run(_store("ep-a", facts=(("ep-a", CareerFactType.APPLICATION_SUBMITTED),)))
    assert r.delivered
    confirmed = [c for c in r.claims if c.claim_scope.value == "confirmed_fact"]
    assert confirmed and all(c.source_refs for c in confirmed)


def test_post_output_audit_detects_forecast_stated_as_fact() -> None:
    payload_r = _run(_store("ep-a"))
    assert payload_r.payload is not None
    action, violations = post_output_audit(
        "반드시 오퍼가 옵니다.", payload_r.claims, payload_r.payload
    )
    assert action is OutputAuditAction.REWRITE
    assert ConsumerViolation.FACT_FORECAST_LANGUAGE_MIXING in violations
