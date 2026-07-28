"""진행 사실 ↔ 사건 후보 호환 판정 (P2-2b) — 중앙 SSOT, fail-closed.

설계: `doc/v2_2/REVIEW_ACTIVE_PROCESS_CONTRACT.md` · `REVIEW_PROCESS_FACT_PATTERNS.md`

`EventFamily` 중간 계층을 신설하지 않는다. 지금 만들면 "어떤 사건끼리 같은 family인가"
라는 별도 의미 체계를 추가로 감수해야 하는데, P2-2b의 목적은 분류 체계 확장이 아니라
**진행 중인 현실 과정이 어떤 기존 사건 후보만 예외적으로 열 수 있는지 제한하는 것**이다.

대신 `EventKeyV2` 21개를 전수 감사하고 `ProcessFamily + Stage + EntryScope →
명시적 event_key allowlist`로 판정한다.

**도메인 일치는 호환이 아니다.**

    대출 심사 중  → contract_document 허용 / windfall 불허
                   둘 다 도메인은 재물이다 — 도메인만으로는 못 가른다

그래서 `EVENT_DOMAIN` 비교나 키 이름 문자열 매칭으로 호환을 추론하지 않는다.
중앙 allowlist에 명시된 조합만 호환이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from saju_shared_types.event_engine import EventKeyV2, EventScope
from saju_shared_types.process_fact import (
    PROCESS_COVERAGE,
    EventGateAction,
    ProcessCoverage,
    ProcessFact,
    ProcessFamily,
    ProcessSourceStatus,
    ProcessStage,
    resolve_gate_action,
)

from .layer_evidence_scope import derive_event_scope


class EventProcessAuditStatus(StrEnum):
    """`EventKeyV2` 21개 각각이 P2 예외에 대해 어떤 상태인가.

    새 event key가 추가되면 감사표 불변식 테스트가 실패해 호환성을 명시적으로 감수하게
    된다 — 중간 family 없이도 누락을 막는 장치다.
    """

    ALLOWED_BY_RULE = "ALLOWED_BY_RULE"  # 어떤 process 규칙에서 허용
    NOT_PROCESS_GATED = "NOT_PROCESS_GATED"  # 진행 과정으로 열 사건이 아님
    COVERAGE_PENDING = "COVERAGE_PENDING"  # 자료 부족으로 보류(coverage=UNSUPPORTED)
    REVIEW_PENDING = "REVIEW_PENDING"  # 의미가 모호해 감수 보류


#: 21개 전수 감사 — 이 표가 비어 있는 키가 있으면 테스트가 실패한다.
EVENT_KEY_PROCESS_AUDIT: dict[EventKeyV2, EventProcessAuditStatus] = {
    # 커리어 — coverage AUTHORITATIVE. EntryScope로 외부/내부를 가른다.
    EventKeyV2.CAREER_CHANGE: EventProcessAuditStatus.ALLOWED_BY_RULE,
    EventKeyV2.JOB_GAIN: EventProcessAuditStatus.ALLOWED_BY_RULE,
    EventKeyV2.PROMOTION: EventProcessAuditStatus.ALLOWED_BY_RULE,
    # 이사 — coverage POSITIVE_ONLY. 실행·일정만 열고 재물은 열지 않는다.
    EventKeyV2.RELOCATION: EventProcessAuditStatus.ALLOWED_BY_RULE,
    # 계약 — coverage TERMINAL_ONLY. 닫기만 하고 열지 않으므로 allowlist 없음.
    EventKeyV2.CONTRACT_DOCUMENT: EventProcessAuditStatus.COVERAGE_PENDING,
    # 대출·연애·선발 — 추출기 없음(UNSUPPORTED). 미리 추측해 넣지 않는다.
    EventKeyV2.WEALTH_CHANGE: EventProcessAuditStatus.COVERAGE_PENDING,
    EventKeyV2.RELATIONSHIP_CHANGE: EventProcessAuditStatus.COVERAGE_PENDING,
    EventKeyV2.NEW_RELATIONSHIP: EventProcessAuditStatus.COVERAGE_PENDING,
    EventKeyV2.MARRIAGE_SIGNAL: EventProcessAuditStatus.COVERAGE_PENDING,
    EventKeyV2.EDUCATION_ADMISSION: EventProcessAuditStatus.COVERAGE_PENDING,
    # 진행 과정으로 여는 사건이 아니다 — 우연·상태·외부 요인이 주도한다.
    EventKeyV2.WINDFALL: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.HEALTH_ATTENTION: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.SOCIAL_CONFLICT: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.LEGAL_CONFLICT: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.PREPARATION_DELAY: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.CREATIVE_OUTPUT: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.PUBLIC_EXPOSURE: EventProcessAuditStatus.NOT_PROCESS_GATED,
    EventKeyV2.CHILDBIRTH: EventProcessAuditStatus.NOT_PROCESS_GATED,
    # 의미가 모호해 감수 보류 — 창업·확장이 커리어 이직 과정과 겹치는지 미확정.
    EventKeyV2.BUSINESS_START: EventProcessAuditStatus.REVIEW_PENDING,
    EventKeyV2.BUSINESS_EXPANSION: EventProcessAuditStatus.REVIEW_PENDING,
    EventKeyV2.EDUCATION_COMPLETION: EventProcessAuditStatus.REVIEW_PENDING,
}


@dataclass(frozen=True)
class ProcessCompatibilityRule:
    """한 진행 과정이 열 수 있는 사건 후보의 명시적 목록."""

    rule_id: str
    process_family: ProcessFamily
    active_stages: frozenset[ProcessStage]
    #: None이면 scope를 보지 않는다. 값이 있으면 그 scope에서만 성립한다.
    entry_scopes: frozenset[str] | None
    allowed_event_keys: frozenset[EventKeyV2]


#: 1차 개방 범위 — coverage가 AUTHORITATIVE·POSITIVE_ONLY인 도메인만.
#: 계약(TERMINAL_ONLY)은 닫기만 하므로 active 규칙이 없고, 대출·연애·선발은
#: 추출기가 없어 추측 규칙을 넣지 않는다.
PROCESS_EVENT_COMPATIBILITY: tuple[ProcessCompatibilityRule, ...] = (
    ProcessCompatibilityRule(
        rule_id="CAREER_EXTERNAL_OPPORTUNITY",
        process_family=ProcessFamily.CAREER_OPPORTUNITY,
        active_stages=frozenset({
            ProcessStage.APPLIED,
            ProcessStage.IN_REVIEW,
            ProcessStage.INTERVIEWING,
            ProcessStage.RESULT_PENDING,
            ProcessStage.NEGOTIATING,
            ProcessStage.APPROVED,
        }),
        entry_scopes=frozenset({"external_employer"}),
        allowed_event_keys=frozenset({
            EventKeyV2.JOB_GAIN,
            EventKeyV2.CAREER_CHANGE,
        }),
    ),
    ProcessCompatibilityRule(
        rule_id="CAREER_INTERNAL_PROMOTION",
        process_family=ProcessFamily.CAREER_OPPORTUNITY,
        active_stages=frozenset({
            ProcessStage.IN_REVIEW,
            ProcessStage.INTERVIEWING,
            ProcessStage.RESULT_PENDING,
            ProcessStage.NEGOTIATING,
            ProcessStage.APPROVED,
        }),
        entry_scopes=frozenset({"internal_role", "internal_department"}),
        allowed_event_keys=frozenset({EventKeyV2.PROMOTION}),
    ),
    ProcessCompatibilityRule(
        rule_id="CAREER_EXIT",
        process_family=ProcessFamily.CAREER_EXIT,
        active_stages=frozenset({
            ProcessStage.IN_PROGRESS,
            ProcessStage.NOTICE_GIVEN,
            ProcessStage.NEGOTIATING,
        }),
        entry_scopes=None,
        allowed_event_keys=frozenset({EventKeyV2.CAREER_CHANGE}),
    ),
    ProcessCompatibilityRule(
        rule_id="CAREER_ENTRY_EXTERNAL",
        process_family=ProcessFamily.CAREER_ENTRY,
        active_stages=frozenset({
            ProcessStage.RESULT_PENDING,
            ProcessStage.SCHEDULED,
            ProcessStage.APPROVED,
            ProcessStage.ONBOARDING,
            ProcessStage.IN_PROGRESS,
        }),
        entry_scopes=frozenset({"external_employer"}),
        allowed_event_keys=frozenset({
            EventKeyV2.JOB_GAIN,
            EventKeyV2.CAREER_CHANGE,
        }),
    ),
    ProcessCompatibilityRule(
        rule_id="CAREER_ENTRY_INTERNAL",
        process_family=ProcessFamily.CAREER_ENTRY,
        active_stages=frozenset({
            ProcessStage.RESULT_PENDING,
            ProcessStage.SCHEDULED,
            ProcessStage.APPROVED,
            ProcessStage.ONBOARDING,
            ProcessStage.IN_PROGRESS,
        }),
        entry_scopes=frozenset({"internal_role", "internal_department"}),
        allowed_event_keys=frozenset({EventKeyV2.PROMOTION}),
    ),
    ProcessCompatibilityRule(
        rule_id="MOVE_EXECUTION",
        process_family=ProcessFamily.MOVE_PROCESS,
        active_stages=frozenset({
            ProcessStage.IN_PROGRESS,
            ProcessStage.SCHEDULED,
        }),
        entry_scopes=None,
        # 이사 실행·일정만. 계약 성사 전반·부동산 횡재·재물 증가는 열지 않는다.
        allowed_event_keys=frozenset({EventKeyV2.RELOCATION}),
    ),
)


class ProcessCompatibilityResult(StrEnum):
    """왜 호환/불호환인가 — 같은 도메인인데 예외가 안 열린 이유를 설명할 수 있어야 한다."""

    COMPATIBLE = "COMPATIBLE"
    FAMILY_MISMATCH = "FAMILY_MISMATCH"
    STAGE_MISMATCH = "STAGE_MISMATCH"
    ENTRY_SCOPE_MISMATCH = "ENTRY_SCOPE_MISMATCH"
    #: 규칙이 scope를 요구하는데 사실에 scope가 **없다**. `MISMATCH`(명시된 scope가
    #: 규칙과 다름)와 구분한다 — 이건 판정 실패가 아니라 **판정 입력 부재**이므로
    #: `ENFORCE_LOCAL_ONLY`가 아니라 coverage bypass다(F1 — entry_scope producer 부재).
    ENTRY_SCOPE_UNAVAILABLE = "ENTRY_SCOPE_UNAVAILABLE"
    EVENT_KEY_NOT_ALLOWED = "EVENT_KEY_NOT_ALLOWED"
    PROCESS_NOT_USABLE = "PROCESS_NOT_USABLE"
    COVERAGE_BYPASS = "COVERAGE_BYPASS"

    @property
    def opens_exception(self) -> bool:
        """이 결과가 minor-only 후보의 예외를 여는가."""
        return self is ProcessCompatibilityResult.COMPATIBLE

    @property
    def blocks_measurement(self) -> bool:
        """이 결과가 active-process 판정 자체를 불가능하게 만드는가.

        `0건`(진행 사실이 없었다)과 `측정 불가`(판정 입력이 없었다)를 섞지 않기 위한 축이다.
        """
        return self is ProcessCompatibilityResult.ENTRY_SCOPE_UNAVAILABLE


def match_process_to_event(
    process: ProcessFact, event_key: EventKeyV2
) -> ProcessCompatibilityResult:
    """진행 사실 하나가 사건 후보 하나를 열 수 있는지 판정한다(fail-closed).

    도메인 일치·키 이름 유사성으로 추론하지 않는다. `PROCESS_EVENT_COMPATIBILITY`에
    명시된 조합만 호환이다.

    Args:
        process: 정규화된 진행 사실.
        event_key: 후보의 사건 키.

    Returns:
        호환이면 `COMPATIBLE`, 아니면 가장 먼저 걸린 불일치 사유. 규칙에 도달하지
        못한 경우 `EVENT_KEY_NOT_ALLOWED`(기본 불허)다.
    """
    if not process.is_usable_exception():
        return ProcessCompatibilityResult.PROCESS_NOT_USABLE
    coverage = PROCESS_COVERAGE.get(
        process.process_family, ProcessCoverage.UNSUPPORTED
    )
    if coverage in (ProcessCoverage.UNSUPPORTED, ProcessCoverage.TERMINAL_ONLY):
        return ProcessCompatibilityResult.COVERAGE_BYPASS

    verdict = ProcessCompatibilityResult.FAMILY_MISMATCH
    for rule in PROCESS_EVENT_COMPATIBILITY:
        if rule.process_family is not process.process_family:
            continue
        verdict = _demote(verdict, ProcessCompatibilityResult.STAGE_MISMATCH)
        if process.stage not in rule.active_stages:
            continue
        if rule.entry_scopes is not None and process.entry_scope is None:
            # 사실이 틀린 게 아니라 scope를 만들어 주는 producer가 없다(F1).
            verdict = _demote(
                verdict, ProcessCompatibilityResult.ENTRY_SCOPE_UNAVAILABLE
            )
            continue
        verdict = _demote(verdict, ProcessCompatibilityResult.ENTRY_SCOPE_MISMATCH)
        if rule.entry_scopes is not None and process.entry_scope not in rule.entry_scopes:
            continue
        verdict = _demote(verdict, ProcessCompatibilityResult.EVENT_KEY_NOT_ALLOWED)
        if event_key in rule.allowed_event_keys:
            return ProcessCompatibilityResult.COMPATIBLE
    return verdict


#: 불일치 사유의 구체성 순서 — 더 깊이 통과한 사유를 남긴다.
_SPECIFICITY: dict[ProcessCompatibilityResult, int] = {
    ProcessCompatibilityResult.FAMILY_MISMATCH: 0,
    ProcessCompatibilityResult.STAGE_MISMATCH: 1,
    # 한 사실의 entry_scope는 하나뿐이라 UNAVAILABLE 과 MISMATCH 가 동시에 나오지
    # 않는다(None 이면 전자만, 값이 있으면 후자만). 같은 깊이로 둔다.
    ProcessCompatibilityResult.ENTRY_SCOPE_UNAVAILABLE: 2,
    ProcessCompatibilityResult.ENTRY_SCOPE_MISMATCH: 2,
    ProcessCompatibilityResult.EVENT_KEY_NOT_ALLOWED: 3,
}


def _demote(
    current: ProcessCompatibilityResult, candidate: ProcessCompatibilityResult
) -> ProcessCompatibilityResult:
    """더 깊은 단계까지 통과한 사유로 갱신한다(감사 설명력 확보)."""
    return (
        candidate
        if _SPECIFICITY.get(candidate, -1) > _SPECIFICITY.get(current, -1)
        else current
    )


@dataclass(frozen=True)
class ActiveProcessMatch:
    """어떤 현실 사실이 이 후보의 예외를 열었는가 — boolean만 남기지 않는다."""

    process_fact_id: str
    process_family: ProcessFamily
    stage: ProcessStage
    entry_scope: str | None
    event_key: EventKeyV2
    compatibility_rule_id: str
    evidence_origin: str


#: 대표 근거 선택 순서 — 임의 선택하지 않고 결정적으로 고른다.
_ORIGIN_PRIORITY: dict[str, int] = {
    "CURRENT_TURN_EXPLICIT": 0,
    "LEDGER_EXPLICIT": 1,
    "CAREER_HARD_FACT_EPISODE": 2,
}


def _matching_rule_id(process: ProcessFact, event_key: EventKeyV2) -> str:
    """호환을 성립시킨 규칙 id — 감사에서 근거를 특정한다."""
    for rule in PROCESS_EVENT_COMPATIBILITY:
        if (
            rule.process_family is process.process_family
            and process.stage in rule.active_stages
            and (
                rule.entry_scopes is None
                or (process.entry_scope or "") in rule.entry_scopes
            )
            and event_key in rule.allowed_event_keys
        ):
            return rule.rule_id
    return ""


def find_active_process_matches(
    facts: list[ProcessFact], event_key: EventKeyV2, *, subject_id: str | None
) -> list[ActiveProcessMatch]:
    """이 후보를 열 수 있는 진행 사실 전부를 근거와 함께 반환한다.

    여러 사실이 동시에 호환되면 하나를 임의로 고르지 않고 모두 보존한다. 대표 근거가
    필요하면 현재 발화 > 원장 > Episode > source_order 최신 순으로 정렬된 첫 건을 쓴다.
    """
    matches = [
        ActiveProcessMatch(
            process_fact_id=f.fact_id,
            process_family=f.process_family,
            stage=f.stage,
            entry_scope=f.entry_scope,
            event_key=event_key,
            compatibility_rule_id=_matching_rule_id(f, event_key),
            evidence_origin=str(f.evidence_origin),
        )
        for f in facts
        if f.subject_id == subject_id
        and match_process_to_event(f, event_key).opens_exception
    ]
    by_id = {f.fact_id: f for f in facts}
    return sorted(
        matches,
        key=lambda m: (
            _ORIGIN_PRIORITY.get(m.evidence_origin, 9),
            -(by_id[m.process_fact_id].source_order),
        ),
    )


def has_compatible_active(
    facts: list[ProcessFact], event_key: EventKeyV2, *, subject_id: str | None
) -> bool:
    """이 후보를 열 수 있는 진행 사실이 하나라도 있는가.

    `resolve_gate_action`의 입력이다 — 아무 active로나 채워지지 않도록 주체 일치와
    호환 판정을 모두 통과한 사실만 센다.
    """
    return bool(find_active_process_matches(facts, event_key, subject_id=subject_id))


def has_unmeasurable_entry_scope(
    facts: list[ProcessFact], event_key: EventKeyV2, *, subject_id: str | None
) -> bool:
    """이 후보의 판정이 `entry_scope` 부재로 **측정 불가**인가.

    사실이 family·stage까지는 규칙에 닿았는데 scope가 없어서 멈춘 경우다. 이때
    "호환 사실 0건"을 "진행 중인 게 없다"로 읽으면 안 된다 — 자료가 없는 것이다(F1).

    Args:
        facts: 해소된 진행 사실 목록.
        event_key: 후보의 사건 키.
        subject_id: 후보의 주체.

    Returns:
        scope 부재로 판정이 막힌 사실이 하나라도 있으면 True.
    """
    return any(
        match_process_to_event(f, event_key).blocks_measurement
        for f in facts
        if f.subject_id == subject_id
    )


@dataclass(frozen=True)
class CandidateProcessScope:
    """후보 하나의 최종 범위 판정 + 근거 (P2-2c).

    `raw_event_scope`와 `gate_action`을 분리해 보존한다 — 전자는 "층위·진행 사실이
    말하는 범위", 후자는 "그 범위를 실제로 적용했는가"다. 자료가 없는 도메인에서는
    범위는 산출되지만 적용은 되지 않는다.
    """

    raw_event_scope: EventScope
    gate_action: EventGateAction
    matches: tuple[ActiveProcessMatch, ...] = ()

    @property
    def primary_match(self) -> ActiveProcessMatch | None:
        """대표 근거 — 임의 선택이 아니라 결정적 정렬의 첫 건."""
        return self.matches[0] if self.matches else None


def resolve_candidate_scope(
    candidate_source_layers: list[str],
    event_key: EventKeyV2,
    *,
    facts: list[ProcessFact],
    subject_id: str | None,
    coverage_override: ProcessCoverage | None = None,
    source_status: ProcessSourceStatus | None = None,
) -> CandidateProcessScope:
    """후보의 층위 근거 + 진행 사실 → 사용 범위와 게이트 동작.

    Args:
        candidate_source_layers: selected base occurrence의 층위(상위 지지의 SSOT).
        event_key: 후보의 사건 키.
        facts: 해소된 진행 사실 목록.
        subject_id: 후보의 주체.
        coverage_override: 저장소 장애 시 `SOURCE_UNAVAILABLE`을 넘긴다 —
            "사실이 없다"와 "읽지 못했다"를 구분한다.
        source_status: 저장소 조회 4상태. `LOAD_FAILED`·`CONTRACT_MISMATCH`는
            사유가 서로 다른 bypass로 갈린다.

    Returns:
        범위·게이트 동작·근거. 점수·순위는 건드리지 않는다.
    """
    matches = tuple(
        find_active_process_matches(facts, event_key, subject_id=subject_id)
    )
    scope = derive_event_scope(
        candidate_source_layers, active_process=bool(matches)
    )
    if scope is EventScope.MAJOR_EVENT_ELIGIBLE:
        # 상위 근거가 있으면 진행 사실과 무관하게 주요 사건 자격이다.
        return CandidateProcessScope(scope, EventGateAction.ENFORCE_MAJOR, matches)
    if scope is EventScope.UNKNOWN:
        return CandidateProcessScope(
            scope, EventGateAction.BYPASS_INCOMPLETE_COVERAGE, matches
        )
    # 저장소를 소비할 수 없으면 사실 유무를 논하기 전에 bypass다(사유별로 분리).
    if source_status is not None and not source_status.is_readable:
        action = source_status.bypass_action
        assert action is not None  # is_readable 이 False 면 항상 존재한다
        return CandidateProcessScope(scope, action, matches)
    if not matches and has_unmeasurable_entry_scope(
        facts, event_key, subject_id=subject_id
    ):
        # 사실은 있는데 scope producer가 없어 판정이 불가능하다 — "없음" 확정 금지.
        return CandidateProcessScope(
            scope, EventGateAction.BYPASS_INCOMPLETE_COVERAGE, matches
        )
    coverage = coverage_override or _coverage_for(matches, event_key)
    action = resolve_gate_action(coverage, has_compatible_active=bool(matches))
    return CandidateProcessScope(scope, action, matches)


def _coverage_for(
    matches: tuple[ActiveProcessMatch, ...], event_key: EventKeyV2
) -> ProcessCoverage:
    """이 후보에 적용할 coverage — 호환 사실이 있으면 그 도메인, 없으면 키 감사 기준.

    호환 사실이 없을 때가 중요하다. 커리어 키는 `AUTHORITATIVE`라 "진행 중인 게 없다"를
    확정할 수 있지만, 자료가 없는 도메인 키는 확정할 수 없어 bypass여야 한다.
    """
    if matches:
        return PROCESS_COVERAGE.get(
            matches[0].process_family, ProcessCoverage.UNSUPPORTED
        )
    status = EVENT_KEY_PROCESS_AUDIT.get(event_key)
    if status is EventProcessAuditStatus.ALLOWED_BY_RULE:
        # 규칙이 있는 키 — 그 규칙 도메인의 coverage를 따른다.
        for rule in PROCESS_EVENT_COMPATIBILITY:
            if event_key in rule.allowed_event_keys:
                return PROCESS_COVERAGE.get(
                    rule.process_family, ProcessCoverage.UNSUPPORTED
                )
    return ProcessCoverage.UNSUPPORTED
