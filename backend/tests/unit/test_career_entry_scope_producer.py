"""CARR-SCOPE — `entry_scope` producer (2026-07-28 확정 계약).

핵심은 범위를 **추론하지 않는 것**이다. 명시된 hard fact가 말한 범위만 저장한다.
자료가 없는 것을 추론으로 채우면 F1을 푸는 대신 오귀속을 만든다.

golden 경로는 발화부터 게이트 판정까지 **실제 저장소를 통과**해야 한다 — 스텁에
entry_scope를 직접 넣는 테스트만으로는 배선 단절을 잡지 못한다.
"""

from __future__ import annotations

import pytest

from saju_engines.career_fact_parser import parse_career_fact
from saju_engines.career_process_adapter import build_career_process_snapshots
from saju_engines.career_shadow_repository import InMemoryCareerShadowRepository
from saju_engines.career_state_shadow import PersistenceStatus, process_career_turn
from saju_engines.process_event_compatibility import (
    ProcessCompatibilityResult,
    match_process_to_event,
    resolve_candidate_scope,
)
from saju_engines.process_fact_resolver import adapt_career_snapshot
from saju_shared_types.career_transition import EntryScope
from saju_shared_types.event_engine import EventKeyV2, EventScope
from saju_shared_types.process_fact import EventGateAction, ProcessStage

_MINOR = ["ilwoon"]
_N = 0


def _turn(repo, text, *, thread="t1", subject="s1"):
    """실제 운영 경로와 같은 turn 처리(load→parse→reducer→save)."""
    global _N
    _N += 1
    return process_career_turn(
        repo, thread_id=thread, subject_id=subject, conversation_text=text,
        command_id=f"c{_N}", source_fact_id=f"sf{_N}", recorded_at=f"2026-07-{_N:02d}",
    )


def _facts_after(text, *, extra=None):
    """발화 → 저장 → replay → Episode → 스냅샷 → ProcessFact 전 구간."""
    repo = InMemoryCareerShadowRepository()
    for t in [text, *(extra or [])]:
        result = _turn(repo, t)
    loaded = repo.load("t1", "s1")
    snapshots = build_career_process_snapshots(loaded.store, subject_id="self")
    facts = [f for f in (adapt_career_snapshot(s) for s in snapshots) if f is not None]
    return result, loaded.store, facts


# ── 1. 파서: 명시된 범위만 읽는다 ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("외부 회사 면접을 봤고 결과를 기다려", EntryScope.EXTERNAL_EMPLOYER),
        ("다른 회사 면접을 봤어", EntryScope.EXTERNAL_EMPLOYER),
        ("사내 승진 면접을 봤어", EntryScope.INTERNAL_ROLE),
        ("승진 심사 면접을 봤어", EntryScope.INTERNAL_ROLE),
        ("다른 부서로 전보가 확정됐어", EntryScope.INTERNAL_DEPARTMENT),
        ("다른 팀으로 이동 발령 났어", EntryScope.INTERNAL_DEPARTMENT),
        ("부산 지점으로 이동이 결정됐어", EntryScope.INTERNAL_LOCATION),
        ("부산 지사로 발령 났어", EntryScope.INTERNAL_LOCATION),
    ],
)
def test_explicit_scope_is_parsed(text, expected) -> None:
    parsed = parse_career_fact(text)

    assert parsed.entry_scope is expected
    assert parsed.scope_rule_id, "판정 규칙 id를 감사에 남겨야 한다"
    assert parsed.scope_evidence_text, "근거 구절을 남겨야 한다"


@pytest.mark.parametrize(
    "text",
    [
        "면접을 봤어",              # 외부인지 사내인지 알 수 없다
        "지원서 넣었어",
        "오퍼 받았어",
        "입사했어",                # 완료 사실에서 외부 입사를 단정하지 않는다
        "퇴사 통보했어",
    ],
)
def test_scope_is_not_inferred_from_fact_type(text) -> None:
    """fact type만 보고 범위를 추정하지 않는다 — 계약의 핵심 금지 항목."""
    parsed = parse_career_fact(text)

    assert parsed.entry_scope is None
    assert parsed.scope_rule_id is None


