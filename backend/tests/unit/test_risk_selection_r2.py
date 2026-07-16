"""R2 선별 계층 필수 fixture (감수 34차 — RISK_DICTIONARY_REVIEW.md §20-9).

성공 조건: 같은 현실 건은 도메인·항목이 달라도 하나의 episode, 같은 원인은 여러
episode에 연결돼도 포트폴리오 1회, budget을 채우려 약한 위험을 만들지 않는다.
"""

from __future__ import annotations

from saju_engines.risk_scoring import score_shadow
from saju_engines.risk_selection import (
    RiskBudgetPolicy,
    attach_recovery_windows,
    build_episodes,
    portfolio_diagnostics,
    select_episodes,
)
from saju_shared_types.risk_engine import (
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
)

_CHUNG = "relation:CHUNG:month_pillar:branch:ZHENGCAI"
_HYEONG = "relation:HYEONG:month_pillar:branch:ZHENGCAI"
_PA_DAY = "relation:PA:day_pillar:branch:BIJIAN"


def _ev(source: str, *, strength=0.5, role=EvidenceRole.TRIGGER,
        period="2026") -> RiskEvidence:
    return RiskEvidence(
        evidence_id=f"{period}|{source}", code="R2", period_key=period,
        layer="sewoon", source=source, strength=strength, role=role,
        source_group="event_shape", target_domain=RiskDomain.FINANCE,
    )


def _cand(*, risk_id, domain=RiskDomain.FINANCE, family="fam",
          role="financial_outflow", period="2026", sources=(_CHUNG,),
          exposure=ExposureStatus.CONFIRMED, kind=RiskKind.INCIDENT_RISK,
          rank=2, **overrides) -> RiskCandidate:
    ev = [_ev(s, period=period) for s in sources]
    atoms = sorted({a for e in ev for a in e.source.split("&")})
    return RiskCandidate(
        risk_id=risk_id, domain=domain, kind=kind, risk_family=family,
        period_key=period, evidence=ev, exposure_status=exposure,
        specificity_rank=rank, normalized_effect_role=role,
        trigger_cause_atoms=atoms, **overrides)


def _scored(cands):
    return score_shadow(cands, {c.risk_id: 0.6 for c in cands})


# ── 병합 4종(§13) ─────────────────────────────────────────────────


def test_same_explicit_episode_merges_across_domains() -> None:
    """같은 explicit episode + 다른 risk_id·domain·cause → episode 하나."""
    mov = _cand(risk_id="MOV_X", domain=RiskDomain.RELOCATION,
                family="housing_contract", role="contract_setback",
                mobility_episode_id="housing_1")
    leg = _cand(risk_id="LEG_X", domain=RiskDomain.CONTRACT_LEGAL,
                family="contract", role="document_defect",
                sources=(_HYEONG,), mobility_episode_id="housing_1")
    eps = build_episodes(_scored([mov, leg]))
    assert len(eps) == 1
    ep = eps[0]
    assert set(ep.domains) == {RiskDomain.RELOCATION, RiskDomain.CONTRACT_LEGAL}
    assert len(ep.canonical_cause_ids) == 2  # 같은 episode + 다른 cause → cause 둘
    assert ep.episode_key.startswith("explicit:")


def test_different_episode_same_cause_two_episodes_portfolio_once() -> None:
    """다른 episode + 같은 cause → episode 둘 · portfolio cause 1회."""
    a = _cand(risk_id="LEG_A", legal_episode_id="contract_1",
              role="contract_termination")
    b = _cand(risk_id="LEG_B", legal_episode_id="permit_2",
              role="administrative_delay")
    eps = build_episodes(_scored([a, b]))
    assert len(eps) == 2
    diag = portfolio_diagnostics(eps, eps)
    assert diag["unique_cause_count"] == 1  # 같은 원인 — 포트폴리오 1회
    assert diag["shared_cause_episode_count"] == 2


