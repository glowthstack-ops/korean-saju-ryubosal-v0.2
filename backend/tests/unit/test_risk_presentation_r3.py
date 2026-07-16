"""R3 노출 계층 필수 fixture (감수 41차 — RISK_DICTIONARY_REVIEW.md §26·§19).

성공 조건: 위험 수준은 점수 재계산이 아니라 **기 감수 episode의 문장 강도
변환**이다 — R2 선택 집합 byte 불변, UNKNOWN·kind별 상한, critical=독립
canonical cause≥2(층 반복≠2), P0(claim·qualifier·대표 요약) 절대 보존.
"""

from __future__ import annotations

import json

from saju_engines.risk_presentation import (
    GLOBAL_PROHIBITED_CLAIM_CODES,
    build_presentation,
    critical_eligible_cause_count,
    identity_phrase_mode,
    independent_cause_count,
    presentation_decision,
    presentation_level,
    serialize_llm_payload,
)
from saju_engines.risk_scoring import score_shadow
from saju_engines.risk_selection import (
    RiskBudgetPolicy,
    attach_recovery_windows,
    build_episodes,
    select_episodes,
)
from saju_shared_types.risk_engine import (
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
    RiskScoreComponents,
)

_CHUNG = "relation:CHUNG:month_pillar:branch:ZHENGCAI"
_HYEONG = "relation:HYEONG:month_pillar:branch:ZHENGCAI"


def _ev(source: str, *, strength=0.5, period="2026",
        layer="sewoon") -> RiskEvidence:
    return RiskEvidence(
        evidence_id=f"{period}|{source}", code="R3", period_key=period,
        layer=layer, source=source, strength=strength,
        role=EvidenceRole.TRIGGER, source_group="event_shape",
        target_domain=RiskDomain.FINANCE,
    )


def _cand(*, risk_id, domain=RiskDomain.CONTRACT_LEGAL, family="fam",
          role="legal_dispute", period="2026", sources=(_CHUNG,),
          exposure=ExposureStatus.CONFIRMED, kind=RiskKind.INCIDENT_RISK,
          rank=2, **overrides) -> RiskCandidate:
    ev = [_ev(s, period=period) for s in sources]
    atoms = sorted({a for e in ev for a in e.source.split("&")})
    return RiskCandidate(
        risk_id=risk_id, domain=domain, kind=kind, risk_family=family,
        period_key=period, evidence=ev, exposure_status=exposure,
        specificity_rank=rank, normalized_effect_role=role,
        trigger_cause_atoms=atoms, **overrides)


def _scored(cands, impact=0.6):
    return score_shadow(cands, {c.risk_id: impact for c in cands})


def _comp(occ: float, exp: float = 1.0) -> RiskScoreComponents:
    return RiskScoreComponents(occurrence=occ, impact=0.9, exposure=exp,
                               persistence=0.0, compound=0.0, protection=0.0)


def _episode_with(rep_overrides: dict, *, ctx_conf: float | None = None):
    """단일 후보 episode + 대표를 원하는 상태로 만든 (ep, rep)."""
    c = _cand(risk_id="LEG_X", legal_episode_id="e1", **rep_overrides)
    scored = _scored([c])
    eps = build_episodes(scored)
    assert len(eps) == 1
    ep = eps[0]
    if ctx_conf is not None:
        ep = ep.model_copy(update={"context_confidence": ctx_conf})
    return ep, scored[0]


# ── §19 level fixture 5종 ─────────────────────────────────────────


def test_same_score_confirmed_over_unknown_over_unexposed() -> None:
    """같은 점수: CONFIRMED > UNKNOWN(상한) > 비노출(none)."""
    ep_c, rep_c = _episode_with({"exposure": ExposureStatus.CONFIRMED})
    ep_u, rep_u = _episode_with({"exposure": ExposureStatus.UNKNOWN})
    ep_d, rep_d = _episode_with({"exposure": ExposureStatus.DENIED})
    rep_c = rep_c.model_copy(update={"score_components": _comp(0.5)})
    rep_u = rep_u.model_copy(update={"score_components": _comp(0.5)})
    rep_d = rep_d.model_copy(update={"score_components": _comp(0.5)})
    order = ["none", "advisory", "watch", "warning", "critical"]
    lv_c = presentation_level(ep_c, rep_c)
    lv_u = presentation_level(ep_u, rep_u)
    lv_d = presentation_level(ep_d, rep_d)
    assert order.index(lv_c) > order.index(lv_u) > order.index(lv_d)
    assert lv_d == "none"


