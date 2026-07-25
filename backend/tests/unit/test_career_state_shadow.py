"""P3 사실 상속 runtime shadow 회귀 — CAREER_TRANSITION_SYSTEM §7·§12·§15.

우선순위: 필수 현실 사실 10종 → Episode 안전성 → 과장 방지.
정상 차단(`EPISODE_UNRESOLVED`·자격 미달·멱등)은 위반이 아니라 telemetry다.
"""

from __future__ import annotations

from saju_engines.career_fact_parser import parse_career_fact
from saju_engines.career_state_shadow import (
    SHADOW_NAMESPACE,
    run_career_state_shadow,
)
from saju_engines.career_transition_reducer import reduce_career_command
from saju_shared_types.career_commands import (
    CareerFactSource,
    CareerFactType,
    CreateEpisodeCommand,
    FactEvidenceClass,
    RejectionCode,
)
from saju_shared_types.career_transition import (
    CareerEpisodeStore,
    EntryStage,
    ExitStage,
    OpportunityStage,
)

UC = CareerFactSource.USER_CONFIRMED
_N = 0


def _store(*episode_ids: str) -> CareerEpisodeStore:
    store = CareerEpisodeStore()
    for i, eid in enumerate(episode_ids):
        r = reduce_career_command(
            store,
            CreateEpisodeCommand(
                command_id=f"mk{i}", episode_id=eid, recorded_at="t0", source_kind=UC
            ),
        )
        store = r.store
    return store


def _run(text: str, store: CareerEpisodeStore, *, episode: str | None = None):
    global _N
    _N += 1
    return run_career_state_shadow(
        text, store, command_id=f"cmd{_N}", source_fact_id=f"sf{_N}",
        recorded_at="t1", target_episode_id=episode,
    )


# ── 필수 현실 사실 10종 ────────────────────────────────────────────────────


def test_application_submitted() -> None:
    r = _run("A사 지원서를 냈다", _store("ep-a"), episode="ep-a")
    assert r.applied and r.result is not None
    ep = r.result.store.by_id["ep-a"]
    assert ep.opportunity.frontier_stage is not None
    assert ep.opportunity.frontier_stage.stage is OpportunityStage.APPLICATION


def test_interview_completed() -> None:
    r = _run("어제 면접을 봤다", _store("ep-a"))
    assert r.applied and r.result is not None
    ep = r.result.store.by_id["ep-a"]
    assert [o.stage.stage for o in ep.opportunity.observed_stages] == [
        OpportunityStage.INTERVIEW
    ]


def test_written_offer_received() -> None:
    r = _run("서면 오퍼를 받았다", _store("ep-a"))
    assert r.applied and r.result is not None
    ep = r.result.store.by_id["ep-a"]
    assert ep.opportunity.frontier_stage is not None
    assert ep.opportunity.frontier_stage.stage is OpportunityStage.OFFER_RECEIVED


def test_offer_accepted_changes_link_only() -> None:
    """수락은 링크만 — 퇴사·입사 자동 전진 0."""
    r = _run("오퍼를 수락했다", _store("ep-a"))
    assert r.applied and r.result is not None
    store = r.result.store
    assert store.current_employment is not None
    assert store.current_employment.linked_accepted_episode_id == "ep-a"
    assert store.by_id["ep-a"].entry.observed_stages == ()
    assert store.current_employment.exit_state.observed_stages == ()


def test_scheduled_join_is_not_joined() -> None:
    """'다음 주 입사 예정'은 확정 사실이 아니므로 전이하지 않는다."""
    r = _run("다음 주 입사 예정이다", _store("ep-a"))
    assert not r.applied
    assert r.parsed.evidence_class is not FactEvidenceClass.OBSERVABLE_HARD_FACT
    assert r.blocked_as_not_authoritative


def test_started_working_is_joined_sparse() -> None:
    r = _run("오늘부터 출근했다", _store("ep-a"))
    assert r.applied and r.result is not None
    ep = r.result.store.by_id["ep-a"]
    assert ep.entry.frontier_stage is not None
    assert ep.entry.frontier_stage.stage is EntryStage.JOINED
    assert ep.opportunity.observed_stages == ()   # 중간 단계 합성 0


def test_considering_resignation_makes_no_transition() -> None:
    """'퇴사할까 고민 중'은 상태 전이 없음."""
    r = _run("퇴사할까 고민 중이야", _store("ep-a"))
    assert not r.applied
    assert r.blocked_as_not_authoritative


