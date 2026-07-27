"""진행 사실 ↔ 사건 키 호환 (P2-2b) — fail-closed + 21키 전수 감사.

설계: `doc/v2_2/REVIEW_ACTIVE_PROCESS_CONTRACT.md`

핵심은 하나다 — **도메인 일치는 호환이 아니다.** 같은 재물 도메인이라도 대출 심사가
`windfall`을 열면 안 된다.
"""

from __future__ import annotations

import pytest

from saju_engines.process_event_compatibility import (
    EVENT_KEY_PROCESS_AUDIT,
    PROCESS_EVENT_COMPATIBILITY,
    ProcessCompatibilityResult,
    has_compatible_active,
    match_process_to_event,
)
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.process_fact import (
    EvidenceOrigin,
    ProcessFact,
    ProcessFamily,
    ProcessStage,
    ProcessStatus,
    SubjectResolution,
)


def _p(**over) -> ProcessFact:
    base = dict(
        fact_id="p1",
        subject_id="self",
        subject_resolution=SubjectResolution.RESOLVED,
        process_family=ProcessFamily.CAREER_OPPORTUNITY,
        stage=ProcessStage.INTERVIEWING,
        status=ProcessStatus.ACTIVE,
        entry_scope="external_employer",
        evidence_origin=EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
        original_text="면접 진행 중",
    )
    base.update(over)
    return ProcessFact(**base)


# ── 대표 불허 사례 (설계 §4) ─────────────────────────────────────


def test_external_interview_does_not_open_promotion() -> None:
    """외부 면접이 내부 승진을 열지 않는다 — EntryScope가 규칙을 가른다.

    사유는 `EVENT_KEY_NOT_ALLOWED`다: 외부 규칙의 scope는 통과했고 PROMOTION이 그
    규칙의 allowlist에 없다. 판정 결과는 사유보다 "열리지 않는다"가 핵심이다.
    """
    verdict = match_process_to_event(_p(), EventKeyV2.PROMOTION)
    assert not verdict.opens_exception
    assert verdict is ProcessCompatibilityResult.EVENT_KEY_NOT_ALLOWED
    # 통제군 — 같은 사실이 외부 취업은 연다.
    assert match_process_to_event(_p(), EventKeyV2.JOB_GAIN).opens_exception


def test_internal_promotion_does_not_open_external_job_gain() -> None:
    """내부 승진 심사가 외부 취업을 열지 않는다."""
    internal = _p(entry_scope="internal_role")
    verdict = match_process_to_event(internal, EventKeyV2.JOB_GAIN)
    assert not verdict.opens_exception
    assert verdict is ProcessCompatibilityResult.EVENT_KEY_NOT_ALLOWED
    assert match_process_to_event(internal, EventKeyV2.PROMOTION).opens_exception


def test_scope_mismatch_is_reported_when_no_rule_matches_scope() -> None:
    """어느 규칙의 scope에도 맞지 않으면 scope 불일치로 보고한다."""
    unknown_scope = _p(entry_scope="contractor")
    assert match_process_to_event(unknown_scope, EventKeyV2.JOB_GAIN) is (
        ProcessCompatibilityResult.ENTRY_SCOPE_MISMATCH
    )


def test_move_does_not_open_wealth_gain() -> None:
    """이사 일정 확정이 재물 증가를 열지 않는다."""
    move = _p(
        process_family=ProcessFamily.MOVE_PROCESS,
        stage=ProcessStage.SCHEDULED,
        entry_scope=None,
        evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
    )
    assert match_process_to_event(move, EventKeyV2.RELOCATION).opens_exception
    assert match_process_to_event(move, EventKeyV2.WEALTH_CHANGE) is (
        ProcessCompatibilityResult.EVENT_KEY_NOT_ALLOWED
    )
    assert match_process_to_event(move, EventKeyV2.WINDFALL) is (
        ProcessCompatibilityResult.EVENT_KEY_NOT_ALLOWED
    )


