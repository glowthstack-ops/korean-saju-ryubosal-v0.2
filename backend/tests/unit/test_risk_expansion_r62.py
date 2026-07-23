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


# ── 4단계: 동반자 개방 ─────────────────────────────────────────────────


def test_pairwise_mapping_opened_group_blocked() -> None:
    from saju_shared_types.intent import SubjectMode
    out = map_intent_to_exposure_question(
        _intent(subject_mode=SubjectMode.PAIRWISE))
    assert out is not None and out["subject_scope"] == "companion_pair"
    assert map_intent_to_exposure_question(
        _intent(subject_mode=SubjectMode.GROUP_AGGREGATE)) is None
    assert map_intent_to_exposure_question(
        _intent(subject_mode=SubjectMode.RANKING)) is None
    # 비교는 단일 대상만(1차 계약)
    assert map_intent_to_exposure_question(
        _intent(query_type=QueryType.COMPARISON,
                subject_mode=SubjectMode.PAIRWISE)) is None


def test_gate3_companion_ceiling_matrix() -> None:
    """전 조합 매트릭스 fixture — min() 교집합(순차 강등 금지)."""
    from saju_engines.risk_exposure import companion_effective_level

    matrix = [
        # (전역 외부 수준, 도메인, 기대 유효 수준)
        ("warning", ("finance",), "watch"),        # 일반 동반자 ceiling
        ("warning", ("health_safety",), "advisory"),
        ("warning", ("contract_legal",), "advisory"),
        ("watch", ("finance",), "watch"),          # min(watch, watch)=watch
        ("watch", ("health_safety",), "advisory"),
        ("advisory", ("finance",), "advisory"),    # 이미 낮음 — 불변
        ("advisory", ("health_safety",), "advisory"),
        ("none", ("health_safety",), "none"),      # none은 대상 아님
        ("warning", (), "watch"),                  # 도메인 ceiling 없음=제약 없음
    ]
    for level, domains, expected in matrix:
        effective, _reason = companion_effective_level(level, domains)
        assert effective == expected, (level, domains, effective)


def test_companion_payload_ceiling_applied_with_audit() -> None:
    from saju_engines.risk_exposure import apply_companion_ceiling

    payload: dict = {
        "presentationRecords": [
            {"presentationLevel": "warning", "domains": ["health_safety"],
             "diagnostics": {"episodeKey": "k1"}},
            {"presentationLevel": "none", "domains": ["finance"],
             "diagnostics": {"episodeKey": "k2"}},
        ],
        "llmRiskEpisodes": [
            {"guidanceRef": "r1", "presentationLevel": "warning",
             "presentationLabel": "주의 필요"}],
    }
    out = apply_companion_ceiling(payload)
    rec = out["presentationRecords"][0]
    assert rec["globalExternalLevel"] == "warning"  # 원본 보존
    assert rec["effectiveExternalLevel"] == "advisory"
    assert rec["companionPolicyReason"] == "COMPANION_HEALTH_SAFETY_CEILING"
    assert out["llmRiskEpisodes"][0]["presentationLevel"] == "advisory"
    # 입력 불변
    assert payload["llmRiskEpisodes"][0]["presentationLevel"] == "warning"


def test_companion_kill_switch_scoped_bypass(monkeypatch) -> None:
    """동반자 kill switch — 동반자만 BYPASS, 본인 경로는 진행."""
    from saju_api.services import risk_exposure_service as svc

    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_COMPANION_KILL_SWITCH", True)
    prompt, _sys, obs = svc.apply_risk_exposure(
        "본문", None, subject_scope="companion_pair")
    assert obs["disposition"] == "BYPASS"
    assert obs["reason"] == "COMPANION_KILL_SWITCH"
    assert prompt == "본문"  # byte 불변
    # 본인 경로는 kill switch 무관(게이트 정상 평가 경로 진입)
    _p2, _s2, obs2 = svc.apply_risk_exposure("본문", None,
                                             subject_scope="single")
    assert obs2.get("reason") != "COMPANION_KILL_SWITCH"


def test_request_local_risk_shadow_thread_isolation() -> None:
    """async/thread interleaving 오귀속 차단 — thread-local sink 격리."""
    import threading

    from saju_engines.event_engine_v2 import EventEngineV2

    scorer = EventEngineV2.__new__(EventEngineV2)  # 무거운 __init__ 우회
    scorer._risk_tls = threading.local()

    results: dict[str, tuple] = {}
    barrier = threading.Barrier(2)

    def run(name: str, items: list[str]) -> None:
        sink: list = []
        scorer._risk_tls.sink = sink
        barrier.wait()  # 두 스레드가 sink 설정 후 동시에 진행(interleave)
        for it in items:
            sink.append(f"{name}:{it}")
        scorer._risk_tls.last = tuple(sink)
        results[name] = scorer.take_risk_shadow()

    t1 = threading.Thread(target=run, args=("A", ["r1", "r2"]))
    t2 = threading.Thread(target=run, args=("B", ["r3"]))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert results["A"] == ("A:r1", "A:r2")  # B 항목 혼입 없음
    assert results["B"] == ("B:r3",)


