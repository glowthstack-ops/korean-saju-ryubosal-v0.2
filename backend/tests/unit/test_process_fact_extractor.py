"""진행 사실 추출기 (P2-PROC-2) — 골든 fixture 중심.

설계: `doc/v2_2/REVIEW_PROCESS_FACT_PATTERNS.md` §9

문장은 **실로그 카탈로그와 테스터 회귀에서 가져온 것만** 쓴다. 합성 문장은 near-miss
방어용으로만 최소한 넣는다. 추측 표현으로 사양을 만들면 `user_facts.py`가 겪은
실패(추측 패턴 → 테스터 실문장 전부 미추출)가 반복된다.
"""

from __future__ import annotations

from saju_engines.process_fact_extractor import extract_process_facts
from saju_shared_types.process_fact import (
    PROCESS_COVERAGE,
    EventGateAction,
    IntentLevel,
    ProcessCoverage,
    ProcessFamily,
    ProcessStage,
    ProcessStatus,
    resolve_gate_action,
    usable_active_facts,
)


def _facts(text: str):
    return [e.normalized_fact for e in extract_process_facts(text) if e.normalized_fact]


# ── 골든: 테스터 회귀 문장 ────────────────────────────────────────


def test_move_decision_is_in_progress_not_scheduled() -> None:
    """"9월 30일에 이사가 결정되었어" — 날짜가 이삿날인지 결정일인지 모호하다.

    날짜가 있다는 이유로 SCHEDULED로 올리지 않는다(설계 §8-3).
    """
    facts = _facts("나는 9월 30일에 이사가 결정되었어.")
    assert len(facts) == 1
    assert facts[0].process_family is ProcessFamily.MOVE_PROCESS
    assert facts[0].stage is ProcessStage.IN_PROGRESS
    assert facts[0].is_usable_exception()


def test_move_date_fixed_is_scheduled() -> None:
    """이삿날 자체가 확정되면 SCHEDULED다."""
    facts = _facts("이사 날짜가 9월 30일로 확정됐어.")
    assert facts[0].stage is ProcessStage.SCHEDULED


def test_contract_signed_is_terminal_and_closes() -> None:
    """"계약서는 이미 다 썼고" — 여는 게 아니라 닫는다."""
    facts = _facts("계약서는 이미 다 썼고 그 날은 짐만 옮기는 날이야.")
    assert len(facts) == 1
    assert facts[0].process_family is ProcessFamily.CONTRACT_PROCESS
    assert facts[0].stage is ProcessStage.COMPLETED
    assert facts[0].status is ProcessStatus.TERMINAL
    assert not facts[0].is_usable_exception()


def test_loan_plan_creates_no_fact() -> None:
    """"8~9월 동안 은행 대출을 진행해야되는데" — 계획이지 진행이 아니다.

    대출은 coverage=UNSUPPORTED라 패턴 자체가 없다.
    """
    assert _facts("8~9월 동안 은행 대출과 인테리어를 진행해야되는데") == []


def test_loan_purpose_creates_no_fact() -> None:
    """"주택을 사기 위한 대출" — 목적 설명이다. 신청·심사 단계가 없다."""
    assert _facts("주택을 사기 위한 대출이야.") == []


# ── 골든: 카탈로그 negative ──────────────────────────────────────


def test_deadline_goal_is_not_active_process() -> None:
    """C9 — 날짜 선택 질문의 전형인데 진행 사실이 아니다."""
    assert _facts("2027년 2월까지 이사를 완료하고 싶어.") == []


def test_preparing_is_not_active_process() -> None:
    """A11 — "준비하고 있어"는 관측 가능한 단계가 아니다."""
    assert _facts("올해 이사를 준비하고 있어.") == []


def test_skipped_reason_is_recorded() -> None:
    """만들지 않은 이유를 남겨 오분류를 사후 검증할 수 있게 한다."""
    got = extract_process_facts("이사 날짜가 확정될까 해서 알아보고 있어.")
    assert got and got[0].normalized_fact is None
    assert got[0].skipped_reason is IntentLevel.PLANNED_OR_INTENDED


# ── near-miss 방어 ───────────────────────────────────────────────


def test_third_party_subject_fails_closed() -> None:
    """동반자 사실이 본인 후보를 열지 않는다."""
    facts = _facts("남편이 이사가 결정되었어.")
    assert facts and not facts[0].is_usable_exception()


def test_past_fact_is_recorded_but_not_usable() -> None:
    """작년 사실은 사실이되 현재가 아니다 — 만들지 않는 것과 구분한다."""
    facts = _facts("작년에 이사가 결정되었어.")
    assert facts and not facts[0].current
    assert not facts[0].is_usable_exception()


