"""P2-3b dual-run 회귀 — 같은 후보 집합을 legacy·scoped로 나눠 비교한다.

핵심은 **legacy 결과가 오염되지 않는 것**과 **`0건`과 `측정 불가`가 섞이지 않는 것**이다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, GraphIndex, load_event_graph, period_v2_config
from saju_engines.context_reducer import build_llm_input, candidate_audit_key
from saju_engines.process_dual_run import (
    compare_candidate_selections,
    measurement_status_for,
)
from saju_engines.process_event_compatibility import CandidateProcessScope
from saju_engines.process_fact_resolver import build_request_process_context
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventScope
from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.graph import EvidenceBundle
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.process_fact import (
    CareerEntryScope,
    CareerProcessSnapshot,
    DualRunComparisonResult,
    EventGateAction,
    ProcessFamily,
    ProcessMeasurementStatus,
    ProcessSourceStatus,
    ProcessStage,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_R = DualRunComparisonResult


@pytest.fixture(scope="module")
def chart() -> ManseV2Result:
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def scorer() -> EventEngineV2:
    return EventEngineV2(_DICTS)


@pytest.fixture(scope="module")
def candidates(chart: ManseV2Result, scorer: EventEngineV2) -> list[EventCandidate]:
    return scorer.score_legacy(chart, levels={GanjiLevel.YEAR})


@pytest.fixture(scope="module")
def bundles() -> list[EvidenceBundle]:
    graph = load_event_graph(_BACKEND / "compiled" / "event_graph_v1.1.0.json")
    return GraphIndex(graph).retrieve([EventKey.CAREER_CHANGE])


@pytest.fixture
def dual_run_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(period_v2_config, "EVENT_PROCESS_DUAL_RUN_ENABLED", True)


def _intent() -> IntentJson:
    return IntentJson(
        intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS,
        domain=Domain.CAREER, time_scope=TimeScope.MID_TERM,
        event_key=EventKey.CAREER_CHANGE,
    )


def _context(*, entry_scope=CareerEntryScope.EXTERNAL_EMPLOYER):
    return build_request_process_context(
        subject_id="self", current_turn_text="",
        career_snapshots=[
            CareerProcessSnapshot(
                episode_id="ep1", subject_id="self",
                process_family=ProcessFamily.CAREER_OPPORTUNITY,
                stage=ProcessStage.RESULT_PENDING, entry_scope=entry_scope,
            )
        ],
        source_status=ProcessSourceStatus.LOADED_WITH_FACTS,
    )


def _scope(action, raw=EventScope.LOCAL_TRIGGER_ONLY, matches=()):
    return CandidateProcessScope(raw, action, matches)


# ── 비교 판정 ──────────────────────────────────────────────────────────────


class _Cand:
    """비교 로직 단위 검증용 최소 후보(선별기를 타지 않는다)."""

    def __init__(self, key: str) -> None:
        self.event_key = key
        self.period = "2027"
        self.score = 70
        self.confidence = "medium"


def _compare(scope, *, in_legacy, in_scoped):
    keys = ["k0"]
    return compare_candidate_selections(
        keys=keys, candidates=[_Cand("job_gain")], scopes={"k0": scope},
        legacy_keys=["k0"] if in_legacy else [],
        scoped_keys=["k0"] if in_scoped else [],
    )


@pytest.mark.parametrize(
    ("action", "raw", "in_legacy", "in_scoped", "expected"),
    [
        (EventGateAction.ENFORCE_MAJOR, EventScope.MAJOR_EVENT_ELIGIBLE, True, True,
         _R.RETAINED_UPPER_SUPPORTED),
        (EventGateAction.ENFORCE_ACTIVE_TRIGGER, EventScope.ACTIVE_PROCESS_TRIGGER,
         True, True, _R.RETAINED_ACTIVE_TRIGGER),
        (EventGateAction.ENFORCE_LOCAL_ONLY, EventScope.LOCAL_TRIGGER_ONLY, True, False,
         _R.EXCLUDED_LOCAL_TRIGGER),
        (EventGateAction.ENFORCE_LOCAL_ONLY, EventScope.LOCAL_TRIGGER_ONLY, False, True,
         _R.NEWLY_ENTERED_ELIGIBLE),
        (EventGateAction.BYPASS_INCOMPLETE_COVERAGE, EventScope.LOCAL_TRIGGER_ONLY,
         True, True, _R.RETAINED_BY_COVERAGE_BYPASS),
        (EventGateAction.BYPASS_PROCESS_SOURCE_UNAVAILABLE, EventScope.LOCAL_TRIGGER_ONLY,
         True, True, _R.RETAINED_BY_SOURCE_UNAVAILABLE),
        (EventGateAction.ENFORCE_LOCAL_ONLY, EventScope.LOCAL_TRIGGER_ONLY, False, False,
         _R.NOT_SELECTED_IN_EITHER),
    ],
)
def test_comparison_verdicts(action, raw, in_legacy, in_scoped, expected) -> None:
    audit = _compare(_scope(action, raw), in_legacy=in_legacy, in_scoped=in_scoped)

    assert audit.candidates[0].comparison_result is expected


@pytest.mark.parametrize(
    ("action", "raw", "expected"),
    [
        (EventGateAction.ENFORCE_MAJOR, EventScope.MAJOR_EVENT_ELIGIBLE,
         _R.UNEXPECTED_UPPER_EXCLUSION),
        (EventGateAction.ENFORCE_ACTIVE_TRIGGER, EventScope.ACTIVE_PROCESS_TRIGGER,
         _R.UNEXPECTED_ACTIVE_EXCLUSION),
        (EventGateAction.BYPASS_INCOMPLETE_COVERAGE, EventScope.LOCAL_TRIGGER_ONLY,
         _R.UNEXPECTED_BYPASS_CHANGE),
        (EventGateAction.BYPASS_PROCESS_CONTRACT_MISMATCH, EventScope.LOCAL_TRIGGER_ONLY,
         _R.UNEXPECTED_BYPASS_CHANGE),
    ],
)
def test_forbidden_exclusions_are_flagged(action, raw, expected) -> None:
    """게이트가 건드리면 안 되는 것을 건드리면 즉시 실패로 표시된다."""
    audit = _compare(_scope(action, raw), in_legacy=True, in_scoped=False)

    assert audit.candidates[0].comparison_result is expected
    assert expected.is_failure
    assert audit.has_failure


def test_clean_run_has_no_failure() -> None:
    audit = _compare(
        _scope(EventGateAction.ENFORCE_LOCAL_ONLY), in_legacy=True, in_scoped=False
    )

    assert not audit.has_failure
    assert audit.excluded_local_count == 1
    assert audit.membership_flip_count == 1


def test_unselected_candidates_do_not_inflate_flips() -> None:
    """두 실행 모두 미선정인 후보는 변화 집계에 넣지 않는다."""
    audit = _compare(
        _scope(EventGateAction.ENFORCE_LOCAL_ONLY), in_legacy=False, in_scoped=False
    )

    assert audit.membership_flip_count == 0
    assert audit.excluded_local_count == 0


# ── 경로별 유지 건수 분리 ──────────────────────────────────────────────────


def _match(rule_id, entry_scope):
    from saju_engines.process_event_compatibility import ActiveProcessMatch
    from saju_shared_types.event_engine import EventKeyV2

    return ActiveProcessMatch(
        process_fact_id="f1", process_family=ProcessFamily.CAREER_OPPORTUNITY,
        stage=ProcessStage.RESULT_PENDING, entry_scope=entry_scope,
        event_key=EventKeyV2.JOB_GAIN, compatibility_rule_id=rule_id,
        evidence_origin="CAREER_HARD_FACT_EPISODE",
    )


@pytest.mark.parametrize(
    ("rule_id", "scope_value", "field_name"),
    [
        ("CAREER_EXTERNAL_OPPORTUNITY", "external_employer",
         "retained_external_opportunity_count"),
        ("CAREER_INTERNAL_PROMOTION", "internal_role", "retained_internal_role_count"),
        ("CAREER_EXIT", None, "retained_exit_trigger_count"),
        ("CAREER_ENTRY_EXTERNAL", "external_employer", "retained_entry_trigger_count"),
    ],
)
def test_retained_counts_split_by_path(rule_id, scope_value, field_name) -> None:
    """외부 이직·사내 승진·퇴사·입사를 한 칸에 담지 않는다."""
    scope = _scope(
        EventGateAction.ENFORCE_ACTIVE_TRIGGER, EventScope.ACTIVE_PROCESS_TRIGGER,
        matches=(_match(rule_id, scope_value),),
    )

    audit = _compare(scope, in_legacy=True, in_scoped=True)

    assert audit.retained_active_trigger_count == 1
    assert getattr(audit, field_name) == 1


def test_bypass_records_entry_scope_unavailable() -> None:
    """scope 부재 bypass는 별도로 센다 — '진행 사실 0건'과 섞지 않는다."""
    audit = _compare(
        _scope(EventGateAction.BYPASS_INCOMPLETE_COVERAGE),
        in_legacy=True, in_scoped=True,
    )

    assert audit.bypass_count == 1
    assert audit.entry_scope_unavailable_count == 1
    assert audit.retained_active_trigger_count == 0


# ── 측정 상태 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("entry_scope", "expected"),
    [
        ("external_employer", ProcessMeasurementStatus.MEASURABLE),
        ("internal_role", ProcessMeasurementStatus.MEASURABLE),
        ("internal_department", ProcessMeasurementStatus.INCOMPLETE_FACT_COVERAGE),
        ("internal_location", ProcessMeasurementStatus.INCOMPLETE_FACT_COVERAGE),
        (None, ProcessMeasurementStatus.BLOCKED_BY_ENTRY_SCOPE_PRODUCER),
        ("", ProcessMeasurementStatus.BLOCKED_BY_ENTRY_SCOPE_PRODUCER),
    ],
)
def test_measurement_status(entry_scope, expected) -> None:
    """부서·근무지 이동은 fact coverage 공백이라 성공·실패 분모에 넣지 않는다."""
    assert measurement_status_for(entry_scope) is expected


# ── 실제 요청 경로 ─────────────────────────────────────────────────────────


def test_dual_run_does_not_change_payload(chart, candidates, bundles, scorer, dual_run_on):
    """dual-run을 켜도 사용자에게 나가는 결과는 legacy 그대로다."""
    baseline = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer
    )
    with_dual = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=_context(),
    )

    assert with_dual.model_dump_json() == baseline.model_dump_json()


def test_dual_run_is_recorded_in_audit(
    chart: ManseV2Result, candidates: list[EventCandidate],
    bundles: list[EvidenceBundle], scorer: EventEngineV2, dual_run_on: None,
) -> None:
    """비교 결과가 감사 채널에 남는다."""
    audit: dict = {}
    build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=_context(), process_scope_audit=audit,
    )

    dual = audit.get("__dual_run__")
    assert dual is not None
    assert dual.legacy_top_n_count > 0
    assert not dual.has_failure, "기준선에서 예상 밖 제외가 나오면 안 된다"


def test_dual_run_is_off_by_default(
    chart: ManseV2Result, candidates: list[EventCandidate],
    bundles: list[EvidenceBundle], scorer: EventEngineV2,
) -> None:
    """플래그 OFF면 두 번째 선별을 돌리지 않는다(계측 비용 0)."""
    audit: dict = {}
    build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=_context(), process_scope_audit=audit,
    )

    assert "__dual_run__" not in audit


def test_upper_supported_candidates_are_never_excluded(
    chart: ManseV2Result, candidates: list[EventCandidate],
    bundles: list[EvidenceBundle], scorer: EventEngineV2, dual_run_on: None,
) -> None:
    """세운 지지 후보는 게이트와 무관하게 유지된다 — 활성화 절대 조건."""
    audit: dict = {}
    build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=_context(), process_scope_audit=audit,
    )

    dual = audit["__dual_run__"]
    assert dual.unexpected_upper_exclusion_count == 0
    assert dual.unexpected_active_exclusion_count == 0
    assert dual.unexpected_bypass_change_count == 0


def test_audit_keys_are_shared_between_runs(candidates) -> None:
    """두 실행이 같은 후보를 같은 ID로 본다 — 비교의 전제."""
    keys = [candidate_audit_key(i, c, "self") for i, c in enumerate(candidates)]

    assert len(set(keys)) == len(keys)
