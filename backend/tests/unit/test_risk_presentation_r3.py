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
    identity_phrase_mode,
    independent_cause_count,
    presentation_level,
    serialize_presentation,
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
    payloads = build_presentation(selected, cands)
    after = ([ep.model_dump() for ep in selected], list(dropped))
    assert before == after
    # episode 추가·삭제 없음 — NONE도 payload 보존(조용한 삭제 금지).
    assert len(payloads) == len(selected)
    keys = {p["diagnostics"]["episodeKey"] for p in payloads}
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
    payloads = build_presentation(selected, patched)
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
    base = build_presentation(eps, cands)
    with_rec = attach_recovery_windows(
        eps, cands, ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"])
    after = build_presentation(with_rec, cands)
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
    payloads = build_presentation(eps, scored)
    p = payloads[0]
    assert "possibly_related" in p["requiredQualifiers"]
    assert "same_episode_certainty" in p["prohibitedClaimCodes"]


def test_token_guard_preserves_p0_under_extreme_budget() -> None:
    """극단적 예산 부족 → prohibited claim·qualifier·대표 요약·level 보존,
    episode 삭제 없음(compact P0 표현으로 유지)."""
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
    payloads = build_presentation(eps, cands, claims)
    out = serialize_presentation(payloads, char_budget=10)  # 극단 부족
    data = json.loads(out)
    assert len(data["riskEpisodes"]) == len(payloads)  # 조용한 삭제 없음
    for p in data["riskEpisodes"]:
        assert set(GLOBAL_PROHIBITED_CLAIM_CODES) <= set(
            p["prohibitedClaimCodes"])
        assert "presentationLevel" in p and "requiredQualifiers" in p
        assert "diagnostics" not in p  # P3부터 탈락
    # 충분한 예산이면 전체 tier 포함.
    full = json.loads(serialize_presentation(payloads, char_budget=100_000))
    assert "diagnostics" in full["riskEpisodes"][0]


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
    allowed = {"risk_presentation.py"}
    offenders = [h for h in hits if Path(h).name not in allowed]
    assert offenders == [], offenders
    assert sys.modules  # sanity
