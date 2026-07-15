"""위험 사전 LEG 재검토 차수(C8 — 감수 23차) 의미론 fixture.

데굴님 차수 불변식: 문서·지연·계약·분쟁 신호가 있다는 이유만으로 모든 절차가 법적
위험으로 복제되지 않게 하고, 실제로 진행 중인 계약·행정·분쟁 episode에 해당하는
LEG 후보만 남긴다.

고정 범위(§13): ①process 없는 일반 인성 약화=RCW 독립 노출 없음 ②선발 서류=SEL·채용
대기=CAR primary(LEG 비노출) ③허가·등록 진행=ADMIN_DELAY 가능 ④같은 process episode
수렴(대표+supporting/background) ⑤다른 episode 병존 ⑥소송 절차 exposure-aware 대표
(test_risk_leg_c2 개정판) ⑦vulnerability 단독 노출 없음 명문화.

감수 23차 커밋 조건(데굴님 검토) 추가 고정: ⑧구 PENALTY(감수 24차 C8-f에서
LEG_COMPLIANCE_OBLIGATION_PRESSURE·pressure로 정합화)=formal process 없이 비노출
⑨termination=active_contract 필수(negotiating 대체 불가) ⑩closed stage 신규
후보 생성 제한 ⑪RCW 역할 보장(대표·독립 노출 불가) ⑫episode 중복 컨텍스트 결정적
병합 ⑬stage 상호 배타 수렴 금지 ⑭타 도메인 소유권(SEL·CAR·MOV·REL·FIN)
⑮vulnerability 역전 방지 전 도메인 일반화(synthetic).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.risk_engine import (
    LegalProcessContext,
    RelationFact,
    RiskEngine,
    SelectionContext,
    build_raw_period_facts,
)
from saju_shared_types.event_engine import (
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
)
from saju_shared_types.risk_engine import (
    ExposureStatus,
    RiskDomain,
    is_active,
    is_exposable,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    """위험 엔진(모듈 1회 로드)."""
    return RiskEngine(_DICTS)


def _facts(*, gods=None, relations=None, void=False, role=PolarityRole.GI):
    return build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=void, polarity_role=role, twelve_stage=None,
    )


_ADMIN_CONFIRMED = LegalProcessContext(
    target_type="administrative_application", stage="review",
    exposure_status=ExposureStatus.CONFIRMED, process_episode_id="process_a",
)


def _doc_admin_facts():
    """문서·계획 공망 shape + 문서 채널 해 피격 + 관성 공망 activation(행정 지연)."""
    return _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )


# ── ① process 없는 일반 신호 → 독립 노출 없음 ────────────────────


def test_no_process_generic_resource_weak_not_exposable(engine: RiskEngine) -> None:
    """행정 절차 없음 + 일반 인성 약화 → REVIEW_CAPACITY_WEAK 독립 노출 없음.

    vulnerability 단독 노출 없음 원칙(감수 23차 is_exposable 명문화)과 legal 축
    미확인 이중으로 차단 — 구조 후보는 보존된다.
    """
    cands = engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}}, void=True,
    ))
    rcw = next(c for c in cands if c.risk_id == "LEG_REVIEW_CAPACITY_WEAK")
    assert is_active(rcw)  # 구조 보존
    assert rcw.legal_alignment == "unknown"
    assert not is_exposable(rcw)


# ── ② 소유권 — 선발 서류·채용 대기에서 LEG 비노출 ────────────────


def test_selection_document_owned_by_sel(engine: RiskEngine) -> None:
    """선발 서류 단계 → SEL_DOCUMENT_DEFECT가 노출 가능, LEG_DOCUMENT는 비노출."""
    facts = _facts(
        gods={TenGod.PIANYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )
    cands = engine.generate(
        facts, exposure_status=ExposureStatus.CONFIRMED,
        selection_context=SelectionContext(
            target_type="examination", stage="application_document"),
    )
    by_id = {c.risk_id: c for c in cands}
    sel = by_id["SEL_DOCUMENT_DEFECT_RISK"]
    assert is_active(sel) and is_exposable(sel)
    leg = by_id["LEG_DOCUMENT_ERROR"]
    assert leg.legal_alignment == "unknown"  # 법적 절차 확인 없음
    assert not is_exposable(leg)


def test_hiring_wait_does_not_expose_admin_delay(engine: RiskEngine) -> None:
    """채용 결과 대기(법적 절차 아님) → LEG_ADMIN_DELAY 비노출(CAR 소관)."""
    facts = _facts(gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}}, void=True)
    cands = engine.generate(
        facts, exposure_status=ExposureStatus.CONFIRMED,
        selection_context=SelectionContext(
            target_type="employment_hiring", stage="result_wait"),
    )
    adm = next(c for c in cands if c.risk_id == "LEG_ADMIN_DELAY")
    assert adm.legal_alignment == "unknown"
    assert not is_exposable(adm)


# ── ③ 공식 행정 절차 진행 → ADMIN_DELAY 가능 ─────────────────────


def test_admin_process_confirmed_exposable(engine: RiskEngine) -> None:
    """허가·등록 절차 진행 확인 → LEG_ADMIN_DELAY 활성·노출 가능."""
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}}, void=True),
        legal_contexts=[_ADMIN_CONFIRMED],
    )
    adm = next(c for c in cands if c.risk_id == "LEG_ADMIN_DELAY")
    assert is_active(adm) and is_exposable(adm)
    assert adm.legal_episode_id == "process_a"


# ── ④ 같은 process episode 수렴 / ⑤ 다른 episode 병존 ────────────


def test_same_process_episode_converges(engine: RiskEngine) -> None:
    """같은 process episode: 문서 결함 대표 아래 지연=supporting, 검토 취약=background.

    문서·지연·검토 취약이 모두 별도 경고로 노출되지 않는다(대표 1건 수렴).
    """
    cands = engine.generate(_doc_admin_facts(), legal_contexts=[_ADMIN_CONFIRMED])
    by_id = {c.risk_id: c for c in cands}
    doc = by_id["LEG_DOCUMENT_ERROR"]
    assert is_active(doc) and is_exposable(doc)
    adm = by_id["LEG_ADMIN_DELAY"]
    assert adm.suppressed_by_specificity == "LEG_DOCUMENT_ERROR"
    assert adm.absorbed_role == "supporting_manifestation"
    rcw = by_id["LEG_REVIEW_CAPACITY_WEAK"]
    assert rcw.suppressed_by_specificity == "LEG_DOCUMENT_ERROR"
    assert rcw.absorbed_role == "background_vulnerability"
    active_leg_families = {
        c.risk_family for c in cands
        if c.domain is RiskDomain.CONTRACT_LEGAL and is_active(c)
    }
    assert len(active_leg_families) == 1


def test_different_process_episodes_coexist(engine: RiskEngine) -> None:
    """서로 다른 process episode(계약 vs 행정)는 원인을 공유해도 병존한다."""
    contract_ctx = LegalProcessContext(
        target_type="contract", stage="review",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="contract_1")
    cands = engine.generate(
        _doc_admin_facts(),
        legal_contexts=[contract_ctx, _ADMIN_CONFIRMED],
    )
    docs = {c.legal_episode_id: c for c in cands
            if c.risk_id == "LEG_DOCUMENT_ERROR"}
    assert set(docs) == {"contract_1", "process_a"}
    adm = next(c for c in cands if c.risk_id == "LEG_ADMIN_DELAY"
               and c.legal_episode_id == "process_a")
    # 행정 episode 안에서는 문서 대표에 수렴하되, 계약 episode 후보를 넘보지 않는다.
    assert adm.suppressed_by_specificity in (None, "LEG_DOCUMENT_ERROR")
    if adm.suppressed_by_specificity:
        rep = next(c for c in cands if c.risk_id == "LEG_DOCUMENT_ERROR"
                   and c.legal_episode_id == "process_a")
        assert rep.suppressed_by_specificity is None


# ── ⑥ 계약 종료 위험 — 진행 중 계약(active_contract) 필요 ────────


def _termination_facts():
    return _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
    )


def test_contract_termination_requires_active_contract(engine: RiskEngine) -> None:
    """계약 종료 위험은 성립·이행 중 계약(stage=active_contract)에서만 노출된다.

    감수 23차 커밋 조건: 협상 중 계약 미성립(negotiating)은 계약 종료 위험이 아니라
    도메인별 setback 소관 — negotiating 컨텍스트만으로 '계약 종료 위험'을 생성하면
    안 된다(stage 축이 있으므로 unknown 강등·비노출, 구조 보존).
    """
    facts = _termination_facts()
    trm = next(c for c in engine.generate(facts)
               if c.risk_id == "LEG_CONTRACT_TERMINATION_RISK")
    assert is_active(trm) and not is_exposable(trm)

    # 협상 중(성립 전) — 종료 위험 비노출.
    nego = LegalProcessContext(target_type="contract", stage="negotiating",
                               exposure_status=ExposureStatus.CONFIRMED)
    trm2 = next(c for c in engine.generate(facts, legal_contexts=[nego])
                if c.risk_id == "LEG_CONTRACT_TERMINATION_RISK")
    assert trm2.legal_alignment == "unknown"
    assert not is_exposable(trm2)

    # 성립·이행 중 계약 — 노출 가능.
    active = LegalProcessContext(target_type="contract", stage="active_contract",
                                 exposure_status=ExposureStatus.CONFIRMED,
                                 process_episode_id="contract_1")
    trm3 = next(c for c in engine.generate(facts, legal_contexts=[active])
                if c.risk_id == "LEG_CONTRACT_TERMINATION_RISK")
    assert is_active(trm3) and is_exposable(trm3)
    assert trm3.legal_episode_id == "contract_1"


# ── ⑧ 준법·의무 부담(구 PENALTY) — formal process 없이 비노출 ────


def _penalty_facts():
    """형+편관(targeted — 관성 피격 강제 조정 구조)."""
    return _facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.QISHA)],
    )


def test_penalty_requires_formal_process(engine: RiskEngine) -> None:
    """COMPLIANCE_OBLIGATION_PRESSURE(감수 24차 C8-f 개명·pressure 정합화) —
    제재·의무 절차 확인 없이 비노출.

    kind=pressure: 허용 표현·노출 조건이 전부 준법·의무 이행 점검 수준이라
    incident가 아니다(R1 impact prior·risk budget 왜곡 방지 — 데굴님 확정).
    unknownExposable=false: '위반이 있다면' 류 조건부 표현 우회도 금지(구조 보존).
    """
    from saju_shared_types.risk_engine import RiskKind
    pen = next(c for c in engine.generate(_penalty_facts())
               if c.risk_id == "LEG_COMPLIANCE_OBLIGATION_PRESSURE")
    assert pen.kind is RiskKind.PRESSURE  # 감수 24차 kind 정합화
    assert is_active(pen)  # 구조 보존
    assert pen.legal_alignment == "unknown"
    assert not pen.exposable_when_unknown
    assert not is_exposable(pen)


def test_penalty_exposable_with_obligation_process(engine: RiskEngine) -> None:
    """제재 가능성 있는 의무 절차(rights_obligation·response_required) 확인 → 노출 가능."""
    ctx = LegalProcessContext(
        target_type="rights_obligation", stage="response_required",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="obligation_1")
    pen = next(c for c in engine.generate(_penalty_facts(), legal_contexts=[ctx])
               if c.risk_id == "LEG_COMPLIANCE_OBLIGATION_PRESSURE")
    assert is_active(pen) and is_exposable(pen)
    assert pen.legal_episode_id == "obligation_1"


def test_penalty_not_exposable_pre_contract(engine: RiskEngine) -> None:
    """성립 전 협의(negotiating)는 제재·의무 위반 절차가 아니다 — PENALTY 비노출."""
    ctx = LegalProcessContext(
        target_type="contract", stage="negotiating",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="draft_1")
    pen = next(c for c in engine.generate(_penalty_facts(), legal_contexts=[ctx])
               if c.risk_id == "LEG_COMPLIANCE_OBLIGATION_PRESSURE")
    assert pen.legal_alignment == "unknown"
    assert not is_exposable(pen)


# ── ⑪ RCW 역할 보장 — 대표 불가·독립 노출 불가(컨텍스트 확인 시에도) ──


def test_rcw_never_representative_nor_exposable(engine: RiskEngine) -> None:
    """RCW는 절차가 확인(matched·CONFIRMED)돼도 독립 노출·대표가 될 수 없다.

    감수 23차 커밋 조건 4: RCW 독립 사용자 노출=0 · RCW가 대표를 흡수한 수=0.
    같은 episode의 원인(void)을 공유하는 더 일반적인 압박(ADMIN rank 0)이 있어도
    RCW(rank 1)가 이를 흡수하지 않는다.
    """
    ctx = LegalProcessContext(
        target_type="administrative_application", stage="review",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="permit_1")
    cands = engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        void=True,
    ), legal_contexts=[ctx])
    by_id = {c.risk_id: c for c in cands}
    rcw = by_id["LEG_REVIEW_CAPACITY_WEAK"]
    assert rcw.legal_alignment == "matched"
    assert not is_exposable(rcw)  # 확인된 절차에서도 독립 노출 없음
    adm = by_id["LEG_ADMIN_DELAY"]
    assert adm.suppressed_by_specificity != "LEG_REVIEW_CAPACITY_WEAK"
    assert adm.suppressed_by_specificity is None  # RCW가 대표로 흡수 금지
    # RCW가 어떤 후보의 대표도 아니다.
    assert all(c.suppressed_by_specificity != "LEG_REVIEW_CAPACITY_WEAK"
               for c in cands)


# ── ⑫ 같은 episode 중복 컨텍스트 — 입력 순서 무관 결정적 병합 ────


def test_duplicate_episode_contexts_merge_deterministically(
    engine: RiskEngine,
) -> None:
    """같은 process_episode_id의 중복 컨텍스트는 입력 순서와 무관하게 같은 결과."""
    a = LegalProcessContext(
        target_type="administrative_application", stage="review",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="p1")
    b = LegalProcessContext(
        target_type="administrative_application", stage="submission",
        exposure_status=ExposureStatus.UNKNOWN, process_episode_id="p1")
    facts = _doc_admin_facts()
    fwd = [c.model_dump() for c in engine.generate(facts, legal_contexts=[a, b])]
    rev = [c.model_dump() for c in engine.generate(facts, legal_contexts=[b, a])]
    assert fwd == rev
    adm = next(c for c in engine.generate(facts, legal_contexts=[a, b])
               if c.risk_id == "LEG_ADMIN_DELAY")
    assert adm.legal_episode_id == "p1"
    # 결정적 병합 규칙: 완전 매칭 + 노출 선호(CONFIRMED) 컨텍스트가 이긴다.
    assert adm.exposure_status is ExposureStatus.CONFIRMED


# ── ⑬ stage 상호 배타 — 같은 원인·같은 episode여도 수렴 금지 ─────


def test_stage_incompatible_candidates_do_not_converge(engine: RiskEngine) -> None:
    """진행 중 계약 종료 위험(active_contract)과 작성·검토 단계 문서 결함은 stage
    집합이 상호 배타라 같은 원인을 공유해도 한 경고로 흡수되지 않는다."""
    ctx = LegalProcessContext(
        target_type="contract", stage="active_contract",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="contract_1")
    cands = engine.generate(_facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.PIANYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    ), legal_contexts=[ctx])
    by_id = {c.risk_id: c for c in cands}
    trm = by_id["LEG_CONTRACT_TERMINATION_RISK"]
    assert is_active(trm) and is_exposable(trm)
    doc = by_id["LEG_DOCUMENT_ERROR"]
    assert doc.suppressed_by_specificity is None  # 상호 배타 stage — 흡수 금지
    assert not is_exposable(doc)  # 작성·검토 절차 미확인 — 중복 노출도 없음


# ── ⑩ closed stage — 종결 절차에서 신규 LEG 후보 생성 제한 ───────


def test_closed_stage_creates_no_new_candidates(engine: RiskEngine) -> None:
    """종결된 계약(stage=closed)은 어떤 LEG 항목과도 매칭되지 않는다(명시 opt-in 없음).

    사후 정산·청구는 별도 episode의 비종결 stage 컨텍스트로 병존한다.
    """
    dispute_facts = _facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )
    closed = LegalProcessContext(
        target_type="contract", stage="closed",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="old_contract")
    only_closed = [c for c in engine.generate(dispute_facts, legal_contexts=[closed])
                   if c.domain is RiskDomain.CONTRACT_LEGAL]
    assert only_closed  # 구조 후보는 보존되지만
    assert all(c.legal_alignment != "matched" for c in only_closed)
    assert all(c.legal_episode_id != "old_contract" for c in only_closed)
    assert all(not is_exposable(c) for c in only_closed)
    # 사후 정산·청구 별도 episode → 그 episode 기준으로만 매칭·병존.
    settlement = LegalProcessContext(
        target_type="settlement_recovery", stage="response_required",
        exposure_status=ExposureStatus.CONFIRMED, process_episode_id="post_settlement")
    with_settlement = engine.generate(
        dispute_facts, legal_contexts=[closed, settlement])
    dsr = next(c for c in with_settlement if c.risk_id == "LEG_DISPUTE_RISK")
    assert dsr.legal_alignment == "matched"
    assert dsr.legal_episode_id == "post_settlement"
    assert is_exposable(dsr)


# ── ⑭ 소유권 — 이동 일정·선발 대기·관계 갈등은 LEG가 아니다 ──────


def test_moving_delay_owned_by_mov(engine: RiskEngine) -> None:
    """이사 일정 지연(이동 계획 확인) → MOV_SCHEDULE_DISRUPTION 노출, LEG_ADMIN 비노출."""
    from saju_engines.risk_engine import MobilityContext
    facts = _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )
    cands = engine.generate(facts, mobility_contexts=[MobilityContext(
        target_type="residential_move", stage="moving",
        exposure_status=ExposureStatus.CONFIRMED, episode_id="move_1")])
    by_id = {c.risk_id: c for c in cands}
    mov = by_id["MOV_SCHEDULE_DISRUPTION"]
    assert is_active(mov) and is_exposable(mov)
    adm = by_id["LEG_ADMIN_DELAY"]
    assert adm.legal_alignment == "unknown"
    assert not is_exposable(adm)


def test_selection_result_wait_owned_by_sel(engine: RiskEngine) -> None:
    """일반 선발 결과 대기 → SEL_RESULT_DELAY_PRESSURE 노출, LEG_ADMIN 비노출."""
    facts = _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )
    cands = engine.generate(
        facts, exposure_status=ExposureStatus.CONFIRMED,
        selection_context=SelectionContext(
            target_type="examination", stage="result_wait"),
    )
    by_id = {c.risk_id: c for c in cands}
    sel = by_id["SEL_RESULT_DELAY_PRESSURE"]
    assert is_active(sel) and is_exposable(sel)
    adm = by_id["LEG_ADMIN_DELAY"]
    assert adm.legal_alignment == "unknown"
    assert not is_exposable(adm)


def test_peer_trust_signals_do_not_create_leg_dispute(engine: RiskEngine) -> None:
    """관계 신뢰 신호(겁재+비겁 파)만으로 LEG_DISPUTE가 생기지 않는다(REL 소관)."""
    cands = engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.PA, Pillar4.MONTH,
                                target_ten_god=TenGod.BIJIAN)],
    ))
    by_id = {c.risk_id: c for c in cands}
    assert "REL_TRUST_STABILITY_WEAK" in by_id
    dsr = by_id.get("LEG_DISPUTE_RISK")
    assert dsr is None or not is_active(dsr)


# ── ⑮ vulnerability 역전 방지 — 전 도메인 synthetic 일반화 ────────


def _synthetic_candidate(domain: RiskDomain, *, kind, rank: int, risk_id: str,
                         exposure_requirement: str = "not_required"):
    """suppression 단위 검증용 synthetic 후보 — 공유 관계 원자 1개."""
    from saju_shared_types.risk_engine import (
        EvidenceRole,
        RiskCandidate,
        RiskEvidence,
    )
    return RiskCandidate(
        risk_id=risk_id, domain=domain, kind=kind, risk_family="shared_family",
        period_key="2026", evidence=[RiskEvidence(
            evidence_id="2026|relation:CHUNG:month:branch:zhengguan",
            code="SYN_T1", period_key="2026", layer="sewoon",
            source="relation:CHUNG:month:branch:zhengguan", strength=0.5,
            role=EvidenceRole.TRIGGER, source_group="event_shape",
            target_domain=domain,
        )],
        exposure_requirement=exposure_requirement,
        specificity_rank=rank,
        trigger_cause_atoms=["relation:CHUNG:month:branch:zhengguan"],
    )


@pytest.mark.parametrize("domain", list(RiskDomain))
def test_vulnerability_never_absorbs_exposable_pressure(domain: RiskDomain) -> None:
    """전 도메인: 비노출 vulnerability는 노출 가능한 pressure를 흡수할 수 없고,
    어떤 후보의 대표도 될 수 없다(감수 23차 커밋 조건 8 — FIN 사례의 전역 고정)."""
    from saju_engines.risk_engine import _apply_specificity_suppression
    from saju_shared_types.risk_engine import RiskKind
    vuln = _synthetic_candidate(
        domain, kind=RiskKind.VULNERABILITY, rank=1, risk_id="SYN_VULN")
    pressure = _synthetic_candidate(
        domain, kind=RiskKind.PRESSURE, rank=0, risk_id="SYN_PRESSURE")
    out = {c.risk_id: c for c in _apply_specificity_suppression([vuln, pressure])}
    assert out["SYN_PRESSURE"].suppressed_by_specificity is None
    assert out["SYN_VULN"].suppressed_by_specificity is None
    # 반대 방향(노출 가능한 사건 대표가 취약성을 background로 흡수)은 보존된다.
    incident = _synthetic_candidate(
        domain, kind=RiskKind.INCIDENT_RISK, rank=2, risk_id="SYN_INCIDENT")
    out2 = {c.risk_id: c for c in _apply_specificity_suppression(
        [vuln, pressure, incident])}
    assert out2["SYN_VULN"].suppressed_by_specificity == "SYN_INCIDENT"
    assert out2["SYN_VULN"].absorbed_role == "background_vulnerability"
    assert out2["SYN_INCIDENT"].suppressed_by_specificity is None