def test_unknown_incident_capped_at_watch() -> None:
    """UNKNOWN incident risk → WATCH 초과 금지(밴드가 critical이어도)."""
    ep, rep = _episode_with({"exposure": ExposureStatus.UNKNOWN,
                             "kind": RiskKind.INCIDENT_RISK})
    rep = rep.model_copy(update={"score_components": _comp(0.9, exp=0.55)})
    assert presentation_level(ep, rep) == "watch"
    # 허용 UNKNOWN pressure는 warning까지.
    ep2, rep2 = _episode_with({"exposure": ExposureStatus.UNKNOWN,
                               "kind": RiskKind.PRESSURE})
    rep2 = rep2.model_copy(update={"score_components": _comp(0.9, exp=0.55)})
    assert presentation_level(ep2, rep2) == "warning"
    # confirmed_required + UNKNOWN = none.
    ep3, rep3 = _episode_with({"exposure": ExposureStatus.UNKNOWN,
                               "exposure_requirement": "confirmed_required"})
    rep3 = rep3.model_copy(update={"score_components": _comp(0.9, exp=0.55)})
    assert presentation_level(ep3, rep3) == "none"


def test_vulnerability_capped_at_advisory() -> None:
    """vulnerability → ADVISORY 초과 금지."""
    ep, rep = _episode_with({"kind": RiskKind.VULNERABILITY,
                             "role": "financial_buffer"})
    rep = rep.model_copy(update={"score_components": _comp(0.9)})
    assert presentation_level(ep, rep) == "advisory"


def test_layer_repetition_is_not_two_independent_causes() -> None:
    """같은 cause의 대운·세운 반복 → 독립 canonical cause 1개(critical
    게이트에서 2개로 계산 금지 — layer corroboration은 confidence 소관)."""
    c = _cand(risk_id="LEG_X", legal_episode_id="e1")
    c = c.model_copy(update={"evidence": [
        _ev(_CHUNG, layer="daewoon"),
        _ev(_CHUNG, layer="sewoon"),
    ]})
    assert independent_cause_count(c) == 1
    two = _cand(risk_id="LEG_Y", legal_episode_id="e2",
                sources=(_CHUNG, _HYEONG))
    assert independent_cause_count(two) == 2


def test_critical_gate_requires_confirmed_and_two_causes() -> None:
    """critical = 밴드 critical + CONFIRMED + 독립 cause≥2 + identity
    resolved/explicit + context confidence — 미충족은 warning 하향."""
    # ① 충족: explicit episode·CONFIRMED·cause 2·confidence 충분.
    ep, rep = _episode_with({"sources": (_CHUNG, _HYEONG)}, ctx_conf=0.9)
    rep = rep.model_copy(update={"score_components": _comp(0.9)})
    assert presentation_level(ep, rep) == "critical"
    # ② cause 1개 → warning 하향.
    ep1, rep1 = _episode_with({}, ctx_conf=0.9)
    rep1 = rep1.model_copy(update={"score_components": _comp(0.9)})
    assert presentation_level(ep1, rep1) == "warning"
    # ③ partial identity → critical 금지(warning 하향).
    c = _cand(risk_id="MOV_P", domain=RiskDomain.RELOCATION,
              role="contract_setback", sources=(_CHUNG, _HYEONG),
              mobility_episode_id="mv1", reality_episode_id="deal_1")
    scored = _scored([c])
    eps = build_episodes(scored)
    ep_p = eps[0].model_copy(update={"context_confidence": 0.9})
    assert ep_p.reality_identity_status == "partial"
    rep_p = scored[0].model_copy(update={"score_components": _comp(0.9)})
    assert presentation_level(ep_p, rep_p) == "warning"
    # ④ context confidence 미달 → warning 하향.
    ep4, rep4 = _episode_with({"sources": (_CHUNG, _HYEONG)}, ctx_conf=0.2)
    rep4 = rep4.model_copy(update={"score_components": _comp(0.9)})
    assert presentation_level(ep4, rep4) == "warning"


# ── R2 불변 3종 ───────────────────────────────────────────────────


