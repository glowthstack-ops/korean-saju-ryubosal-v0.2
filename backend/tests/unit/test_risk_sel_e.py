"""SEL-e 차수(감수 25차) — 다중 선발 episode 의미론 fixture.

데굴님 필수 기준: ①명시 selection_episode_id ②episode별 후보 identity ③episode별
CAR–SEL 소유권 ④동일 target type의 복수 episode 보존 ⑤episode 간 MISMATCHED 전파
금지 ⑥같은 cause의 후보 보존(R1 1회 계산은 trigger_cause_atoms 연결) ⑦결정적
병합·보완과 CONTEXT_CONFLICT ⑧단수 selection_context와 [ctx]의 결과 동일.
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
from saju_shared_types.event_engine import (
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
)
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    ExposureStatus,
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


def _delay_facts():
    """인성 해 피격 + 공망 — 선발 결과 지연(SEL_RESULT_DELAY) 성립 조합(C8 검증)."""
    return _facts(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )


def _coexist_facts():
    """채용 지연(공망+관성 shape·해 관성 피격) + 서류 결함(편인·공망 shape·충 인성
    피격) 동시 성립 — 관계 종류를 분리해 원인 서명 병합을 피한 조합."""
    return _facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON},
              TenGod.ZHENGYIN: {LuckLayer.SEWOON},
              TenGod.PIANYIN: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.HAE, Pillar4.YEAR,
                         target_ten_god=TenGod.ZHENGGUAN),
            RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                         target_ten_god=TenGod.ZHENGYIN),
        ],
        void=True,
    )


_HIRING = SelectionContext(
    target_type="employment_hiring", stage="result_wait",
    exposure_status=ExposureStatus.CONFIRMED, episode_id="employment_hiring_1")
_EXAM = SelectionContext(
    target_type="examination", stage="result_wait",
    exposure_status=ExposureStatus.CONFIRMED, episode_id="examination_1")


# ── ①·③·⑤ episode별 소유권 병존 + mismatch 미전파 ────────────────


def test_hiring_and_exam_episodes_coexist(engine: RiskEngine) -> None:
    """채용 결과 대기 + 별도 자격시험 결과 대기 → CAR·SEL이 각자 episode에서 병존.

    채용 episode의 SEL 결과 후보 차단이 시험 episode로 전파되지 않는다(데굴님
    필수 불변식 — 단수 SelectionContext 시절엔 표현 불가였던 시나리오).
    """
    cands = engine.generate(_delay_facts(), selection_contexts=[_HIRING, _EXAM])
    sel = {c.selection_episode_id: c for c in cands
           if c.risk_id == "SEL_RESULT_DELAY_PRESSURE"}
    # SEL 결과 지연: 시험 episode에서만 매칭·노출(채용은 대상 밖 — 그 episode로는
    # 후보 자체가 생성되지 않음 = 차단, 시험 episode는 살아 있음 = 미전파).
    assert set(sel) == {"examination_1"}
    assert is_active(sel["examination_1"]) and is_exposable(sel["examination_1"])


def test_hiring_and_exam_document_ownership_coexist(engine: RiskEngine) -> None:
    """채용 결과 대기 + 시험 서류 단계 — CAR 지연과 SEL 문서 결함이 각자 episode에서
    병존하고, 결과 지연은 두 episode 모두의 명시적 대상 밖이라 BLOCKED."""
    exam_doc = SelectionContext(
        target_type="examination", stage="application_document",
        exposure_status=ExposureStatus.CONFIRMED, episode_id="examination_1")
    cands = engine.generate(_coexist_facts(),
                            selection_contexts=[_HIRING, exam_doc])
    car = {c.selection_episode_id: c for c in cands
           if c.risk_id == "CAR_HIRING_PROCESS_DELAY"}
    assert set(car) == {"employment_hiring_1"}
    assert is_active(car["employment_hiring_1"])
    assert is_exposable(car["employment_hiring_1"])
    doc = {c.selection_episode_id: c for c in cands
           if c.risk_id == "SEL_DOCUMENT_DEFECT_RISK"}
    assert set(doc) == {"examination_1"}
    assert is_active(doc["examination_1"]) and is_exposable(doc["examination_1"])
    rdl = next(c for c in cands if c.risk_id == "SEL_RESULT_DELAY_PRESSURE")
    assert rdl.eligibility_status is EligibilityStatus.BLOCKED  # 두 episode 다 대상 밖


def test_hiring_only_still_blocks_sel(engine: RiskEngine) -> None:
    """채용 episode만 있으면(질문 대상) SEL 결과 후보는 여전히 BLOCKED(단수 의미 보존)."""
    cands = engine.generate(_delay_facts(), selection_contexts=[_HIRING])
    sel = next(c for c in cands if c.risk_id == "SEL_RESULT_DELAY_PRESSURE")
    assert sel.eligibility_status is EligibilityStatus.BLOCKED
    assert "selection_target_type_mismatch" in sel.suppression_reasons


# ── ②·④ 동일 target type 복수 episode → 후보 분리 보존 ───────────


def test_same_target_type_two_episodes_two_candidates(engine: RiskEngine) -> None:
    """examination_1(결과 대기) + examination_2(결과 대기) → 같은 risk_id 후보 2개."""
    exam2 = SelectionContext(
        target_type="examination", stage="result_wait",
        exposure_status=ExposureStatus.UNKNOWN, episode_id="examination_2")
    cands = engine.generate(_delay_facts(), selection_contexts=[_EXAM, exam2])
    sel = {c.selection_episode_id: c for c in cands
           if c.risk_id == "SEL_RESULT_DELAY_PRESSURE"}
    assert set(sel) == {"examination_1", "examination_2"}
    # episode별 exposure 독립 — 확인된 건은 CONFIRMED, 미확인 건은 전역(UNKNOWN).
    assert sel["examination_1"].exposure_status is ExposureStatus.CONFIRMED
    assert sel["examination_2"].exposure_status is ExposureStatus.UNKNOWN
    # 서로 다른 episode는 같은 원인을 공유해도 자동 흡수 금지(⑥).
    assert all(c.suppressed_by_specificity is None for c in sel.values())
    shared = set(sel["examination_1"].trigger_cause_atoms) & set(
        sel["examination_2"].trigger_cause_atoms)
    assert shared  # R1 shared-cause 1회 계산용 연결 정보 보존


# ── ⑦ 결정적 병합·보완·충돌 ──────────────────────────────────────


def test_duplicate_contexts_merge_deterministically(engine: RiskEngine) -> None:
    """같은 episode 중복·보완 컨텍스트 — 입력 순서 무관, 보완 값은 구체 값으로 병합."""
    a = SelectionContext(target_type="examination", stage="result_wait",
                         episode_id="exam_x")
    b = SelectionContext(target_type="examination",
                         exposure_status=ExposureStatus.CONFIRMED,
                         episode_id="exam_x")
    fwd = [c.model_dump() for c in engine.generate(
        _delay_facts(), selection_contexts=[a, b])]
    rev = [c.model_dump() for c in engine.generate(
        _delay_facts(), selection_contexts=[b, a])]
    assert fwd == rev
    sel = next(c for c in engine.generate(_delay_facts(), selection_contexts=[a, b])
               if c.risk_id == "SEL_RESULT_DELAY_PRESSURE")
    assert sel.selection_episode_id == "exam_x"
    assert sel.selection_alignment == "matched"  # stage는 a가, 노출은 b가 보완
    assert sel.exposure_status is ExposureStatus.CONFIRMED


def test_conflicting_contexts_not_exposable(engine: RiskEngine) -> None:
    """같은 episode의 명시적 충돌(mode lottery vs competitive) → 구조 보존·비노출."""
    a = SelectionContext(mode="lottery_draw", target_type="lottery_allocation",
                         stage="draw", episode_id="draw_x",
                         exposure_status=ExposureStatus.CONFIRMED)
    b = SelectionContext(mode="competitive_assessment",
                         target_type="lottery_allocation", stage="draw",
                         episode_id="draw_x")
    cands = engine.generate(_delay_facts(), selection_contexts=[a, b])
    sel = next(c for c in cands if c.risk_id == "SEL_RESULT_DELAY_PRESSURE")
    assert sel.selection_context_conflict
    assert "selection_context_conflict" in sel.suppression_reasons
    assert is_active(sel)  # 구조 보존
    assert not is_exposable(sel)  # 임의 우선순위 병합 금지 — 비노출
    assert sel.selection_alignment == "unknown"


# ── ⑧ 단수 하위 호환 — selection_context=ctx == selection_contexts=[ctx] ──


def test_legacy_single_context_equivalence(engine: RiskEngine) -> None:
    """단수 파라미터와 길이 1 목록은 byte-identical 결과를 만든다."""
    facts = _delay_facts()
    single = [c.model_dump() for c in engine.generate(
        facts, exposure_status=ExposureStatus.CONFIRMED,
        selection_context=_HIRING)]
    listed = [c.model_dump() for c in engine.generate(
        facts, exposure_status=ExposureStatus.CONFIRMED,
        selection_contexts=[_HIRING])]
    assert single == listed


# ── ⑩ 문서·자격 공통 위험 매트릭스 유지 — 채용에서도 SEL 문서 적용 ──


def test_hiring_document_stage_keeps_sel_document(engine: RiskEngine) -> None:
    """채용 + 서류 단계 → SEL_DOCUMENT_DEFECT 적용 가능(소유권은 risk_id×target×stage)."""
    doc_ctx = SelectionContext(
        target_type="employment_hiring", stage="application_document",
        exposure_status=ExposureStatus.CONFIRMED, episode_id="employment_hiring_1")
    facts = _facts(
        gods={TenGod.PIANYIN: {LuckLayer.SEWOON},
              TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True,
    )
    cands = engine.generate(facts, selection_contexts=[doc_ctx])
    doc = next(c for c in cands if c.risk_id == "SEL_DOCUMENT_DEFECT_RISK")
    assert is_active(doc) and is_exposable(doc)
    assert doc.selection_episode_id == "employment_hiring_1"