def test_no_explicit_id_same_cause_different_target_no_merge() -> None:
    """명시 episode 없음 + 같은 관계 종류·다른 대상 → 병합 금지(fail-closed)."""
    a = _cand(risk_id="FIN_A", family="fam_a", sources=(_CHUNG,))
    b = _cand(risk_id="FIN_B", family="fam_b", sources=(_PA_DAY,))
    eps = build_episodes(_scored([a, b]))
    assert len(eps) == 2


def test_fallback_time_merge_requires_identity_contract() -> None:
    """fallback 시간 병합: 같은 대상·원인·family+인접 기간만 — family 다르면 분리."""
    s1 = _cand(risk_id="FIN_S", period="2026-01",
               sources=(_CHUNG,), family="fam_s")
    s2 = _cand(risk_id="FIN_S", period="2026-02",
               sources=(_CHUNG,), family="fam_s")
    other = _cand(risk_id="FIN_T", period="2026-01",
                  sources=(_CHUNG,), family="fam_t")
    eps = build_episodes(_scored([s1, s2, other]))
    keys = sorted(ep.episode_key for ep in eps)
    assert len(eps) == 2  # 같은 계열 2기간=1 episode + 다른 family=별도
    merged = next(ep for ep in eps if len(ep.member_candidate_ids) == 2)
    assert merged.start_period == "2026-01" and merged.end_period == "2026-02"
    assert all(k.startswith("fallback:") for k in keys)


# ── 대표 선택 2종(§13) ────────────────────────────────────────────


def test_unexposed_specific_does_not_displace_exposable_general() -> None:
    """비노출 구체 후보는 대표가 못 되고, 노출 가능한 일반 후보가 대표."""
    specific = _cand(risk_id="LEG_SPEC", rank=3,
                     exposure=ExposureStatus.UNKNOWN,
                     exposure_requirement="confirmed_required",
                     exposable_when_unknown=False,
                     legal_episode_id="e1", role="legal_dispute")
    general = _cand(risk_id="LEG_GEN", rank=2,
                    exposure=ExposureStatus.CONFIRMED,
                    legal_episode_id="e1", role="administrative_delay",
                    sources=(_HYEONG,))
    eps = build_episodes(_scored([specific, general]))
    assert len(eps) == 1
    rep = eps[0].representative_candidate_id
    assert rep is not None and rep.startswith("LEG_GEN|")


def test_high_scoring_vulnerability_cannot_represent() -> None:
    """vulnerability는 점수가 높아도 대표 불가 — background로만 보존."""
    vuln = _cand(risk_id="FIN_V", kind=RiskKind.VULNERABILITY, rank=1,
                 sources=(_CHUNG, _HYEONG), legal_episode_id="e1",
                 role="financial_buffer")
    weak = _cand(risk_id="FIN_W", rank=2, sources=(_PA_DAY,),
                 legal_episode_id="e1", role="cashflow_pressure")
    eps = build_episodes(_scored([vuln, weak]))
    assert len(eps) == 1
    rep = eps[0].representative_candidate_id
    assert rep is not None and rep.startswith("FIN_W|")
    assert eps[0].background_vulnerability_ids  # 삭제가 아니라 역할 보존


# ── budget 3종(§13) ──────────────────────────────────────────────


def test_budget_zero_when_no_qualified() -> None:
    """적격 후보 0 → 선택 0(hard_min 없음 — 약한 후보 끌어올림 금지)."""
    vuln = _cand(risk_id="FIN_V", kind=RiskKind.VULNERABILITY,
                 legal_episode_id="e1", role="financial_buffer")
    scored = _scored([vuln])
    eps = build_episodes(scored)
    selected, dropped = select_episodes(eps, scored, RiskBudgetPolicy())
    assert selected == []
    assert dropped and dropped[0][1] == "no_qualified_representative"


