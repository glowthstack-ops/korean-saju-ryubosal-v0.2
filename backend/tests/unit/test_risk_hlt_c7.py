"""위험 사전 HLT 차수(C7 — 감수 21차) 의미론 fixture.

데굴님 HLT 차수 불변식: 건강 질문이나 명리 신호만으로 질병·치료·신체 부위를
만들어내지 않으며, 기존 질환·치료·신체적 업무 부담이 실제로 확인된 경우에만 해당
맥락의 위험을 설명한다.

고정 범위(§15): ①질환 존재 분리(질문≠질환, DENIED 차단, CONFIRMED 활성) ②치료·회복
(미확인 시 치료 표현 금지) ③신체 부담(직업 존재≠신체 부하) ④health episode 분리
⑤질병명·부위·수술·입원 단정 차단(사전 전수) ⑥신호만으로 질병 incident 미생성
⑦기존 대표 항목 강등·재승격 절차 ⑧같은 건강 episode 수렴.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.risk_engine import (
    HealthContext,
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
    TwelveStage,
)
from saju_shared_types.risk_engine import (
    EligibilityStatus,
    ExposureStatus,
    RiskKind,
    is_active,
    is_exposable,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"

# 커버리지 게이트 연동(test_risk_engine.py) — HLT 승격 시 항목별 양성 fixture 원천.
HLT_POSITIVE_IDS = {
    "HLT_EXISTING_CONDITION_STRAIN",
    "HLT_FATIGUE_ACCUMULATION",
    "HLT_RECOVERY_CAPACITY_WEAK",
    "HLT_FOCUS_DROP",
    "HLT_MOBILITY_SAFETY_CAUTION",
    "HLT_CHECKUP_NEED",
    "HLT_TREATMENT_RECOVERY_LOAD",
    "HLT_PHYSICAL_WORKLOAD_STRAIN",
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
    stage: TwelveStage | None = None,
):
    """테스트용 원시 신호 스냅샷 헬퍼."""
    return build_raw_period_facts(
        period_key=period, layer=LuckLayer.SEWOON,
        ten_god_layers=gods or {}, relations=relations or [],
        void_active=void, polarity_role=role, twelve_stage=stage,
    )


def _active_ids(cands) -> set[str]:
    return {c.risk_id for c in cands if is_active(c)}


_CONDITION_CONFIRMED = HealthContext(
    context_type="existing_condition", condition_status="managed",
    exposure_status=ExposureStatus.CONFIRMED, episode_id="health_1",
)
_TREATMENT_CONFIRMED = HealthContext(
    context_type="treatment_process", treatment_status="ongoing",
    exposure_status=ExposureStatus.CONFIRMED, episode_id="treatment_1",
)
_PHYSICAL_HIGH = HealthContext(
    context_type="physical_workload", physical_demand="high",
    exposure_status=ExposureStatus.CONFIRMED, episode_id="workload_1",
)


def _condition_facts():
    """조정 반복(형+병 운성) + 신체 기둥(일지) 충 — 독립 2원인."""
    return _facts(
        relations=[
            RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
            RelationFact(RelationKind.CHUNG, Pillar4.DAY),
        ],
        role=PolarityRole.GI, stage=TwelveStage.BYEONG,
    )


# ── ① 항목별 양성 recall(승격 게이트 원천) ─────────────────────────

_HLT_POSITIVE_CASES: list[tuple[str, dict, list[HealthContext]]] = [
    ("HLT_EXISTING_CONDITION_STRAIN", dict(
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
                   RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI, stage=TwelveStage.BYEONG,
    ), [_CONDITION_CONFIRMED]),
    # 소모 구조 shape(기신 관살=책임 과다) + 체력 기반(비겁군) 충 — 22차 계약.
    # (년주 사용 — 일·월주 충은 REL·MOV targeted 대표와 겹친다.)
    ("HLT_FATIGUE_ACCUMULATION", dict(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI,
    ), []),
    # 회복 자원(인성군) 공망 구조 약화.
    ("HLT_RECOVERY_CAPACITY_WEAK", dict(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}}, void=True,
        role=PolarityRole.GI,
    ), []),
    # 기신 편인(도식) 구조 약화.
    ("HLT_FOCUS_DROP", dict(
        gods={TenGod.PIANYIN: {LuckLayer.SEWOON}}, role=PolarityRole.GI,
    ), []),
    # 시주(이동) 직접 충 + 차량 노출(MobilityContext 재사용) — 아래 별도 검증.
    ("HLT_CHECKUP_NEED", dict(
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH)],
        role=PolarityRole.GI, stage=TwelveStage.BYEONG,
    ), []),
    # 치료·회복 자원 공망 + 자원 채널 형 피격 + 치료 중 확인.
    ("HLT_TREATMENT_RECOVERY_LOAD", dict(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void=True, role=PolarityRole.GI,
    ), [_TREATMENT_CONFIRMED]),
    # 기신 관살 부담 형태 + 체력 기반 피격 + 신체 부담 확인.
    ("HLT_PHYSICAL_WORKLOAD_STRAIN", dict(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI,
    ), [_PHYSICAL_HIGH]),
]


@pytest.mark.parametrize(("risk_id", "kwargs", "ctxs"), _HLT_POSITIVE_CASES)
def test_hlt_positive_recall(
    engine: RiskEngine, risk_id: str, kwargs: dict, ctxs: list[HealthContext],
) -> None:
    """HLT 항목 전수 — 명확 양성 조합에서 활성 생성(항목별 recall 게이트)."""
    cands = engine.generate(_facts(**kwargs), health_contexts=ctxs)
    assert risk_id in _active_ids(cands)


def test_mobility_safety_positive_without_vehicle(engine: RiskEngine) -> None:
    """대중교통·도보 장거리 이동자 — 차량 사건(MOV)은 차단되고 안전 주의(HLT)만 활성.

    독립적으로 남는 경우의 recall 원천: 차량 없음 확인(vehicle_exposure=False)이라
    MOV_VEHICLE은 BLOCKED, 이동 중 주의력 압박은 유지된다.
    """
    ctx = MobilityContext(target_type="travel_transport",
                          exposure_status=ExposureStatus.CONFIRMED,
                          vehicle_exposure=False)
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR)],
               role=PolarityRole.GI),
        mobility_contexts=[ctx],
    )
    by_id = {c.risk_id: c for c in cands}
    assert by_id["MOV_VEHICLE_TRANSPORT_ISSUE"].eligibility_status \
        is EligibilityStatus.BLOCKED
    msc = by_id["HLT_MOBILITY_SAFETY_CAUTION"]
    assert is_active(msc) and is_exposable(msc)


def test_same_vehicle_episode_mov_primary_hlt_supporting(engine: RiskEngine) -> None:
    """같은 차량 episode·같은 원인 → MOV 차량 사건이 대표, HLT 안전 주의는 보조.

    교차 도메인 수렴(감수 22차) — HLT가 독립 대표로 중복되지 않는다.
    """
    ctx = MobilityContext(target_type="vehicle_use",
                          exposure_status=ExposureStatus.CONFIRMED,
                          vehicle_exposure=True, episode_id="vehicle_1")
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR)],
               role=PolarityRole.GI),
        mobility_contexts=[ctx],
    )
    by_id = {c.risk_id: c for c in cands}
    assert is_active(by_id["MOV_VEHICLE_TRANSPORT_ISSUE"])
    msc = by_id["HLT_MOBILITY_SAFETY_CAUTION"]
    assert msc.suppressed_by_specificity == "MOV_VEHICLE_TRANSPORT_ISSUE"
    assert msc.absorbed_role == "impact_amplifier"


def test_gi_strong_only_no_fatigue(engine: RiskEngine) -> None:
    """GI_STRONG만 존재 → FATIGUE 미활성(길흉 강도는 사건 형태가 아님 — 감수 22차)."""
    cands = engine.generate(_facts(role=PolarityRole.GI_STRONG))
    assert "HLT_FATIGUE_ACCUMULATION" not in {c.risk_id for c in cands}


def test_fatigue_shape_with_gi_strong_amplified(engine: RiskEngine) -> None:
    """소모 shape+체력 피격이 있을 때 GI_STRONG은 강도만 증폭(amplifier 근거)."""
    cands = engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI_STRONG,
    ))
    ftg = next(c for c in cands if c.risk_id == "HLT_FATIGUE_ACCUMULATION")
    assert is_active(ftg)
    from saju_shared_types.risk_engine import EvidenceRole
    assert any(e.role is EvidenceRole.AMPLIFIER and "GI_STRONG" in e.source
               for e in ftg.evidence)


def test_existing_condition_single_cause_watch(engine: RiskEngine) -> None:
    """질환 CONFIRMED + 연결된 targeted 원인 1개 → 후보 활성(watch 상한은 R1).

    2원인 필수 계약 제거(감수 22차) — 생성 조건≠등급 조건 원칙 복원.
    """
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.HYEONG, Pillar4.DAY)],
               role=PolarityRole.GI, stage=TwelveStage.BYEONG),
        health_contexts=[_CONDITION_CONFIRMED],
    )
    ecs = next(c for c in cands if c.risk_id == "HLT_EXISTING_CONDITION_STRAIN")
    assert is_active(ecs) and is_exposable(ecs)
    assert len(ecs.trigger_cause_atoms) >= 1


def test_shift_alone_does_not_activate_physical_strain(engine: RiskEngine) -> None:
    """shift_or_irregular 단독 → 신체 부담 미노출(리듬 패턴≠신체 강도 — 감수 22차)."""
    ctx = HealthContext(context_type="physical_workload",
                        physical_demand="shift_or_irregular",
                        exposure_status=ExposureStatus.CONFIRMED)
    cands = engine.generate(
        _facts(gods={TenGod.QISHA: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR,
                                       target_ten_god=TenGod.BIJIAN)],
               role=PolarityRole.GI),
        health_contexts=[ctx],
    )
    pws = next(c for c in cands if c.risk_id == "HLT_PHYSICAL_WORKLOAD_STRAIN")
    assert is_active(pws)  # 구조 보존
    assert pws.exposure_status is ExposureStatus.UNKNOWN  # 확인 취급 아님
    assert not is_exposable(pws)


def test_treatment_monitoring_not_confirmed(engine: RiskEngine) -> None:
    """monitoring(관찰 중)은 치료 중 단정 금지 — CONFIRMED여도 UNKNOWN 강등."""
    ctx = HealthContext(context_type="treatment_process",
                        treatment_status="monitoring",
                        exposure_status=ExposureStatus.CONFIRMED)
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGYIN)],
               void=True, role=PolarityRole.GI),
        health_contexts=[ctx],
    )
    trl = next(c for c in cands if c.risk_id == "HLT_TREATMENT_RECOVERY_LOAD")
    assert is_active(trl)
    assert trl.exposure_status is ExposureStatus.UNKNOWN
    assert not is_exposable(trl)


# ── ② 질환 존재 분리 — 질문 ≠ 질환 ──────────────────────────────


def test_health_question_does_not_confirm_condition(engine: RiskEngine) -> None:
    """건강 질문이라는 사실이 기존 질환을 자동 확인하지 않는다.

    질환 미확인 → 일반 컨디션 advisory(FATIGUE)는 가능하되, 질환 특정 후보(ECS)는
    구조 보존+비노출("질환이 있다면" 우회도 금지 — unknownExposable=false).
    """
    question = HealthContext(is_question_target=True)  # "건강운?" — 상태 전부 미확인
    cands = engine.generate(
        _facts(
            gods={TenGod.QISHA: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
                       RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                    target_ten_god=TenGod.BIJIAN)],
            role=PolarityRole.GI, stage=TwelveStage.BYEONG,
        ),
        health_contexts=[question],
    )
    by_id = {c.risk_id: c for c in cands}
    ftg = by_id["HLT_FATIGUE_ACCUMULATION"]
    assert is_active(ftg) and is_exposable(ftg)  # 일반 컨디션 advisory 경로
    ecs = by_id["HLT_EXISTING_CONDITION_STRAIN"]
    assert is_active(ecs)  # 구조 보존
    assert ecs.exposure_status is ExposureStatus.UNKNOWN  # 자동 CONFIRMED 금지
    assert not is_exposable(ecs)


def test_condition_denied_blocks_specific(engine: RiskEngine) -> None:
    """기존 질환 없음(none) 명시 → 질환 특정 후보 BLOCKED."""
    none_ctx = HealthContext(context_type="existing_condition",
                             condition_status="none",
                             exposure_status=ExposureStatus.CONFIRMED)
    cands = engine.generate(_condition_facts(), health_contexts=[none_ctx])
    ecs = next(c for c in cands if c.risk_id == "HLT_EXISTING_CONDITION_STRAIN")
    assert ecs.eligibility_status is EligibilityStatus.BLOCKED
    assert "exposure_denied" in ecs.suppression_reasons


def test_condition_confirmed_exposable(engine: RiskEngine) -> None:
    """기존 질환 확인(managed) → 질환 특정 후보 활성·노출 가능."""
    cands = engine.generate(_condition_facts(),
                            health_contexts=[_CONDITION_CONFIRMED])
    ecs = next(c for c in cands if c.risk_id == "HLT_EXISTING_CONDITION_STRAIN")
    assert is_active(ecs) and is_exposable(ecs)
    assert ecs.health_episode_id == "health_1"


# ── ③ 치료·회복 / ④ 신체 부담 ───────────────────────────────────


def test_treatment_unknown_not_exposable(engine: RiskEngine) -> None:
    """치료 중 미확인 → '치료가 늦어진다' 류 표현 금지(비노출, 구조 보존)."""
    ctx = HealthContext(context_type="treatment_process",
                        exposure_status=ExposureStatus.CONFIRMED)  # 상태 미확인
    cands = engine.generate(
        _facts(gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
               relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGYIN)],
               void=True, role=PolarityRole.GI),
        health_contexts=[ctx],
    )
    trl = next(c for c in cands if c.risk_id == "HLT_TREATMENT_RECOVERY_LOAD")
    assert is_active(trl)
    assert trl.exposure_status is ExposureStatus.UNKNOWN  # CONFIRMED 강등
    assert not is_exposable(trl)


def test_physical_demand_axes(engine: RiskEngine) -> None:
    """직업 존재만으로 신체 부하 추론 금지 — 미확인=비노출, low=차단, high=노출."""
    facts = _facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI,
    )
    unknown = HealthContext(context_type="physical_workload",
                            exposure_status=ExposureStatus.CONFIRMED)
    pws = next(c for c in engine.generate(facts, health_contexts=[unknown])
               if c.risk_id == "HLT_PHYSICAL_WORKLOAD_STRAIN")
    assert is_active(pws) and not is_exposable(pws)
    assert pws.exposure_status is ExposureStatus.UNKNOWN

    low = HealthContext(context_type="physical_workload", physical_demand="low",
                        exposure_status=ExposureStatus.CONFIRMED)
    pws2 = next(c for c in engine.generate(facts, health_contexts=[low])
                if c.risk_id == "HLT_PHYSICAL_WORKLOAD_STRAIN")
    assert pws2.eligibility_status is EligibilityStatus.BLOCKED


# ── ⑤ episode 분리 / ⑧ 같은 episode 수렴 ────────────────────────


def test_health_episodes_preserved_independently(engine: RiskEngine) -> None:
    """동일 기간 + health episode 2개 → 후보 독립 보존(질환 관리 vs 치료 회복)."""
    cands = engine.generate(
        _facts(
            gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
            relations=[
                RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                             target_ten_god=TenGod.ZHENGYIN),
                RelationFact(RelationKind.CHUNG, Pillar4.DAY),
            ],
            void=True, role=PolarityRole.GI, stage=TwelveStage.BYEONG,
        ),
        health_contexts=[_CONDITION_CONFIRMED, _TREATMENT_CONFIRMED],
    )
    ecs = next(c for c in cands if c.risk_id == "HLT_EXISTING_CONDITION_STRAIN"
               and c.health_episode_id == "health_1")
    trl = next(c for c in cands if c.risk_id == "HLT_TREATMENT_RECOVERY_LOAD"
               and c.health_episode_id == "treatment_1")
    assert is_active(ecs) and is_active(trl)  # 다른 episode — 상호 흡수 금지


def test_same_episode_fatigue_absorbed_as_supporting(engine: RiskEngine) -> None:
    """같은 건강 episode·같은 원인 → 대표(기존 질환 부담) 아래 피로=supporting."""
    cands = engine.generate(
        _facts(
            gods={TenGod.QISHA: {LuckLayer.SEWOON}},
            relations=[
                RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
                RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                             target_ten_god=TenGod.BIJIAN),
            ],
            role=PolarityRole.GI, stage=TwelveStage.BYEONG,
        ),
        health_contexts=[_CONDITION_CONFIRMED],
    )
    by_id = {c.risk_id: c for c in cands}
    assert is_active(by_id["HLT_EXISTING_CONDITION_STRAIN"])
    ftg = by_id["HLT_FATIGUE_ACCUMULATION"]
    assert ftg.suppressed_by_specificity == "HLT_EXISTING_CONDITION_STRAIN"
    assert ftg.absorbed_role == "supporting_manifestation"


# ── ⑥ 질병·부위 단정 차단(사전 전수) ─────────────────────────────

_FORBIDDEN_HEALTH_TOKENS = (
    "암", "당뇨", "고혈압", "뇌", "심장", "간암", "폐", "수술", "입원", "응급",
    "사망", "골절", "디스크", "우울증",
)


def test_no_disease_or_body_part_claims_in_dictionary() -> None:
    """HLT 사전의 발현·허용 표현에 질병명·수술·입원 토큰이 없다(거짓 구체성 차단)."""
    data = json.loads(
        (_DICTS / "risks" / "health_safety.json").read_text(encoding="utf-8"))
    for item in data["items"]:
        texts = [m["ko"] for m in item["manifestations"]]
        texts += item.get("allowedClaimScope", [])
        for text in texts:
            for token in _FORBIDDEN_HEALTH_TOKENS:
                assert token not in text, (item["riskId"], text, token)


def test_no_health_incident_kind_in_dictionary() -> None:
    """신호만으로 질병 incident를 만들지 않는다 — HLT 전 항목 pressure/vulnerability."""
    data = json.loads(
        (_DICTS / "risks" / "health_safety.json").read_text(encoding="utf-8"))
    assert all(i["kind"] in ("pressure", "vulnerability") for i in data["items"])


def test_signals_only_no_health_incident(engine: RiskEngine) -> None:
    """강한 불리 신호만으로 건강 도메인 활성 incident가 생기지 않는다(런타임)."""
    cands = engine.generate(_facts(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
                   RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        void=True, role=PolarityRole.GI_STRONG, stage=TwelveStage.SA,
    ))
    hlt_active = [c for c in cands
                  if c.risk_id.startswith("HLT_") and is_active(c)]
    assert hlt_active  # 압박·취약 후보는 생성
    assert all(c.kind is not RiskKind.INCIDENT_RISK for c in hlt_active)


# ── ⑦ 기존 대표 항목 강등 상태 ──────────────────────────────────


def test_chronic_flareup_demote_repromote_procedure() -> None:
    """구 HLT_CHRONIC_FLAREUP은 개명 후 강등→재승격 절차를 완료했다(감수 22차 승인).

    재승격 상태 정합: reviewed=true + reviewVersions=C7 + reviewPending 부재
    (reviewed와 reviewPending 동시 존재는 lint 금지 — 절차 가드).
    """
    data = json.loads(
        (_DICTS / "risks" / "health_safety.json").read_text(encoding="utf-8"))
    ids = {i["riskId"] for i in data["items"]}
    assert "HLT_CHRONIC_FLAREUP" not in ids
    ecs = next(i for i in data["items"]
               if i["riskId"] == "HLT_EXISTING_CONDITION_STRAIN")
    assert ecs["reviewed"] is True
    assert ecs["reviewVersions"]["shadow_structure"] == "C7"
    assert "reviewPending" not in ecs
