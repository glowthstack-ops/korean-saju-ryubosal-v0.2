"""R1-a 점수 인프라 불변식 fixture (감수 26차 착수 — RISK_ENGINE.md §5).

데굴님 R1 성공 조건: 동일한 원인을 여러 도메인·episode에서 한 번만 평가하고,
점수 계산이 이미 감수된 적격성·노출·대표 선택을 단 한 건도 변경하지 않는 것.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.risk_engine import (
    RelationFact,
    RiskEngine,
    SelectionContext,
    build_raw_period_facts,
)
from saju_engines.risk_scoring import (
    RISK_SCORING_VERSION,
    cause_occurrence_table,
    risk_priority,
    score_shadow,
)
from saju_shared_types.event_engine import (
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
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

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    """위험 엔진(모듈 1회 로드)."""
    return RiskEngine(_DICTS)


def _facts(*, period="2026", gods=None, relations=None, void=False,
           role=PolarityRole.GI):
    return build_raw_period_facts(
        period_key=period, layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=void, polarity_role=role, twelve_stage=None,
    )


def _evidence(source: str, *, strength=0.5, role=EvidenceRole.TRIGGER,
              group="event_shape", layer="sewoon", period="2026") -> RiskEvidence:
    return RiskEvidence(
        evidence_id=f"{period}|{source}", code="SYN", period_key=period,
        layer=layer, source=source, strength=strength, role=role,
        source_group=group, target_domain=RiskDomain.FINANCE,
    )


def _candidate(*, risk_id="SYN_RISK", period="2026", evidence,
               exposure=ExposureStatus.UNKNOWN, family="syn",
               kind=RiskKind.INCIDENT_RISK, **overrides) -> RiskCandidate:
    atoms = sorted({
        a for e in evidence if e.role is EvidenceRole.TRIGGER
        for a in e.source.split("&")
    })
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.FINANCE, kind=kind,
        risk_family=family, period_key=period, evidence=evidence,
        exposure_status=exposure, trigger_cause_atoms=atoms, **overrides,
    )


_CHUNG = "relation:CHUNG:month_pillar:branch:ZHENGCAI"
_HYEONG = "relation:HYEONG:month_pillar:branch:ZHENGCAI"


def _comp(c: RiskCandidate) -> RiskScoreComponents:
    """score_components Optional narrowing 헬퍼."""
    assert c.score_components is not None
    return c.score_components


# ── 1. 적격성·대표·노출 결과 불변 — 점수는 아무 상태도 바꾸지 않는다 ──


def test_scoring_changes_nothing_but_scores(engine: RiskEngine) -> None:
    """엔진 실후보 전체: score_components·confidence 외 전 필드 byte 불변."""
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON},
                     TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGCAI)],
               void=True),
        selection_contexts=[SelectionContext(
            target_type="examination", stage="result_wait",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="exam_1")],
    )
    scored = score_shadow(cands, engine.base_impacts())
    assert len(scored) == len(cands)
    for before, after in zip(cands, scored, strict=True):
        b = before.model_dump(exclude={"score_components", "confidence"})
        a = after.model_dump(exclude={"score_components", "confidence"})
        assert a == b  # 적격성·대표·정렬·노출·episode 전부 불변
        assert after.score_components is not None
    # 원본 목록 자체도 불변(순수 함수).
    assert all(c.score_components is None for c in cands)


# ── 2. evidence 1회 반영 — 같은 원인을 잡은 복수 룰 = 1회 ─────────


def test_same_source_two_rules_counted_once() -> None:
    """같은 source를 일반 룰·targeted 룰이 함께 잡아도 occurrence는 1원인."""
    dup = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5, group="event_shape"),
        _evidence(_CHUNG, strength=0.5, group="targeted_event_shape"),
    ])
    single = _candidate(evidence=[_evidence(_CHUNG, strength=0.5)])
    [d, s] = score_shadow([dup, single], {})
    assert d.score_components is not None and s.score_components is not None
    assert _comp(d).occurrence == _comp(s).occurrence


# ── 3. 같은 대상의 충+형 = 독립 원인 2 / 다층 반복 = 원인 1 ───────


def test_two_relations_two_causes_multi_layer_one() -> None:
    two_kinds = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5), _evidence(_HYEONG, strength=0.5),
    ])
    multi_layer = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5, layer="daewoon+sewoon"),
    ])
    single = _candidate(evidence=[_evidence(_CHUNG, strength=0.5)])
    [a, b, c] = score_shadow([two_kinds, multi_layer, single], {})
    assert _comp(a).occurrence > _comp(c).occurrence
    # 다층 수렴은 occurrence 재합산 금지(원인 1) — confidence 진단으로만 상승.
    assert _comp(b).occurrence == _comp(c).occurrence
    assert b.confidence > c.confidence


# ── 4. 컨텍스트는 증거가 아님 — occurrence 비기여 ─────────────────


def test_context_never_raises_occurrence() -> None:
    """episode·질문 대상·CONFIRMED 노출·conflict가 occurrence를 못 올린다."""
    ev = [_evidence(_CHUNG, strength=0.5)]
    plain = _candidate(evidence=ev)
    contexted = _candidate(
        evidence=ev, exposure=ExposureStatus.CONFIRMED,
        selection_episode_id="exam_1", legal_episode_id="contract_1",
    )
    conflicted = _candidate(evidence=ev, selection_context_conflict=True)
    [p, ctx, cf] = score_shadow([plain, contexted, conflicted], {})
    assert _comp(p).occurrence == _comp(ctx).occurrence
    assert _comp(p).occurrence == _comp(cf).occurrence
    # exposure는 별도 축으로만 갈린다.
    assert _comp(ctx).exposure > _comp(p).exposure


# ── 5. 기여 0 역할 — polarity amplifier·mitigator는 occurrence 밖 ──


def test_amplifier_and_mitigator_zero_occurrence_contribution() -> None:
    base = _candidate(evidence=[_evidence(_CHUNG, strength=0.5)])
    with_amp = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5),
        _evidence("polarity:GI_STRONG", strength=0.9,
                  role=EvidenceRole.AMPLIFIER, group=None, layer="period"),
    ])
    [b, w] = score_shadow([base, with_amp], {})
    assert _comp(b).occurrence == _comp(w).occurrence
    # 실질 mitigator는 protection 축으로만(occurrence 불변).
    with_mit = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5),
        _evidence("relation:HAP:month_pillar:branch:ZHENGYIN", strength=0.4,
                  role=EvidenceRole.MITIGATOR, group=None),
    ])
    polarity_mit = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5),
        _evidence("polarity:YONG", strength=0.9,
                  role=EvidenceRole.MITIGATOR, group=None, layer="period"),
    ])
    [m, pm] = score_shadow([with_mit, polarity_mit], {})
    assert _comp(m).occurrence == _comp(b).occurrence
    assert _comp(m).protection > 0.0
    assert _comp(pm).protection == 0.0  # 극성 단독 전역 완화 금지


# ── 6. cause-level 1회 계산 — 교차 도메인·episode 공유 원인 ───────


def test_cause_occurrence_table_single_entry_per_cause() -> None:
    """같은 원인을 공유하는 다른 family 후보 — 표에는 (기간, 원인) 1항목."""
    a = _candidate(risk_id="SYN_A", family="fam_a",
                   evidence=[_evidence(_CHUNG, strength=0.5)])
    b = _candidate(risk_id="SYN_B", family="fam_b",
                   evidence=[_evidence(_CHUNG, strength=0.4)])
    table = cause_occurrence_table([a, b])
    assert list(table) == [("2026", _CHUNG)]
    assert table[("2026", _CHUNG)] == 0.5  # 최강 strength 1회(결정적)
    # compound 축이 독립 효과군 연결을 표현한다(occurrence 중복 가산 아님) —
    # 감수 29차: effect identity는 episode 서명으로 해결(resolved)돼야 한다.
    a_ep = a.model_copy(update={"legal_episode_id": "ep_a"})
    b_ep = b.model_copy(update={"legal_episode_id": "ep_b"})
    [sa, sb] = score_shadow([a_ep, b_ep], {})
    assert _comp(sa).compound > 0 and _comp(sb).compound > 0
    lone = _candidate(risk_id="SYN_C", evidence=[
        _evidence("relation:PA:day_pillar:branch:BIJIAN", strength=0.5)])
    [sc] = score_shadow([lone], {})
    assert _comp(sc).compound == 0.0  # 연결 없으면 0


def test_compound_requires_independent_exposable_effect() -> None:
    """감수 26차 보완 4(+29차 resolved 필수): alias·흡수·비노출 연결은 compound 0."""
    base = _candidate(risk_id="SYN_A", family="fam_a", legal_episode_id="e1",
                      evidence=[_evidence(_CHUNG, strength=0.5)])
    # 같은 family(role fallback 동일 — 동일 효과 계열의 파생 표현) → 연결 아님.
    alias = _candidate(risk_id="SYN_A2", family="fam_a", legal_episode_id="e2",
                       evidence=[_evidence(_CHUNG, strength=0.4)])
    [sa, _] = score_shadow([base, alias], {})
    assert _comp(sa).compound == 0.0
    # 흡수된 supporting 후보 → 연결 아님.
    absorbed = _candidate(
        risk_id="SYN_B", family="fam_b", legal_episode_id="e2",
        evidence=[_evidence(_CHUNG, strength=0.4)],
        suppressed_by_specificity="SYN_A", primary_risk_id="SYN_A",
        absorbed_role="supporting_manifestation")
    [sa2, _] = score_shadow([base, absorbed], {})
    assert _comp(sa2).compound == 0.0
    # 비노출 vulnerability 연결 → 연결 아님(rankable).
    vuln = RiskCandidate(
        risk_id="SYN_V", domain=RiskDomain.FINANCE,
        kind=RiskKind.VULNERABILITY, risk_family="fam_v", period_key="2026",
        legal_episode_id="e2",
        evidence=[_evidence(_CHUNG, strength=0.4)],
        trigger_cause_atoms=[_CHUNG])
    [sa3, _] = score_shadow([base, vuln], {})
    assert _comp(sa3).compound == 0.0
    # 독립 exposable 다른 효과(role 상이·resolved) → 연결 1건.
    other = _candidate(risk_id="SYN_C", family="fam_c", legal_episode_id="e2",
                       evidence=[_evidence(_CHUNG, strength=0.4)])
    [sa4, _] = score_shadow([base, other], {})
    assert _comp(sa4).compound == pytest.approx(0.10)  # 잠정 증분(감수 32차)


def test_multi_episode_same_cause_portfolio_once(engine: RiskEngine) -> None:
    """D-프로필 golden 축소판: 시험 2 episode 후보가 같은 원인을 공유해도
    cause 표 기여는 1회 — episode 개수는 occurrence bonus가 아니다."""
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGYIN)],
               void=True),
        selection_contexts=[
            SelectionContext(target_type="examination", stage="result_wait",
                             episode_id="exam_1"),
            SelectionContext(target_type="examination", stage="result_wait",
                             episode_id="exam_2"),
        ],
    )
    rdl = [c for c in cands if c.risk_id == "SEL_RESULT_DELAY_PRESSURE"]
    assert {c.selection_episode_id for c in rdl} == {"exam_1", "exam_2"}
    table = cause_occurrence_table(rdl)
    shared = set(rdl[0].trigger_cause_atoms) & set(rdl[1].trigger_cause_atoms)
    assert shared
    for atom in shared:
        assert ("2026", atom) in table  # (기간, 원인)당 정확히 1항목
    scored = score_shadow(rdl, engine.base_impacts())
    assert _comp(scored[0]).occurrence == (
        _comp(scored[1]).occurrence)  # 같은 원인 → 같은 평가(1회 계산 참조)


# ── 7. persistence·총점 — 반복 횟수만·포화 금지 ───────────────────


def _month_ev(p):
    """월 기간의 period-native(월운 발동) trigger 근거."""
    return [_evidence(_CHUNG, strength=0.5, period=p, layer="wolwoon")]


def test_persistence_contiguous_not_intermittent() -> None:
    """감수 26차 보완 5: 연속 3개월 ≠ 간헐 3회 — longest contiguous run 기준."""
    contiguous = [_candidate(period=p, evidence=_month_ev(p)) for p in
                  ("2026-01", "2026-02", "2026-03")]
    intermittent = [_candidate(risk_id="SYN_GAP", period=p, evidence=_month_ev(p))
                    for p in ("2026-01", "2026-06", "2026-11")]
    lone = _candidate(period="2026-07", evidence=_month_ev("2026-07"),
                      risk_id="SYN_LONE")
    scored = score_shadow(contiguous + intermittent + [lone], {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)  # 연속 3
    assert _comp(scored[3]).persistence == 0.0  # 간헐 3회 = run 1
    assert _comp(scored[6]).persistence == 0.0
    assert _comp(scored[0]).occurrence == (
        _comp(scored[6]).occurrence)  # 반복이 신호 강도를 재합산 금지


def test_persistence_year_boundary_contiguous() -> None:
    """연도 경계(2026-12→2027-02)도 canonical month index로 연속 3."""
    series = [_candidate(period=p, evidence=_month_ev(p)) for p in
              ("2026-12", "2027-01", "2027-02")]
    scored = score_shadow(series, {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)


def test_persistence_serialized_upper_layer_not_maximized() -> None:
    """감수 27차: 세운 원인이 월 후보 12개에 단순 복제(직렬화)된 계열은
    persistence를 자동 최대화하지 않는다 — 월운 native 발동 계열만 지속."""
    serialized = [
        _candidate(risk_id="SYN_SER", period=f"2026-{m:02d}",
                   evidence=[_evidence(_CHUNG, strength=0.5,
                                       period=f"2026-{m:02d}", layer="sewoon")])
        for m in range(1, 13)
    ]
    native = [_candidate(risk_id="SYN_NAT", period=f"2026-{m:02d}",
                         evidence=_month_ev(f"2026-{m:02d}"))
              for m in (1, 2, 3)]
    scored = score_shadow(serialized + native, {})
    assert _comp(scored[0]).persistence == 0.0  # 직렬화 12개월 → 지속 근거 아님
    assert _comp(scored[12]).persistence == pytest.approx(2 / 5)  # native 연속 3
    # 직렬화가 occurrence를 바꾸지도 않는다(같은 사실).
    assert _comp(scored[0]).occurrence == _comp(scored[12]).occurrence


def test_persistence_year_containing_month_not_double_counted() -> None:
    """연운과 월운이 같은 달을 지지 → 기간 2가 아니라 1(+layer convergence 소관)."""
    pair = [_candidate(period="2026", evidence=[
                _evidence(_CHUNG, strength=0.5, period="2026", layer="sewoon")]),
            _candidate(period="2026-03", evidence=_month_ev("2026-03"))]
    scored = score_shadow(pair, {})
    assert _comp(scored[0]).persistence == 0.0  # 월 라벨 존재 시 월 연속만(run 1)
    assert _comp(scored[1]).persistence == 0.0


def test_priority_raw_and_capped_no_saturation() -> None:
    """총점은 마지막 한 번 — raw 보존, capped만 [0,1] clamp."""
    heavy = _candidate(
        evidence=[_evidence(_CHUNG, strength=0.95),
                  _evidence(_HYEONG, strength=0.95)],
        exposure=ExposureStatus.CONFIRMED,
    )
    [h] = score_shadow([heavy], {"SYN_RISK": 1.0})
    comp = _comp(h).model_copy(
        update={"persistence": 1.0, "compound": 1.0})
    raw, capped = risk_priority(comp)
    assert raw > 1.0  # 원값 보존(포화 진단)
    assert capped == 1.0  # 소비값만 clamp
    assert RISK_SCORING_VERSION.startswith("risk-score-r1.")


# ── 8. cause identity 계약(감수 26차 보완 1) — 관계 원자=target 내장 canonical ──


def test_cause_identity_target_and_kind_and_layer() -> None:
    """①같은 원자+다른 대상=원인 2 ②같은 대상+다른 관계=원인 2 ③같은 대상·관계의
    다층=원인 1(+supporting layer). 관계 원자에 target_object_signature 내장."""
    other_target = "relation:CHUNG:day_pillar:branch:ZHENGGUAN"
    # ① 같은 관계 종류(충) + 다른 대상 → 서로 다른 원자 → cause row 2개.
    a = _candidate(risk_id="SYN_A", family="fam_a",
                   evidence=[_evidence(_CHUNG, strength=0.5)])
    b = _candidate(risk_id="SYN_B", family="fam_b",
                   evidence=[_evidence(other_target, strength=0.5)])
    assert len(cause_occurrence_table([a, b])) == 2
    # ② 같은 대상 + 다른 관계(충 vs 형) → cause row 2개.
    c = _candidate(risk_id="SYN_C", family="fam_c",
                   evidence=[_evidence(_HYEONG, strength=0.5)])
    assert len(cause_occurrence_table([a, c])) == 2
    # ③ 같은 대상·같은 관계의 다층 반복 → cause row 1개(layer는 서명 밖).
    multi = _candidate(risk_id="SYN_D", family="fam_d", evidence=[
        _evidence(_CHUNG, strength=0.5, layer="daewoon+sewoon")])
    assert len(cause_occurrence_table([a, multi])) == 1


# ── 9. exposure = rankable 가중(감수 26차 보완 2·3) — 게이트 미통과 0 ──


def test_exposure_weight_policy_gated() -> None:
    """DENIED·confirmed_required+UNKNOWN·conflict·vulnerability → exposure 0.
    required_for_warning+UNKNOWN → 0.55 잠정 / CONFIRMED → 1.0."""
    ev = [_evidence(_CHUNG, strength=0.5)]
    confirmed = _candidate(evidence=ev, exposure=ExposureStatus.CONFIRMED)
    warn_unknown = _candidate(
        evidence=ev, exposure=ExposureStatus.UNKNOWN,
        exposure_requirement="required_for_warning")
    hard_unknown = _candidate(
        evidence=ev, exposure=ExposureStatus.UNKNOWN,
        exposure_requirement="confirmed_required")
    conflicted = _candidate(evidence=ev, selection_context_conflict=True)
    vuln = RiskCandidate(
        risk_id="SYN_V", domain=RiskDomain.FINANCE,
        kind=RiskKind.VULNERABILITY, risk_family="fam_v", period_key="2026",
        evidence=ev, trigger_cause_atoms=[_CHUNG])
    scored = score_shadow(
        [confirmed, warn_unknown, hard_unknown, conflicted, vuln],
        {"SYN_RISK": 0.6, "SYN_V": 0.4})
    assert _comp(scored[0]).exposure == 1.0
    assert _comp(scored[1]).exposure == pytest.approx(0.55)
    assert _comp(scored[2]).exposure == 0.0  # 확인 전 ranking 대상 아님
    assert _comp(scored[3]).exposure == 0.0  # CONTEXT_CONFLICT
    assert _comp(scored[4]).exposure == 0.0  # vulnerability 단독 노출 없음
    # rankable=0이어도 구조 진단은 보존(DENIED counterfactual 경로).
    from saju_engines.risk_scoring import structural_priority
    assert structural_priority(_comp(scored[2])) > 0
    raw, capped = risk_priority(_comp(scored[2]))
    assert raw <= 0.0 or capped == 0.0 or _comp(scored[2]).exposure == 0.0


def test_denied_blocked_candidate_rankable_zero(engine: RiskEngine) -> None:
    """엔진 실후보: 전역 DENIED → BLOCKED(기존 판정 유지) + exposure 축 0 —
    구조 진단(structural_priority)은 별도로 살아 있다."""
    from saju_engines.risk_scoring import structural_priority
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGCAI)]),
        exposure_status=ExposureStatus.DENIED,
    )
    scored = score_shadow(cands, engine.base_impacts())
    denied = [c for c in scored
              if c.exposure_status is ExposureStatus.DENIED
              and c.score_components is not None]
    assert denied
    for c in denied:
        assert _comp(c).exposure == 0.0  # ranking 가중 0(0.15 제거)
        raw, capped = risk_priority(_comp(c))
        assert _comp(c).occurrence * _comp(c).impact * _comp(c).exposure == 0.0
        if _comp(c).occurrence > 0:
            assert structural_priority(_comp(c)) != raw or capped == 0.0


# ── 10. cause namespace 계약(감수 27차 — R1-b 슬라이스 1) ─────────


def test_cause_namespace_contract() -> None:
    """canonical 식별 ≠ occurrence 적격(감수 28차 registry): CAUSE 의미만 원인
    row 생성, 보조 상태(void/no_void/stage/polarity)는 진입 금지, 미상 거부."""
    ok = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5),  # relation:* — CAUSE
        _evidence("ten_god:ZHENGCAI", strength=0.4),  # ten_god:* — CAUSE
        _evidence("void", strength=0.4),  # CONDITIONAL — 단독=원인 아님
        _evidence("stage:병", strength=0.3),  # ACTIVATION — 원인 아님
    ])
    table = cause_occurrence_table([ok])
    assert len(table) == 2  # relation·ten_god만 — 상태 원자는 row 금지
    # 극성은 TRIGGER 조건에 섞여 있어도 원인이 아니다(진입 금지).
    with_pol = _candidate(evidence=[
        _evidence(f"{_CHUNG}&polarity:GI", strength=0.5)])
    assert list(cause_occurrence_table([with_pol])) == [("2026", _CHUNG)]
    # 미상 namespace → 계약 위반 감지(조용한 과소/과대 dedup 방지).
    bad = _candidate(evidence=[_evidence("pattern:some_new_thing", strength=0.5)])
    with pytest.raises(ValueError, match="canonical cause 계약 위반"):
        score_shadow([bad], {})


def test_state_atoms_zero_occurrence_contribution() -> None:
    """감수 28차 필수: no_void·stage·일반 void 추가 → occurrence·원인 수 불변."""
    base = _candidate(evidence=[_evidence(_CHUNG, strength=0.5)])
    with_states = _candidate(evidence=[
        _evidence(_CHUNG, strength=0.5),
        _evidence("no_void", strength=0.9),  # 비공망 상태 — GATE
        _evidence("stage:병", strength=0.9),  # 운성 상태 — ACTIVATION
        _evidence("void", strength=0.9),  # 일반 공망 단독 — 원인 아님
    ])
    [b, w] = score_shadow([base, with_states], {})
    assert _comp(b).occurrence == _comp(w).occurrence
    assert b.confidence == w.confidence  # 독립 원인 수 불변(휴리스틱 동일)
    # 형 + 병 운성: 운성이 두 번째 원인이 되지 않는다 — cause row 1.
    hyeong_stage = _candidate(evidence=[
        _evidence(_HYEONG, strength=0.5), _evidence("stage:병", strength=0.5)])
    assert len(cause_occurrence_table([hyeong_stage])) == 1
    # 감수 룰의 조건부 공망(같은 source에 CAUSE 동반)은 그 원인의 조건일 뿐
    # 별도 원인이 아니다 — row는 CAUSE 원자만.
    conditional = _candidate(evidence=[
        _evidence("ten_god:ZHENGYIN&void", strength=0.5)])
    assert list(cause_occurrence_table([conditional])) == [
        ("2026", "ten_god:ZHENGYIN")]


def test_ten_god_semantic_collapse() -> None:
    """감수 28차: 같은 십성의 source·layer 반복 = semantic cause 1개."""
    single = _candidate(evidence=[_evidence("ten_god:ZHENGCAI", strength=0.5)])
    repeated = _candidate(evidence=[
        _evidence("ten_god:ZHENGCAI", strength=0.5, group="event_shape"),
        _evidence("ten_god:ZHENGCAI", strength=0.5, group="activation"),
    ])
    multi_layer = _candidate(evidence=[
        _evidence("ten_god:ZHENGCAI", strength=0.5, layer="daewoon+sewoon")])
    [s, r, m] = score_shadow([single, repeated, multi_layer], {})
    assert _comp(s).occurrence == _comp(r).occurrence  # source 수 재가산 금지
    assert len(cause_occurrence_table([repeated])) == 1
    assert _comp(m).occurrence == _comp(s).occurrence  # layer는 confidence만
    assert m.confidence > s.confidence


def test_engine_atoms_all_canonical(engine: RiskEngine) -> None:
    """엔진 실후보의 전 TRIGGER 원자가 계약을 충족한다(전 도메인 관측 조합)."""
    facts = _facts(
        gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON},
              TenGod.ZHENGGUAN: {LuckLayer.SEWOON},
              TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.QISHA: {LuckLayer.SEWOON},
              TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                         target_ten_god=TenGod.ZHENGCAI),
            RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                         target_ten_god=TenGod.ZHENGGUAN),
            RelationFact(RelationKind.HAE, Pillar4.YEAR,
                         target_ten_god=TenGod.ZHENGYIN),
        ],
        void=True,
    )
    cands = engine.generate(facts)
    table = cause_occurrence_table(cands)  # 미상 namespace면 여기서 raise
    assert table


# ── 11. structural 진단의 exposability 불변(감수 27차 — 슬라이스 1) ──


def test_structural_metrics_invariant_under_exposure_flip() -> None:
    """동일 구조에서 CONFIRMED→DENIED 전환: structural(occ·impact·persistence·
    구조 compound·protection) 완전 동일, rankable(exposure·compound·total)만 변화."""
    from saju_engines.risk_scoring import compound_family_links, structural_priority

    def pair(exposure):
        base = _candidate(risk_id="SYN_A", family="fam_a", exposure=exposure,
                          legal_episode_id="c1",
                          evidence=[_evidence(_CHUNG, strength=0.5)])
        other = _candidate(risk_id="SYN_B", family="fam_b", exposure=exposure,
                           legal_episode_id="c1",
                           evidence=[_evidence(_CHUNG, strength=0.4)])
        return [base, other]

    confirmed = pair(ExposureStatus.CONFIRMED)
    denied = pair(ExposureStatus.DENIED)
    sc, sd = (score_shadow(p, {"SYN_A": 0.6, "SYN_B": 0.5})
              for p in (confirmed, denied))
    # 구조 축 동일.
    for a, b in zip(sc, sd, strict=True):
        assert _comp(a).occurrence == _comp(b).occurrence
        assert _comp(a).impact == _comp(b).impact
        assert _comp(a).persistence == _comp(b).persistence
        assert _comp(a).protection == _comp(b).protection
        assert structural_priority(_comp(a)) == structural_priority(_comp(b))
    # 구조 연결(exposure 무관) 동일 — exposability 누수 차단.
    assert compound_family_links(confirmed, exposable_only=False) == (
        compound_family_links(denied, exposable_only=False))
    # rankable만 변화: DENIED는 exposure·compound 0.
    assert _comp(sc[0]).exposure == 1.0 and _comp(sd[0]).exposure == 0.0
    assert _comp(sc[0]).compound > 0 and _comp(sd[0]).compound == 0.0
    raw_c, _ = risk_priority(_comp(sc[0]))
    raw_d, capped_d = risk_priority(_comp(sd[0]))
    assert raw_c > raw_d and capped_d == 0.0


def test_targeted_void_fail_closed_until_defined() -> None:
    """감수 29차 §1: 현재 매처의 void는 시점 전역 상태(궁위 무관) — 궁위 지정
    void 원자는 미정의 namespace라 fail-closed 거부된다(도입 시 동반 CAUSE와의
    target 일치 검증을 registry에 정의해야 함)."""
    bad = _candidate(evidence=[
        _evidence("void:month_pillar&ten_god:ZHENGCAI", strength=0.5)])
    with pytest.raises(ValueError, match="canonical cause 계약 위반"):
        score_shadow([bad], {})


# ── 12. persistence = cause lineage(감수 28차) — 원인 교체·무관 episode ──


def test_persistence_cause_lineage_not_effect_run() -> None:
    """같은 risk_id·episode의 연속이라도 매달 원인이 바뀌면 cause run 1 —
    effect run(진단)은 3으로 별도 관찰된다."""
    from saju_engines.risk_scoring import effect_contiguous_runs
    same_cause = [
        _candidate(risk_id="SYN_SAME", period=p, evidence=_month_ev(p))
        for p in ("2026-01", "2026-02", "2026-03")
    ]
    rotating_sources = [_CHUNG, _HYEONG, "ten_god:ZHENGCAI"]
    rotating = [
        _candidate(risk_id="SYN_ROT", period=p, evidence=[
            _evidence(src, strength=0.5, period=p, layer="wolwoon")])
        for p, src in zip(("2026-01", "2026-02", "2026-03"),
                          rotating_sources, strict=True)
    ]
    scored = score_shadow(same_cause + rotating, {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)  # cause run 3
    assert _comp(scored[3]).persistence == 0.0  # 원인 교체 — cause run 1
    runs = effect_contiguous_runs(same_cause + rotating)
    assert runs[("SYN_SAME", frozenset())] == 3
    assert runs[("SYN_ROT", frozenset())] == 3  # 효과 연속은 진단으로 보존


def test_persistence_per_cause_lineage_not_bundle() -> None:
    """감수 29차 §3: {A}→{A,B}→{A} — A 원인 run 3(0.4)·bundle run 1(진단).

    보조 원인의 추가·제거가 지속성을 끊지 않는다. 원인 전체 교체({A}→{B}→{C})만
    run 1(기존 fixture). {A,B}×3은 양쪽 run 3=bundle run 3.
    """
    from saju_engines.risk_scoring import trigger_bundle_contiguous_runs
    ab_mid = [
        _candidate(period="2026-01", evidence=_month_ev("2026-01")),
        _candidate(period="2026-02", evidence=[
            _evidence(_CHUNG, strength=0.5, period="2026-02", layer="wolwoon"),
            _evidence("ten_god:ZHENGCAI", strength=0.4, period="2026-02",
                      layer="wolwoon")]),
        _candidate(period="2026-03", evidence=_month_ev("2026-03")),
    ]
    scored = score_shadow(ab_mid, {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)  # A run 3
    bundles = trigger_bundle_contiguous_runs(ab_mid)
    assert max(bundles.values()) == 1  # 묶음 자체는 매달 다름 — 진단으로만
    both = [
        _candidate(period=p, evidence=[
            _evidence(_CHUNG, strength=0.5, period=p, layer="wolwoon"),
            _evidence("ten_god:ZHENGCAI", strength=0.4, period=p,
                      layer="wolwoon")])
        for p in ("2026-01", "2026-02", "2026-03")
    ]
    scored2 = score_shadow(both, {})
    assert _comp(scored2[0]).persistence == pytest.approx(2 / 5)
    assert max(trigger_bundle_contiguous_runs(both).values()) == 3


def test_persistence_gap_splits_run() -> None:
    """같은 cause라도 중간 한 달 비활성이면 run 분리(최장 구간만)."""
    series = [_candidate(period=p, evidence=_month_ev(p))
              for p in ("2026-01", "2026-02", "2026-04", "2026-05", "2026-06")]
    scored = score_shadow(series, {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)  # 최장 run 3(4~6월)


def test_unrelated_episode_does_not_change_lineage(engine: RiskEngine) -> None:
    """감수 28차 필수: 무관 health episode 추가 → 계약 후보 lineage·전 점수 불변."""
    from saju_engines.risk_engine import HealthContext, LegalProcessContext
    facts = _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
    )
    leg_ctx = LegalProcessContext(
        target_type="contract", stage="active_contract",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="contract_1")
    base = engine.generate(facts, legal_contexts=[leg_ctx])
    with_health = engine.generate(
        facts, legal_contexts=[leg_ctx],
        health_contexts=[HealthContext(
            context_type="treatment_process", treatment_status="ongoing",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="treatment_9")],
    )
    pick = lambda cands: {  # noqa: E731
        (c.risk_id, c.legal_episode_id): c for c in cands
        if c.risk_id == "LEG_CONTRACT_TERMINATION_RISK"}
    b = pick(base)[("LEG_CONTRACT_TERMINATION_RISK", "contract_1")]
    w = pick(with_health)[("LEG_CONTRACT_TERMINATION_RISK", "contract_1")]
    [sb] = score_shadow([b], engine.base_impacts())
    [sw] = score_shadow([w], engine.base_impacts())
    assert sb.model_dump() == sw.model_dump()  # lineage 포함 전 점수·필드 불변


# ── 13. compound normalized effect identity(감수 28차) ────────────


def test_compound_normalized_effect_role_semantics() -> None:
    """감수 29차 §8: compound = 서로 다른 normalized effect role의 개수.

    ①같은 episode+같은 role(교차 도메인 문서 결함 복제)=0 ②같은 episode+다른
    role=가능 ③다른 episode+같은 role=0(episode 수는 compound 아님 — breadth
    소관) ④episode-free 미해결=0+unresolved 진단(fail-closed).
    """
    from saju_engines.risk_scoring import (
        compound_unresolved_counts,
        normalized_effect_role,
    )
    ev = [_evidence(_CHUNG, strength=0.5)]
    # ① 같은 episode + 같은 role(document_defect — LEG·SEL 교차 복제) → 0.
    leg_doc = _candidate(risk_id="LEG_DOCUMENT_ERROR", family="contract",
                         evidence=ev, legal_episode_id="contract_1",
                         normalized_effect_role="document_defect")
    sel_doc = _candidate(risk_id="SEL_DOCUMENT_DEFECT_RISK",
                         family="selection_process", evidence=ev,
                         legal_episode_id="contract_1",
                         normalized_effect_role="document_defect")
    assert normalized_effect_role(leg_doc) == normalized_effect_role(sel_doc)
    [sl, ss] = score_shadow([leg_doc, sel_doc], {})
    assert _comp(sl).compound == 0.0 and _comp(ss).compound == 0.0
    # ② 같은 episode + 다른 role(종료 vs 행정 지연 — 둘 다 pressure여도 다른
    # 현실 효과) → compound 가능.
    trm = _candidate(risk_id="LEG_CONTRACT_TERMINATION_RISK", family="contract",
                     kind=RiskKind.PRESSURE, evidence=ev,
                     legal_episode_id="contract_1",
                     normalized_effect_role="contract_termination")
    adm = _candidate(risk_id="LEG_ADMIN_DELAY", family="procedure",
                     kind=RiskKind.PRESSURE, evidence=ev,
                     legal_episode_id="contract_1",
                     normalized_effect_role="administrative_delay")
    [st, _] = score_shadow([trm, adm], {})
    assert _comp(st).compound == pytest.approx(0.10)  # 잠정 증분(감수 32차)
    # ③ 다른 episode + 같은 role → episode 수만으로 compound 증가 금지.
    doc2 = _candidate(risk_id="SEL_DOCUMENT_DEFECT_RISK",
                      family="selection_process", evidence=ev,
                      legal_episode_id="permit_9",
                      normalized_effect_role="document_defect")
    [sl3, _] = score_shadow([leg_doc, doc2], {})
    assert _comp(sl3).compound == 0.0
    # ④ episode-free — 독립 효과 증명 불가 → compound 0 + unresolved 진단.
    free_a = _candidate(risk_id="SYN_FA", family="fam_a",
                        kind=RiskKind.PRESSURE, evidence=ev)
    free_b = _candidate(risk_id="SYN_FB", family="fam_b",
                        kind=RiskKind.PRESSURE, evidence=ev)
    [sf, _] = score_shadow([free_a, free_b], {})
    assert _comp(sf).compound == 0.0
    assert compound_unresolved_counts([free_a, free_b]) == [1, 1]


# ── 14. confidence 분리(감수 28차) — structural vs context ─────────


def test_confidence_axes_separated() -> None:
    """context CONFIRMED가 structural confidence를 못 올리고, UNKNOWN이
    occurrence를 못 내린다 — context confidence만 별도 축으로 변화."""
    from saju_engines.risk_scoring import context_confidence
    ev = [_evidence(_CHUNG, strength=0.5)]
    unknown = _candidate(evidence=ev, exposure=ExposureStatus.UNKNOWN)
    confirmed = _candidate(evidence=ev, exposure=ExposureStatus.CONFIRMED)
    conflicted = _candidate(evidence=ev, selection_context_conflict=True)
    [su, sc, sx] = score_shadow([unknown, confirmed, conflicted], {})
    assert su.confidence == sc.confidence  # structural — context 무관
    assert _comp(su).occurrence == _comp(sc).occurrence  # UNKNOWN이 occ 불변
    assert context_confidence(sc) == 1.0
    assert context_confidence(su) == 0.5
    assert context_confidence(sx) == 0.0  # conflict — 완전성 훼손


# ── 15. R1-c1 착수 조건(감수 30차) — 연결 그래프·질문 대상 제외 ────


def test_compound_requires_explicit_link_not_co_period() -> None:
    """같은 기간 + 다른 role + 아무 연결(원인 공유) 없음 → compound 0.

    compound는 전역 동시 후보 스캔이 아니라 연결된 effect graph(shared canonical
    cause)에서만 계산된다 — 우연한 동시 발생은 복합 위험이 아니다.
    """
    a = _candidate(risk_id="SYN_A", family="fam_a", legal_episode_id="e1",
                   evidence=[_evidence(_CHUNG, strength=0.5)])
    unlinked = _candidate(
        risk_id="SYN_B", family="fam_b", legal_episode_id="e2",
        evidence=[_evidence("relation:PA:day_pillar:branch:BIJIAN",
                            strength=0.5)])
    [sa, sb] = score_shadow([a, unlinked], {})
    assert _comp(sa).compound == 0.0 and _comp(sb).compound == 0.0
    linked = _candidate(risk_id="SYN_C", family="fam_c", legal_episode_id="e2",
                        evidence=[_evidence(_CHUNG, strength=0.4)])
    [sa2, _] = score_shadow([a, linked], {})
    assert _comp(sa2).compound == pytest.approx(0.10)  # 원인 공유 연결만(잠정 증분)


def test_question_target_excluded_from_context_confidence() -> None:
    """is_question_target은 답변 관련성이지 현실 상태의 정확성이 아니다 —
    context confidence 증감 금지(relevance 축은 R2/R3 소관)."""
    from saju_engines.risk_engine import RiskEngine as _RE  # noqa: F401
    from saju_engines.risk_engine import SelectionContext
    from saju_engines.risk_scoring import context_confidence
    engine = RiskEngine(_DICTS)
    facts = _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )
    def rdl(question: bool):
        cands = engine.generate(facts, selection_contexts=[SelectionContext(
            target_type="examination", stage="result_wait",
            exposure_status=ExposureStatus.CONFIRMED, episode_id="exam_1",
            is_question_target=question)])
        return next(c for c in cands if c.risk_id == "SEL_RESULT_DELAY_PRESSURE")
    assert context_confidence(rdl(True)) == context_confidence(rdl(False))


# ── 16. ByContext role 해소(감수 32차) — 치료 ≠ 회복 ──────────────


def test_by_context_role_resolution(engine: RiskEngine) -> None:
    """TRL: 치료 과정 컨텍스트=treatment_management, 회복 과정=recovery_adjustment
    — 같은 항목이라도 현실 효과가 다르면 role이 갈린다(compound 재료)."""
    from saju_engines.risk_engine import HealthContext
    from saju_engines.risk_scoring import normalized_effect_role
    facts = _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )
    def trl(ctx):
        cands = engine.generate(facts, health_contexts=[ctx])
        return next(c for c in cands
                    if c.risk_id == "HLT_TREATMENT_RECOVERY_LOAD")
    treat = trl(HealthContext(
        context_type="treatment_process", treatment_status="ongoing",
        exposure_status=ExposureStatus.CONFIRMED, episode_id="t1"))
    recover = trl(HealthContext(
        context_type="recovery_process", recovery_status="in_progress",
        exposure_status=ExposureStatus.CONFIRMED, episode_id="r1"))
    assert normalized_effect_role(treat) == "treatment_management"
    assert normalized_effect_role(recover) == "recovery_adjustment"
    # 컨텍스트 부재(unknown) → base role로 항상 해소(lint가 base 필수 강제).
    base = next(c for c in engine.generate(facts)
                if c.risk_id == "HLT_TREATMENT_RECOVERY_LOAD")
    assert normalized_effect_role(base) == "treatment_management"


def test_persistence_cannot_outrank_strong_base() -> None:
    """감수 32차 공식: 약한 원인의 장기 지속이 강한 단기 구조를 못 넘는다
    (persistence 기여 상한 = base×1 — modifier 구조)."""
    weak_persistent = _candidate(
        risk_id="SYN_WEAK", family="fam_w", exposure=ExposureStatus.CONFIRMED,
        period="2026-01",
        evidence=[_evidence(_CHUNG, strength=0.2, period="2026-01",
                            layer="wolwoon")])
    series = [weak_persistent] + [
        _candidate(risk_id="SYN_WEAK", family="fam_w",
                   exposure=ExposureStatus.CONFIRMED, period=p,
                   evidence=[_evidence(_CHUNG, strength=0.2, period=p,
                                       layer="wolwoon")])
        for p in ("2026-02", "2026-03", "2026-04", "2026-05", "2026-06")
    ]
    strong_short = _candidate(
        risk_id="SYN_STRONG", family="fam_s", exposure=ExposureStatus.CONFIRMED,
        period="2026-07",
        evidence=[_evidence(_CHUNG, strength=0.8, period="2026-07",
                            layer="wolwoon"),
                  _evidence(_HYEONG, strength=0.7, period="2026-07",
                            layer="wolwoon")])
    scored = score_shadow(series + [strong_short],
                          {"SYN_WEAK": 0.6, "SYN_STRONG": 0.6})
    weak_raw, _ = risk_priority(_comp(scored[0]))
    strong_raw, _ = risk_priority(_comp(scored[6]))
    assert _comp(scored[0]).persistence == 1.0  # 6개월 연속 — 지속 최대
    assert strong_raw > weak_raw  # 지속만으로 강한 단기 구조를 못 넘는다
    # 비노출 후보는 지속·복합으로 부활 불가(전 양의 항에 exposure 게이트).
    unexposed = scored[0].model_copy(update={
        "exposure_status": ExposureStatus.UNKNOWN,
        "exposure_requirement": "confirmed_required"})
    comp = _comp(unexposed).model_copy(update={"exposure": 0.0})
    assert risk_priority(comp) == (0.0, 0.0)
