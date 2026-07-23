"""위험 노출 확대(감수 62차) — 3단계: 대화 5유형 개방 검증.

TIMING_SEARCH 분기·episode_followup 결정적 해소·모드별 허용 유형·
비교 consolidation(전면 EXPOSE 테스트 게이트 2 포함).
"""

from __future__ import annotations

from saju_engines import risk_engine_config
from saju_engines.risk_question_mapping import (
    map_intent_to_exposure_question,
)
from saju_shared_types.intent import (
    Domain,
    IntentJson,
    QueryType,
    TimeRange,
    TimeScope,
)
from saju_shared_types.risk_engine import (
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
)


def _intent(**kw) -> IntentJson:
    base = dict(intent_id="i1", query_type=QueryType.FORTUNE_OVERVIEW,
                time_scope=TimeScope.MID_TERM,
                time_range=TimeRange(type="relative", granularity="month",
                                     start="2026-07", end="2027-06"),
                domains=[Domain.WEALTH])
    base.update(kw)
    return IntentJson(**base)


# ── TIMING_SEARCH 분기 ──────────────────────────────────────────────────


def test_timing_search_single_domain() -> None:
    out = map_intent_to_exposure_question(
        _intent(query_type=QueryType.TIMING_SEARCH,
                domains=[Domain.CAREER]))
    assert out is not None
    assert out["question_type"] == "single_domain_period"
    assert out["target_domains"] == ("career",)


def test_timing_search_general_overview() -> None:
    out = map_intent_to_exposure_question(
        _intent(query_type=QueryType.TIMING_SEARCH,
                domains=[Domain.GENERAL]))
    assert out is not None
    assert out["question_type"] == "period_overview"


def test_timing_search_no_time_range_bypass() -> None:
    assert map_intent_to_exposure_question(
        _intent(query_type=QueryType.TIMING_SEARCH,
                time_range=None)) is None


# ── episode_followup 결정적 해소 ────────────────────────────────────────

_STORED = (("fallback:abc|x", "finance", "2026"),
           ("fallback:def", "career", "2026"))


def test_followup_resolves_single_match() -> None:
    out = map_intent_to_exposure_question(
        _intent(query_type=QueryType.EVENT_EXPLANATION,
                event_key="career_change",
                domains=[Domain.CAREER]),
        stored_episode_keys=_STORED)
    assert out is not None
    assert out["question_type"] == "episode_followup"
    assert out["episode_key"] == "fallback:def"


def test_followup_no_keys_keeps_specific_event() -> None:
    out = map_intent_to_exposure_question(
        _intent(query_type=QueryType.EVENT_EXPLANATION,
                event_key="career_change", domains=[Domain.CAREER]))
    assert out is not None
    assert out["question_type"] == "specific_event"


def test_followup_ambiguous_keeps_specific_event() -> None:
    stored = (("k1", "career", "2026"), ("k2", "career", "2027"))
    out = map_intent_to_exposure_question(
        _intent(query_type=QueryType.EVENT_EXPLANATION,
                event_key="career_change", domains=[Domain.CAREER]),
        stored_episode_keys=stored)
    assert out is not None
    assert out["question_type"] == "specific_event"  # 복수건=승격 금지


# ── 모드별 허용 유형(expose=5 / canary=3) ──────────────────────────────


def test_exposed_question_types_superset() -> None:
    canary = set(risk_engine_config.RISK_CANARY_QUESTION_TYPES)
    exposed = set(risk_engine_config.RISK_EXPOSED_QUESTION_TYPES)
    assert canary < exposed
    assert exposed - canary == {"multi_episode_compare", "episode_followup"}


# ── 비교 consolidation(P0⑨ — 테스트 게이트 2) ─────────────────────────