def test_presentation_does_not_change_r2_selection() -> None:
    """R3 산출 전후: 선택 episode id·대표·누락 기록 byte-identical +
    입력 episode 객체 불변(순수 함수)."""
    cands = _scored([
        _cand(risk_id="LEG_A", legal_episode_id="e1"),
        _cand(risk_id="LEG_B", legal_episode_id="e2", sources=(_HYEONG,),
              role="administrative_delay"),
        _cand(risk_id="FIN_C", domain=RiskDomain.FINANCE,
              legal_episode_id="e3", role="financial_outflow"),
    ])
    eps = build_episodes(cands)
    selected, dropped = select_episodes(
        eps, cands, RiskBudgetPolicy(soft_target=2, hard_max=2))
    before = ([ep.model_dump() for ep in selected], list(dropped))
    payload = build_presentation(selected, cands)
    after = ([ep.model_dump() for ep in selected], list(dropped))
    assert before == after
    # episode 추가·삭제 없음 — NONE도 감사 record에 보존(조용한 삭제 금지).
    records = payload["presentationRecords"]
    assert len(records) == len(selected)
    keys = {p["diagnostics"]["episodeKey"] for p in records}
    assert keys == {ep.episode_key for ep in selected}


def test_warning_first_is_stable_within_buckets() -> None:
    """warning-first는 bucket 사이만 재배열 — bucket 안은 R2 순서 유지."""
    strong = _cand(risk_id="LEG_S", legal_episode_id="e1",
                   sources=(_CHUNG, _HYEONG))
    weak_a = _cand(risk_id="LEG_A", legal_episode_id="e2",
                   role="administrative_delay", sources=(_HYEONG,))
    weak_b = _cand(risk_id="FIN_B", domain=RiskDomain.FINANCE,
                   legal_episode_id="e3", role="financial_outflow")
    scored = _scored([strong, weak_a, weak_b])
    # 대표 점수 조작: strong=warning 밴드, weak 2건=advisory 밴드.
    by_id = {c.risk_id: c for c in scored}
    patched = [
        by_id["LEG_A"].model_copy(update={"score_components": _comp(0.15)}),
        by_id["FIN_B"].model_copy(update={"score_components": _comp(0.14)}),
        by_id["LEG_S"].model_copy(update={"score_components": _comp(0.35)}),
    ]
    eps = build_episodes(patched)
    selected, _ = select_episodes(eps, patched,
                                  RiskBudgetPolicy(soft_target=3, hard_max=3))
    payloads = build_presentation(selected, patched)["presentationRecords"]
    levels = [p["presentationLevel"] for p in payloads]
    assert levels == sorted(
        levels, key=lambda lv: {"critical": 0, "warning": 0, "watch": 1,
                                "advisory": 2, "none": 3}[lv])
    # bucket 내 R2 순서 유지: advisory 2건은 selection 순서 그대로.
    adv = [p["diagnostics"]["selectionOrder"] for p in payloads
           if p["presentationLevel"] in ("advisory", "watch")]
    assert adv == sorted(adv)


