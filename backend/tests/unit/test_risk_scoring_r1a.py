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
               **overrides) -> RiskCandidate:
    atoms = sorted({
        a for e in evidence if e.role is EvidenceRole.TRIGGER
        for a in e.source.split("&")
    })
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.FINANCE, kind=RiskKind.INCIDENT_RISK,
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
    # compound 축이 독립 효과군 연결을 표현한다(occurrence 중복 가산 아님).
    [sa, sb] = score_shadow([a, b], {})
    assert _comp(sa).compound > 0 and _comp(sb).compound > 0
    lone = _candidate(risk_id="SYN_C", evidence=[
        _evidence("relation:PA:day_pillar:branch:BIJIAN", strength=0.5)])
    [sc] = score_shadow([lone], {})
    assert _comp(sc).compound == 0.0  # 연결 없으면 0


def test_compound_requires_independent_exposable_effect() -> None:
    """감수 26차 보완 4: 같은 family alias·흡수 후보·비노출 연결은 compound 0."""
    base = _candidate(risk_id="SYN_A", family="fam_a",
                      evidence=[_evidence(_CHUNG, strength=0.5)])
    # 같은 family의 다른 risk_id(동일 효과 계열의 파생 표현) → 연결 아님.
    alias = _candidate(risk_id="SYN_A2", family="fam_a",
                       evidence=[_evidence(_CHUNG, strength=0.4)])
    [sa, _] = score_shadow([base, alias], {})
    assert _comp(sa).compound == 0.0
    # 흡수된 supporting 후보 → 연결 아님.
    absorbed = _candidate(
        risk_id="SYN_B", family="fam_b",
        evidence=[_evidence(_CHUNG, strength=0.4)],
        suppressed_by_specificity="SYN_A", primary_risk_id="SYN_A",
        absorbed_role="supporting_manifestation")
    [sa2, _] = score_shadow([base, absorbed], {})
    assert _comp(sa2).compound == 0.0
    # 비노출 vulnerability 연결 → 연결 아님.
    vuln = RiskCandidate(
        risk_id="SYN_V", domain=RiskDomain.FINANCE,
        kind=RiskKind.VULNERABILITY, risk_family="fam_v", period_key="2026",
        evidence=[_evidence(_CHUNG, strength=0.4)],
        trigger_cause_atoms=[_CHUNG])
    [sa3, _] = score_shadow([base, vuln], {})
    assert _comp(sa3).compound == 0.0
    # 독립 exposable 다른 family → 연결 1건.
    other = _candidate(risk_id="SYN_C", family="fam_c",
                       evidence=[_evidence(_CHUNG, strength=0.4)])
    [sa4, _] = score_shadow([base, other], {})
    assert _comp(sa4).compound == pytest.approx(0.25)


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


def test_persistence_contiguous_not_intermittent() -> None:
    """감수 26차 보완 5: 연속 3개월 ≠ 간헐 3회 — longest contiguous run 기준."""
    ev = lambda p: [_evidence(_CHUNG, strength=0.5, period=p)]  # noqa: E731
    contiguous = [_candidate(period=p, evidence=ev(p)) for p in
                  ("2026-01", "2026-02", "2026-03")]
    intermittent = [_candidate(risk_id="SYN_GAP", period=p, evidence=ev(p))
                    for p in ("2026-01", "2026-06", "2026-11")]
    lone = _candidate(period="2026-07", evidence=ev("2026-07"),
                      risk_id="SYN_LONE")
    scored = score_shadow(contiguous + intermittent + [lone], {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)  # 연속 3
    assert _comp(scored[3]).persistence == 0.0  # 간헐 3회 = run 1
    assert _comp(scored[6]).persistence == 0.0
    assert _comp(scored[0]).occurrence == (
        _comp(scored[6]).occurrence)  # 반복이 신호 강도를 재합산 금지


def test_persistence_year_containing_month_not_double_counted() -> None:
    """연운과 월운이 같은 달을 지지 → 기간 2가 아니라 1(+layer convergence 소관)."""
    ev = lambda p: [_evidence(_CHUNG, strength=0.5, period=p)]  # noqa: E731
    pair = [_candidate(period="2026", evidence=ev("2026")),
            _candidate(period="2026-03", evidence=ev("2026-03"))]
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