def _candidate(rid: str, period: str, dom=RiskDomain.FINANCE,
               strength: float = 0.6) -> RiskCandidate:
    src = f"relation:CHUNG:month_pillar:branch:ZHENGCAI:{rid}"
    return RiskCandidate(
        risk_id=rid, domain=dom, kind=RiskKind.INCIDENT_RISK,
        risk_family=f"fam-{rid}", period_key=period,
        evidence=[RiskEvidence(
            evidence_id=f"{period}|{src}", code="T", period_key=period,
            layer="sewoon", source=src, strength=strength,
            role=EvidenceRole.TRIGGER, source_group="event_shape",
            target_domain=dom)],
        exposure_status=ExposureStatus.CONFIRMED, specificity_rank=2,
        normalized_effect_role="financial_pressure",
        trigger_cause_atoms=[src], legal_episode_id=f"ep-{rid}")


def test_gate2_comparison_preserves_both_period_occurrences() -> None:
    """같은 위험(가족)이 두 기간에 있을 때 두 occurrence 모두 보존."""
    from saju_api.services.risk_exposure_bootstrap import build_risk_payload

    shadow = [_candidate("FIN_UNEXPECTED_EXPENSE", "2026"),
              _candidate("FIN_UNEXPECTED_EXPENSE", "2027"),
              _candidate("FIN_CASHFLOW_PRESSURE", "2026")]
    payload = build_risk_payload(
        shadow, question_type="multi_episode_compare",
        comparison_periods=("2026", "2027"))
    assert payload is not None
    cons = payload["comparativeConsolidation"]
    assert cons, "통합 결과가 있어야 한다"
    # 항목당 두 기간 occurrence가 기록되고, 하나 이상은 양쪽 present
    for item in cons:
        periods = {o["period"] for o in item["occurrences"]}
        assert periods == {"2026", "2027"}


def test_comparison_total_cap_and_no_fill() -> None:
    from saju_api.services.risk_exposure_bootstrap import build_risk_payload

    # 2026에만 후보 6건, 2027은 0건 — 빈 기간을 채우지 않고 cap 준수
    shadow = [_candidate("FIN_UNEXPECTED_EXPENSE", "2026"),
              _candidate("FIN_CASHFLOW_PRESSURE", "2026"),
              _candidate("CAR_ORG_CONFLICT", "2026", RiskDomain.CAREER),
              _candidate("LEG_CONTRACT_TERMINATION_RISK", "2026",
                         RiskDomain.CONTRACT_LEGAL)]
    payload = build_risk_payload(
        shadow, question_type="multi_episode_compare",
        comparison_periods=("2026", "2027"))
    assert payload is not None
    cons = payload["comparativeConsolidation"]
    from saju_engines.risk_selection import budget_for
    assert len(cons) <= budget_for("multi_episode_compare").hard_max
    for item in cons:
        by_period = {o["period"]: o["present"] for o in item["occurrences"]}
        assert by_period["2027"] is False  # 빈 기간 미충전


def test_comparison_selection_omitted_audited() -> None:
    from saju_api.services.risk_exposure_bootstrap import build_risk_payload

    shadow = ([_candidate("FIN_UNEXPECTED_EXPENSE", "2026"),
               _candidate("FIN_CASHFLOW_PRESSURE", "2026"),
               _candidate("CAR_ORG_CONFLICT", "2026", RiskDomain.CAREER),
               _candidate("LEG_CONTRACT_TERMINATION_RISK", "2026",
                          RiskDomain.CONTRACT_LEGAL)]
              + [_candidate("FIN_UNEXPECTED_EXPENSE", "2027"),
                 _candidate("FIN_CASHFLOW_PRESSURE", "2027"),
                 _candidate("CAR_ORG_CONFLICT", "2027", RiskDomain.CAREER)])
    payload = build_risk_payload(
        shadow, question_type="multi_episode_compare",
        comparison_periods=("2026", "2027"))
    assert payload is not None
    reasons = {o["reason"] for o in payload["selectionOmitted"]}
    assert reasons  # per-period cap 또는 전체 cap 탈락이 감사에 남는다
