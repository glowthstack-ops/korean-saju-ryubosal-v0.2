"""위험 사전 MOV 차수(C6 — 감수 18·19차) 의미론 fixture.

데굴님 MOV 차수 불변식: 이동·주거 위험은 운 신호만으로 이사 계획·계약·차량·통근의
존재를 만들지 않으며, "원치 않는 이동"은 preference=undesired 확인이 결정한다. 같은
이동 episode의 위험만 대표 1건+보조 역할로 수렴한다(계약 전 단계와 정착 후 단계는
상호 배타 — stage 호환 억제, 서로 다른 계획은 episode_id로 병존).

고정 범위(19차 조건): ①양성 recall ②소유권(발령 질문=MISMATCHED)+workplace의 물리적
이동 결과 병존 ③구체 항목 UNKNOWN 비노출 vs 일반 이동 압박 조건부(차등) ④차량 추론
금지 ⑤stage 호환 수렴+episode 분리 ⑥하자=별개 현실 문제 ⑦preference 적격성 무영향.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.risk_engine import (
    MobilityContext,
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
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    ExposureStatus,
    is_active,
    is_exposable,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"

# 커버리지 게이트 연동(test_risk_engine.py) — MOV 승격 시 항목별 양성 fixture 원천.
MOV_POSITIVE_IDS = {
    "MOV_CONTRACT_SETBACK_RISK",
    "MOV_SCHEDULE_DISRUPTION",
    "MOV_HOUSING_DEFECT_RISK",
    "MOV_COMMUTE_BURDEN",
    "MOV_RELOCATION_PRESSURE",
    "MOV_VEHICLE_TRANSPORT_ISSUE",
}


@pytest.fixture(scope="module")
def engine() -> RiskEngine:
    """위험 엔진(모듈 1회 로드)."""
    return RiskEngine(_DICTS)


def _facts(
    *,
    period: str = "2026",
    gods: dict[TenGod, set[LuckLayer]] | None = None,
    relations: list[RelationFact] | None = None,
    void: bool = False,
    role: PolarityRole = PolarityRole.NEUTRAL,
):
    """테스트용 원시 신호 스냅샷 헬퍼."""
    return build_raw_period_facts(
        period_key=period, layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=void, polarity_role=role, twelve_stage=None,
    )


def _active_ids(cands) -> set[str]:
    return {c.risk_id for c in cands if is_active(c)}


_MOVE_CONTRACTED = MobilityContext(
    target_type="residential_move", stage="contracted",
    exposure_status=ExposureStatus.CONFIRMED, episode_id="move_plan_1",
)
_COMMUTE_CONFIRMED = MobilityContext(
    target_type="commute_change", stage="moving",
    exposure_status=ExposureStatus.CONFIRMED, commute_dependency=True,
    episode_id="commute_route_1",
)
_VEHICLE_CONFIRMED = MobilityContext(
    target_type="vehicle_use", exposure_status=ExposureStatus.CONFIRMED,
    vehicle_exposure=True, episode_id="vehicle_1",
)


# ── ① 항목별 양성 recall(승격 게이트 원천) ─────────────────────────

_MOV_POSITIVE_CASES: list[tuple[str, dict, MobilityContext]] = [
    # 문서 공망 shape + 주거궁(일지) 활성 — 계약 단계 확인.
    ("MOV_CONTRACT_SETBACK_RISK", dict(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        void=True, role=PolarityRole.GI,
    ), _MOVE_CONTRACTED),
    # 문서·계획 공망(인성 동반) shape + 계획 채널(인성군) 해 — 이사 준비 단계.
    ("MOV_SCHEDULE_DISRUPTION", dict(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True, role=PolarityRole.GI,
    ), MobilityContext(target_type="residential_move", stage="preparing",
                       exposure_status=ExposureStatus.CONFIRMED)),
    # 비용 발생 형태(겁재-인성 동반) + 주거·문서 채널 형 — 입주·수리 책임 확인.
    ("MOV_HOUSING_DEFECT_RISK", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON},
              TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        role=PolarityRole.GI,
    ), MobilityContext(target_type="residential_move", stage="settled",
                       exposure_status=ExposureStatus.CONFIRMED,
                       repair_responsibility=True)),
    # 충 발동 + 통근 의존·이동 단계 확인.
    # (연주 사용 — 일·월주는 RELOCATION_PRESSURE targeted라 대표 흡수와 겹친다.)
    ("MOV_COMMUTE_BURDEN", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR)],
        role=PolarityRole.GI,
    ), _COMMUTE_CONFIRMED),
    # 일지(거처) 직접 충 targeted + 주거 이동 확인.
    ("MOV_RELOCATION_PRESSURE", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI,
    ), _MOVE_CONTRACTED),
    # 시주(이동 수단) 직접 충 targeted + 차량 노출 확인.
    ("MOV_VEHICLE_TRANSPORT_ISSUE", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR)],
        role=PolarityRole.GI,
    ), _VEHICLE_CONFIRMED),
]


@pytest.mark.parametrize(("risk_id", "kwargs", "ctx"), _MOV_POSITIVE_CASES)
def test_mov_positive_recall(
    engine: RiskEngine, risk_id: str, kwargs: dict, ctx: MobilityContext,
) -> None:
    """MOV 6항목 전수 — 명확 양성 조합에서 활성 생성(항목별 recall 게이트)."""
    cands = engine.generate(_facts(**kwargs), mobility_contexts=[ctx])
    assert risk_id in _active_ids(cands)


# ── ② 소유권 — 발령 질문 차단 + 물리적 이동 결과 병존 ────────────


def test_workplace_question_blocks_mov_pressure(engine: RiskEngine) -> None:
    """질문 직접 대상이 발령이면 주거 이동 압박 항목은 MISMATCHED(BLOCKED).

    발령·보직 결정은 CAR_REASSIGNMENT_RISK primary. 질문 대상이 아닌 컨텍스트는
    존재 정보일 뿐이므로 mismatch를 만들지 않는다(is_question_target 한정).
    """
    ctx = MobilityContext(target_type="workplace_relocation",
                          exposure_status=ExposureStatus.CONFIRMED,
                          is_question_target=True)
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        mobility_contexts=[ctx],
    )
    rlp = next(c for c in cands if c.risk_id == "MOV_RELOCATION_PRESSURE")
    assert rlp.eligibility_status is EligibilityStatus.BLOCKED
    assert "mobility_target_mismatch" in rlp.suppression_reasons


def test_workplace_with_residential_move_coexists(engine: RiskEngine) -> None:
    """발령 질문 + 별도 주거 이동 확인 → CAR·MOV 병존(감수 19차 조건 6).

    발령의 물리적 결과(주거 이전)가 확인되면 workplace 질문이어도 MOV residential
    episode 후보를 버리지 않는다 — 과소탐지 방지.
    """
    workplace = MobilityContext(target_type="workplace_relocation",
                                exposure_status=ExposureStatus.CONFIRMED,
                                is_question_target=True)
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        mobility_contexts=[workplace, _MOVE_CONTRACTED],
    )
    rlp = next(c for c in cands if c.risk_id == "MOV_RELOCATION_PRESSURE")
    assert is_active(rlp) and is_exposable(rlp)
    assert rlp.mobility_alignment == "matched"
    assert rlp.mobility_episode_id == "move_plan_1"


def test_other_domain_unaffected_by_mobility(engine: RiskEngine) -> None:
    """이동 축이 없는 타 도메인 항목은 MobilityContext에 영향받지 않는다."""
    ctx = MobilityContext(target_type="workplace_relocation",
                          is_question_target=True)
    cands = engine.generate(
        _facts(gods={TenGod.SHANGGUAN: {LuckLayer.SEWOON},
                     TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGGUAN)],
               role=PolarityRole.GI),
        mobility_contexts=[ctx],
    )
    org = next(c for c in cands if c.risk_id == "CAR_ORG_CONFLICT")
    assert is_active(org) and org.mobility_alignment == "matched"


# ── ③ UNKNOWN 노출 차등 — 구체 항목 비노출 vs 일반 압박 조건부 ────


def test_specific_items_unknown_not_exposable(engine: RiskEngine) -> None:
    """계획 미확인 → 구체 항목(계약 차질)은 구조 보존 + 비노출."""
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               void=True, role=PolarityRole.GI),
    )
    ctf = next(c for c in cands if c.risk_id == "MOV_CONTRACT_SETBACK_RISK")
    assert is_active(ctf)
    assert ctf.mobility_alignment == "unknown"
    assert not is_exposable(ctf)


def test_relocation_pressure_unknown_conditional(engine: RiskEngine) -> None:
    """일반 이동 압박은 계획 미확인에서도 조건부 경로 유지(감수 19차 조건 5).

    required_for_warning — 총운에서 강한 이동 구조를 '거주·이동 조건을 조정할 변수'
    수준(advisory 상한)으로 경고할 수 있다(예상 못한 이동 압박 경고 목적). 경고
    (warning) 승격은 계획 확인 필요(R1).
    """
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
    )
    rlp = next(c for c in cands if c.risk_id == "MOV_RELOCATION_PRESSURE")
    assert is_active(rlp)
    assert rlp.mobility_alignment == "unknown"
    assert rlp.exposure_requirement == "required_for_warning"
    assert is_exposable(rlp)  # 조건부 서술 경로 — 표현 상한은 R3 advisory


def test_mobility_stage_mismatch_blocked(engine: RiskEngine) -> None:
    """정착(settled) 단계 질문에서 계약 차질 항목은 단계 MISMATCHED(BLOCKED)."""
    ctx = MobilityContext(target_type="residential_move", stage="settled",
                          exposure_status=ExposureStatus.CONFIRMED,
                          is_question_target=True)
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               void=True, role=PolarityRole.GI),
        mobility_contexts=[ctx],
    )
    ctf = next(c for c in cands if c.risk_id == "MOV_CONTRACT_SETBACK_RISK")
    assert ctf.eligibility_status is EligibilityStatus.BLOCKED
    assert "mobility_target_mismatch" in ctf.suppression_reasons


# ── ④ 차량·통근 실질 노출 조건 ──────────────────────────────────


def test_vehicle_exposure_axes(engine: RiskEngine) -> None:
    """차량 존재 추론 금지 — 미확인=비노출('차가 있다면' 우회 불가), 없음=차단."""
    facts = _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR)],
                   role=PolarityRole.GI)
    unknown = MobilityContext(target_type="vehicle_use",
                              exposure_status=ExposureStatus.CONFIRMED)
    vhc = next(
        c for c in engine.generate(facts, mobility_contexts=[unknown])
        if c.risk_id == "MOV_VEHICLE_TRANSPORT_ISSUE")
    assert is_active(vhc)
    assert vhc.exposure_status is ExposureStatus.UNKNOWN  # CONFIRMED 강등
    assert not is_exposable(vhc)

    no_vehicle = MobilityContext(target_type="vehicle_use",
                                 exposure_status=ExposureStatus.CONFIRMED,
                                 vehicle_exposure=False)
    vhc2 = next(
        c for c in engine.generate(facts, mobility_contexts=[no_vehicle])
        if c.risk_id == "MOV_VEHICLE_TRANSPORT_ISSUE")
    assert vhc2.eligibility_status is EligibilityStatus.BLOCKED


def test_commute_dependency_downgrade(engine: RiskEngine) -> None:
    """통근 의존 미확인 → CONFIRMED여도 UNKNOWN 강등(상시 경고 방지)."""
    ctx = MobilityContext(target_type="commute_change", stage="moving",
                          exposure_status=ExposureStatus.CONFIRMED)
    cmt = next(
        c for c in engine.generate(
            _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR)],
                   role=PolarityRole.GI),
            mobility_contexts=[ctx])
        if c.risk_id == "MOV_COMMUTE_BURDEN")
    assert is_active(cmt)
    assert cmt.exposure_status is ExposureStatus.UNKNOWN


# ── ⑤ stage 호환 수렴 + episode 분리 ─────────────────────────────


def test_pre_move_episode_converges_stage_compatible_only(engine: RiskEngine) -> None:
    """같은 계약 episode: 일정 차질(단계 호환)만 수렴, 통근 부담(정착 후)은 수렴 금지.

    계약 차질(searching~contracted)과 일정 차질(contracted~moving)은 {contracted}
    교집합으로 수렴 가능. 통근 부담(moving·settled)은 계약 전 단계와 상호 배타 —
    계약이 무산되면 발생하지 않을 별개 국면이므로 같은 원인이어도 흡수하지 않는다.
    """
    cands = engine.generate(
        _facts(
            gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                    target_ten_god=TenGod.ZHENGYIN)],
            void=True, role=PolarityRole.GI,
        ),
        mobility_contexts=[_MOVE_CONTRACTED],
    )
    by_id = {c.risk_id: c for c in cands}
    assert is_active(by_id["MOV_CONTRACT_SETBACK_RISK"])
    sch = by_id["MOV_SCHEDULE_DISRUPTION"]
    assert sch.suppressed_by_specificity == "MOV_CONTRACT_SETBACK_RISK"
    assert sch.absorbed_role == "supporting_manifestation"
    cmt = by_id["MOV_COMMUTE_BURDEN"]
    assert cmt.suppressed_by_specificity is None  # stage 상호 배타 — 수렴 금지
    assert not is_exposable(cmt)  # 정착 후 축 미확인 — 비노출 구조 보존


def test_post_move_commute_absorbs_as_impact(engine: RiskEngine) -> None:
    """이사 이후 episode: 이동 압박 대표 아래 통근 부담=impact_amplifier 수렴."""
    ctx = MobilityContext(target_type="residential_move", stage="moving",
                          exposure_status=ExposureStatus.CONFIRMED,
                          commute_dependency=True, episode_id="move_plan_1")
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        mobility_contexts=[ctx],
    )
    by_id = {c.risk_id: c for c in cands}
    assert is_active(by_id["MOV_RELOCATION_PRESSURE"])
    cmt = by_id["MOV_COMMUTE_BURDEN"]
    assert cmt.suppressed_by_specificity == "MOV_RELOCATION_PRESSURE"
    assert cmt.absorbed_role == "impact_amplifier"


def test_different_episodes_do_not_converge(engine: RiskEngine) -> None:
    """서로 다른 이동 계획(episode_id 상이)은 원인을 공유해도 병존한다."""
    move_ctx = MobilityContext(target_type="residential_move", stage="moving",
                               exposure_status=ExposureStatus.CONFIRMED,
                               episode_id="move_plan_1")
    commute_ctx = MobilityContext(target_type="commute_change", stage="moving",
                                  exposure_status=ExposureStatus.CONFIRMED,
                                  commute_dependency=True,
                                  episode_id="commute_route_1")
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        mobility_contexts=[move_ctx, commute_ctx],
    )
    rlp = next(c for c in cands if c.risk_id == "MOV_RELOCATION_PRESSURE"
               and c.mobility_episode_id == "move_plan_1")
    cmt_other = next(c for c in cands if c.risk_id == "MOV_COMMUTE_BURDEN"
                     and c.mobility_episode_id == "commute_route_1")
    assert is_active(rlp) and is_active(cmt_other)  # 다른 episode — 병존
    # 같은 episode(move_plan_1)의 통근 후보는 이동 압박 대표에 수렴 — episode 경계가
    # 흡수 범위를 정확히 가른다(한 episode의 대표가 다른 episode를 흡수하지 않음).
    cmt_same = next(c for c in cands if c.risk_id == "MOV_COMMUTE_BURDEN"
                    and c.mobility_episode_id == "move_plan_1")
    assert cmt_same.suppressed_by_specificity == "MOV_RELOCATION_PRESSURE"


def test_same_item_two_episodes_two_candidates(engine: RiskEngine) -> None:
    """동일 기간·동일 risk_id + episode 2개 → 후보 2개 보존(감수 20차 조건 4).

    각 후보의 exposure·정렬이 독립이다 — CONFIRMED episode와 UNKNOWN episode가
    섞이거나 exposure가 잘못 승계되지 않는다.
    """
    plan1 = MobilityContext(target_type="residential_move", stage="contracted",
                            exposure_status=ExposureStatus.CONFIRMED,
                            episode_id="move_plan_1")
    plan2 = MobilityContext(target_type="residential_move",
                            exposure_status=ExposureStatus.UNKNOWN,
                            episode_id="move_plan_2")
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        mobility_contexts=[plan1, plan2],
    )
    rlps = {c.mobility_episode_id: c for c in cands
            if c.risk_id == "MOV_RELOCATION_PRESSURE"}
    assert set(rlps) == {"move_plan_1", "move_plan_2"}
    assert rlps["move_plan_1"].exposure_status is ExposureStatus.CONFIRMED
    assert rlps["move_plan_2"].exposure_status is ExposureStatus.UNKNOWN
    assert is_active(rlps["move_plan_1"]) and is_active(rlps["move_plan_2"])


def test_duplicate_contexts_same_episode_deterministic_merge(
    engine: RiskEngine,
) -> None:
    """같은 episode의 중복 컨텍스트는 입력 순서 무관 결정적 병합 — 후보 1개."""
    a = MobilityContext(target_type="residential_move", stage="contracted",
                        exposure_status=ExposureStatus.CONFIRMED,
                        episode_id="move_plan_1")
    b = MobilityContext(target_type="residential_move",
                        exposure_status=ExposureStatus.UNKNOWN,
                        episode_id="move_plan_1")
    facts = _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
                   role=PolarityRole.GI)
    for ctxs in ([a, b], [b, a]):
        rlps = [c for c in engine.generate(facts, mobility_contexts=ctxs)
                if c.risk_id == "MOV_RELOCATION_PRESSURE"]
        assert len(rlps) == 1
        assert rlps[0].exposure_status is ExposureStatus.CONFIRMED
        assert rlps[0].mobility_alignment == "matched"


def test_relocation_plan_denied_blocked(engine: RiskEngine) -> None:
    """계획 DENIED('이사 계획 전혀 없음' 명시) → BLOCKED — UNKNOWN과 동일 처리 금지.

    구체 이사·이전 표현이 차단된다(감수 20차 조건 3). 일반 생활환경 조정 fallback은
    저작하지 않음(fallback 금지 원칙 — 필요 시 R3 별도 감수).
    """
    denied = MobilityContext(target_type="residential_move",
                             exposure_status=ExposureStatus.DENIED)
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        mobility_contexts=[denied],
    )
    rlp = next(c for c in cands if c.risk_id == "MOV_RELOCATION_PRESSURE")
    assert rlp.eligibility_status is EligibilityStatus.BLOCKED
    assert "exposure_denied" in rlp.suppression_reasons
    assert not is_exposable(rlp)


def test_defect_active_without_repair_responsibility(engine: RiskEngine) -> None:
    """수리 책임이 없어도(DENIED) 하자 위험 본체는 유지된다(감수 20차 조건 2).

    임차인도 입주 지연·사용 불편·보수 요청을 겪는다 — repair_responsibility는 본체
    적격성이 아니라 FIN 파생(repair_cost_exposure)의 게이트다(R1 배선).
    """
    no_repair = MobilityContext(target_type="residential_move", stage="moving",
                                exposure_status=ExposureStatus.CONFIRMED,
                                repair_responsibility=False)
    cands = engine.generate(
        _facts(
            gods={TenGod.JIECAI: {LuckLayer.SEWOON},
                  TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGYIN)],
            role=PolarityRole.GI,
        ),
        mobility_contexts=[no_repair],
    )
    dfc = next(c for c in cands if c.risk_id == "MOV_HOUSING_DEFECT_RISK")
    assert is_active(dfc) and is_exposable(dfc)
    assert dfc.exposure_status is ExposureStatus.CONFIRMED  # 본체는 강등 없음


# ── ⑥ 하자·수리 = 별개 현실 문제 ────────────────────────────────


def test_defect_not_auto_absorbed(engine: RiskEngine) -> None:
    """하자·수리는 별개 현실 문제 — 같은 원인이어도 자동 흡수 금지(hint 없음).

    비용 규모=FIN 파생(repair_cost_exposure), 책임 분쟁=LEG 파생(contract_
    responsibility_review) — 같은 cause atom 보존으로 R2가 대표를 결정한다.
    """
    cands = engine.generate(
        _facts(
            gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON},
                  TenGod.JIECAI: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HYEONG, Pillar4.DAY,
                                    target_ten_god=TenGod.ZHENGYIN)],
            void=True, role=PolarityRole.GI,
        ),
        mobility_contexts=[MobilityContext(
            target_type="residential_move", stage="moving",
            exposure_status=ExposureStatus.CONFIRMED, repair_responsibility=True)],
    )
    by_id = {c.risk_id: c for c in cands}
    dfc = by_id["MOV_HOUSING_DEFECT_RISK"]
    assert is_active(dfc)
    assert dfc.suppressed_by_specificity is None
    assert dfc.trigger_cause_atoms  # R2 교차 도메인 연결 키 보존


# ── ⑦ preference는 적격성 미사용(R3 표현 전용) ───────────────────


def test_preference_does_not_change_eligibility(engine: RiskEngine) -> None:
    """preference(desired/undesired)는 적격성·노출 상태를 바꾸지 않는다.

    '원치 않는 이동' 여부는 R3 표현 정책이 preference=undesired 확인 시에만 반영 —
    운 신호·적격성 단계에서 비자발성을 판단하지 않는다.
    """
    facts = _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
                   role=PolarityRole.GI)
    results = []
    for pref in ("desired", "undesired", None):
        ctx = MobilityContext(target_type="residential_move", preference=pref,
                              exposure_status=ExposureStatus.CONFIRMED)
        rlp = next(c for c in engine.generate(facts, mobility_contexts=[ctx])
                   if c.risk_id == "MOV_RELOCATION_PRESSURE")
        results.append((rlp.eligibility_status, rlp.exposure_status,
                        rlp.mobility_alignment, is_exposable(rlp)))
    assert results[0] == results[1] == results[2]
