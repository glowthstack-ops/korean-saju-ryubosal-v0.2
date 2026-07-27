"""명시적 진행 사실 모델 (P2-PROC-1) — 2026-07-27 데굴님 확정.

설계: `doc/v2_2/REVIEW_ACTIVE_PROCESS_CONTRACT.md`

P2 사건 범위 게이트의 예외 근거는 **사용자가 직접 말한 현실 진행 사실**과 **검증된
hard-fact Episode**뿐이다. 엔진이 추정한 상태는 쓰지 않는다 — 쓰면 엔진 추정이 자기
자신의 게이트를 열어주는 순환이 된다.

    "소개팅 날짜가 잡혔어"      → 예외 근거 가능 (사용자 명시)
    RelationshipStage.CONTACT  → 예외 근거 불가 (엔진 추정)

기존 `user_facts` 원장은 개조하지 않는다. 원문·어법 슬롯 저장은 일반 대화 승계에도
쓰이므로 그대로 두고, 이 모델을 **파생 레이어**로 얹는다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ProcessFamily(StrEnum):
    """진행 중인 현실 과정의 종류.

    커리어는 새 추상화를 만들지 않고 기존 3트랙(`OpportunityStage`/`ExitStage`/
    `EntryStage`)에 정렬한다. 같은 커리어라도 `EntryScope`가 다르면 호환 사건이 다르다
    (외부 이직 면접이 내부 승진을 열면 안 된다).
    """

    CAREER_OPPORTUNITY = "CAREER_OPPORTUNITY"
    CAREER_EXIT = "CAREER_EXIT"
    CAREER_ENTRY = "CAREER_ENTRY"

    RELATIONSHIP_CONTACT = "RELATIONSHIP_CONTACT"
    RELATIONSHIP_DATING = "RELATIONSHIP_DATING"
    RELATIONSHIP_COMMITMENT = "RELATIONSHIP_COMMITMENT"

    CONTRACT_PROCESS = "CONTRACT_PROCESS"
    LOAN_PROCESS = "LOAN_PROCESS"
    MOVE_PROCESS = "MOVE_PROCESS"

    SELECTION_PROCESS = "SELECTION_PROCESS"
    ADMISSION_PROCESS = "ADMISSION_PROCESS"


class ProcessStage(StrEnum):
    """과정의 진행 단계. terminal 단계는 `TERMINAL_STAGES`로 따로 묶는다."""

    APPLIED = "APPLIED"
    SCHEDULED = "SCHEDULED"
    IN_REVIEW = "IN_REVIEW"
    INTERVIEWING = "INTERVIEWING"
    NEGOTIATING = "NEGOTIATING"
    RESULT_PENDING = "RESULT_PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    NOTICE_GIVEN = "NOTICE_GIVEN"
    ONBOARDING = "ONBOARDING"

    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    EXPIRED = "EXPIRED"


#: 과정이 끝난 단계 — 활성 예외 근거가 될 수 없다.
TERMINAL_STAGES: frozenset[ProcessStage] = frozenset({
    ProcessStage.COMPLETED,
    ProcessStage.REJECTED,
    ProcessStage.CANCELLED,
    ProcessStage.ABANDONED,
    ProcessStage.EXPIRED,
})


class ProcessStatus(StrEnum):
    """과정이 지금 살아 있는가."""

    ACTIVE = "ACTIVE"
    TERMINAL = "TERMINAL"
    UNKNOWN = "UNKNOWN"


class EvidenceOrigin(StrEnum):
    """이 사실이 어디서 왔는가 — P2 예외 자격을 결정하는 축.

    `ENGINE_INFERRED`·`SHADOW`는 기록은 하되 예외 근거로 쓰지 않는다. 엔진이 추정한
    상태로 게이트를 열면 추정이 자기 자신을 정당화한다.
    """

    CURRENT_TURN_EXPLICIT = "CURRENT_TURN_EXPLICIT"
    LEDGER_EXPLICIT = "LEDGER_EXPLICIT"
    CAREER_HARD_FACT_EPISODE = "CAREER_HARD_FACT_EPISODE"

    ENGINE_INFERRED = "ENGINE_INFERRED"
    SHADOW = "SHADOW"


#: P2 active-process 예외에 투입 가능한 출처 — allowlist다(제외 목록이 아니라).
ALLOWED_EVIDENCE_ORIGINS: frozenset[EvidenceOrigin] = frozenset({
    EvidenceOrigin.CURRENT_TURN_EXPLICIT,
    EvidenceOrigin.LEDGER_EXPLICIT,
    EvidenceOrigin.CAREER_HARD_FACT_EPISODE,
})


class SubjectResolution(StrEnum):
    """이 사실이 누구 것인지 확정됐는가.

    불명확하면 본인으로 추정하지 않는다 — fail closed. 동반자의 대출 심사가 본인
    재물 후보를 여는 것을 막는다.
    """

    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"


class IntentLevel(StrEnum):
    """실행 단계인가, 계획인가, 욕구인가.

    `DESIRE_ONLY`는 애초에 `ProcessFact`를 만들지 않는다(추출기에서 차단). 이 enum은
    추출기가 "왜 만들지 않았는지"를 감사에 남기기 위한 것이다.
    """

    ACTIVE_PROCESS = "ACTIVE_PROCESS"
    PLANNED_OR_INTENDED = "PLANNED_OR_INTENDED"
    DESIRE_ONLY = "DESIRE_ONLY"


class ProcessFact(BaseModel):
    """구조화된 진행 사실 1건.

    `original_text`를 반드시 보존한다 — 정규화 값만 남기면 오분류를 사후 검증할 수 없다.
    """

    fact_id: str
    subject_id: str | None = None
    #: 관계 과정에서 상대가 등록된 동반자인 경우 — pairwise 후보에만 적용한다.
    counterparty_subject_id: str | None = None
    subject_resolution: SubjectResolution = SubjectResolution.UNKNOWN

    process_family: ProcessFamily
    stage: ProcessStage
    status: ProcessStatus
    intent_level: IntentLevel = IntentLevel.ACTIVE_PROCESS
    #: 커리어 전용 — 외부 이직과 내부 승진을 가른다(`EntryScope` 값 문자열).
    entry_scope: str | None = None

    evidence_origin: EvidenceOrigin
    original_text: str
    rule_id: str = ""
    source_turn: int | None = None
    source_ledger_key: str | None = None

    explicit: bool = True
    current: bool = True
    started_at: str | None = None
    ended_at: str | None = None

    def is_usable_exception(self) -> bool:
        """P2 active-process 예외 근거로 쓸 수 있는가.

        Returns:
            출처가 allowlist에 있고, 명시적·현재 사실이며, 주체가 확정됐고,
            단계가 terminal이 아니며 상태가 ACTIVE일 때만 True.
        """
        return (
            self.evidence_origin in ALLOWED_EVIDENCE_ORIGINS
            and self.explicit
            and self.current
            and self.subject_resolution is SubjectResolution.RESOLVED
            and self.status is ProcessStatus.ACTIVE
            and self.stage not in TERMINAL_STAGES
            and self.intent_level is IntentLevel.ACTIVE_PROCESS
        )


class ProcessCoverage(StrEnum):
    """도메인별로 진행 사실을 **얼마나 알 수 있는가**.

    P2 게이트를 적용할지는 후보의 층위가 아니라 이 값이 정한다. 자료가 없는 도메인에서
    "active를 못 찾았다"를 "진행 중인 게 없다"로 읽으면, 사용자가 명시한 사실이 무시되는
    회귀가 난다(설계 §8-1).
    """

    AUTHORITATIVE = "AUTHORITATIVE"  # active 없음을 확정할 수 있다
    POSITIVE_ONLY = "POSITIVE_ONLY"  # 있을 때만 안다 — 없음은 모른다
    TERMINAL_ONLY = "TERMINAL_ONLY"  # 닫는 것만 안다
    UNSUPPORTED = "UNSUPPORTED"  # 판단 근거 없음
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"  # 저장소 장애·파싱 실패

    @property
    def can_confirm_absence(self) -> bool:
        """active가 없다는 것을 이 도메인에서 확정할 수 있는가."""
        return self is ProcessCoverage.AUTHORITATIVE


class EventGateAction(StrEnum):
    """게이트가 이 후보에 무엇을 했는가 — 감사용.

    `BYPASS_*`는 "게이트를 적용하지 않았다"이지 "후보가 정상이다"가 아니다.
    어느 도메인에서 왜 미적용인지 구분하려고 사유별로 나눈다.
    """

    ENFORCE_MAJOR = "ENFORCE_MAJOR"
    ENFORCE_ACTIVE_TRIGGER = "ENFORCE_ACTIVE_TRIGGER"
    ENFORCE_LOCAL_ONLY = "ENFORCE_LOCAL_ONLY"
    BYPASS_UNSUPPORTED_PROCESS_COVERAGE = "BYPASS_UNSUPPORTED_PROCESS_COVERAGE"
    BYPASS_PROCESS_SOURCE_UNAVAILABLE = "BYPASS_PROCESS_SOURCE_UNAVAILABLE"

    @property
    def is_bypass(self) -> bool:
        """기존 동작을 유지했는가."""
        return self.value.startswith("BYPASS_")


#: 도메인별 1차 coverage (2026-07-27 데굴님 확정 — 설계 §8-2).
#: 자료가 확보되면 TERMINAL_ONLY → POSITIVE_ONLY → AUTHORITATIVE로 단계 승격한다.
PROCESS_COVERAGE: dict[ProcessFamily, ProcessCoverage] = {
    ProcessFamily.CAREER_OPPORTUNITY: ProcessCoverage.AUTHORITATIVE,
    ProcessFamily.CAREER_EXIT: ProcessCoverage.AUTHORITATIVE,
    ProcessFamily.CAREER_ENTRY: ProcessCoverage.AUTHORITATIVE,
    ProcessFamily.MOVE_PROCESS: ProcessCoverage.POSITIVE_ONLY,
    ProcessFamily.CONTRACT_PROCESS: ProcessCoverage.TERMINAL_ONLY,
    ProcessFamily.LOAN_PROCESS: ProcessCoverage.UNSUPPORTED,
    ProcessFamily.RELATIONSHIP_CONTACT: ProcessCoverage.UNSUPPORTED,
    ProcessFamily.RELATIONSHIP_DATING: ProcessCoverage.UNSUPPORTED,
    ProcessFamily.RELATIONSHIP_COMMITMENT: ProcessCoverage.UNSUPPORTED,
    ProcessFamily.SELECTION_PROCESS: ProcessCoverage.UNSUPPORTED,
    ProcessFamily.ADMISSION_PROCESS: ProcessCoverage.UNSUPPORTED,
}


def usable_active_facts(
    facts: list[ProcessFact], *, subject_id: str | None
) -> list[ProcessFact]:
    """`has_compatible_active`를 만들 수 있는 후보만 걸러낸다.

    `resolve_gate_action`은 bool을 받으므로, 그 bool이 **아무 active로나** 채워지지
    않게 하는 것이 이 함수의 책임이다. 출처·주체·현재성·terminal·의향을 여기서 모두
    통과시키고, 사건 family 호환은 P2-2b가 이어서 판정한다.

    Args:
        facts: 정규화된 진행 사실.
        subject_id: 후보의 주체. 불일치 사실은 제외한다.

    Returns:
        `is_usable_exception()`을 통과하고 주체가 일치하는 사실만.
    """
    return [
        f for f in facts
        if f.is_usable_exception() and f.subject_id == subject_id
    ]


def resolve_gate_action(
    coverage: ProcessCoverage, *, has_compatible_active: bool
) -> EventGateAction:
    """coverage × active 발견 여부 → 게이트 동작(설계 §8-1 표).

    Args:
        coverage: 그 후보가 속한 도메인의 진행 사실 관측 수준.
        has_compatible_active: 호환되는 활성 process를 찾았는가.

    Returns:
        active를 찾았으면 항상 `ENFORCE_ACTIVE_TRIGGER`. 못 찾은 경우
        `AUTHORITATIVE`만 `ENFORCE_LOCAL_ONLY`로 강제하고, 나머지는 BYPASS다.
    """
    if has_compatible_active:
        return EventGateAction.ENFORCE_ACTIVE_TRIGGER
    if coverage is ProcessCoverage.SOURCE_UNAVAILABLE:
        return EventGateAction.BYPASS_PROCESS_SOURCE_UNAVAILABLE
    if coverage.can_confirm_absence:
        return EventGateAction.ENFORCE_LOCAL_ONLY
    return EventGateAction.BYPASS_UNSUPPORTED_PROCESS_COVERAGE


class ProcessMatchResult(StrEnum):
    """후보 하나에 대해 진행 사실이 어떻게 판정됐는가.

    boolean으로 뭉개면 "근거가 없어서"와 "저장소를 못 읽어서"를 구분할 수 없다.
    후자를 없음으로 단정하면 진행 중인 사건이 조용히 강등된다.
    """

    COMPATIBLE_ACTIVE = "COMPATIBLE_ACTIVE"
    INCOMPATIBLE_EVENT = "INCOMPATIBLE_EVENT"
    TERMINAL_PROCESS = "TERMINAL_PROCESS"
    STALE_OR_NOT_CURRENT = "STALE_OR_NOT_CURRENT"
    DESIRE_ONLY = "DESIRE_ONLY"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    NO_EVIDENCE = "NO_EVIDENCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

    @property
    def opens_exception(self) -> bool:
        """이 결과가 minor-only 후보의 예외를 여는가."""
        return self is ProcessMatchResult.COMPATIBLE_ACTIVE

    @property
    def is_fail_safe(self) -> bool:
        """판정 불가라 기존 동작을 유지해야 하는가.

        저장소 장애·파싱 실패는 "진행 사실 없음"이 아니다. 이 경우 게이트를 적용하지
        않고 기존 동작으로 되돌린다(EventScope.UNKNOWN).
        """
        return self is ProcessMatchResult.SOURCE_UNAVAILABLE


def supersede(facts: list[ProcessFact]) -> list[ProcessFact]:
    """같은 (subject, family)에서 최신 terminal 사실이 과거 active 사실을 종료시킨다.

    우선순위는 현재 발화 > 원장 > Episode다. 원장에 '대출 심사 중'이 있어도 현재 발화의
    '대출은 거절됐어'가 이긴다.

    Args:
        facts: 정규화된 진행 사실 목록(출처 혼재 가능).

    Returns:
        (subject, family)별로 한 건씩 남긴 목록. 입력 순서는 보존하지 않는다.
    """
    priority = {
        EvidenceOrigin.CURRENT_TURN_EXPLICIT: 0,
        EvidenceOrigin.LEDGER_EXPLICIT: 1,
        EvidenceOrigin.CAREER_HARD_FACT_EPISODE: 2,
        EvidenceOrigin.ENGINE_INFERRED: 3,
        EvidenceOrigin.SHADOW: 4,
    }
    best: dict[tuple[str | None, ProcessFamily], ProcessFact] = {}
    ordered = sorted(
        facts,
        key=lambda x: (priority.get(x.evidence_origin, 9), -(x.source_turn or 0)),
    )
    for fact in ordered:
        key = (fact.subject_id, fact.process_family)
        if key not in best:  # 우선순위 높은 출처가 먼저 온다 — 첫 승자를 유지한다
            best[key] = fact
    return list(best.values())


class ExtractedProcessFact(BaseModel):
    """추출기 산출물 — 원문·규칙 id를 함께 남겨 사후 검증이 가능하게 한다."""

    original_text: str
    source_slot: str
    rule_id: str
    normalized_fact: ProcessFact | None = None
    #: 사실을 만들지 않은 경우의 사유(욕구 진술 등) — 감사용.
    skipped_reason: IntentLevel | None = Field(default=None)
