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


def test_current_turn_terminal_supersedes_ledger_active() -> None:
    """원장의 '심사 중'보다 현재 발화의 '거절됐어'가 이긴다."""
    ledger = _fact(
        fact_id="ledger",
        evidence_origin=EvidenceOrigin.LEDGER_EXPLICIT,
        stage=ProcessStage.IN_REVIEW,
        status=ProcessStatus.ACTIVE,
        original_text="대출 심사 중",
    )
    now = _fact(
        fact_id="now",
        evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
        stage=ProcessStage.REJECTED,
        status=ProcessStatus.TERMINAL,
        original_text="대출은 거절됐어",
    )
    survivors = supersede([ledger, now])

    assert len(survivors) == 1
    assert survivors[0].fact_id == "now"
    assert not survivors[0].is_usable_exception()


def test_supersede_keeps_distinct_families() -> None:
    """다른 과정은 서로를 밀어내지 않는다."""
    loan = _fact(fact_id="loan", process_family=ProcessFamily.LOAN_PROCESS)
    move = _fact(fact_id="move", process_family=ProcessFamily.MOVE_PROCESS)
    assert len(supersede([loan, move])) == 2


def test_supersede_separates_subjects() -> None:
    """동반자 사실이 본인 사실을 덮어쓰지 않는다."""
    mine = _fact(fact_id="mine", subject_id="self")
    partner = _fact(fact_id="partner", subject_id="partner-1")
    assert len(supersede([mine, partner])) == 2


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