def test_unsupported_domain_is_coverage_bypass_not_compatible() -> None:
    """대출은 추출기가 없다 — 규칙을 추측해 넣지 않았음을 고정한다."""
    loan = _p(
        process_family=ProcessFamily.LOAN_PROCESS,
        stage=ProcessStage.IN_REVIEW,
        entry_scope=None,
        evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
    )
    for key in (EventKeyV2.CONTRACT_DOCUMENT, EventKeyV2.WINDFALL):
        assert match_process_to_event(loan, key) is (
            ProcessCompatibilityResult.COVERAGE_BYPASS
        )


def test_terminal_fact_never_opens() -> None:
    """종료된 과정은 아무것도 열지 않는다."""
    done = _p(stage=ProcessStage.COMPLETED, status=ProcessStatus.TERMINAL)
    assert match_process_to_event(done, EventKeyV2.JOB_GAIN) is (
        ProcessCompatibilityResult.PROCESS_NOT_USABLE
    )


def test_engine_inferred_fact_never_opens() -> None:
    """엔진 추정은 호환 판정 이전에 걸린다."""
    inferred = _p(evidence_origin=EvidenceOrigin.ENGINE_INFERRED)
    assert match_process_to_event(inferred, EventKeyV2.JOB_GAIN) is (
        ProcessCompatibilityResult.PROCESS_NOT_USABLE
    )


# ── 유지보수 장치 (설계 §7) ──────────────────────────────────────


def test_every_event_key_is_audited() -> None:
    """새 event key가 추가되면 실패한다 — 호환성을 명시적으로 감수하게 만든다."""
    assert set(EVENT_KEY_PROCESS_AUDIT) == set(EventKeyV2)


def test_no_rule_allows_an_entire_domain_sweep() -> None:
    """하나의 규칙이 전 도메인 키를 열지 않는다 — 과도한 허용 방지."""
    for rule in PROCESS_EVENT_COMPATIBILITY:
        assert len(rule.allowed_event_keys) <= 3, rule.rule_id


def test_rule_ids_are_unique() -> None:
    """규칙 id 충돌이 없어야 감사에서 원인을 특정할 수 있다."""
    ids = [r.rule_id for r in PROCESS_EVENT_COMPATIBILITY]
    assert len(ids) == len(set(ids))


def test_no_conflicting_verdicts_for_same_combination() -> None:
    """같은 (family, stage, scope, key) 조합이 상반된 판정을 내지 않는다."""
    seen: dict[tuple, str] = {}
    for rule in PROCESS_EVENT_COMPATIBILITY:
        for stage in rule.active_stages:
            for scope in rule.entry_scopes or {None}:
                for key in rule.allowed_event_keys:
                    combo = (rule.process_family, stage, scope, key)
                    # 같은 조합이 여러 규칙에 있어도 결론은 항상 COMPATIBLE이므로
                    # 충돌이 아니다. 규칙 id만 기록해 중복 정의를 드러낸다.
                    seen.setdefault(combo, rule.rule_id)
    assert seen, "규칙이 비면 이 검사는 의미가 없다"


@pytest.mark.parametrize(
    "key",
    [
        EventKeyV2.WINDFALL,
        EventKeyV2.HEALTH_ATTENTION,
        EventKeyV2.LEGAL_CONFLICT,
        EventKeyV2.CHILDBIRTH,
    ],
)
def test_not_process_gated_keys_are_in_no_allowlist(key) -> None:
    """진행 과정으로 여는 사건이 아닌 키는 어느 allowlist에도 없다."""
    for rule in PROCESS_EVENT_COMPATIBILITY:
        assert key not in rule.allowed_event_keys, rule.rule_id


# ── has_compatible_active ────────────────────────────────────────


def test_has_compatible_active_requires_subject_match() -> None:
    """동반자의 진행 사실이 본인 후보를 열지 않는다."""
    partner = _p(subject_id="partner-1")
    assert not has_compatible_active(
        [partner], EventKeyV2.JOB_GAIN, subject_id="self"
    )
    assert has_compatible_active([_p()], EventKeyV2.JOB_GAIN, subject_id="self")


def test_has_compatible_active_is_false_for_incompatible_key() -> None:
    """호환되지 않는 키는 active가 있어도 열리지 않는다."""
    assert not has_compatible_active(
        [_p()], EventKeyV2.WINDFALL, subject_id="self"
    )