def test_recovery_addition_does_not_change_level() -> None:
    """미래 recovery window 추가 → presentation level 불변."""
    cands = _scored([_cand(risk_id="LEG_A", legal_episode_id="e1",
                           period=p) for p in ("2026-01", "2026-02")])
    eps = build_episodes(cands)
    base = build_presentation(eps, cands)["presentationRecords"]
    with_rec = attach_recovery_windows(
        eps, cands, ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"])
    after = build_presentation(with_rec, cands)["presentationRecords"]
    assert [p["presentationLevel"] for p in base] == \
        [p["presentationLevel"] for p in after]
    assert after[0]["recoveryConfidenceBand"] is not None  # band만 노출


# ── identity·claim·token guard ───────────────────────────────────


def test_partial_identity_requires_qualifier() -> None:
    """partial episode → possibly_related 문구 모드 + qualifier 필수,
    same_episode_certainty는 전역 prohibited에 상존."""
    mov = _cand(risk_id="MOV_X", domain=RiskDomain.RELOCATION,
                role="contract_setback", mobility_episode_id="mv1",
                reality_episode_id="deal_1")
    leg = _cand(risk_id="LEG_X", role="legal_dispute", sources=(_HYEONG,),
                legal_episode_id="lg1", reality_episode_id="deal_1")
    scored = _scored([mov, leg])
    eps = build_episodes(scored)
    assert eps[0].reality_identity_status == "partial"
    assert identity_phrase_mode(eps[0]) == "possibly_related"
    payload = build_presentation(eps, scored)
    p = payload["presentationRecords"][0]
    assert "possibly_related" in p["requiredQualifiers"]
    assert "same_episode_certainty" in payload["globalProhibitedClaimCodes"]


def test_token_guard_fail_closed_and_tiers() -> None:
    """token guard(감수 43차): 512 미만=전체 비주입(fail-closed), 512 이상은
    tier 축약 — episode 삭제·qualifier/prohibited 제거는 어떤 단계에도 없고
    overflow 상태 주입 경로도 없다."""
    from saju_engines.risk_presentation import (
        MIN_SAFE_RISK_PRESENTATION_BUDGET,
    )

    cands = _scored([
        _cand(risk_id="LEG_A", legal_episode_id="e1",
              exposure=ExposureStatus.UNKNOWN, kind=RiskKind.PRESSURE,
              role="compliance_pressure"),
        _cand(risk_id="FIN_B", domain=RiskDomain.FINANCE,
              legal_episode_id="e2", role="financial_outflow"),
    ])
    eps = build_episodes(cands)
    claims = {"LEG_A": {"manifestations": ["점검 부담 증가 가능성"],
                        "prohibited": ["처분 단정"]}}
    payload = build_presentation(eps, cands, claims)
    # ① 512 미만 → 위험 payload 전체 비주입 + 사유(감사 기록은 payload 유지).
    low = json.loads(serialize_llm_payload(payload, token_budget=256))
    assert low["riskEpisodes"] == []
    assert low["exposureSuppressedReason"] == "TOKEN_BUDGET_INSUFFICIENT"
    assert low["globalProhibitedClaimCodes"] == list(
        GLOBAL_PROHIBITED_CLAIM_CODES)
    assert len(payload["presentationRecords"]) == 2  # 감사 기록 불변
    # ② min_safe(512)에서는 축약 계층으로 주입 가능해야 함(이 payload 크기).
    mid = json.loads(serialize_llm_payload(
        payload, token_budget=MIN_SAFE_RISK_PRESENTATION_BUDGET))
    assert len(mid["riskEpisodes"]) == len(payload["llmRiskEpisodes"])
    for ep in mid["riskEpisodes"]:
        assert "presentationLevel" in ep and "requiredQualifiers" in ep
        assert "diagnostics" not in ep
    assert "tokenBudgetOverflow" not in mid  # overflow 주입 경로 없음
    # ③ 충분한 예산 → 전체 tier(P2) — 진단은 여전히 미포함.
    full = json.loads(serialize_llm_payload(payload, token_budget=100_000))
    assert "effectRoles" in full["riskEpisodes"][0]
    assert "diagnostics" not in full["riskEpisodes"][0]
    # ④ P0_COMPACT조차 초과(episode 다수) → 전체 비주입(512 이상이어도).
    many = _scored([
        _cand(risk_id=f"LEG_{i:02d}", legal_episode_id=f"e{i}")
        for i in range(60)
    ])
    eps_many = build_episodes(many)
    payload_big = build_presentation(eps_many, many)
    big = json.loads(serialize_llm_payload(payload_big, token_budget=512))
    assert big["riskEpisodes"] == []
    assert big["exposureSuppressedReason"] == "TOKEN_BUDGET_INSUFFICIENT"


def test_estimator_is_conservative_for_korean() -> None:
    """estimator(감수 43차): 한국어(비ascii)는 1자≈1토큰 + 여유 — /3 과소
    추정 금지. tokenizer adapter 주입 시 그 결과를 우선한다."""
    from saju_engines.risk_presentation import estimate_tokens

    korean = "위험" * 300  # 600자 비ascii
    est = estimate_tokens(korean)
    assert est >= 600  # 비ascii 1:1 하한(구 ceil/3=200은 과소)
    ascii_text = "a" * 400
    assert estimate_tokens(ascii_text) >= 100  # ascii/4
    # adapter 주입 우선.
    assert estimate_tokens("anything", counter=lambda _t: 42) == 42


def test_user_labels_confirmed() -> None:
    """표시명(감수 43차 확정) — 사건 확정으로 읽히지 않는 대응 우선도."""
    from saju_engines.risk_presentation import USER_LEVEL_LABELS

    assert USER_LEVEL_LABELS == {
        "advisory": "참고 신호",
        "watch": "관찰 필요",
        "warning": "주의 필요",
        "critical": "우선 점검 필요",
    }


def test_shadow_mode_no_prompt_wiring() -> None:
    """SHADOW 계약: R3 모듈은 어떤 LLM 프롬프트 빌더에서도 import되지 않는다
    (payload 계산·검증만 — 기존 LLM 입력 byte 불변의 구조적 보장)."""
    import subprocess
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parents[2]
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "risk_presentation",
         str(backend / "apps"),
         str(backend / "packages" / "saju_engines" / "saju_engines")],
        capture_output=True, text=True, check=False).stdout.splitlines()
    # 위험 스택 내부 모듈(프롬프트 빌더 아님)만 허용.
    allowed = {"risk_presentation.py", "risk_exposure.py",
               "risk_claim_audit.py"}
    offenders = [h for h in hits if Path(h).name not in allowed]
    assert offenders == [], offenders
    assert sys.modules  # sanity