def test_desire_only_has_no_hard_fact() -> None:
    """'이직하고 싶어'는 범위 표지가 있어도 사실이 아니다."""
    parsed = parse_career_fact("이직하고 싶어")

    assert parsed.fact_type is None
    assert not parsed.is_transition_eligible


def test_planned_utterance_is_not_eligible() -> None:
    """계획·의도는 hard fact 로 승격하지 않는다."""
    parsed = parse_career_fact("이직하려고 면접을 볼까 고민 중")

    assert not parsed.is_transition_eligible


# ── 2. 저장: 명시 사실만 Episode에 반영된다 ─────────────────────────────────


def test_scope_survives_journal_replay() -> None:
    """journal → replay → Episode.entry_scope 까지 살아남는다."""
    _, store, facts = _facts_after("다른 회사 면접을 봤어")

    (episode,) = store.episodes
    assert episode.entry_scope is EntryScope.EXTERNAL_EMPLOYER
    assert facts and facts[0].entry_scope == "external_employer"


def test_non_eligible_utterance_stores_no_scope() -> None:
    """자격 미달 발화는 명령 자체가 만들어지지 않아 범위도 저장되지 않는다."""
    result, store, _ = _facts_after("이직하고 싶어")

    assert result.persistence_status is not PersistenceStatus.SAVED
    assert store.episodes == ()


def test_scope_absent_stays_none() -> None:
    """범위 미상은 None으로 남는다 — 기본값을 채우지 않는다."""
    _, store, facts = _facts_after("면접을 봤어")

    (episode,) = store.episodes
    assert episode.entry_scope is None
    assert facts[0].entry_scope is None


def test_none_then_explicit_fills() -> None:
    """기존 scope=None + 새 명시 사실 → 채운다."""
    _, store, _ = _facts_after("면접을 봤어", extra=["다른 회사 지원서 넣었어"])

    (episode,) = store.episodes
    assert episode.entry_scope is EntryScope.EXTERNAL_EMPLOYER


def test_existing_scope_is_not_auto_changed() -> None:
    """기존 external + 새 internal → 자동 변경 금지."""
    _, store, _ = _facts_after("다른 회사 면접을 봤어", extra=["사내 승진 지원했어"])

    (episode,) = store.episodes
    assert episode.entry_scope is EntryScope.EXTERNAL_EMPLOYER, (
        "나중 선언이 기존 범위를 덮어쓰면 외부 지원이 사내 승진으로 조용히 바뀐다"
    )


def test_scope_conflict_is_audited_as_blocked() -> None:
    """충돌은 위반이 아니라 정상 차단이다(INV-24)."""
    from saju_engines.career_shadow_metrics import METRIC_ENTRY_SCOPE_CONFLICT
    from saju_engines.career_shadow_observation import GuardOutcome

    repo = InMemoryCareerShadowRepository()
    _turn(repo, "다른 회사 면접을 봤어")
    result = _turn(repo, "사내 승진 지원했어")

    conflicts = [
        o for o in (result.run.observations if result.run else ())
        if o.metric_name == METRIC_ENTRY_SCOPE_CONFLICT
    ]
    assert conflicts, "충돌을 감사에 남겨야 한다"
    assert conflicts[0].guard_outcome is GuardOutcome.BLOCKED
    assert conflicts[0].audit_event == "ENTRY_SCOPE_CONFLICT_EXISTING_VALUE"


def test_scope_fill_is_audited() -> None:
    from saju_engines.career_shadow_metrics import METRIC_ENTRY_SCOPE_FILLED

    repo = InMemoryCareerShadowRepository()
    result = _turn(repo, "다른 회사 면접을 봤어")

    filled = [
        o for o in (result.run.observations if result.run else ())
        if o.metric_name == METRIC_ENTRY_SCOPE_FILLED
    ]
    assert filled and filled[0].audit_event == "ENTRY_SCOPE_FILLED_FROM_EXPLICIT_FACT"


def test_scope_unavailable_is_counted_separately() -> None:
    """범위 부재는 결함이 아니라 자료 부재 — 별도 지표로 센다."""
    from saju_engines.career_shadow_metrics import METRIC_ENTRY_SCOPE_UNAVAILABLE

    repo = InMemoryCareerShadowRepository()
    result = _turn(repo, "면접을 봤어")

    names = {o.metric_name for o in (result.run.observations if result.run else ())}
    assert METRIC_ENTRY_SCOPE_UNAVAILABLE in names


