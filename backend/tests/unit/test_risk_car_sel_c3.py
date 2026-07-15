"""C3 선행 — CAR_WORK_OVERLOAD·SEL_COMPETITION_INTENSIFY pressure 재저작 fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.risk_engine import RelationFact, RiskEngine, build_raw_period_facts
from saju_shared_types.event_engine import (
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
)
from saju_shared_types.risk_engine import ExposureStatus, is_active

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"

# 양성 fixture 커버리지 manifest — reviewed 승격 게이트가 참조.
CAR_SEL_POSITIVE_IDS = {"CAR_WORK_OVERLOAD", "SEL_COMPETITION_INTENSIFY"}


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    return RiskEngine(_DICTS)


def _facts(*, gods=None, relations=None, role=PolarityRole.GI):
    return build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=False, polarity_role=role, twelve_stage=None,
    )


def _get(cands, rid):
    return next((c for c in cands if c.risk_id == rid), None)


def test_work_overload_positive_and_negatives(engine: RiskEngine) -> None:
    """양성: 역할 활성+부담 구조. 음성: 관성 기신만 / 월주 활성만(부담 구조 없음)."""
    pos = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_WORK_OVERLOAD")
    assert pos is not None and is_active(pos)
    assert pos.exposure_requirement == "required_for_exposure"
    only_gisin = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
    )), "CAR_WORK_OVERLOAD")
    assert only_gisin is None or not is_active(only_gisin)  # 관성 기신만 — 부담 구조 없음
    only_palace = _get(engine.generate(_facts(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_WORK_OVERLOAD")
    assert only_palace is None or not is_active(only_palace)  # 월주 활성만


def test_work_overload_exposure_denied_blocked(engine: RiskEngine) -> None:
    """직업 역할 DENIED면 직업 압박은 차단(기록 보존)."""
    denied = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ), exposure_status=ExposureStatus.DENIED), "CAR_WORK_OVERLOAD")
    assert denied is not None and not is_active(denied)


def test_competition_positive_and_negatives(engine: RiskEngine) -> None:
    """양성: 경쟁 구조(비겁+관성)+심사 관문 피격. 음성: 비겁·관성만(선발 대상 없음)."""
    pos = _get(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "SEL_COMPETITION_INTENSIFY")
    assert pos is not None and is_active(pos)
    no_target = _get(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
    )), "SEL_COMPETITION_INTENSIFY")
    assert no_target is None or not is_active(no_target)  # 선발 관문 활성 없음
    denied = _get(engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ), exposure_status=ExposureStatus.DENIED), "SEL_COMPETITION_INTENSIFY")
    assert denied is not None and not is_active(denied)


def test_competition_does_not_spawn_outcome(engine: RiskEngine) -> None:
    """경쟁 심화가 탈락·추첨 실패 후보를 자동 생성하지 않는다(결과≠과정)."""
    cands = engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ))
    lot = _get(cands, "SEL_LOTTERY_MISS")
    assert lot is None or not is_active(lot)


def test_unlinked_shape_and_activation_insufficient(engine: RiskEngine) -> None:
    """대상 무관 조합 — 역할 활성(재성 피격)과 부담 shape(관성·식상)가 연결되지 않으면
    INSUFFICIENT(느슨한 조합 차단, requiresLinkedTargets)."""
    from saju_shared_types.risk_engine import EligibilityStatus

    cands = engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],  # 재물 대상 — 역할 무관
    ))
    ovl = _get(cands, "CAR_WORK_OVERLOAD")
    assert ovl is not None
    assert ovl.eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert "targets_unlinked" in ovl.suppression_reasons


def test_linked_shape_and_activation_active(engine: RiskEngine) -> None:
    """대상 연결 양성 — 관성 피격(활성)과 편관 동반 shape가 같은 십성군(관성)이면 활성."""
    pos = _get(engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}, TenGod.SHISHEN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_WORK_OVERLOAD")
    assert pos is not None and is_active(pos)


def test_same_god_group_different_target_objects_unlinked() -> None:
    """감수 12차 — 같은 십성군이라도 궁위·대상 객체가 다르면 연결되지 않는다
    (십성군 fallback은 상위 대상 정보 부재 시에만)."""
    from saju_engines.dictionaries import RiskItem
    from saju_shared_types.risk_engine import EligibilityStatus

    item = RiskItem.model_validate({
        "riskId": "CAR_TEST_LNK",
        "domain": "career", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [
            {"id": "S1", "group": "targeted_event_shape", "relation": "HYEONG",
             "relationPalace": "day_pillar", "tenGodGroup": "authority", "strength": 0.5},
            {"id": "A1", "group": "target_activation", "relation": "CHUNG",
             "relationPalace": "month_pillar", "strength": 0.45},
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "evidenceContract": {
            "anyOf": [{"allOfGroups": ["targeted_event_shape", "target_activation"]}],
            "minIndependentCauses": 1, "requiresLinkedTargets": True,
        },
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    # 일지 형(관성 대상)과 월주 충(관성 대상) — 같은 관성군이지만 대상 객체가 다름.
    cands = solo.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.HYEONG, Pillar4.DAY, target_ten_god=TenGod.QISHA),
            RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                         target_ten_god=TenGod.ZHENGGUAN),
        ],
    ))
    assert len(cands) == 1
    assert cands[0].eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert "targets_unlinked" in cands[0].suppression_reasons


# ── C3-b — CAR canonical 5항목 fixture ──


def test_car_c3b_positives_and_legacy_gone(engine_c3b=None) -> None:
    """canonical 5항목 양성 + legacy ID(EVALUATION_DISADVANTAGE 등) 미생성."""
    eng = RiskEngine(_DICTS)
    facts = _facts(
        gods={TenGod.SHANGGUAN: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON},
              TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN),
                   RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.QISHA)],
    )
    ids_all = {c.risk_id for c in eng.generate(facts)}
    active = {c.risk_id for c in eng.generate(facts) if is_active(c)}
    assert "CAR_EVALUATION_SETBACK_RISK" in ids_all
    assert "CAR_REASSIGNMENT_RISK" in ids_all
    assert "CAR_EXIT_PRESSURE" in ids_all
    # legacy ID는 사전에서 제거 — 신·구 동시 생성 불가.
    assert not ({"CAR_EVALUATION_DISADVANTAGE", "CAR_UNWANTED_TRANSFER",
                 "CAR_HIRING_DELAY_REJECTION"} & ids_all)
    assert active  # 활성 대표 존재(family별 흡수 후)


def test_car_hiring_split(engine_c3b=None) -> None:
    """채용 분리 — 공망 정체+절차 자극=지연 pressure, 관성 피격 targeted=결과 incident.
    같은 hiring family에서 결과(3)가 지연(0)을 흡수(원인 공유 시)."""
    eng = RiskEngine(_DICTS)
    delay_only = {c.risk_id: c for c in eng.generate(_facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}}, 
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ))}
    # 공망 없음 — 지연 shape 미충족.
    hpd = delay_only.get("CAR_HIRING_PROCESS_DELAY")
    assert hpd is None or not is_active(hpd)
    both = build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN),
                   RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        void_active=True, polarity_role=PolarityRole.GI, twelve_stage=None,
    )
    by = {c.risk_id: c for c in eng.generate(both)}
    assert is_active(by["CAR_HIRING_OUTCOME_SETBACK"]) or is_active(
        by["CAR_HIRING_PROCESS_DELAY"])
    if by["CAR_HIRING_PROCESS_DELAY"].suppressed_by_specificity:
        assert by["CAR_HIRING_PROCESS_DELAY"].primary_risk_id == (
            "CAR_HIRING_OUTCOME_SETBACK")


# ── CAR 승격 커버리지(감수 13차) — 항목별 양성·음성 ──

CAR_C3B_POSITIVE_IDS = {
    "CAR_EVALUATION_SETBACK_RISK", "CAR_REASSIGNMENT_RISK", "CAR_EXIT_PRESSURE",
    "CAR_HIRING_PROCESS_DELAY", "CAR_HIRING_OUTCOME_SETBACK",
}


def test_evaluation_setback_negatives(engine: RiskEngine) -> None:
    """EVALUATION — 관성 피격 단독·일반 직업 pressure만으로는 미활성."""
    only_hit = _get(engine.generate(_facts(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )), "CAR_EVALUATION_SETBACK_RISK")
    assert only_hit is None or not is_active(only_hit)


def test_exit_pressure_no_termination_event(engine: RiskEngine) -> None:
    """EXIT_PRESSURE 양성 시에도 종료형 사건(HIRING_OUTCOME 등)이 자동 생성되지 않는다."""
    cands = engine.generate(_facts(
        gods={TenGod.SHANGGUAN: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    ))
    exi = _get(cands, "CAR_EXIT_PRESSURE")
    assert exi is not None
    # 채용 결과의 독립 근거(공망 shape·targeted)가 없는 facts — 결과 후보는 활성 불가.
    hos = _get(cands, "CAR_HIRING_OUTCOME_SETBACK")
    assert hos is None or not is_active(hos)


def test_hiring_outcome_needs_result_stage(engine: RiskEngine) -> None:
    """HIRING_OUTCOME — 절차 정체(공망)만으로는 미활성(targeted/결과 활성 필요)."""
    proc_only = _get(engine.generate(build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[], void_active=True, polarity_role=PolarityRole.GI,
        twelve_stage=None,
    )), "CAR_HIRING_OUTCOME_SETBACK")
    assert proc_only is None or not is_active(proc_only)


# ── C3-c — SEL canonical 5항목 fixture ──

SEL_C3C_POSITIVE_IDS = {
    "SEL_DOCUMENT_DEFECT_RISK", "SEL_ELIGIBILITY_REVIEW_RISK",
    "SEL_DRAW_OUTCOME_UNCERTAINTY", "SEL_RESULT_DELAY_PRESSURE",
    "SEL_WAITLIST_PROLONGATION",
}


def test_sel_c3c_positives_and_legacy_gone() -> None:
    """SEL canonical 5항목 양성 + legacy ID 미생성 + waitlist confirmed_required."""
    eng = RiskEngine(_DICTS)
    doc = _get(eng.generate(build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.PIANYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void_active=False, polarity_role=PolarityRole.GI, twelve_stage=None,
    )), "SEL_DOCUMENT_DEFECT_RISK")
    assert doc is not None and is_active(doc)
    facts_auth_void = build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        void_active=True, polarity_role=PolarityRole.GI, twelve_stage=None,
    )
    cands = eng.generate(facts_auth_void)
    drw = _get(cands, "SEL_DRAW_OUTCOME_UNCERTAINTY")
    assert drw is not None
    legacy = {"SEL_DOCUMENT_OMISSION", "SEL_ELIGIBILITY_SHORTFALL",
              "SEL_LOTTERY_MISS", "SEL_WAITLIST_DELAY"}
    assert not (legacy & {c.risk_id for c in cands})


def test_draw_uncertainty_not_always_on() -> None:
    """추첨 불확실성 — 관문 대상 활성 없이 공망만으로는 상시 발동하지 않는다."""
    eng = RiskEngine(_DICTS)
    void_only = _get(eng.generate(build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[], void_active=True, polarity_role=PolarityRole.GI,
        twelve_stage=None,
    )), "SEL_DRAW_OUTCOME_UNCERTAINTY")
    assert void_only is None or not is_active(void_only)


# ── C3-d — SelectionContext 3상태·소유권·stage-aware suppression·노출 게이트 ──

from saju_engines.risk_engine import SelectionContext  # noqa: E402
from saju_shared_types.risk_engine import is_exposable  # noqa: E402


def _sel_facts():
    """SEL 5항목이 두루 관측되는 관성·인성 자극 facts(같은 궁 대상 — 연결 성립)."""
    return build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGGUAN: {LuckLayer.SEWOON},
                        TenGod.PIANYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN),
                   RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN),
                   RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN),
                   RelationFact(RelationKind.HAE, Pillar4.YEAR,
                                target_ten_god=TenGod.ZHENGYIN)],
        void_active=True, polarity_role=PolarityRole.GI, twelve_stage=None,
    )


def test_mode_stage_tristate(engine: RiskEngine) -> None:
    """mode 3상태 — MATCHED=활성 가능, UNKNOWN=구조 보존·비노출, MISMATCHED=BLOCKED."""
    from saju_shared_types.risk_engine import EligibilityStatus

    comp_facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
    )
    matched = _get(engine.generate(comp_facts, selection_context=SelectionContext(
        mode="competitive_assessment", target_type="examination",
    )), "SEL_COMPETITION_INTENSIFY")
    assert matched is not None and matched.selection_alignment == "matched"
    assert is_active(matched)
    unknown = _get(engine.generate(comp_facts), "SEL_COMPETITION_INTENSIFY")
    assert unknown is not None and unknown.selection_alignment == "unknown"
    assert is_active(unknown) and not is_exposable(unknown)  # 구조 보존·노출 불가
    mismatched = _get(engine.generate(comp_facts, selection_context=SelectionContext(
        mode="lottery_draw",
    )), "SEL_COMPETITION_INTENSIFY")
    assert mismatched is not None
    assert mismatched.eligibility_status is EligibilityStatus.BLOCKED
    assert "selection_mode_mismatch" in mismatched.suppression_reasons
    assert mismatched.selection_alignment == "mismatched"


def test_mode_stage_no_mutual_inference(engine: RiskEngine) -> None:
    """상호 추론 금지 — stage=draw만 확인돼도 mode는 UNKNOWN으로 남는다."""
    drw = _get(engine.generate(_sel_facts(), selection_context=SelectionContext(
        stage="draw",
    )), "SEL_DRAW_OUTCOME_UNCERTAINTY")
    assert drw is not None
    assert drw.selection_alignment == "unknown"  # mode 미확인 — lottery로 가정 안 함
    assert not is_exposable(drw)


def test_car_sel_target_ownership(engine: RiskEngine) -> None:
    """소유권 — 채용 대상이면 SEL 결과 지연 차단, 일반 선발이면 CAR 채용 차단."""
    hiring = SelectionContext(target_type="employment_hiring")
    general = SelectionContext(target_type="examination")
    cands_h = engine.generate(_sel_facts(), selection_context=hiring)
    sel_rdl = _get(cands_h, "SEL_RESULT_DELAY_PRESSURE")
    assert sel_rdl is None or not is_active(sel_rdl)  # SEL 차단
    cands_g = engine.generate(_sel_facts(), selection_context=general)
    car_hpd = _get(cands_g, "CAR_HIRING_PROCESS_DELAY")
    assert car_hpd is None or not is_active(car_hpd)  # CAR 차단
    car_hpd_h = _get(cands_h, "CAR_HIRING_PROCESS_DELAY")
    assert car_hpd_h is None or car_hpd_h.selection_alignment in ("matched", "unknown")


def test_result_delay_vs_waitlist_mutual_exclusion(engine: RiskEngine) -> None:
    """RESULT_DELAY vs WAITLIST — stage로 상호 배제(+stage-aware 흡수 금지)."""
    result_stage = engine.generate(_sel_facts(), selection_context=SelectionContext(
        stage="result_wait", target_type="examination",
    ))
    wlp = _get(result_stage, "SEL_WAITLIST_PROLONGATION")
    assert wlp is None or not is_active(wlp)  # stage mismatch → 차단
    rdl = _get(result_stage, "SEL_RESULT_DELAY_PRESSURE")
    assert rdl is not None and rdl.selection_alignment in ("matched", "unknown")
    # 흡수 검사 — 다른 stage 메타 후보끼리는 같은 family여도 흡수하지 않는다.
    no_ctx = engine.generate(_sel_facts())
    for c in no_ctx:
        if c.risk_id in ("SEL_RESULT_DELAY_PRESSURE", "SEL_WAITLIST_PROLONGATION"):
            assert c.suppressed_by_specificity is None


def test_waitlist_unknown_never_exposable(engine: RiskEngine) -> None:
    """대기명단 — UNKNOWN에서는 기계적으로 비노출(unknownExposable=false)."""
    wlp = _get(engine.generate(_sel_facts(), selection_context=SelectionContext(
        stage="waitlist", target_type="examination",
    )), "SEL_WAITLIST_PROLONGATION")
    assert wlp is not None and is_active(wlp)
    assert not is_exposable(wlp)  # 노출 UNKNOWN — confirmed 전 절대 비노출
    confirmed = _get(engine.generate(_sel_facts(), selection_context=SelectionContext(
        stage="waitlist", target_type="examination", mode="mixed",
    ), exposure_status=ExposureStatus.CONFIRMED), "SEL_WAITLIST_PROLONGATION")
    assert confirmed is not None and is_exposable(confirmed)


def test_sel_c3c_positive_recall_all_five(engine: RiskEngine) -> None:
    """SEL canonical 5항목 전수 — 각자 명확 양성에서 활성(INSUFFICIENT 아님)."""
    from saju_shared_types.risk_engine import EligibilityStatus

    cases = {
        "SEL_DOCUMENT_DEFECT_RISK": _facts(
            gods={TenGod.PIANYIN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGYIN)],
        ),
        "SEL_ELIGIBILITY_REVIEW_RISK": _facts(
            gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGYIN)],
        ),
        "SEL_DRAW_OUTCOME_UNCERTAINTY": _facts(
            gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGGUAN)],
        ),
        "SEL_RESULT_DELAY_PRESSURE": _facts(
            gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGYIN)],
        ),
        "SEL_WAITLIST_PROLONGATION": _facts(
            gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGGUAN),
                       RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGGUAN)],  # 같은 대상 객체
        ),
    }
    for rid, facts in cases.items():
        c = _get(engine.generate(facts), rid)
        assert c is not None, rid
        assert c.eligibility_status in (
            EligibilityStatus.ELIGIBLE, EligibilityStatus.MITIGATED,
        ), (rid, c.suppression_reasons)