def test_unsupported_domains_have_no_patterns() -> None:
    """대출·연애·선발은 패턴을 만들지 않는다 — 추측 표현 금지."""
    for text in (
        "대출 심사 중이야.",
        "소개팅 날짜가 잡혔어.",
        "청약 추첨 결과를 기다리는 중이야.",
    ):
        assert _facts(text) == [], text


# ── coverage × 게이트 동작 ───────────────────────────────────────


def test_unsupported_domain_bypasses_instead_of_enforcing() -> None:
    """자료 없는 도메인은 게이트를 적용하지 않는다 — UNKNOWN으로 덮지 않는다."""
    action = resolve_gate_action(
        PROCESS_COVERAGE[ProcessFamily.LOAN_PROCESS], has_compatible_active=False
    )
    assert action is EventGateAction.BYPASS_UNSUPPORTED_PROCESS_COVERAGE
    assert action.is_bypass


def test_career_can_confirm_absence() -> None:
    """커리어만 "진행 중인 게 없다"를 확정할 수 있다."""
    action = resolve_gate_action(
        PROCESS_COVERAGE[ProcessFamily.CAREER_OPPORTUNITY], has_compatible_active=False
    )
    assert action is EventGateAction.ENFORCE_LOCAL_ONLY


def test_move_positive_only_bypasses_when_absent() -> None:
    """이사는 있을 때만 안다 — 못 찾았다고 강등하지 않는다."""
    assert resolve_gate_action(
        PROCESS_COVERAGE[ProcessFamily.MOVE_PROCESS], has_compatible_active=False
    ) is EventGateAction.BYPASS_UNSUPPORTED_PROCESS_COVERAGE
    assert resolve_gate_action(
        PROCESS_COVERAGE[ProcessFamily.MOVE_PROCESS], has_compatible_active=True
    ) is EventGateAction.ENFORCE_ACTIVE_TRIGGER


def test_source_unavailable_has_its_own_bypass_reason() -> None:
    """저장소 장애와 자료 부재를 감사에서 구분한다."""
    assert resolve_gate_action(
        ProcessCoverage.SOURCE_UNAVAILABLE, has_compatible_active=False
    ) is EventGateAction.BYPASS_PROCESS_SOURCE_UNAVAILABLE


def test_contract_gate_is_not_opened() -> None:
    """계약은 terminal만 알아서 게이트를 열지 않는다."""
    assert PROCESS_COVERAGE[ProcessFamily.CONTRACT_PROCESS] is (
        ProcessCoverage.TERMINAL_ONLY
    )
    assert not PROCESS_COVERAGE[ProcessFamily.CONTRACT_PROCESS].can_confirm_absence


def test_active_trigger_requires_usable_compatible_process_fact() -> None:
    """`has_compatible_active`가 아무 active로나 채워지지 않는다.

    같은 도메인에 active fact가 하나 있다는 것만으로는 부족하다 — 출처·주체·현재성·
    terminal·의향을 모두 통과해야 한다(사건 family 호환은 P2-2b가 이어서 본다).
    """
    from saju_shared_types.process_fact import (
        EvidenceOrigin,
        ProcessFact,
        SubjectResolution,
    )

    def mk(**over) -> ProcessFact:
        base = dict(
            fact_id="x", subject_id="self",
            subject_resolution=SubjectResolution.RESOLVED,
            process_family=ProcessFamily.MOVE_PROCESS,
            stage=ProcessStage.IN_PROGRESS, status=ProcessStatus.ACTIVE,
            evidence_origin=EvidenceOrigin.CURRENT_TURN_EXPLICIT,
            original_text="이사가 결정되었어",
        )
        base.update(over)
        return ProcessFact(**base)

    rejected = [
        mk(evidence_origin=EvidenceOrigin.ENGINE_INFERRED),   # 엔진 추정
        mk(evidence_origin=EvidenceOrigin.SHADOW),            # shadow
        mk(subject_id="partner-1"),                            # 다른 주체
        mk(current=False),                                     # 과거 사실
        mk(stage=ProcessStage.CANCELLED, status=ProcessStatus.TERMINAL),
        mk(intent_level=IntentLevel.PLANNED_OR_INTENDED),      # 계획
        mk(subject_resolution=SubjectResolution.UNKNOWN),      # 주체 미상
    ]
    assert usable_active_facts(rejected, subject_id="self") == []
    assert len(usable_active_facts([mk(), *rejected], subject_id="self")) == 1