# ── 3. golden 경로 — 발화부터 게이트까지 ────────────────────────────────────


def _gate(facts, event_key):
    return resolve_candidate_scope(
        _MINOR, event_key, facts=facts, subject_id="self"
    )


@pytest.mark.parametrize(
    ("text", "event_key", "expected_action", "expected_scope"),
    [
        # 외부 면접 결과 대기
        ("다른 회사 면접을 봤어", EventKeyV2.JOB_GAIN,
         EventGateAction.ENFORCE_ACTIVE_TRIGGER, EventScope.ACTIVE_PROCESS_TRIGGER),
        ("다른 회사 면접을 봤어", EventKeyV2.PROMOTION,
         EventGateAction.ENFORCE_LOCAL_ONLY, EventScope.LOCAL_TRIGGER_ONLY),
        # 내부 승진 심사
        ("사내 승진 면접을 봤어", EventKeyV2.PROMOTION,
         EventGateAction.ENFORCE_ACTIVE_TRIGGER, EventScope.ACTIVE_PROCESS_TRIGGER),
        ("사내 승진 면접을 봤어", EventKeyV2.JOB_GAIN,
         EventGateAction.ENFORCE_LOCAL_ONLY, EventScope.LOCAL_TRIGGER_ONLY),
    ],
)
def test_golden_paths_end_to_end(text, event_key, expected_action, expected_scope) -> None:
    """4 golden 경로가 실제 저장소를 통과해 게이트까지 도달한다."""
    _, _, facts = _facts_after(text)

    scope = _gate(facts, event_key)

    assert scope.gate_action is expected_action
    assert scope.raw_event_scope is expected_scope


def test_active_trigger_carries_evidence() -> None:
    """예외가 열렸다면 어떤 사실이 열었는지 특정할 수 있어야 한다."""
    _, _, facts = _facts_after("다른 회사 면접을 봤어")

    scope = _gate(facts, EventKeyV2.JOB_GAIN)

    assert scope.matches
    match = scope.primary_match
    assert match is not None
    assert match.compatibility_rule_id == "CAREER_EXTERNAL_OPPORTUNITY"
    assert match.stage is ProcessStage.RESULT_PENDING
    assert match.entry_scope == "external_employer"


def test_unknown_scope_bypasses_instead_of_enforcing() -> None:
    """범위 미상 → '진행 중인 게 없다'가 아니라 자료 부족 → bypass."""
    _, _, facts = _facts_after("면접을 봤어")

    scope = _gate(facts, EventKeyV2.JOB_GAIN)

    assert scope.gate_action is EventGateAction.BYPASS_INCOMPLETE_COVERAGE
    assert not scope.matches


def test_internal_location_is_fail_closed() -> None:
    """INTERNAL_LOCATION은 허용 규칙이 없다 — 열리지도, 오귀속되지도 않는다."""
    from saju_shared_types.process_fact import (
        CareerEntryScope,
        CareerProcessSnapshot,
        ProcessFamily,
    )

    fact = adapt_career_snapshot(
        CareerProcessSnapshot(
            episode_id="ep-loc", subject_id="self",
            process_family=ProcessFamily.CAREER_OPPORTUNITY,
            stage=ProcessStage.RESULT_PENDING,
            entry_scope=CareerEntryScope.INTERNAL_LOCATION,
        )
    )
    assert fact is not None

    for key in (EventKeyV2.JOB_GAIN, EventKeyV2.PROMOTION, EventKeyV2.CAREER_CHANGE):
        assert match_process_to_event(fact, key) is not ProcessCompatibilityResult.COMPATIBLE
        assert _gate([fact], key).gate_action is not (
            EventGateAction.ENFORCE_ACTIVE_TRIGGER
        )


def test_exit_still_works_without_scope() -> None:
    """Exit 규칙은 scope를 요구하지 않는다 — F1 영향을 받지 않는다."""
    _, _, facts = _facts_after("퇴사 통보했어")

    scope = _gate(facts, EventKeyV2.CAREER_CHANGE)

    assert scope.gate_action is EventGateAction.ENFORCE_ACTIVE_TRIGGER
    assert scope.primary_match is not None
    assert scope.primary_match.compatibility_rule_id == "CAREER_EXIT"