# ── 5단계: 리포트 소유권·기간 집합 ─────────────────────────────────────


def test_gate4_owner_resolver_respects_available_sections() -> None:
    from saju_api.services.report_service import resolve_risk_owner

    avail_full = frozenset({"C-06", "F-18", "RL-05"})
    assert resolve_risk_owner("RPT_FULL", "health_safety",
                              avail_full) == "F-18"
    assert resolve_risk_owner("RPT_YEAR", "health_safety",
                              frozenset({"Y-09", "C-06"})) == "Y-09"
    # 전문 섹션 부재 → C-06 fallback
    assert resolve_risk_owner("RPT_FULL", "health_safety",
                              frozenset({"C-06"})) == "C-06"
    # 둘 다 부재 → None(감사 가능한 미노출)
    assert resolve_risk_owner("RPT_FULL", "health_safety",
                              frozenset()) is None
    # 불변식: owner ∈ available ∪ {None}
    for domain in ("health_safety", "relocation", "finance"):
        owner = resolve_risk_owner("RPT_FOCUS", domain, avail_full)
        assert owner is None or owner in avail_full


def test_period_exact_set_excludes_gap_year() -> None:
    """{2026,2028} 허용 시 2027 후보 배제(min/max 범위 폐기 — P0⑤)."""
    from saju_api.services.risk_exposure_bootstrap import build_risk_payload

    shadow = [_candidate("FIN_UNEXPECTED_EXPENSE", "2026"),
              _candidate("FIN_CASHFLOW_PRESSURE", "2027"),
              _candidate("CAR_ORG_CONFLICT", "2028", RiskDomain.CAREER)]
    payload = build_risk_payload(
        shadow, question_type="period_overview",
        allowed_periods=frozenset({"2026", "2028"}))
    assert payload is not None
    audit = payload["exposureFilterAudit"]
    assert any(a["periodKey"] == "2027"
               and a["reason"] == "OUTSIDE_TIME_SCOPE" for a in audit)
    exposed_periods = {
        str((r.get("diagnostics") or {}).get("startPeriod", ""))[:4]
        for r in payload["presentationRecords"]}
    assert "2027" not in exposed_periods


def test_domain_filter_keeps_target_candidates() -> None:
    """타 도메인 고득점이 있어도 대상 도메인 후보가 정상 선별(P0②)."""
    from saju_api.services.risk_exposure_bootstrap import build_risk_payload

    shadow = [_candidate("FIN_UNEXPECTED_EXPENSE", "2026",
                         strength=0.9),  # 고득점 타 도메인
              _candidate("CAR_ORG_CONFLICT", "2026", RiskDomain.CAREER,
                         strength=0.5)]
    payload = build_risk_payload(
        shadow, question_type="single_domain_period",
        target_domains=("career",))
    assert payload is not None
    domains = {d for r in payload["presentationRecords"]
               for d in (r.get("domains") or [])
               if r.get("presentationLevel") != "none"}
    assert domains <= {"career"}
    assert any(a["reason"] == "OUTSIDE_TARGET_DOMAIN"
               for a in payload["exposureFilterAudit"])


# ── 6단계: reserve 활성 판정(테스트 게이트 5)·MAX_TOKENS ───────────────


def test_gate5_reserve_inactive_on_predetermined_bypass(monkeypatch) -> None:
    from saju_api.services.risk_exposure_service import risk_reserve_active

    good_inputs = {"counter": lambda t: 1,
                   "reviewed_shape_digests": frozenset({"d1"})}
    good_payload = {"llmRiskEpisodes": [{"guidanceRef": "r1"}]}
    good_mapped = {"question_type": "period_overview",
                   "subject_scope": "single"}
    assert risk_reserve_active(good_mapped, good_payload, good_inputs)
    # BYPASS 사전 확정 5경로 — 전부 reserve 미적용
    assert not risk_reserve_active(None, good_payload, good_inputs)  # TIMELESS
    assert not risk_reserve_active(
        good_mapped, {"llmRiskEpisodes": []}, good_inputs)  # 후보 0건
    assert not risk_reserve_active(
        good_mapped, good_payload,
        {"counter": None, "reviewed_shape_digests": frozenset({"d"})},
    )  # adapter 미검증(lease 무효 등)
    assert not risk_reserve_active(
        good_mapped, good_payload,
        {"counter": lambda t: 1, "reviewed_shape_digests": frozenset()},
    )  # shape 미검증
    monkeypatch.setattr(
        "saju_engines.risk_engine_config.RISK_COMPANION_KILL_SWITCH", True)
    assert not risk_reserve_active(
        {"question_type": "period_overview",
         "subject_scope": "companion_pair"}, good_payload, good_inputs)


