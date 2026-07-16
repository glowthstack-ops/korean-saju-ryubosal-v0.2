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


def test_question_gate_temporal_and_intent() -> None:
    """과거 회고(past_only)·intent 불허·미등록 유형 → 비주입."""
    payload = _payload()
    for override in ({"temporal_scope": "past_only"},
                     {"risk_intent_allowed": False},
                     {"question_type": "unknown_type"}):
        out = evaluate_risk_exposure_gate(_ctx(**override), payload,
                                          counter=_tok)
        assert out["suppression_reason"] == "QUESTION_TYPE_NOT_ALLOWED"


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
