"""R4 EXPOSE 게이트 필수 fixture (감수 44차 — RISK_DICTIONARY_REVIEW.md §27).

성공 조건: 위험 payload가 안전하게 만들어졌더라도 실제 모델·질문·프롬프트의
남은 토큰과 감수 상태를 모두 확인하기 전에는 절대 주입하지 않는다.
"""

from __future__ import annotations

import json

import pytest

from saju_engines.risk_exposure import (
    CRITICAL_DOWNGRADE_REASON,
    ExposureGateContext,
    apply_exposure_levels,
    available_risk_tokens,
    effective_risk_budget,
    evaluate_risk_exposure_gate,
    exposure_token_budget_for,
)
from saju_engines.risk_presentation import build_presentation
from saju_engines.risk_scoring import score_shadow
from saju_engines.risk_selection import build_episodes
from saju_shared_types.risk_engine import (
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEngineMode,
    RiskEvidence,
    RiskKind,
)

_CHUNG = "relation:CHUNG:month_pillar:branch:ZHENGCAI"
_HYEONG = "relation:HYEONG:month_pillar:branch:ZHENGCAI"


def _ev(source: str, *, period="2026") -> RiskEvidence:
    return RiskEvidence(
        evidence_id=f"{period}|{source}", code="R4", period_key=period,
        layer="sewoon", source=source, strength=0.5,
        role=EvidenceRole.TRIGGER, source_group="event_shape",
        target_domain=RiskDomain.CONTRACT_LEGAL,
    )


def _cand(*, risk_id, sources=(_CHUNG,),
          role="legal_dispute", **overrides) -> RiskCandidate:
    ev = [_ev(s) for s in sources]
    atoms = sorted({a for e in ev for a in e.source.split("&")})
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.CONTRACT_LEGAL,
        kind=RiskKind.INCIDENT_RISK, risk_family="fam", period_key="2026",
        evidence=ev, exposure_status=ExposureStatus.CONFIRMED,
        specificity_rank=2, normalized_effect_role=role,
        trigger_cause_atoms=atoms, **overrides)


def _payload():
    cands = score_shadow(
        [_cand(risk_id="LEG_A", legal_episode_id="e1"),
         _cand(risk_id="LEG_B", legal_episode_id="e2", sources=(_HYEONG,),
               role="administrative_delay")],
        {"LEG_A": 0.6, "LEG_B": 0.6})
    return build_presentation(build_episodes(cands), cands)


def _ctx(**overrides) -> ExposureGateContext:
    base: dict = dict(
        mode=RiskEngineMode.EXPOSE,
        question_type="period_overview",
        temporal_scope="future",
        risk_intent_allowed=True,
        token_count_mode="MODEL_TOKENIZER",
        model_context_limit=16_000,
        base_prompt_tokens=4_000,
        user_input_tokens=200,
        existing_context_tokens=6_000,
        response_reserve=2_000,
        scopes_all_reviewed=True,
        policy_hashes_match=True,
        expose_pipeline_reviewed=True,
        counter_model_id="test-model",
        resolved_model_id="test-model",
    )
    base.update(overrides)
    return ExposureGateContext(**base)


_COUNTER = len  # 결정적 대체 tokenizer(문자=토큰 — 테스트 전용 과대 계수)