def test_notice_given() -> None:
    r = _run("어제 퇴사 통보했다", _store("ep-a"))
    assert r.applied and r.result is not None
    assert r.parsed.fact_type is CareerFactType.NOTICE_GIVEN
    exit_state = r.result.store.current_employment
    assert exit_state is not None
    assert exit_state.exit_state.frontier_stage is not None
    assert exit_state.exit_state.frontier_stage.stage is ExitStage.NOTICE_GIVEN


def test_exit_completed() -> None:
    r = _run("지난달 퇴사했다", _store("ep-a"))
    assert r.applied and r.result is not None
    assert r.parsed.fact_type is CareerFactType.EXIT_COMPLETED
    assert r.result.store.current_employment is None   # 고용 종료


def test_internal_transfer_completed() -> None:
    store = _store("ep-a")
    joined = _run("오늘부터 출근했다", store)
    assert joined.result is not None
    r = _run("부서 이동이 끝났다", joined.result.store)
    assert r.applied and r.parsed.fact_type is CareerFactType.TRANSFER_COMPLETED
    assert r.result is not None
    assert r.result.store.current_employment is not None   # 고용 유지


# ── Episode 안전성 ─────────────────────────────────────────────────────────


def test_multiple_open_episodes_without_target_is_unresolved() -> None:
    """복수 open Episode + '면접 봤어' → 미해소, 상태 변화 0(정상 차단)."""
    store = _store("ep-a", "ep-b")
    r = _run("면접 봤어", store)
    assert not r.applied
    assert r.result is not None
    assert r.result.rejection_code is RejectionCode.EPISODE_UNRESOLVED
    assert r.result.store == store


def test_fact_does_not_leak_into_other_episode() -> None:
    """A사 사실이 B사에 적용되지 않는다."""
    store = _store("ep-a", "ep-b")
    r = _run("면접 봤어", store, episode="ep-a")
    assert r.applied and r.result is not None
    assert r.result.store.by_id["ep-b"].opportunity.observed_stages == ()


def test_shadow_uses_isolated_namespace() -> None:
    """shadow 사실은 production 원장과 다른 namespace를 쓴다."""
    r = _run("지원서를 냈다", _store("ep-a"))
    assert r.result is not None
    fact = r.result.store.fact_journal[-1]
    assert fact.source_ref.source_namespace == SHADOW_NAMESPACE


# ── 과장 방지 (forecast_to_confirmed_mutation = 0) ─────────────────────────


def test_positive_interview_impression_makes_no_transition() -> None:
    r = _run("면접관 반응이 좋았다", _store("ep-a"))
    assert not r.applied
    assert r.parsed.evidence_class is FactEvidenceClass.COUNTERPARTY_SPECULATION


def test_almost_passed_guess_makes_no_transition() -> None:
    r = _run("거의 합격한 것 같다", _store("ep-a"))
    assert not r.applied
    assert r.parsed.evidence_class is FactEvidenceClass.SUBJECTIVE_IMPRESSION


def test_saju_forecast_makes_no_transition() -> None:
    """사주 전망은 절대 단계 전이가 되지 않는다(INV-18)."""
    r = _run("사주에서 다음 달 오퍼가 올 운이래", _store("ep-a"))
    assert not r.applied
    assert r.parsed.evidence_class is not FactEvidenceClass.OBSERVABLE_HARD_FACT


def test_company_intent_claim_is_not_hard_fact() -> None:
    """'회사에서 뽑기로 한 것 같다'는 사용자 발화여도 hard fact 로 승격하지 않는다."""
    r = _run("회사에서 나를 뽑기로 한 것 같아", _store("ep-a"))
    assert not r.applied
    assert r.parsed.evidence_class is FactEvidenceClass.COUNTERPARTY_SPECULATION


def test_forecast_to_confirmed_mutation_is_zero_across_speculation_corpus() -> None:
    """추측 코퍼스 전체에서 confirmed 단계 변화 0."""
    corpus = [
        "다음 달 오퍼가 올 것 같아",
        "사주에서 합격 가능성이 높대",
        "회사도 나를 좋게 보는 듯해",
        "면접 분위기가 좋았어",
        "될 것 같아",
    ]
    store = _store("ep-a")
    for text in corpus:
        r = _run(text, store)
        assert not r.applied, text
        if r.result is not None:
            assert r.result.store == store, text
    assert store.by_id["ep-a"].opportunity.observed_stages == ()


# ── 파서 단위 ──────────────────────────────────────────────────────────────


def test_parser_keeps_blocked_utterances_instead_of_dropping() -> None:
    """차단된 발화도 버리지 않고 등급만 낮춰 보관한다."""
    parsed = parse_career_fact("회사가 나를 마음에 들어하는 것 같다")
    assert parsed.text
    assert not parsed.is_transition_eligible
    assert parsed.evidence_class is FactEvidenceClass.COUNTERPARTY_SPECULATION