def test_one_episode_many_candidates_one_representative() -> None:
    """한 episode 후보 5개 → 대표 1개(구성원·역할 보존)."""
    cands = [
        _cand(risk_id=f"LEG_{i}", rank=r, legal_episode_id="e1", role=role,
              sources=(s,))
        for i, (r, role, s) in enumerate((
            (3, "contract_termination", _CHUNG),
            (2, "document_defect", _CHUNG),
            (2, "administrative_delay", _HYEONG),
            (2, "legal_dispute", _HYEONG),
            (1, "review_capacity", _CHUNG),
        ))
    ]
    scored = _scored(cands)
    eps = build_episodes(scored)
    assert len(eps) == 1 and len(eps[0].member_candidate_ids) == 5
    selected, _ = select_episodes(eps, scored, RiskBudgetPolicy())
    assert len(selected) == 1


def test_hard_max_selects_top_and_records_drops() -> None:
    """서로 다른 episode 4 + hard_max 3 → 상위 3 선택 + 누락 이유 기록.

    도메인 다양성 강제 없음 — 같은 도메인 episode 3개도 선택 가능.
    """
    cands = []
    for i, s in enumerate((0.9, 0.8, 0.7, 0.6)):
        c = _cand(risk_id=f"LEG_{i}", legal_episode_id=f"e{i}",
                  domain=RiskDomain.CONTRACT_LEGAL,
                  role=("contract_termination", "document_defect",
                        "administrative_delay", "legal_dispute")[i],
                  sources=(f"relation:CHUNG:month_pillar:branch:T{i}",))
        c = c.model_copy(update={"evidence": [
            _ev(f"relation:CHUNG:month_pillar:branch:T{i}", strength=s)]})
        cands.append(c)
    scored = _scored(cands)
    eps = build_episodes(scored)
    assert len(eps) == 4
    selected, dropped = select_episodes(eps, scored, RiskBudgetPolicy(hard_max=3))
    assert len(selected) == 3
    assert any(reason == "hard_max_budget" for _, reason in dropped)
    # 같은 effect role 중복은 budget 전에 제거된다.
    dup_role = _cand(risk_id="LEG_DUP", legal_episode_id="e9",
                     role="contract_termination", sources=(_PA_DAY,))
    scored2 = _scored(cands + [dup_role])
    eps2 = build_episodes(scored2)
    _, dropped2 = select_episodes(eps2, scored2, RiskBudgetPolicy(hard_max=4))
    assert any("duplicate_effect_role" in reason for _, reason in dropped2)


# ── recovery 1종(§13) — 점수·순위 완전 불변 ──────────────────────


def test_recovery_window_never_changes_scores_or_ranking() -> None:
    a = _cand(risk_id="LEG_A", legal_episode_id="e1", period="2026-01",
              role="contract_termination")
    b = _cand(risk_id="LEG_B", legal_episode_id="e2", period="2026-01",
              role="administrative_delay", sources=(_HYEONG,))
    scored = _scored([a, b])
    eps = build_episodes(scored)
    before_sel, _ = select_episodes(eps, scored, RiskBudgetPolicy())
    horizon = ["2026-01", "2026-02", "2026-03", "2026-04"]
    with_recovery = attach_recovery_windows(eps, scored, horizon)
    assert any(ep.recovery_window is not None for ep in with_recovery)
    # 점수 필드·대표·선택 결과 byte 불변(recovery_window만 추가).
    for ep0, ep1 in zip(eps, with_recovery, strict=True):
        assert ep0.model_dump(exclude={"recovery_window"}) == (
            ep1.model_dump(exclude={"recovery_window"}))
    after_sel, _ = select_episodes(with_recovery, scored, RiskBudgetPolicy())
    assert [ep.episode_key for ep in before_sel] == [
        ep.episode_key for ep in after_sel]
    # 단정 금지 — confidence는 보수 고정값.
    rw = next(ep.recovery_window for ep in with_recovery
              if ep.recovery_window is not None)
    assert rw.recovery_confidence <= 0.5
    assert rw.earliest_relief_window > "2026-01"