# ── 감수 42차 preflight fixture ──────────────────────────────────


def test_item_claim_ceiling_caps_level_without_touching_r1r2() -> None:
    """항목 claimCeiling이 level을 상한(감수 42차 §3) — 같은 점수·같은
    exposure에서 ceiling만 바꾸면 level만 내려가고 episode·점수는 불변."""
    ep, rep = _episode_with({}, ctx_conf=0.9)
    rep = rep.model_copy(update={"score_components": _comp(0.3)})  # warning 밴드
    before = (ep.model_dump(), rep.model_dump())
    d_plain = presentation_decision(ep, rep)
    d_capped = presentation_decision(ep, rep, item_claim_ceiling="advisory")
    assert d_plain["level"] == "warning"
    assert d_capped["level"] == "advisory"
    assert d_capped["primary_downgrade_reason"] == "ITEM_CLAIM_CEILING"
    assert (ep.model_dump(), rep.model_dump()) == before  # R1/R2 불변
    # exposurePolicy UNKNOWN ceiling — UNKNOWN일 때만 적용.
    ep_u, rep_u = _episode_with({"exposure": ExposureStatus.UNKNOWN,
                                 "kind": RiskKind.PRESSURE})
    rep_u = rep_u.model_copy(update={"score_components": _comp(0.9, 0.55)})
    d_u = presentation_decision(ep_u, rep_u,
                                unknown_claim_ceiling="advisory")
    assert d_u["level"] == "advisory"
    assert "EXPOSURE_POLICY_CEILING" in d_u["downgrade_reasons"]
    # ceiling "none" → 비노출 + CLAIM_CEILING_NONE 사유.
    d_none = presentation_decision(ep, rep, item_claim_ceiling="none")
    assert d_none["level"] == "none"
    assert d_none["omission_reason"] == "CLAIM_CEILING_NONE"


def test_critical_eligible_causes_exclude_supporting_and_partial() -> None:
    """critical 원인 수는 episode 전체가 아니라 적격 집합만(감수 42차 §4):
    absorbed supporting 원인 제외·독립 exposable primary effect 원인 포함·
    partial은 대표 원인만."""
    rep = _cand(risk_id="LEG_R", legal_episode_id="e1",
                role="contract_termination")
    absorbed = _cand(risk_id="LEG_S", legal_episode_id="e1",
                     role="administrative_delay", sources=(_HYEONG,),
                     suppressed_by_specificity="LEG_R")
    ep1 = build_episodes(_scored([rep, absorbed]))[0]
    scored = _scored([rep, absorbed])
    # ① 대표 1원인 + absorbed supporting 1원인 → 적격 1.
    assert critical_eligible_cause_count(ep1, scored[0], scored) == 1
    # ② 대표 1원인 + 독립 exposable primary effect(비흡수) 1원인 → 2 가능.
    independent = _cand(risk_id="LEG_I", legal_episode_id="e1",
                        role="legal_dispute", sources=(_HYEONG,))
    scored2 = _scored([rep, independent])
    ep2 = build_episodes(scored2)[0]
    assert critical_eligible_cause_count(ep2, scored2[0], scored2) == 2
    # ③ partial identity — 교차 연결 원인 배제(대표 원인만).
    mov = _cand(risk_id="MOV_X", domain=RiskDomain.RELOCATION,
                role="contract_setback", mobility_episode_id="mv1",
                reality_episode_id="deal_1")
    leg = _cand(risk_id="LEG_X", role="legal_dispute", sources=(_HYEONG,),
                legal_episode_id="lg1", reality_episode_id="deal_1")
    scored3 = _scored([mov, leg])
    ep3 = build_episodes(scored3)[0]
    assert ep3.reality_identity_status == "partial"
    assert critical_eligible_cause_count(ep3, scored3[0], scored3) == 1