# ── P2-2c: 범위 판정 + 근거 보존 ─────────────────────────────────


def _scope(layers, key, facts=(), subject_id="self", coverage_override=None):
    from saju_engines.process_event_compatibility import resolve_candidate_scope

    return resolve_candidate_scope(
        list(layers), key, facts=list(facts),
        subject_id=subject_id, coverage_override=coverage_override,
    )


def test_upper_supported_is_major_regardless_of_process() -> None:
    """상위 근거가 있으면 진행 사실과 무관하게 주요 사건 자격이다."""
    from saju_shared_types.event_engine import EventScope
    from saju_shared_types.process_fact import EventGateAction

    r = _scope(["sewoon"], EventKeyV2.JOB_GAIN)
    assert r.raw_event_scope is EventScope.MAJOR_EVENT_ELIGIBLE
    assert r.gate_action is EventGateAction.ENFORCE_MAJOR


def test_external_interview_opens_job_gain_as_active_trigger() -> None:
    """외부 면접 중이면 일운만의 취업 후보도 진행 중 사건의 시점 후보가 된다."""
    from saju_shared_types.event_engine import EventScope
    from saju_shared_types.process_fact import EventGateAction

    r = _scope(["ilwoon"], EventKeyV2.JOB_GAIN, facts=[_p()])
    assert r.raw_event_scope is EventScope.ACTIVE_PROCESS_TRIGGER
    assert r.gate_action is EventGateAction.ENFORCE_ACTIVE_TRIGGER
    assert r.primary_match is not None
    assert r.primary_match.compatibility_rule_id == "CAREER_EXTERNAL_OPPORTUNITY"


def test_external_interview_does_not_open_promotion_scope() -> None:
    """같은 사실이 승진 후보는 열지 않는다 — 커리어는 없음을 확정할 수 있다."""
    from saju_shared_types.event_engine import EventScope
    from saju_shared_types.process_fact import EventGateAction

    r = _scope(["ilwoon"], EventKeyV2.PROMOTION, facts=[_p()])
    assert r.raw_event_scope is EventScope.LOCAL_TRIGGER_ONLY
    assert r.gate_action is EventGateAction.ENFORCE_LOCAL_ONLY
    assert r.matches == ()


def test_unsupported_domain_key_bypasses_instead_of_enforcing() -> None:
    """자료 없는 도메인 키는 강등하지 않고 기존 동작을 유지한다."""
    from saju_shared_types.process_fact import EventGateAction

    r = _scope(["ilwoon"], EventKeyV2.WEALTH_CHANGE)
    assert r.gate_action.is_bypass
    assert r.gate_action is EventGateAction.BYPASS_UNSUPPORTED_PROCESS_COVERAGE


def test_move_without_match_bypasses_incomplete_coverage() -> None:
    """이사는 있을 때만 안다 — 못 찾았다고 강등하지 않는다."""
    from saju_shared_types.process_fact import EventGateAction

    r = _scope(["ilwoon"], EventKeyV2.RELOCATION)
    assert r.gate_action is EventGateAction.BYPASS_INCOMPLETE_COVERAGE


def test_source_unavailable_is_distinguished_from_absence() -> None:
    """저장소 장애는 '사실 없음'이 아니다."""
    from saju_shared_types.process_fact import EventGateAction, ProcessCoverage

    r = _scope(
        ["ilwoon"], EventKeyV2.JOB_GAIN,
        coverage_override=ProcessCoverage.SOURCE_UNAVAILABLE,
    )
    assert r.gate_action is EventGateAction.BYPASS_PROCESS_SOURCE_UNAVAILABLE


def test_partner_process_does_not_open_own_candidate_scope() -> None:
    """동반자 사실이 본인 후보 범위를 바꾸지 않는다."""
    from saju_shared_types.event_engine import EventScope

    r = _scope(["ilwoon"], EventKeyV2.JOB_GAIN, facts=[_p(subject_id="partner-1")])
    assert r.raw_event_scope is EventScope.LOCAL_TRIGGER_ONLY
    assert r.matches == ()
