"""P2-3b dual-run — 같은 후보 집합을 legacy·scoped 두 번 선택해 비교한다.

```
실제 chat 요청
  → 후보 생성
  → 후보별 raw_event_scope + gate_action 부착 (P2-3a)
  → 동일한 후보 스냅샷 고정
     ├─ legacy selection   ← 사용자에게 반환
     └─ scoped selection   ← 감사 전용
  → 후보 ID 기준 비교
```

**합성 후보로 별도 스크립트에서 돌리지 않는다.** 실제 요청에서 생성된 같은 후보 목록을
reducer 직전에 나눠야 Episode 조회 시점·subject 해소·실제 Top-N 진입·빈 결과 문구까지
한 번에 확인된다.

측정 상태를 반드시 분리한다 — `retained_active_trigger_count = 0`은 "진행 사실이
없었다"와 "판정 입력이 없었다"를 섞는다. 전자는 게이트가 정상이라는 뜻이고 후자는
아무것도 모른다는 뜻이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saju_shared_types.event_engine import EventScope
from saju_shared_types.process_fact import (
    ENTRY_SCOPE_MEASUREMENT,
    CareerEntryScope,
    DualRunComparisonResult,
    EventGateAction,
    ProcessMeasurementStatus,
)

from .process_event_compatibility import CandidateProcessScope


@dataclass(frozen=True)
class CandidateDualRunAudit:
    """후보 1건의 legacy·scoped 비교 결과."""

    candidate_id: str
    event_key: str
    period: str
    raw_score: int
    confidence: str
    raw_event_scope: str
    gate_action: str
    legacy_rank: int | None
    legacy_top_n: bool
    scoped_rank: int | None
    scoped_top_n: bool
    comparison_result: DualRunComparisonResult
    active_process_matches: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class DualRunAudit:
    """요청 1건의 비교 결과 — 보고서의 행 하나."""

    legacy_top_n_count: int = 0
    scoped_top_n_count: int = 0
    membership_flip_count: int = 0
    excluded_local_count: int = 0
    newly_entered_count: int = 0
    retained_active_trigger_count: int = 0
    retained_upper_supported_count: int = 0
    bypass_count: int = 0
    unknown_count: int = 0
    unexpected_upper_exclusion_count: int = 0
    unexpected_active_exclusion_count: int = 0
    unexpected_bypass_change_count: int = 0
    #: 진입 범위별 유지 건수 — 외부 이직과 사내 승진을 한 칸에 담지 않는다.
    retained_external_opportunity_count: int = 0
    retained_internal_role_count: int = 0
    retained_exit_trigger_count: int = 0
    retained_entry_trigger_count: int = 0
    #: 측정 상태별 건수 — `0건`과 `측정 불가`의 분리축.
    entry_scope_unavailable_count: int = 0
    incomplete_fact_coverage_count: int = 0
    major_candidates_gated_out: bool = False
    scoped_empty: bool = False
    candidates: tuple[CandidateDualRunAudit, ...] = field(default=())

    @property
    def has_failure(self) -> bool:
        """활성화를 막아야 하는 결과가 있는가 — 절대 조건."""
        return bool(
            self.unexpected_upper_exclusion_count
            or self.unexpected_active_exclusion_count
            or self.unexpected_bypass_change_count
        )

    def summary(self) -> dict[str, object]:
        """로그·보고서용 평면 dict."""
        return {
            k: v for k, v in self.__dict__.items() if k != "candidates"
        }


def _rule_family(scope: CandidateProcessScope) -> str:
    """예외를 연 규칙의 계열 — 유지 건수를 경로별로 가른다."""
    match = scope.primary_match
    if match is None:
        return ""
    return match.compatibility_rule_id


def _classify(
    scope: CandidateProcessScope, *, in_legacy: bool, in_scoped: bool
) -> DualRunComparisonResult:
    """후보 1건의 비교 결과 판정.

    Args:
        scope: P2-3a에서 붙인 범위 판정.
        in_legacy: legacy 선택에 포함됐는가.
        in_scoped: scoped 선택에 포함됐는가.

    Returns:
        비교 결과. 게이트가 건드리면 안 되는 것을 건드렸으면 `UNEXPECTED_*`.
    """
    action = scope.gate_action
    if not in_legacy and not in_scoped:
        return DualRunComparisonResult.NOT_SELECTED_IN_EITHER
    if not in_legacy and in_scoped:
        return DualRunComparisonResult.NEWLY_ENTERED_ELIGIBLE
    if in_legacy and in_scoped:
        if scope.raw_event_scope is EventScope.MAJOR_EVENT_ELIGIBLE:
            return DualRunComparisonResult.RETAINED_UPPER_SUPPORTED
        if action is EventGateAction.ENFORCE_ACTIVE_TRIGGER:
            return DualRunComparisonResult.RETAINED_ACTIVE_TRIGGER
        if action is EventGateAction.BYPASS_PROCESS_SOURCE_UNAVAILABLE:
            return DualRunComparisonResult.RETAINED_BY_SOURCE_UNAVAILABLE
        if action.is_bypass:
            return DualRunComparisonResult.RETAINED_BY_COVERAGE_BYPASS
        return DualRunComparisonResult.RETAINED_UNKNOWN
    # legacy에만 있음 — 제외됐다. 무엇이 제외했는지가 안전성의 핵심이다.
    if scope.raw_event_scope is EventScope.MAJOR_EVENT_ELIGIBLE:
        return DualRunComparisonResult.UNEXPECTED_UPPER_EXCLUSION
    if action is EventGateAction.ENFORCE_ACTIVE_TRIGGER:
        return DualRunComparisonResult.UNEXPECTED_ACTIVE_EXCLUSION
    if action.is_bypass:
        return DualRunComparisonResult.UNEXPECTED_BYPASS_CHANGE
    if action is EventGateAction.ENFORCE_LOCAL_ONLY:
        return DualRunComparisonResult.EXCLUDED_LOCAL_TRIGGER
    # 설명되지 않는 제외 — 조용히 정상으로 넘기지 않는다.
    return DualRunComparisonResult.UNEXPECTED_BYPASS_CHANGE


def compare_candidate_selections(
    *,
    keys: list[str],
    candidates: list,
    scopes: dict[str, CandidateProcessScope],
    legacy_keys: list[str],
    scoped_keys: list[str],
) -> DualRunAudit:
    """legacy·scoped 선택을 후보 ID 기준으로 비교한다.

    Args:
        keys: 축소 이전 후보 목록의 안정 ID(입력 순서와 1:1).
        candidates: 축소 이전 후보 목록.
        scopes: `candidate_audit_key` → 범위 판정.
        legacy_keys: legacy 선택 결과의 ID(순위 순).
        scoped_keys: scoped 선택 결과의 ID(순위 순).

    Returns:
        후보별·요청별 비교 결과.
    """
    legacy_rank = {k: i for i, k in enumerate(legacy_keys)}
    scoped_rank = {k: i for i, k in enumerate(scoped_keys)}
    rows: list[CandidateDualRunAudit] = []
    counts: dict[str, int] = {}

    def bump(name: str, amount: int = 1) -> None:
        counts[name] = counts.get(name, 0) + amount

    for key, candidate in zip(keys, candidates, strict=True):
        scope = scopes.get(key)
        if scope is None:
            continue
        in_legacy = key in legacy_rank
        in_scoped = key in scoped_rank
        verdict = _classify(scope, in_legacy=in_legacy, in_scoped=in_scoped)
        rows.append(
            CandidateDualRunAudit(
                candidate_id=key,
                event_key=str(candidate.event_key),
                period=candidate.period,
                raw_score=int(candidate.score),
                confidence=str(candidate.confidence),
                raw_event_scope=scope.raw_event_scope.value,
                gate_action=scope.gate_action.value,
                legacy_rank=legacy_rank.get(key),
                legacy_top_n=in_legacy,
                scoped_rank=scoped_rank.get(key),
                scoped_top_n=in_scoped,
                comparison_result=verdict,
                active_process_matches=tuple(
                    {
                        "process_fact_id": m.process_fact_id,
                        "rule_id": m.compatibility_rule_id,
                        "stage": m.stage.value,
                        "entry_scope": m.entry_scope or "",
                    }
                    for m in scope.matches
                ),
            )
        )
        if verdict is DualRunComparisonResult.NOT_SELECTED_IN_EITHER:
            continue
        if verdict is DualRunComparisonResult.EXCLUDED_LOCAL_TRIGGER:
            bump("excluded_local_count")
        elif verdict is DualRunComparisonResult.NEWLY_ENTERED_ELIGIBLE:
            bump("newly_entered_count")
        elif verdict is DualRunComparisonResult.RETAINED_ACTIVE_TRIGGER:
            bump("retained_active_trigger_count")
            family = _rule_family(scope)
            if family == "CAREER_EXTERNAL_OPPORTUNITY":
                bump("retained_external_opportunity_count")
            elif family == "CAREER_INTERNAL_PROMOTION":
                bump("retained_internal_role_count")
            elif family == "CAREER_EXIT":
                bump("retained_exit_trigger_count")
            elif family.startswith("CAREER_ENTRY"):
                bump("retained_entry_trigger_count")
        elif verdict is DualRunComparisonResult.RETAINED_UPPER_SUPPORTED:
            bump("retained_upper_supported_count")
        elif verdict in (
            DualRunComparisonResult.RETAINED_BY_COVERAGE_BYPASS,
            DualRunComparisonResult.RETAINED_BY_SOURCE_UNAVAILABLE,
        ):
            bump("bypass_count")
            if scope.gate_action is EventGateAction.BYPASS_INCOMPLETE_COVERAGE:
                bump("entry_scope_unavailable_count")
        elif verdict is DualRunComparisonResult.RETAINED_UNKNOWN:
            bump("unknown_count")
        elif verdict is DualRunComparisonResult.UNEXPECTED_UPPER_EXCLUSION:
            bump("unexpected_upper_exclusion_count")
        elif verdict is DualRunComparisonResult.UNEXPECTED_ACTIVE_EXCLUSION:
            bump("unexpected_active_exclusion_count")
        elif verdict is DualRunComparisonResult.UNEXPECTED_BYPASS_CHANGE:
            bump("unexpected_bypass_change_count")

    flips = set(legacy_rank) ^ set(scoped_rank)
    excluded = counts.get("excluded_local_count", 0)
    return DualRunAudit(
        legacy_top_n_count=len(legacy_keys),
        scoped_top_n_count=len(scoped_keys),
        membership_flip_count=len(flips),
        excluded_local_count=excluded,
        newly_entered_count=counts.get("newly_entered_count", 0),
        retained_active_trigger_count=counts.get("retained_active_trigger_count", 0),
        retained_upper_supported_count=counts.get("retained_upper_supported_count", 0),
        bypass_count=counts.get("bypass_count", 0),
        unknown_count=counts.get("unknown_count", 0),
        unexpected_upper_exclusion_count=counts.get("unexpected_upper_exclusion_count", 0),
        unexpected_active_exclusion_count=counts.get(
            "unexpected_active_exclusion_count", 0
        ),
        unexpected_bypass_change_count=counts.get("unexpected_bypass_change_count", 0),
        retained_external_opportunity_count=counts.get(
            "retained_external_opportunity_count", 0
        ),
        retained_internal_role_count=counts.get("retained_internal_role_count", 0),
        retained_exit_trigger_count=counts.get("retained_exit_trigger_count", 0),
        retained_entry_trigger_count=counts.get("retained_entry_trigger_count", 0),
        entry_scope_unavailable_count=counts.get("entry_scope_unavailable_count", 0),
        major_candidates_gated_out=excluded > 0 and not scoped_keys,
        scoped_empty=not scoped_keys,
        candidates=tuple(rows),
    )


def measurement_status_for(entry_scope: str | None) -> ProcessMeasurementStatus:
    """이 진입 범위를 지금 측정할 수 있는가.

    Args:
        entry_scope: `ProcessFact.entry_scope` 값 문자열.

    Returns:
        범위가 없으면 `BLOCKED_BY_ENTRY_SCOPE_PRODUCER`, 부서·근무지 이동은
        `INCOMPLETE_FACT_COVERAGE`, 나머지는 `MEASURABLE`.
    """
    if not entry_scope:
        return ProcessMeasurementStatus.BLOCKED_BY_ENTRY_SCOPE_PRODUCER
    try:
        scope = CareerEntryScope(entry_scope)
    except ValueError:
        return ProcessMeasurementStatus.BLOCKED_BY_ENTRY_SCOPE_PRODUCER
    return ENTRY_SCOPE_MEASUREMENT.get(scope, ProcessMeasurementStatus.MEASURABLE)


__all__ = [
    "CandidateDualRunAudit",
    "DualRunAudit",
    "compare_candidate_selections",
    "measurement_status_for",
]
