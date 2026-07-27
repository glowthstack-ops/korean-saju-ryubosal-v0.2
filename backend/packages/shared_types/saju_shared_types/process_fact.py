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


class CareerEntryScope(StrEnum):
    """커리어 진입 범위 — 외부 이직과 내부 이동을 가른다.

    `career_transition.EntryScope`의 값을 그대로 미러링한다. 엔진 점수 경로가 커리어
    모듈을 import할 수 없어(`test_career_shadow_drift`) 중립 enum으로 둔다. 값이
    같으므로 호출자 경계에서 무손실 변환된다.
    """

    EXTERNAL_EMPLOYER = "external_employer"
    INTERNAL_ROLE = "internal_role"
    INTERNAL_DEPARTMENT = "internal_department"


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
    #: 같은 family 안에서 서로 다른 건을 가르는 키(커리어는 episode_id).
    #: 없으면 terminal이 무엇을 닫을 수 있는지가 정책에 따라 달라진다(SUPERSESSION_POLICY).
    process_instance_key: str | None = None

    evidence_origin: EvidenceOrigin
    original_text: str
    rule_id: str = ""
    source_turn: int | None = None
    #: 같은 턴 안에서의 절 순서 — "이사를 마쳤어. 다른 집으로 다시 이사 결정했어"에서
    #: 앞 절의 terminal이 뒤 절의 새 active를 지우지 않게 한다.
    source_order: int = 0
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
    #: 부분 지원 도메인에서 아무것도 못 찾음 — "없다"가 아니라 "모른다"다.
    BYPASS_INCOMPLETE_COVERAGE = "BYPASS_INCOMPLETE_COVERAGE"
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
    if coverage in (ProcessCoverage.POSITIVE_ONLY, ProcessCoverage.TERMINAL_ONLY):
        # 부분 지원 — 못 찾은 것을 "없다"로 읽지 않는다.
        return EventGateAction.BYPASS_INCOMPLETE_COVERAGE
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


class SupersessionPolicy(StrEnum):
    """terminal 사실이 **무엇을 닫을 수 있는가** — 도메인마다 다르다.

    다중 인스턴스 가능성이 기준이다. 계약은 임대차·인테리어·대출약정·사업계약이 동시에
    존재할 수 있어, 인스턴스 없는 "계약서 다 썼고"가 전부를 닫으면 안 된다.
    """

    INSTANCE_REQUIRED = "INSTANCE_REQUIRED"  # 키가 있어야만 닫는다(커리어)
    SINGLE_ACTIVE_FAMILY = "SINGLE_ACTIVE_FAMILY"  # 키 없어도 family 단위로 닫는다(이사)
    NO_UNKEYED_SUPERSESSION = "NO_UNKEYED_SUPERSESSION"  # 키 없으면 아무것도 안 닫는다


SUPERSESSION_POLICY: dict[ProcessFamily, SupersessionPolicy] = {
    ProcessFamily.CAREER_OPPORTUNITY: SupersessionPolicy.INSTANCE_REQUIRED,
    ProcessFamily.CAREER_EXIT: SupersessionPolicy.INSTANCE_REQUIRED,
    ProcessFamily.CAREER_ENTRY: SupersessionPolicy.INSTANCE_REQUIRED,
    ProcessFamily.MOVE_PROCESS: SupersessionPolicy.SINGLE_ACTIVE_FAMILY,
    ProcessFamily.CONTRACT_PROCESS: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
    ProcessFamily.LOAN_PROCESS: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
    ProcessFamily.RELATIONSHIP_CONTACT: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
    ProcessFamily.RELATIONSHIP_DATING: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
    ProcessFamily.RELATIONSHIP_COMMITMENT: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
    ProcessFamily.SELECTION_PROCESS: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
    ProcessFamily.ADMISSION_PROCESS: SupersessionPolicy.NO_UNKEYED_SUPERSESSION,
}


class SupersessionResult(StrEnum):
    """왜 닫혔는지 / 왜 남았는지 — 나중에 누락 문장이 나왔을 때 원인을 가른다.

    "추출 실패"인지 "인스턴스 매칭 실패"인지 "의도적 보수 정책"인지를 구분할 수 있어야
    한다. 결과만 남기면 셋이 전부 같은 모습으로 보인다.
    """

    SUPERSEDED_EXACT_INSTANCE = "SUPERSEDED_EXACT_INSTANCE"
    SUPERSEDED_SINGLE_ACTIVE_FAMILY = "SUPERSEDED_SINGLE_ACTIVE_FAMILY"
    PRESERVED_DIFFERENT_INSTANCE = "PRESERVED_DIFFERENT_INSTANCE"
    PRESERVED_MISSING_INSTANCE_KEY = "PRESERVED_MISSING_INSTANCE_KEY"
    PRESERVED_DIFFERENT_SUBJECT = "PRESERVED_DIFFERENT_SUBJECT"
    PRESERVED_DIFFERENT_SCOPE = "PRESERVED_DIFFERENT_SCOPE"


#: terminal이 인스턴스 키 없이 닫으려다 보류된 경우의 감사 코드.
SKIP_TERMINAL_SUPERSESSION_MISSING_INSTANCE_KEY = (
    "SKIP_TERMINAL_SUPERSESSION_MISSING_INSTANCE_KEY"
)


