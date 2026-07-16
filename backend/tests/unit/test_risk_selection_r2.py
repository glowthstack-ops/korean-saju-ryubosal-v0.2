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
    assert dropped and dropped[0][1] == "NO_EXPOSABLE_REPRESENTATIVE"


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
    """서로 다른 episode 4 + hard_max 3 → 상위 3 선택 + 누락 taxonomy 기록.

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
    assert any(reason == "BUDGET_HARD_MAX" for _, reason in dropped)


def test_same_role_distinct_episodes_not_hard_deduped() -> None:
    """감수 35차: 다른 현실 episode의 같은 effect role·shared cause는 제거
    금지(soft tie-break만) — 적격이 예산 이하면 중복이라도 전부 선택."""
    exam1 = _cand(risk_id="SEL_D1", selection_episode_id="exam_1",
                  role="result_wait_delay", sources=(_CHUNG,))
    exam2 = _cand(risk_id="SEL_D2", selection_episode_id="exam_2",
                  role="result_wait_delay", sources=(_CHUNG,))
    scored = _scored([exam1, exam2])
    eps = build_episodes(scored)
    assert len(eps) == 2  # 서로 다른 실제 선발 건
    selected, dropped = select_episodes(eps, scored, RiskBudgetPolicy(hard_max=3))
    assert len(selected) == 2  # 같은 role·같은 cause라도 둘 다 보존
    assert not dropped
    # portfolio에선 같은 원인 1회.
    diag = portfolio_diagnostics(eps, selected)
    assert diag["unique_cause_count"] == 1
    # 예산 초과 시에도 사유는 '중복 제거'가 아니라 우선도 taxonomy.
    selected1, dropped1 = select_episodes(
        eps, scored, RiskBudgetPolicy(hard_max=1))
    assert len(selected1) == 1
    assert dropped1[0][1] in ("BUDGET_HARD_MAX", "LOWER_PRIORITY")


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


# ── 감수 35차 보완 fixture ────────────────────────────────────────


def test_same_local_string_different_axis_never_merges() -> None:
    """같은 local 문자열 + 다른 context 축 → 병합 금지(축 namespace)."""
    mob = _cand(risk_id="MOV_X", domain=RiskDomain.RELOCATION,
                role="schedule_disruption", mobility_episode_id="case_1")
    leg = _cand(risk_id="LEG_X", domain=RiskDomain.CONTRACT_LEGAL,
                role="administrative_delay", legal_episode_id="case_1",
                sources=(_HYEONG,))
    eps = build_episodes(_scored([mob, leg]))
    assert len(eps) == 2  # mobility:case_1 ≠ legal:case_1


def test_reality_alias_merges_across_axes() -> None:
    """다른 local id + 같은 reality_episode_id → 교차 도메인 episode 하나."""
    mov = _cand(risk_id="MOV_X", domain=RiskDomain.RELOCATION,
                role="contract_setback", mobility_episode_id="move_plan_1",
                reality_episode_id="housing_contract_1")
    leg = _cand(risk_id="LEG_X", domain=RiskDomain.CONTRACT_LEGAL,
                role="document_defect", legal_episode_id="process_7",
                sources=(_HYEONG,), reality_episode_id="housing_contract_1")
    eps = build_episodes(_scored([mov, leg]))
    assert len(eps) == 1
    assert eps[0].episode_key == "reality:housing_contract_1"
    assert set(eps[0].domains) == {RiskDomain.RELOCATION,
                                   RiskDomain.CONTRACT_LEGAL}


def test_same_local_id_conflicting_reality_alias_splits() -> None:
    """같은 local id인데 reality alias 상충 → 병합 금지(후보 alias는 None —
    엔진 fail-closed와 동일 원리, alias 명시 후보끼리는 alias별 분리)."""
    a = _cand(risk_id="LEG_A", legal_episode_id="proc_1",
              role="contract_termination", reality_episode_id="deal_1")
    b = _cand(risk_id="LEG_B", legal_episode_id="proc_1",
              role="administrative_delay", sources=(_HYEONG,),
              reality_episode_id="deal_2")
    eps = build_episodes(_scored([a, b]))
    assert len(eps) == 2  # 같은 local id라도 현실 건이 다르면 분리


def test_reality_alias_propagates_from_contexts(  # 엔진 전파 검증
) -> None:
    """엔진: 매칭된 컨텍스트의 reality_episode_id가 후보로 복사되고, 상충 시
    None(fail-closed)."""
    from pathlib import Path as _P

    from saju_engines.risk_engine import (
        LegalProcessContext,
        RelationFact,
        RiskEngine,
        build_raw_period_facts,
    )
    from saju_shared_types.event_engine import (
        LuckLayer,
        Pillar4,
        PolarityRole,
        RelationKind,
        TenGod,
    )
    engine = RiskEngine(
        _P(__file__).resolve().parents[2] / "dictionaries")
    facts = build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void_active=False, polarity_role=PolarityRole.GI, twelve_stage=None)
    ctx = LegalProcessContext(
        target_type="contract", stage="active_contract",
        exposure_status=ExposureStatus.CONFIRMED,
        process_episode_id="proc_1", reality_episode_id="housing_1")
    trm = next(c for c in engine.generate(facts, legal_contexts=[ctx])
               if c.risk_id == "LEG_CONTRACT_TERMINATION_RISK")
    assert trm.reality_episode_id == "housing_1"


def test_ownership_beats_score_and_specificity() -> None:
    """primary ownership이 정렬 선두 — 점수·특이도 높은 비소유 후보가
    소유 축 매칭 후보를 밀어내지 못한다."""
    owner = _cand(risk_id="LEG_OWN", domain=RiskDomain.CONTRACT_LEGAL,
                  role="administrative_delay", rank=2,
                  legal_episode_id="e1",
                  reality_episode_id="deal_1", sources=(_HYEONG,))
    outsider = _cand(risk_id="FIN_OUT", domain=RiskDomain.FINANCE,
                     role="financial_outflow", rank=3,
                     reality_episode_id="deal_1",
                     sources=(_CHUNG, _HYEONG))  # 더 높은 점수·특이도
    scored = _scored([owner, outsider])
    eps = build_episodes(scored)
    assert len(eps) == 1
    rep = eps[0].representative_candidate_id
    assert rep is not None and rep.startswith("LEG_OWN|")


def test_fallback_no_transitive_bridge() -> None:
    """fallback은 완전 일치 그룹만 — pairwise 연쇄(transitive bridge)로
    비호환 후보가 한 episode에 합쳐지지 않는다."""
    a = _cand(risk_id="FIN_S", period="2026-01", family="fam_s",
              sources=(_CHUNG,))
    b = _cand(risk_id="FIN_S", period="2026-02", family="fam_s",
              sources=(_CHUNG, _HYEONG))  # 원인 집합 상이 — 다른 fallback 그룹
    c = _cand(risk_id="FIN_S", period="2026-03", family="fam_s",
              sources=(_HYEONG,))
    eps = build_episodes(_scored([a, b, c]))
    assert len(eps) == 3  # A↔B·B↔C가 부분 겹쳐도 전체 병합 없음(exact-match)


def test_episode_confidence_not_inflated_by_members() -> None:
    """duplicate supporting 구성원 추가 → episode confidence 불변(대표 기준)."""
    rep = _cand(risk_id="LEG_R", rank=3, legal_episode_id="e1",
                role="contract_termination")
    dup1 = _cand(risk_id="LEG_S1", rank=2, legal_episode_id="e1",
                 role="document_defect",
                 suppressed_by_specificity="LEG_R", primary_risk_id="LEG_R",
                 absorbed_role="supporting_manifestation")
    dup2 = _cand(risk_id="LEG_S2", rank=2, legal_episode_id="e1",
                 role="document_defect",
                 suppressed_by_specificity="LEG_R", primary_risk_id="LEG_R",
                 absorbed_role="supporting_manifestation")
    small = build_episodes(_scored([rep, dup1]))
    big = build_episodes(_scored([rep, dup1, dup2]))
    assert small[0].structural_confidence == big[0].structural_confidence
    assert small[0].context_confidence == big[0].context_confidence


def test_recovery_right_censored_and_multi_cause() -> None:
    """recovery: 지평 끝 일시 비활성=stable 미산출(right-censored),
    다른 primary cause 지속=earliest만(부분 완화)."""
    # ① 지평 마지막 직전 종료 — quiet 1기간뿐 → stable None + censored 기록.
    a = [_cand(risk_id="LEG_A", legal_episode_id="e1", period=p,
               role="contract_termination")
         for p in ("2026-01", "2026-02", "2026-03")]
    scored = _scored(a)
    eps = build_episodes(scored)
    horizon = ["2026-01", "2026-02", "2026-03", "2026-04"]
    out = attach_recovery_windows(eps, scored, horizon)
    rw = out[0].recovery_window
    assert rw is not None
    assert rw.earliest_relief_window == "2026-04"
    assert rw.stable_recovery_window is None  # quiet 1기간 — 우측 검열
    assert "right_censored_quiet_span" in rw.recovery_reasons
    # ② 충분한 quiet(2기간) → stable 산출·보수 confidence.
    horizon2 = horizon + ["2026-05"]
    out2 = attach_recovery_windows(eps, scored, horizon2)
    rw2 = out2[0].recovery_window
    assert rw2 is not None and rw2.stable_recovery_window == "2026-05"
    assert rw2.recovery_confidence <= 0.5
    # ③ 다중 cause — 하나 종료·하나 지평 끝까지 지속 → earliest만.
    multi = [
        _cand(risk_id="LEG_M", legal_episode_id="e2", period="2026-01",
              role="legal_dispute", sources=(_CHUNG, _HYEONG)),
        _cand(risk_id="LEG_M", legal_episode_id="e2", period="2026-02",
              role="legal_dispute", sources=(_HYEONG,)),
        _cand(risk_id="LEG_M", legal_episode_id="e2", period="2026-03",
              role="legal_dispute", sources=(_HYEONG,)),
        _cand(risk_id="LEG_M", legal_episode_id="e2", period="2026-04",
              role="legal_dispute", sources=(_HYEONG,)),
    ]
    scored_m = _scored(multi)
    eps_m = build_episodes(scored_m)
    out_m = attach_recovery_windows(eps_m, scored_m, horizon)
    rw_m = next(ep.recovery_window for ep in out_m
                if ep.recovery_window is not None)
    assert rw_m.stable_recovery_window is None
    assert "other_primary_cause_ongoing" in rw_m.recovery_reasons


# ── 감수 36차 보완 fixture ────────────────────────────────────────


def test_novelty_cannot_invert_clear_score_gap() -> None:
    """near-tie(ε=0.02) 밖의 점수 차이는 novelty로 역전 불가."""
    strong_dup = _cand(risk_id="LEG_S", legal_episode_id="e1",
                       role="contract_termination", sources=(_CHUNG,))
    strong_dup = strong_dup.model_copy(update={"evidence": [
        _ev(_CHUNG, strength=0.9)]})
    weak_novel = _cand(risk_id="FIN_N", domain=RiskDomain.FINANCE,
                       legal_episode_id="e2", role="financial_outflow",
                       sources=(_PA_DAY,))
    weak_novel = weak_novel.model_copy(update={"evidence": [
        _ev(_PA_DAY, strength=0.3)]})
    dup2 = _cand(risk_id="LEG_S2", legal_episode_id="e3",
                 role="contract_termination", sources=(_CHUNG,))
    dup2 = dup2.model_copy(update={"evidence": [_ev(_CHUNG, strength=0.85)]})
    scored = _scored([strong_dup, weak_novel, dup2])
    eps = build_episodes(scored)
    selected, _ = select_episodes(eps, scored, RiskBudgetPolicy(hard_max=2))
    reps = {ep.representative_candidate_id.split("|")[0]
            for ep in selected if ep.representative_candidate_id}
    assert reps == {"LEG_S", "LEG_S2"}  # 큰 점수차 — novelty 역전 금지


def test_reality_conflict_isolated_from_fallback() -> None:
    """alias CONFLICT 후보는 fallback 병합에 재진입하지 않고 단독 보존."""
    conflicted = _cand(risk_id="LEG_C", role="administrative_delay",
                       sources=(_HYEONG,), reality_conflict=True)
    normal = _cand(risk_id="LEG_N", family=conflicted.risk_family,
                   role="administrative_delay", sources=(_HYEONG,))
    eps = build_episodes(_scored([conflicted, normal]))
    assert len(eps) == 2
    conflict_ep = next(ep for ep in eps
                       if ep.episode_key.startswith("conflict:"))
    assert conflict_ep.context_confidence == 0.0  # identity 품질 0


def test_identity_quality_orders_context_confidence() -> None:
    """context confidence: reality alias > 축 explicit > fallback."""
    real = _cand(risk_id="LEG_R", legal_episode_id="p1",
                 reality_episode_id="deal_1", role="contract_termination")
    expl = _cand(risk_id="LEG_E", legal_episode_id="p2",
                 role="administrative_delay", sources=(_HYEONG,))
    fall = _cand(risk_id="FIN_F", domain=RiskDomain.FINANCE,
                 role="financial_outflow", sources=(_PA_DAY,))
    eps = {ep.episode_key.split(":")[0]: ep
           for ep in build_episodes(_scored([real, expl, fall]))}
    assert eps["reality"].context_confidence > eps["explicit"].context_confidence
    assert eps["explicit"].context_confidence > eps["fallback"].context_confidence


def test_transition_does_not_flip_ownership_or_create_recovery() -> None:
    """교운기 보정 후 비소유 후보 점수가 더 높아도 primary owner 대표 유지,
    교운 가중 감소가 stable recovery를 단독 생성하지 못한다."""
    owner = _cand(risk_id="LEG_OWN", domain=RiskDomain.CONTRACT_LEGAL,
                  role="administrative_delay", rank=2, legal_episode_id="e1",
                  reality_episode_id="deal_1", sources=(_HYEONG,))
    outsider = _cand(risk_id="FIN_OUT", domain=RiskDomain.FINANCE,
                     role="financial_outflow", rank=3,
                     reality_episode_id="deal_1",
                     sources=(_CHUNG, _HYEONG))
    outsider = outsider.model_copy(
        update={"transition_sensitivity": "high"})
    scored = score_shadow([owner, outsider], {"LEG_OWN": 0.6, "FIN_OUT": 0.6},
                          transition_weights={"2026": 1.0})
    assert scored[1].transition_bonus > scored[0].transition_bonus
    eps = build_episodes(scored)
    rep = eps[0].representative_candidate_id
    assert rep is not None and rep.startswith("LEG_OWN|")  # ownership 유지
    # 교운 가중이 줄어드는 기간이 있어도 cause lineage 지속이면 recovery 없음.
    horizon = ["2026", "2027"]
    out = attach_recovery_windows(eps, scored, horizon)
    rw = out[0].recovery_window
    assert rw is None or rw.stable_recovery_window is None


def test_earliest_relief_requires_top_cause_not_minor() -> None:
    """보조(약한) cause만 종료되면 earliest relief 미생성 — 최고 기여 cause
    완화 기준(감수 36차)."""
    strong_going = [
        _cand(risk_id="LEG_M", legal_episode_id="e1", period=p,
              role="legal_dispute", sources=(_CHUNG, _HYEONG))
        for p in ("2026-01",)
    ]
    # 이후 기간: 강한 cause(_CHUNG, strength 0.5)가 계속, 약한 보조는 소멸.
    strong_going[0] = strong_going[0].model_copy(update={"evidence": [
        _ev(_CHUNG, strength=0.6, period="2026-01"),
        _ev(_HYEONG, strength=0.2, period="2026-01"),
    ], "trigger_cause_atoms": [_CHUNG, _HYEONG]})
    later = [
        _cand(risk_id="LEG_M", legal_episode_id="e1", period=p,
              role="legal_dispute", sources=(_CHUNG,))
        for p in ("2026-02", "2026-03")
    ]
    scored = _scored(strong_going + later)
    eps = build_episodes(scored)
    horizon = ["2026-01", "2026-02", "2026-03"]
    out = attach_recovery_windows(eps, scored, horizon)
    for ep in out:
        rw = ep.recovery_window
        # 최고 기여 cause(_CHUNG)가 지평 끝까지 활성 — relief 미생성.
        assert rw is None
