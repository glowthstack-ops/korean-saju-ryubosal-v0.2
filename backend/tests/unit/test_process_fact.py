"""명시적 진행 사실 모델 (P2-PROC-1) — 2026-07-27 데굴님 확정.

설계: `doc/v2_2/REVIEW_ACTIVE_PROCESS_CONTRACT.md`

이 슬라이스는 EventScope에 연결되지 않는다. 예외 자격의 **불변식**만 고정한다.
핵심은 하나다 — 엔진이 추정한 상태는 자기 자신의 게이트를 열 수 없다.
"""

from __future__ import annotations

import pytest

from saju_shared_types.process_fact import (
    ALLOWED_EVIDENCE_ORIGINS,
    TERMINAL_STAGES,
    EvidenceOrigin,
    IntentLevel,
    ProcessFact,
    ProcessFamily,
    ProcessMatchResult,
    ProcessStage,
    ProcessStatus,
    SubjectResolution,
    SupersessionResult,
    supersede,
)


def _fact(**over) -> ProcessFact:
    base = dict(
        fact_id="f1",
        subject_id="self",
        subject_resolution=SubjectResolution.RESOLVED,
        process_family=ProcessFamily.LOAN_PROCESS,
        stage=ProcessStage.IN_REVIEW,
        status=ProcessStatus.ACTIVE,
        evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
        original_text="대출 심사 중이야",
    )
    base.update(over)
    return ProcessFact(**base)


# ── 순환 차단 — 가장 중요한 불변식 ────────────────────────────────


@pytest.mark.parametrize(
    "origin", [EvidenceOrigin.ENGINE_INFERRED, EvidenceOrigin.SHADOW]
)
def test_engine_inferred_state_cannot_open_the_gate(origin) -> None:
    """엔진 추정·shadow는 예외 근거가 될 수 없다.

    허용하면 엔진이 추정한 관계 단계가 그 관계 사건의 게이트를 스스로 열어준다.
    """
    assert not _fact(evidence_origin=origin).is_usable_exception()
    assert origin not in ALLOWED_EVIDENCE_ORIGINS


def test_explicit_user_fact_opens_the_gate() -> None:
    """사용자가 직접 말한 진행 사실은 예외 근거가 된다."""
    assert _fact().is_usable_exception()


def test_career_hard_fact_episode_is_allowed() -> None:
    """검증된 커리어 Episode는 허용 출처다."""
    assert _fact(
        evidence_origin=EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
        process_family=ProcessFamily.CAREER_OPPORTUNITY,
    ).is_usable_exception()


# ── 종료·주체·의향 ───────────────────────────────────────────────


@pytest.mark.parametrize("stage", sorted(TERMINAL_STAGES))
def test_terminal_stage_never_opens(stage) -> None:
    """거절·취소·포기·완료·만료는 열지 않는다."""
    assert not _fact(stage=stage).is_usable_exception()


def test_unresolved_subject_fails_closed() -> None:
    """주체가 불명확하면 본인으로 추정하지 않는다."""
    assert not _fact(subject_resolution=SubjectResolution.UNKNOWN).is_usable_exception()


@pytest.mark.parametrize(
    "level", [IntentLevel.PLANNED_OR_INTENDED, IntentLevel.DESIRE_ONLY]
)
def test_intent_without_execution_does_not_open(level) -> None:
    """계획·욕구는 진행 중인 과정이 아니다."""
    assert not _fact(intent_level=level).is_usable_exception()


def test_stale_fact_does_not_open() -> None:
    """현재 사실이 아니면 열지 않는다."""
    assert not _fact(current=False).is_usable_exception()


# ── terminal supersession ────────────────────────────────────────


def test_single_active_family_terminal_closes_prior_active() -> None:
    """이사는 SINGLE_ACTIVE_FAMILY라 키 없이도 현재 취소가 기존 진행을 닫는다."""
    ledger = _fact(
        fact_id="ledger",
        process_family=ProcessFamily.MOVE_PROCESS,
        evidence_origin=EvidenceOrigin.LEDGER_EXPLICIT,
        stage=ProcessStage.IN_PROGRESS,
        status=ProcessStatus.ACTIVE,
        original_text="이사가 결정되었어",
    )
    now = _fact(
        fact_id="now",
        process_family=ProcessFamily.MOVE_PROCESS,
        evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
        stage=ProcessStage.CANCELLED,
        status=ProcessStatus.TERMINAL,
        original_text="이번 이사는 취소했어",
    )
    survivors, closed = supersede([ledger, now])

    assert [f.fact_id for f in survivors] == ["now"]  # terminal 기록은 유지
    assert closed and closed[0][0].fact_id == "ledger"
    assert closed[0][1] is SupersessionResult.SUPERSEDED_SINGLE_ACTIVE_FAMILY