def _origin_rank(origin: EvidenceOrigin) -> int:
    """현재 발화 > 원장 > Episode. 엔진 추정·shadow는 맨 뒤."""
    return {
        EvidenceOrigin.CURRENT_TURN_EXPLICIT: 0,
        EvidenceOrigin.LEDGER_EXPLICIT: 1,
        EvidenceOrigin.CAREER_HARD_FACT_EPISODE: 2,
        EvidenceOrigin.ENGINE_INFERRED: 3,
        EvidenceOrigin.SHADOW: 4,
    }.get(origin, 9)


def _can_close(terminal: ProcessFact, target: ProcessFact) -> SupersessionResult:
    """terminal 사실이 target active 사실을 닫을 수 있는가(정책 적용).

    Args:
        terminal: 종료를 주장하는 사실.
        target: 닫힐 후보인 기존 사실.

    Returns:
        닫는 경우 `SUPERSEDED_*`, 남기는 경우 `PRESERVED_*`. 사유를 반드시 남긴다.
    """
    if terminal.subject_id != target.subject_id:
        return SupersessionResult.PRESERVED_DIFFERENT_SUBJECT
    if terminal.entry_scope != target.entry_scope:
        return SupersessionResult.PRESERVED_DIFFERENT_SCOPE
    key, target_key = terminal.process_instance_key, target.process_instance_key
    if key is not None and target_key is not None:
        return (
            SupersessionResult.SUPERSEDED_EXACT_INSTANCE if key == target_key
            else SupersessionResult.PRESERVED_DIFFERENT_INSTANCE
        )
    policy = SUPERSESSION_POLICY.get(
        terminal.process_family, SupersessionPolicy.NO_UNKEYED_SUPERSESSION
    )
    if policy is SupersessionPolicy.SINGLE_ACTIVE_FAMILY:
        # 이사는 한 사람에게 동시 2건이 드물고, 추출기가 건 구분 정보를 만들지 못한다.
        return SupersessionResult.SUPERSEDED_SINGLE_ACTIVE_FAMILY
    # 커리어(INSTANCE_REQUIRED)와 계약·대출·연애·선발은 키 없이 닫지 않는다 —
    # 다중 인스턴스가 흔해 "A는 떨어졌지만 B는 대기 중"을 지울 수 있다.
    return SupersessionResult.PRESERVED_MISSING_INSTANCE_KEY


def supersede(
    facts: list[ProcessFact],
) -> tuple[list[ProcessFact], list[tuple[ProcessFact, SupersessionResult]]]:
    """terminal 사실로 기존 active 사실을 정책에 맞게 종료한다.

    우선순위는 현재 발화 > 원장 > Episode다. 다만 **다른 인스턴스·다른 주체·다른
    entry_scope는 서로를 닫지 않는다** — "A회사에서는 떨어졌지만 다른 회사 결과를
    기다려"에서 REJECTED가 모든 커리어 기회를 종료하면 안 된다.

    Args:
        facts: 정규화된 진행 사실(출처 혼재 가능).

    Returns:
        (살아남은 사실, [(닫힌 사실, 사유)]). terminal 사실 자체는 항상 보존된다 —
        기록이 사라지면 왜 닫혔는지 추적할 수 없다.
    """
    ordered = sorted(
        facts, key=lambda f: (_origin_rank(f.evidence_origin), -(f.source_turn or 0))
    )
    terminals = [f for f in ordered if f.status is ProcessStatus.TERMINAL]
    survivors: list[ProcessFact] = []
    closed: list[tuple[ProcessFact, SupersessionResult]] = []
    for fact in ordered:
        if fact.status is ProcessStatus.TERMINAL:
            survivors.append(fact)  # terminal 기록은 유지한다
            continue
        verdict: SupersessionResult | None = None
        for term in terminals:
            if term.process_family is not fact.process_family:
                continue
            # 뒤에 온 active를 앞선 terminal이 지우지 않게 한다(턴 → 절 순서).
            if (fact.source_turn or 0, fact.source_order) > (
                term.source_turn or 0, term.source_order
            ):
                continue
            result = _can_close(term, fact)
            if result in (
                SupersessionResult.SUPERSEDED_EXACT_INSTANCE,
                SupersessionResult.SUPERSEDED_SINGLE_ACTIVE_FAMILY,
            ):
                verdict = result
                break
        if verdict is None:
            survivors.append(fact)
        else:
            closed.append((fact, verdict))
    return survivors, closed


class CareerProcessSnapshot(BaseModel):
    """커리어 Episode → events 계층 경계 DTO (중립).

    커리어 타입을 참조하지 않고, 원시 문자열도 받지 않는다. 변환은 커리어를 볼 수 있는
    서비스 경계(`chat_service`·`report_service`)가 하고, 여기서부터는 중립 모델만 흐른다.

        career domain model
          → (허용된 호출자 경계에서) CareerProcessSnapshot
          → adapt_career_snapshot()
          → ProcessFact
    """

    episode_id: str
    subject_id: str | None
    process_family: ProcessFamily
    stage: ProcessStage
    entry_scope: CareerEntryScope | None = None
    #: `OBSERVABLE_HARD_FACT`를 통과했는가 — 호출자가 판정해 넣는다.
    observable_hard_fact: bool = True
    current: bool = True
    source_turn: int | None = None
    source_order: int = 0
    original_text: str = ""


class ExtractedProcessFact(BaseModel):
    """추출기 산출물 — 원문·규칙 id를 함께 남겨 사후 검증이 가능하게 한다."""

    original_text: str
    source_slot: str
    rule_id: str
    normalized_fact: ProcessFact | None = None
    #: 사실을 만들지 않은 경우의 사유(욕구 진술 등) — 감사용.
    skipped_reason: IntentLevel | None = Field(default=None)