def _tok(text: str) -> int:
    return max(1, len(text) // 4)


# ── §13 필수 fixture ─────────────────────────────────────────────


def test_tokenizer_absent_or_heuristic_suppresses() -> None:
    """adapter 없음/heuristic 모드 → EXPOSE 비주입(TOKENIZER_UNAVAILABLE)."""
    payload = _payload()
    out = evaluate_risk_exposure_gate(_ctx(), payload, counter=None)
    assert out["inject"] is False
    assert out["suppression_reason"] == "TOKENIZER_UNAVAILABLE"
    out2 = evaluate_risk_exposure_gate(
        _ctx(token_count_mode="HEURISTIC_FALLBACK"), payload, counter=_tok)
    assert out2["suppression_reason"] == "TOKENIZER_UNAVAILABLE"


def test_adapter_actual_count_governs_budget() -> None:
    """adapter actual count > heuristic이면 actual 기준으로 판정 —
    예산 초과 시 비주입(TOKEN_BUDGET_INSUFFICIENT)."""
    payload = _payload()

    def huge_counter(_text: str) -> int:
        return 10_000  # 실제 tokenizer가 훨씬 크게 계수하는 상황

    out = evaluate_risk_exposure_gate(_ctx(), payload, counter=huge_counter)
    assert out["inject"] is False
    assert out["suppression_reason"] == "TOKEN_BUDGET_INSUFFICIENT"
    # 정상 계수면 주입.
    ok = evaluate_risk_exposure_gate(_ctx(), payload, counter=_tok)
    assert ok["inject"] is True


def test_full_prompt_headroom_governs_not_payload_size() -> None:
    """risk payload 단독으론 512 이하라도 전체 prompt headroom<512 → 비주입."""
    payload = _payload()
    tight = _ctx(existing_context_tokens=9_800)  # available < 512
    avail = available_risk_tokens(
        model_context_limit=16_000, base_prompt_tokens=4_000,
        user_input_tokens=200, existing_context_tokens=9_800,
        response_reserve=2_000)
    assert avail < 512
    out = evaluate_risk_exposure_gate(tight, payload, counter=_tok)
    assert out["inject"] is False
    assert out["suppression_reason"] == "TOKEN_BUDGET_INSUFFICIENT"


def test_computed_critical_exposed_as_warning_with_audit() -> None:
    """computed CRITICAL + 실증 pending → exposed WARNING·감사에 computed
    보존(item-level 하향 — payload 전체 차단 아님)."""
    records = [{"presentationLevel": "critical",
                "presentationLabel": "우선 점검 필요",
                "requiredQualifiers": []},
               {"presentationLevel": "watch",
                "presentationLabel": "관찰 필요",
                "requiredQualifiers": []}]
    out = apply_exposure_levels(records)
    crit = out[0]
    assert crit["computedPresentationLevel"] == "critical"
    assert crit["exposedPresentationLevel"] == "warning"
    assert crit["presentationLevel"] == "warning"
    assert crit["exposureDowngradeReason"] == CRITICAL_DOWNGRADE_REASON
    assert out[1]["exposedPresentationLevel"] == "watch"
    assert "exposureDowngradeReason" not in out[1]
    # 원본 불변(순수).
    assert records[0]["presentationLevel"] == "critical"


def test_scope_or_hash_mismatch_suppresses() -> None:
    """scope 미감수·policy hash 불일치 → 비주입."""
    payload = _payload()
    out = evaluate_risk_exposure_gate(
        _ctx(scopes_all_reviewed=False), payload, counter=_tok)
    assert out["suppression_reason"] == "SCOPE_NOT_REVIEWED"
    out2 = evaluate_risk_exposure_gate(
        _ctx(policy_hashes_match=False), payload, counter=_tok)
    assert out2["suppression_reason"] == "POLICY_HASH_MISMATCH"


def test_mode_gates_off_shadow_and_canary() -> None:
    """OFF/SHADOW=비주입(MODE_NOT_EXPOSE), CANARY는 allowlist 필수."""
    payload = _payload()
    for mode in (RiskEngineMode.OFF, RiskEngineMode.SHADOW):
        out = evaluate_risk_exposure_gate(_ctx(mode=mode), payload,
                                          counter=_tok)
        assert out["suppression_reason"] == "MODE_NOT_EXPOSE"
    canary = evaluate_risk_exposure_gate(
        _ctx(mode=RiskEngineMode.EXPOSE_CANARY), payload, counter=_tok)
    assert canary["suppression_reason"] == "CANARY_NOT_ALLOWLISTED"
    canary_ok = evaluate_risk_exposure_gate(
        _ctx(mode=RiskEngineMode.EXPOSE_CANARY, canary_allowlisted=True),
        payload, counter=_tok)
    assert canary_ok["inject"] is True


def test_question_gate_temporal_policy_and_intent() -> None:
    """riskExposurePolicy enum(감수 45차 §9): 과거 회고·미등록 유형=비주입,
    ALLOW_IMPLICIT은 '위험' 단어 없이도 허용, REQUIRE_EXPLICIT만 intent 검사."""
    import saju_engines.risk_exposure as rx

    payload = _payload()
    for override in ({"temporal_scope": "past_only"},
                     {"question_type": "unknown_type"}):
        out = evaluate_risk_exposure_gate(_ctx(**override), payload,
                                          counter=_tok)
        assert out["suppression_reason"] == "QUESTION_TYPE_NOT_ALLOWED"
    # ALLOW_IMPLICIT: 위험을 직접 묻지 않아도(intent=False) 주입 허용.
    implicit = evaluate_risk_exposure_gate(
        _ctx(risk_intent_allowed=False), payload, counter=_tok)
    assert implicit["inject"] is True
    # REQUIRE_EXPLICIT 정책이면 intent=False → 비주입.
    orig = dict(rx.RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE)
    try:
        rx.RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE["period_overview"] = (
            "REQUIRE_EXPLICIT")
        out = evaluate_risk_exposure_gate(
            _ctx(risk_intent_allowed=False), payload, counter=_tok)
        assert out["suppression_reason"] == "QUESTION_TYPE_NOT_ALLOWED"
    finally:
        rx.RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE.clear()
        rx.RISK_EXPOSURE_POLICY_BY_QUESTION_TYPE.update(orig)


def test_token_budgets_are_separate_from_episode_budget() -> None:
    """R2 episode budget(개수)과 R3 token budget(길이)은 별도 정책."""
    from saju_engines.risk_selection import budget_for

    assert exposure_token_budget_for("specific_event") == 768
    assert exposure_token_budget_for("period_overview") == 1024
    assert budget_for("specific_event").hard_max == 2  # 개수 정책은 그대로
    with pytest.raises(ValueError):
        exposure_token_budget_for("unknown")
    # effective = min(유형, DEFAULT, headroom).
    assert effective_risk_budget("period_overview", 700) == 700
    assert effective_risk_budget("period_overview", 5_000) == 1024
    assert effective_risk_budget("specific_event", 5_000) == 768


def test_compact_overflow_suppresses_whole_payload() -> None:
    """P0_COMPACT조차 예산 초과 → episode 일부 삭제가 아니라 전체 비주입."""
    cands = score_shadow(
        [_cand(risk_id=f"LEG_{i:02d}", legal_episode_id=f"e{i}")
         for i in range(60)],
        {f"LEG_{i:02d}": 0.6 for i in range(60)})
    payload = build_presentation(build_episodes(cands), cands)
    ctx = _ctx(question_type="single_domain_period")
    out = evaluate_risk_exposure_gate(ctx, payload, counter=len)  # 과대 계수
    assert out["inject"] is False
    assert out["suppression_reason"] == "TOKEN_BUDGET_INSUFFICIENT"


def test_injection_serialized_has_exposed_levels_only() -> None:
    """주입 payload에는 exposed level만 — computed·downgrade 사유는 감사
    전용(LLM 비노출), 관측값 기록."""
    payload = _payload()
    out = evaluate_risk_exposure_gate(_ctx(), payload, counter=_tok)
    assert out["inject"] is True
    doc = json.loads(out["serialized"])
    for ep in doc["riskEpisodes"]:
        assert "computedPresentationLevel" not in ep
        assert "exposureDowngradeReason" not in ep
    obs = out["observability"]
    assert obs["injected"] is True and obs["effective_budget"] >= 512
    assert "critical_downgraded" in obs


# ── R5-a fixture(감수 45차 — §14 중 배선 전 계층) ────────────────


def test_kill_switch_first_and_pipeline_not_reviewed() -> None:
    """kill switch=게이트 최앞(mode 무관), expose_pipeline reviewed=false면
    모든 조건 충족이어도 비주입(EXPOSE_PIPELINE_NOT_REVIEWED)."""
    payload = _payload()
    out = evaluate_risk_exposure_gate(
        _ctx(kill_switch=True, expose_pipeline_reviewed=False,
             scopes_all_reviewed=False), payload, counter=_tok)
    assert out["suppression_reason"] == "KILL_SWITCH"  # primary=순서 최앞
    assert "EXPOSE_PIPELINE_NOT_REVIEWED" in out["all_suppression_reasons"]
    assert "SCOPE_NOT_REVIEWED" in out["all_suppression_reasons"]
    # 현 상태 계약: reviewed=false 단독으로도 비주입.
    out2 = evaluate_risk_exposure_gate(
        _ctx(expose_pipeline_reviewed=False), payload, counter=_tok)
    assert out2["suppression_reason"] == "EXPOSE_PIPELINE_NOT_REVIEWED"


def test_tokenizer_model_mismatch_suppresses() -> None:
    """counter 모델 ≠ 실제 호출 모델 → TOKENIZER_MODEL_MISMATCH(감수 45차)."""
    payload = _payload()
    out = evaluate_risk_exposure_gate(
        _ctx(counter_model_id="gpt-5-mini", resolved_model_id="gemini"),
        payload, counter=_tok)
    assert out["suppression_reason"] == "TOKENIZER_MODEL_MISMATCH"
    out2 = evaluate_risk_exposure_gate(
        _ctx(counter_model_id=None), payload, counter=_tok)
    assert out2["suppression_reason"] == "TOKENIZER_MODEL_MISMATCH"


def test_mixed_period_filters_to_future_intersection() -> None:
    """혼합 기간 질문: R2 선택 episode ∩ 미래 질문 범위만 노출 —
    past_only=false라는 이유로 과거 episode를 넣지 않는다."""
    from saju_engines.risk_exposure import filter_payload_to_future_scope

    past = _cand(risk_id="LEG_PAST", legal_episode_id="e1")
    past = past.model_copy(update={"period_key": "2024"})
    future = _cand(risk_id="LEG_FUT", legal_episode_id="e2",
                   sources=(_HYEONG,), role="administrative_delay")
    cands = score_shadow([past, future], {"LEG_PAST": 0.6, "LEG_FUT": 0.6})
    payload = build_presentation(build_episodes(cands), cands)
    assert len(payload["llmRiskEpisodes"]) == 2
    filtered = filter_payload_to_future_scope(payload, ("2026-01", "2027-12"))
    assert len(filtered["llmRiskEpisodes"]) == 1
    # 감사 records는 전량 보존(감수 46차 §4) — scope status만 표시.
    assert len(filtered["presentationRecords"]) == 2
    statuses = {r["diagnostics"]["episodeKey"]: r["exposureScopeStatus"]
                for r in filtered["presentationRecords"]}
    assert "OUTSIDE_FUTURE_SCOPE" in statuses.values()
    assert "IN_SCOPE" in statuses.values()
    assert payload["llmRiskEpisodes"] and len(
        payload["llmRiskEpisodes"]) == 2  # 입력 불변
    # 게이트 경유: future_period_range 지정 시 동일 필터.
    out = evaluate_risk_exposure_gate(
        _ctx(temporal_scope="mixed", future_period_range=("2026-01",
                                                          "2027-12")),
        payload, counter=_tok)
    assert out["inject"] is True
    assert out["observability"]["episode_count"] == 1


def test_final_prompt_recount_and_compression_retry() -> None:
    """최종 prompt 2차 계수(감수 45차 §1·§2): 사전 통과 후 wrapper 포함
    재계수 초과 → 더 작은 compression 재시도 → 전부 초과면 비주입."""
    from saju_engines.risk_exposure import (
        RiskPromptBlock,
        finalize_risk_prompt_block,
    )

    payload = _payload()
    exposed = {
        "globalProhibitedClaimCodes": payload["globalProhibitedClaimCodes"],
        "globalAllowedClaimCodes": payload["globalAllowedClaimCodes"],
        "llmRiskEpisodes": payload["llmRiskEpisodes"],
    }
    wrapper = "시스템 프롬프트 " * 100  # 고정 wrapper

    def builder(block_text: str) -> str:
        return wrapper + block_text

    # ① 충분한 한도 → 최대 tier(P2) 채택 + immutable block.
    block, reason = finalize_risk_prompt_block(
        exposed, budget=2_000, counter=_tok, final_prompt_builder=builder,
        final_token_limit=10_000)
    assert reason is None and isinstance(block, RiskPromptBlock)
    assert block.compression_mode == "FULL"  # FULL=P2 별칭(감수 46차 §5)
    assert block.immutable is True and len(block.content_hash) == 16
    import dataclasses

    import pytest as _pytest
    with _pytest.raises(dataclasses.FrozenInstanceError):
        block.serialized_text = "변조"  # type: ignore[misc]
    # ② block 자체는 budget 이내지만 최종 prompt가 한도 초과 → 작은 tier로.
    tight_limit = _tok(wrapper) + _tok(
        __import__("saju_engines.risk_presentation",
                   fromlist=["render_llm_payload"]).render_llm_payload(
            exposed, "P0_COMPACT")) + 1
    block2, reason2 = finalize_risk_prompt_block(
        exposed, budget=2_000, counter=_tok, final_prompt_builder=builder,
        final_token_limit=tight_limit)
    assert reason2 is None and block2 is not None
    assert block2.compression_mode == "P0_COMPACT"
    # ③ 전부 초과 → FINAL_PROMPT_TOKEN_OVERFLOW 비주입.
    block3, reason3 = finalize_risk_prompt_block(
        exposed, budget=2_000, counter=_tok, final_prompt_builder=builder,
        final_token_limit=10)
    assert block3 is None and reason3 == "FINAL_PROMPT_TOKEN_OVERFLOW"


def test_answer_claim_audit_blocks_prohibited_output() -> None:
    """생성 답변 사후 감사(감수 45차 §11): prohibited 표현·partial 동일 건
    단정·recovery 보장·level 격상 → REVISE_REQUIRED(그대로 노출 금지)."""
    from saju_engines.risk_claim_audit import audit_generated_risk_claims

    bad = ("이 시기에는 계약 문제가 반드시 발생하고, 두 신호는 같은"
           " 사건입니다. 6월 이후에는 완전히 해결됩니다.")
    out = audit_generated_risk_claims(
        bad, episode_prohibited_phrases=["계약 무산 단정"],
        required_qualifiers=["possibly_related"],
        max_exposed_level="warning")
    codes = {v["code"] for v in out["violations"]}
    assert out["action"] == "REVISE_REQUIRED"
    assert {"guaranteed_occurrence", "same_episode_certainty",
            "recovery_guarantee"} <= codes
    # 허용 표현(권고 수준)은 통과 — 과잉 차단 금지.
    ok = ("계약 조건을 한 번 더 검토해 두면 좋은 시기입니다. 관련 신호가"
          " 이어질 수 있어 진행 상황을 세심하게 살펴보시길 권합니다.")
    out2 = audit_generated_risk_claims(
        ok, required_qualifiers=["possibly_related"],
        max_exposed_level="warning")
    assert out2["action"] == "ALLOW" and out2["violations"] == []


def test_guard_block_is_expose_only() -> None:
    """suppressed guard block은 EXPOSE 계열 전용 상수 — OFF/SHADOW 프롬프트
    경로(chat/report/llm_client)에서 참조되지 않는다(byte 불변 유지)."""
    import subprocess
    from pathlib import Path

    from saju_engines.risk_exposure import RISK_EXPOSURE_GUARD_BLOCK

    assert "확대 해석하지 않는다" in RISK_EXPOSURE_GUARD_BLOCK
    assert "허용" in RISK_EXPOSURE_GUARD_BLOCK  # 과잉 차단 금지 문구
    backend = Path(__file__).resolve().parents[2]
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "RISK_EXPOSURE_GUARD_BLOCK",
         str(backend / "apps")],
        capture_output=True, text=True, check=False).stdout.splitlines()
    assert hits == []  # R5-b 배선 전 — 배선 시 EXPOSE 분기 내에서만 허용
