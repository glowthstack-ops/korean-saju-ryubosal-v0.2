"""P2-3a 배선 회귀 — 범위 산출이 축소 **전에** 일어나고, 출력은 불변이다.

플래그 OFF 기준선이다. 여기서 payload가 한 바이트라도 달라지면 P2-3b dual-run의
비교 기준이 무너진다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2, GraphIndex, load_event_graph
from saju_engines.context_reducer import (
    build_llm_input,
    candidate_audit_key,
    resolve_process_scopes,
    summarize_process_scopes,
)
from saju_engines.process_fact_resolver import build_request_process_context
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.graph import EvidenceBundle
from saju_shared_types.intent import Domain, IntentJson, QueryType, TimeScope
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.process_fact import (
    CareerEntryScope,
    CareerProcessSnapshot,
    EventGateAction,
    ProcessFamily,
    ProcessSourceStatus,
    ProcessStage,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


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


@pytest.fixture(scope="module")
def minor_candidates(candidates):
    """월·일운만 기여한 후보 — 게이트가 실제로 판정하는 대상.

    상위(대운·세운) 지지가 있으면 진행 사실과 무관하게 `ENFORCE_MAJOR`로 끝나므로
    게이트 동작 행렬을 볼 수 없다. 실제 DTO를 쓰되 층위 축만 고정한다.
    """
    return [c.model_copy(update={"candidate_source_layers": ["ilwoon"]}) for c in candidates]


def _intent() -> IntentJson:
    return IntentJson(
        intent_id="i1", query_type=QueryType.DOMAIN_ANALYSIS,
        domain=Domain.CAREER, time_scope=TimeScope.MID_TERM,
        event_key=EventKey.CAREER_CHANGE,
    )


def _context(*, entry_scope=None, source_status=ProcessSourceStatus.LOADED_WITH_FACTS):
    """면접 완료(결과 대기) Episode 1건이 있는 요청 컨텍스트."""
    return build_request_process_context(
        subject_id="self",
        current_turn_text="",
        career_snapshots=[
            CareerProcessSnapshot(
                episode_id="ep1",
                subject_id="self",
                process_family=ProcessFamily.CAREER_OPPORTUNITY,
                stage=ProcessStage.RESULT_PENDING,
                entry_scope=entry_scope,
            )
        ],
        source_status=source_status,
    )


# ── 출력 불변(기준선) ───────────────────────────────────────────────────────


def test_payload_is_unchanged_by_process_context(chart, candidates, bundles, scorer):
    """컨텍스트 주입이 LLM 입력을 바꾸지 않는다 — P2-3a 핵심 수용 기준."""
    baseline = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer
    )
    wired = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=_context(entry_scope=CareerEntryScope.EXTERNAL_EMPLOYER),
    )

    assert wired.model_dump_json() == baseline.model_dump_json()


def test_payload_unchanged_even_when_gate_would_exclude(
    chart, candidates, bundles, scorer
):
    """게이트가 제외를 말하는 상황에서도 플래그 OFF면 선별이 그대로다."""
    baseline = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer
    )
    wired = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=build_request_process_context(
            subject_id="self", current_turn_text="", career_snapshots=[],
            source_status=ProcessSourceStatus.LOADED_EMPTY,
        ),
    )

    assert wired.model_dump_json() == baseline.model_dump_json()


# ── 축소 전 산출 ───────────────────────────────────────────────────────────


def test_scope_is_resolved_for_every_candidate_before_reduction(
    chart: ManseV2Result, candidates: list[EventCandidate],
    bundles: list[EvidenceBundle], scorer: EventEngineV2,
) -> None:
    """Top-N이 아니라 **전 후보**에 범위가 붙는다(탈락 예정 후보 포함)."""
    audit: dict = {}
    payload = build_llm_input(
        "올해 이직운 어때?", _intent(), chart, candidates, bundles, scorer,
        process_context=_context(entry_scope=CareerEntryScope.EXTERNAL_EMPLOYER),
        process_scope_audit=audit,
    )

    assert len(audit) == len(candidates)
    assert len(audit) > len(payload.event_candidates), (
        "축소 후에 붙였다면 감사 건수가 Top-N을 넘지 못한다"
    )


def test_audit_key_is_stable_and_unique(candidates):
    """같은 입력은 같은 키 — legacy·scoped 비교의 전제."""
    first = [candidate_audit_key(i, c, "self") for i, c in enumerate(candidates)]
    second = [candidate_audit_key(i, c, "self") for i, c in enumerate(candidates)]

    assert first == second
    assert len(set(first)) == len(first)


def test_no_context_means_no_scopes(candidates):
    """컨텍스트가 없으면 아무것도 계산하지 않는다(기존 동작 유지)."""
    assert resolve_process_scopes(candidates, process_context=None) == {}


# ── F1: 측정 불가와 0건의 분리 ──────────────────────────────────────────────


def test_missing_entry_scope_bypasses_instead_of_enforcing(minor_candidates):
    """scope producer 부재는 '진행 중인 게 없다'가 아니다 — bypass로 빠진다."""
    scopes = resolve_process_scopes(minor_candidates, process_context=_context())

    career = [
        s for k, s in scopes.items() if str(EventKey.CAREER_CHANGE.value) in k
    ]
    assert career, "커리어 후보가 있어야 판정이 의미 있다"
    assert all(
        s.gate_action is EventGateAction.BYPASS_INCOMPLETE_COVERAGE for s in career
    )


def test_present_entry_scope_allows_enforcement(minor_candidates):
    """scope가 있으면 정상 판정 경로로 들어간다 — 커리어 후보는 active trigger."""
    scopes = resolve_process_scopes(
        minor_candidates,
        process_context=_context(entry_scope=CareerEntryScope.EXTERNAL_EMPLOYER),
    )

    career = [
        s for k, s in scopes.items() if str(EventKey.CAREER_CHANGE.value) in k
    ]
    assert career
    assert all(s.gate_action is EventGateAction.ENFORCE_ACTIVE_TRIGGER for s in career)
    assert all(s.matches for s in career), "근거 없이 예외가 열리면 안 된다"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ProcessSourceStatus.LOAD_FAILED, EventGateAction.BYPASS_PROCESS_SOURCE_UNAVAILABLE),
        (
            ProcessSourceStatus.CONTRACT_MISMATCH,
            EventGateAction.BYPASS_PROCESS_CONTRACT_MISMATCH,
        ),
    ],
)
def test_source_failure_and_contract_mismatch_are_distinct(
    minor_candidates, status, expected
):
    """두 상태 모두 bypass지만 감사 사유는 다르다."""
    scopes = resolve_process_scopes(
        minor_candidates,
        process_context=build_request_process_context(
            subject_id="self", current_turn_text="", career_snapshots=[],
            source_status=status,
        ),
    )

    assert scopes
    assert {s.gate_action for s in scopes.values()} == {expected}


def test_summary_separates_bypass_reasons(minor_candidates):
    """분포 요약이 사유별로 나뉜다 — 0건과 측정 불가를 한 칸에 담지 않는다."""
    scopes = resolve_process_scopes(minor_candidates, process_context=_context())

    summary = summarize_process_scopes(scopes)

    assert summary["total"] == len(minor_candidates)
    assert sum(v for k, v in summary.items() if k != "total") == len(minor_candidates)
    assert summary.get(EventGateAction.BYPASS_INCOMPLETE_COVERAGE.value, 0) > 0