def test_none_episodes_excluded_from_llm_payload_with_reason() -> None:
    """NONE은 감사 record에 omission reason과 함께 보존하되 LLM payload에서
    제외(감수 42차 §5) — prompt에 넣고 '언급 금지' 지시 방식 불허."""
    ok_a = _cand(risk_id="LEG_A", legal_episode_id="e1")
    ok_b = _cand(risk_id="LEG_B", legal_episode_id="e2",
                 role="administrative_delay", sources=(_HYEONG,))
    denied = _cand(risk_id="FIN_D", domain=RiskDomain.FINANCE,
                   legal_episode_id="e3", role="financial_outflow",
                   exposure=ExposureStatus.UNKNOWN,
                   exposure_requirement="confirmed_required",
                   exposable_when_unknown=False)
    scored = _scored([ok_a, ok_b, denied])
    eps = build_episodes(scored)
    payload = build_presentation(eps, scored)
    records = payload["presentationRecords"]
    llm = payload["llmRiskEpisodes"]
    assert len(records) == 3
    assert len(llm) == 2
    none_rec = next(r for r in records if r["presentationLevel"] == "none")
    assert none_rec["presentationOmissionReason"] in (
        "NON_EXPOSABLE", "CONFIRMED_REQUIRED_UNKNOWN")
    assert all("presentationOmissionReason" not in e for e in llm)
    assert all("diagnostics" not in e for e in llm)


def test_claim_conflict_prohibited_wins_and_unknown_fails() -> None:
    """claim 충돌은 prohibited 우선·미등록 코드 fail-closed(감수 42차 §6)."""
    import pytest

    c = _cand(risk_id="LEG_A", legal_episode_id="e1")
    scored = _scored([c])
    eps = build_episodes(scored)
    # allowed에 전역 prohibited 코드가 들어오면 effective에서 제거.
    payload = build_presentation(eps, scored, {
        "LEG_A": {"allowedCodes": ["watch_timing", "same_episode_certainty"]},
    })
    rec = payload["presentationRecords"][0]
    assert "same_episode_certainty" not in rec["effectiveAllowedClaimCodes"]
    assert "watch_timing" in rec["effectiveAllowedClaimCodes"]
    # 미등록 코드 → 오류.
    with pytest.raises(ValueError):
        build_presentation(eps, scored, {
            "LEG_A": {"allowedCodes": ["totally_unknown_code"]}})
    with pytest.raises(ValueError):
        build_presentation(eps, scored, {
            "LEG_A": {"prohibitedCodes": ["mystery_prohibition"]}})


def test_numeric_band_uses_capped_not_raw() -> None:
    """numeric band 입력=capped(감수 42차 §2) — cap 초과 raw는 R2 정렬
    소관, 표현 밴드는 bounded score로 동일."""
    from saju_engines.risk_presentation import numeric_band, score_band

    over = RiskScoreComponents(occurrence=0.8, impact=0.9, exposure=1.0,
                               persistence=0.6, compound=0.1, protection=0.0)
    ep, rep = _episode_with({}, ctx_conf=0.9)
    rep_over = rep.model_copy(update={"score_components": over})  # raw 1.224
    rep_one = rep.model_copy(update={"score_components": _comp(0.9)})
    d_over = presentation_decision(ep, rep_over)
    d_one = presentation_decision(ep, rep_one)
    # capped가 입력이므로 raw 1.224와 raw 0.81 모두 밴드 결정은 capped 기준
    # (동일 gate 결과) — cap 초과가 표현 밴드를 더 올리지 못한다.
    assert d_over["level"] == d_one["level"]
    assert numeric_band(1.0) == "critical" and score_band(1.0) == "high"