def test_unkeyed_terminal_does_not_close_multi_instance_domain() -> None:
    """계약·대출은 동시에 여러 건이 가능하다 — 키 없는 terminal이 전부를 닫지 않는다."""
    active = _fact(
        fact_id="active",
        process_family=ProcessFamily.CONTRACT_PROCESS,
        evidence_origin=EvidenceOrigin.LEDGER_EXPLICIT,
        stage=ProcessStage.IN_REVIEW,
        original_text="계약 검토 중",
    )
    done = _fact(
        fact_id="done",
        process_family=ProcessFamily.CONTRACT_PROCESS,
        stage=ProcessStage.COMPLETED,
        status=ProcessStatus.TERMINAL,
        original_text="계약서는 이미 다 썼고",
    )
    survivors, closed = supersede([active, done])

    assert {f.fact_id for f in survivors} == {"active", "done"}
    assert closed == []


def test_instance_key_closes_only_its_own_instance() -> None:
    """A회사 거절이 B회사 결과 대기를 닫지 않는다."""
    a = _fact(
        fact_id="a", process_family=ProcessFamily.CAREER_OPPORTUNITY,
        process_instance_key="ep-A", stage=ProcessStage.RESULT_PENDING,
        evidence_origin=EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
    )
    b = _fact(
        fact_id="b", process_family=ProcessFamily.CAREER_OPPORTUNITY,
        process_instance_key="ep-B", stage=ProcessStage.RESULT_PENDING,
        evidence_origin=EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
    )
    reject_a = _fact(
        fact_id="reject-a", process_family=ProcessFamily.CAREER_OPPORTUNITY,
        process_instance_key="ep-A", stage=ProcessStage.REJECTED,
        status=ProcessStatus.TERMINAL,
    )
    survivors, closed = supersede([a, b, reject_a])

    assert "b" in {f.fact_id for f in survivors}
    assert [c[0].fact_id for c in closed] == ["a"]
    assert closed[0][1] is SupersessionResult.SUPERSEDED_EXACT_INSTANCE


def test_career_terminal_without_instance_key_preserves_active() -> None:
    """커리어는 INSTANCE_REQUIRED — 키 없는 terminal은 아무것도 닫지 않는다."""
    active = _fact(
        fact_id="active", process_family=ProcessFamily.CAREER_OPPORTUNITY,
        process_instance_key="ep-A", stage=ProcessStage.RESULT_PENDING,
    )
    unkeyed = _fact(
        fact_id="unkeyed", process_family=ProcessFamily.CAREER_OPPORTUNITY,
        stage=ProcessStage.REJECTED, status=ProcessStatus.TERMINAL,
    )
    survivors, closed = supersede([active, unkeyed])

    assert "active" in {f.fact_id for f in survivors}
    assert closed == []


def test_supersede_keeps_distinct_families() -> None:
    """다른 과정은 서로를 밀어내지 않는다."""
    loan = _fact(fact_id="loan", process_family=ProcessFamily.LOAN_PROCESS)
    move = _fact(fact_id="move", process_family=ProcessFamily.MOVE_PROCESS)
    survivors, _ = supersede([loan, move])
    assert len(survivors) == 2


def test_supersede_separates_subjects() -> None:
    """동반자의 이사 취소가 본인 이사 진행을 닫지 않는다."""
    mine = _fact(
        fact_id="mine", subject_id="self",
        process_family=ProcessFamily.MOVE_PROCESS,
    )
    partner_cancel = _fact(
        fact_id="partner", subject_id="partner-1",
        process_family=ProcessFamily.MOVE_PROCESS,
        stage=ProcessStage.CANCELLED, status=ProcessStatus.TERMINAL,
    )
    survivors, closed = supersede([mine, partner_cancel])
    assert "mine" in {f.fact_id for f in survivors}
    assert closed == []


# ── 판정 결과의 fail-safe 구분 ───────────────────────────────────


def test_source_unavailable_is_not_no_evidence() -> None:
    """저장소 장애는 '진행 사실 없음'이 아니다 — 기존 동작으로 되돌린다."""
    assert ProcessMatchResult.SOURCE_UNAVAILABLE.is_fail_safe
    assert not ProcessMatchResult.NO_EVIDENCE.is_fail_safe


@pytest.mark.parametrize(
    "result",
    [
        ProcessMatchResult.INCOMPATIBLE_EVENT,
        ProcessMatchResult.TERMINAL_PROCESS,
        ProcessMatchResult.STALE_OR_NOT_CURRENT,
        ProcessMatchResult.DESIRE_ONLY,
        ProcessMatchResult.SUBJECT_MISMATCH,
        ProcessMatchResult.NO_EVIDENCE,
        ProcessMatchResult.SOURCE_UNAVAILABLE,
    ],
)
def test_only_compatible_active_opens(result) -> None:
    """예외를 여는 것은 COMPATIBLE_ACTIVE 하나뿐이다."""
    assert not result.opens_exception
    assert ProcessMatchResult.COMPATIBLE_ACTIVE.opens_exception