def test_max_tokens_truncation_discard_and_compact_regen() -> None:
    """MAX_TOKENS 응답 폐기 → REVISION 건너뛰고 REGENERATE(compact) 1회."""
    import hashlib as _hashlib
    import json as _json

    from saju_api.services.risk_llm_pipeline import (
        build_risk_execution_context,
        run_injected_risk_flow,
    )
    from saju_api.services.token_counter_registry import (
        ProviderRequest,
        TokenCounterAdapter,
    )
    from saju_engines.risk_exposure import (
        RiskPromptBlock,
        build_guidance_reference_context,
        wrap_risk_block,
    )

    _guidance = build_guidance_reference_context(
        "t1", {"llmRiskEpisodes": [], "guidanceRefMap": {}})
    serial = '{"riskEpisodes": []}'
    wrapped = wrap_risk_block(RiskPromptBlock(
        serialized_text=serial,
        content_hash=_hashlib.sha256(serial.encode()).hexdigest()[:16],
        compression_mode="FULL", exact_token_count=1))
    from saju_api.services.token_counter_registry import (
        adapter_validation_policy_hash,
        register_adapter,
        set_validation_state,
    )
    adapter = TokenCounterAdapter(
        model_id="m-trunc", mode="PROVIDER_EXACT", counter=lambda s: 50,
        provider_id="gemini", counter_version="t",
        validation_corpus_hash="c" * 64)
    register_adapter(adapter)
    set_validation_state("m-trunc", "VALIDATED")
    manifest_entry = {
        "reviewed": True, "resolvedModelId": "m-trunc",
        "providerId": "gemini", "counterVersion": "t",
        "providerRequestSchemaVersion": "1",
        "countMode": "PROVIDER_EXACT",
        "validationPolicyHash": adapter_validation_policy_hash(),
        "validationCorpusHash": "c" * 64}
    ctx = build_risk_execution_context(
        "t1", manifest_counters=[manifest_entry],
        guidance_context=_guidance,
        baseline_request=ProviderRequest(user_messages=("base",)),
        resolved_model_id="m-trunc")
    calls: list[str] = []

    def _llm(request: ProviderRequest) -> dict:
        calls.append("call")
        if len(calls) == 1:  # INITIAL — 잘린 응답
            return {"answer": "잘린 위험 설명…",
                    "envelope": {"main_answer": "잘린"},
                    "provider_reported_input": 10, "cached_input": 0,
                    "finish_reason": "MAX_TOKENS"}
        return {"answer": "위험 없는 기본 답변", "envelope": None,
                "provider_reported_input": 10, "cached_input": 0,
                "finish_reason": "STOP"}

    result = run_injected_risk_flow(
        initial_request=ProviderRequest(
            user_messages=("q\n" + wrapped,),
            output_schema=_json.dumps({"type": "object"})),
        baseline_request=ProviderRequest(user_messages=("base",)),
        execution_context=ctx, llm_episodes=[], adapter=adapter,
        final_token_limit=100_000, llm_call=_llm,
        renderer=lambda t: t, resolve_model=lambda: "m-trunc",
        reviewed_shape_digests=None, drift_observer=None)
    # 부분 결과 미전달 — 잘린 초안이 최종 텍스트가 아니어야 한다
    assert "잘린" not in str(result.get("final_text", ""))
    attempts = result.get("attempts", [])
    initial = next(a for a in attempts if a.get("kind") == "INITIAL")
    assert "OUTPUT_TRUNCATED_MAX_TOKENS" in (
        initial.get("audit_issues") or [])
    assert initial.get("audit_action") == "DISCARDED"
    # REVISION은 skip(잘린 초안 재전송 금지) — compact 재생성으로 직행
    assert any(a.get("skipped") and "TRUNCATED" in str(a.get("reason", ""))
               for a in attempts if a.get("kind") == "REVISION_1")
    assert any(a.get("kind") == "REGENERATE_WITHOUT_RISK"
               for a in attempts)
    assert len(calls) == 2  # INITIAL + REGENERATE(1회) — 자동 재시도 없음
