"""위험 탐지 엔진 R0 단위 테스트 (RISK_ENGINE.md).

원자 후보 생성 규약을 고정한다: 원시 신호 입력, minimum_evidence 게이트(신호 1개 범람
방지), evidence provenance 중복 방지(동일 원인 파생 = 독립 출처 1개), kind 3분류,
exposure 기본 UNKNOWN. 사전은 reviewed:false 초안이므로 점수가 아니라 **생성/차단 여부와
근거 구조**를 고정한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.dictionaries import (
    RiskItem,
    RiskMappingFile,
    RiskRuleSpec,
    _lint_risk_mapping,
    lint_dictionaries,
    schema_for,
    validate_dictionaries,
)
from saju_engines.risk_engine import RelationFact, RiskEngine, build_raw_period_facts
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
    EvidenceRole,
    ExposureStatus,
    RiskDomain,
    RiskKind,
    is_active,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"


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


# ── 사전 검증 (R0-C) ─────────────────────────────────────────────


def test_risks_schema_registered() -> None:
    """risks/<domain>.json 경로가 RiskMappingFile 스키마로 등록돼 있다."""
    assert schema_for("risks/finance.json") is RiskMappingFile


def test_risks_dictionaries_validate_and_lint_clean() -> None:
    """위험 사전 7종이 스키마 검증·lint를 통과한다."""
    errors = validate_dictionaries(_DICTS) + lint_dictionaries(_DICTS)
    risk_errors = [e for e in errors if e.startswith("risks/")]
    assert risk_errors == []


def test_risks_seven_domains_present() -> None:
    """도메인 7종 파일이 모두 존재한다(배선 누락 감지)."""
    names = {p.stem for p in (_DICTS / "risks").glob("*.json")}
    assert names == {
        "finance", "career", "contract_legal", "health_safety",
        "relationship", "relocation", "selection",
    }


def test_lint_rejects_incident_with_single_source() -> None:
    """incident_risk인데 독립 출처 1개 요구는 lint가 거부한다(범람 방지 정책)."""
    file = RiskMappingFile.model_validate({
        "version": "0.0.1", "domain": "finance",
        "items": [{
            "riskId": "FIN_TEST_ONE",
            "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
            "triggerRules": [{"id": "T1", "tenGod": "JIECAI"}],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": False,
        }],
    })
    assert any("독립 출처 2개" in e for e in _lint_risk_mapping("risks/finance.json", file))


def test_schema_rejects_unconditional_rule() -> None:
    """조건 없는 위험 룰은 스키마가 거부한다."""
    with pytest.raises(ValueError, match="무조건 룰 금지"):
        RiskMappingFile.model_validate({
            "version": "0.0.1", "domain": "finance",
            "items": [{
                "riskId": "FIN_TEST_TWO",
                "domain": "finance", "kind": "pressure", "baseImpact": 0.3,
                "triggerRules": [{"id": "T1", "strength": 0.5}],
                "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
                "manifestations": [{"id": "m1", "ko": "테스트"}],
                "reviewed": False,
            }],
        })


# ── 원자 후보 생성 (R0-D) ─────────────────────────────────────────


def test_no_adverse_signals_no_candidates(engine: RiskEngine) -> None:
    """불리 신호가 전혀 없으면(용신운·무관계·무공망) 위험 후보를 만들지 않는다."""
    facts = _facts(gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}}, role=PolarityRole.YONG)
    assert engine.generate(facts) == []


def _active(cands):
    """활성 후보만(is_active) — 관측(insufficient)·차단·특이도 흡수 제외."""
    return [c for c in cands if is_active(c)]


def test_pressure_only_without_incident(engine: RiskEngine) -> None:
    """압박 신호만 있으면 활성 후보는 pressure뿐 — 사건 위험은 증거 계약에서 걸러진다."""
    facts = _facts(gods={TenGod.QISHA: {LuckLayer.SEWOON}}, role=PolarityRole.GI)
    active = _active(engine.generate(facts))
    assert active, "관살 기신 압박은 pressure 후보를 만든다"
    assert all(c.kind is RiskKind.PRESSURE for c in active)
    assert any(c.risk_id == "CAR_WORK_OVERLOAD" for c in active)


def test_single_trigger_blocks_incident(engine: RiskEngine) -> None:
    """겁재 기신 단독으로는 FIN 사건·압박 모두 생성되지 않는다(C1 — 재정 구조 필수).

    사건 위험은 형태·대상 근거 부재로, 현금흐름 압박도 재성 유입·유출 구조 activation이
    없어 미관측이다(재성 기신 양성은 test_risk_fin_c1의 CFP 케이스가 고정).
    """
    facts = _facts(gods={TenGod.JIECAI: {LuckLayer.SEWOON}}, role=PolarityRole.GI)
    ids = {c.risk_id for c in engine.generate(facts)}
    assert "FIN_UNEXPECTED_EXPENSE" not in ids  # 관측조차 없음
    assert "FIN_CASHFLOW_PRESSURE" not in ids  # 범용 기신+겁재만으로 압박도 미생성


def test_two_independent_sources_create_incident(engine: RiskEngine) -> None:
    """사건 형태(겁재-재성 동반) + 대상 활성(재성 피격)이면 사건 위험이 생성된다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(
            RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI,
        )],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in _active(engine.generate(facts))}
    assert "FIN_UNEXPECTED_EXPENSE" in cands
    c = cands["FIN_UNEXPECTED_EXPENSE"]
    triggers = [e for e in c.evidence if e.role is EvidenceRole.TRIGGER]
    assert len({e.source for e in triggers}) >= 2
    assert {e.source_group for e in triggers} >= {"event_shape", "targeted_event_shape"}
    assert c.domain is RiskDomain.FINANCE
    assert c.score_components is None and c.confidence == 0.0  # R0 미산출 계약
    assert c.exposure_status is ExposureStatus.UNKNOWN  # 기본 — 숫자 대체 금지
    assert c.manifestation_ids  # 발현 형태 제공(노출 미확인 시 조건부 제시 원천)


def test_mitigator_attached_without_deleting_candidate(engine: RiskEngine) -> None:
    """보호 신호(합)는 후보를 삭제하지 않고 mitigator 근거로 동반 보존된다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
            RelationFact(RelationKind.HAP, Pillar4.MONTH),
        ],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in _active(engine.generate(facts))}
    assert "FIN_UNEXPECTED_EXPENSE" in cands  # 보호 신호가 있어도 위험은 남는다
    c = cands["FIN_UNEXPECTED_EXPENSE"]
    assert EvidenceRole.MITIGATOR in {e.role for e in c.evidence}
    assert c.eligibility_status is EligibilityStatus.MITIGATED  # 유지 + 상태 표시


def test_same_cause_counts_once(engine: RiskEngine) -> None:
    """같은 원인 사실을 두 룰이 잡아도 독립 출처 1개로 계산돼 생성이 차단된다."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_DUP",
        "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
        "triggerRules": [
            {"id": "T_GOD", "tenGod": "JIECAI", "strength": 0.5},
            {"id": "T_GROUP", "tenGodGroup": "peer", "strength": 0.5},
        ],
        "minimumEvidence": {"triggerCount": 2, "independentSourceCount": 2},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    # 겁재 1글자 — 십성 룰과 그룹 룰이 같은 원인(ten_god:JIECAI)을 잡는다 → 출처 1개.
    facts = _facts(gods={TenGod.JIECAI: {LuckLayer.SEWOON}})
    cands = solo.generate(facts)
    assert len(cands) == 1  # 관측은 남되(INSUFFICIENT) 활성 아님
    assert cands[0].eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert not is_active(cands[0])


def test_blocker_evidence_preserved(engine: RiskEngine) -> None:
    """blocker는 후보 기록을 삭제하지 않되 BLOCKED 상태로 분리한다(활성 집계 제외 가능)."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_BLK",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [{"id": "T1", "tenGod": "JIECAI", "strength": 0.5}],
        "blockerRules": [{"id": "B1", "relation": "HAP", "strength": 0.5}],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAP, Pillar4.MONTH)],
    )
    cands = solo.generate(facts)
    assert len(cands) == 1
    assert {e.role for e in cands[0].evidence} == {EvidenceRole.TRIGGER, EvidenceRole.BLOCKER}
    assert cands[0].eligibility_status is EligibilityStatus.BLOCKED
    assert cands[0].suppression_reasons == ["B1"]


def test_required_groups_gate() -> None:
    """requiredGroups — '약한 범용 신호 2개'는 차단, '사건 형태+대상 활성'만 생성한다."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_GRP",
        "domain": "finance", "kind": "incident_risk", "baseImpact": 0.6,
        "triggerRules": [
            # 사건 형태: 겁재-재성 동반(탈재 구조).
            {"id": "T_SHAPE", "group": "event_shape", "tenGod": "JIECAI",
             "tenGodGroup": "wealth", "strength": 0.6},
            # 대상 활성: 재성이 충의 직접 대상.
            {"id": "T_TARGET", "group": "target_activation", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.55},
            # 범용(증폭 성격) 신호 — 필수 그룹을 채우지 못한다.
            {"id": "T_GENERIC", "group": "generic",
             "polarityRoleIn": ["GI", "GI_STRONG"], "strength": 0.4},
        ],
        "minimumEvidence": {
            "triggerCount": 2, "independentSourceCount": 2,
            "requiredGroups": ["event_shape", "target_activation"],
        },
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    # 범용 신호(극성 GI)만 매칭: 필수 그룹 미충족 → INSUFFICIENT_EVIDENCE(활성 아님).
    weak = _facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )
    weak_cands = solo.generate(weak)
    assert len(weak_cands) == 1
    assert weak_cands[0].eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert "evidence_groups_unmet" in weak_cands[0].suppression_reasons
    # 사건 형태(겁재+재성) + 대상 활성(재성 충) → 활성 생성.
    strong = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    cands = _active(solo.generate(strong))
    assert [c.risk_id for c in cands] == ["FIN_TEST_GRP"]
    groups = {e.source_group for e in cands[0].evidence if e.role is EvidenceRole.TRIGGER}
    assert {"event_shape", "target_activation"} <= groups


def test_relation_target_filter() -> None:
    """관계 대상 조건 — 같은 충이라도 피자극 십성이 다르면 매칭되지 않는다."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_TGT",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [
            {"id": "T1", "group": "target_activation", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    wealth_hit = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
    ])
    other_hit = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGGUAN),
    ])
    assert [c.risk_id for c in solo.generate(wealth_hit)] == ["FIN_TEST_TGT"]
    assert solo.generate(other_hit) == []  # 대상 불일치 — 룰 자체 미매칭(관측 없음)


def test_same_clash_generic_and_targeted_rule_share_source() -> None:
    """같은 충을 일반 룰과 대상 룰이 잡아도 원인 서명이 같아 독립 출처 1개다."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_SIG",
        "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
        "triggerRules": [
            {"id": "T_ANY", "relation": "CHUNG", "strength": 0.5},
            {"id": "T_TGT", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},
        ],
        "minimumEvidence": {"triggerCount": 2, "independentSourceCount": 2},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    facts = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
    ])
    # 두 룰 모두 매칭되지만 동일 원인(같은 충) → 출처 1개 → 활성 불가(INSUFFICIENT).
    cands = solo.generate(facts)
    assert len(cands) == 1
    assert cands[0].eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    assert "independent_causes_unmet" in cands[0].suppression_reasons


def test_schema_rejects_polarity_only_event_shape() -> None:
    """감수 원칙 — 극성(기신)만으로 구성된 룰은 event_shape 그룹이 될 수 없다."""
    with pytest.raises(ValueError, match="증폭·취약 신호"):
        RiskItem.model_validate({
            "riskId": "FIN_TEST_POL",
            "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
            "triggerRules": [
                {"id": "T1", "group": "event_shape",
                 "polarityRoleIn": ["GI"], "strength": 0.5},
            ],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": False,
        })


def test_lint_reviewed_incident_requires_groups() -> None:
    """감수 승격(reviewed:true) incident_risk는 requiredGroups 필수(lint 게이트)."""
    file = RiskMappingFile.model_validate({
        "version": "0.0.1", "domain": "finance",
        "items": [{
            "riskId": "FIN_TEST_RG",
            "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
            "triggerRules": [
                {"id": "T1", "group": "event_shape", "tenGod": "JIECAI"},
                {"id": "T2", "group": "target_activation", "relation": "CHUNG",
                 "relationTargetTenGodGroup": "wealth"},
            ],
            "minimumEvidence": {"triggerCount": 2, "independentSourceCount": 2},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": True,
        }],
    })
    errors = _lint_risk_mapping("risks/finance.json", file)
    assert any("targeted_event_shape 증거 계약 필수" in e for e in errors)


def test_exposure_status_passthrough(engine: RiskEngine) -> None:
    """호출부가 넘긴 노출 상태(DENIED 등)가 후보에 그대로 실린다."""
    facts = _facts(gods={TenGod.QISHA: {LuckLayer.SEWOON}}, role=PolarityRole.GI)
    cands = engine.generate(facts, exposure_status=ExposureStatus.DENIED)
    assert cands and all(c.exposure_status is ExposureStatus.DENIED for c in cands)


# ── 7도메인 synthetic fixture — 사전 배선 누락 감지 (개정 증거 계약 기준) ──

_DOMAIN_CASES: list[tuple[str, dict]] = [
    # 사건 형태(겁재-재성 동반) + 재성 피격(targeted).
    ("FIN_UNEXPECTED_EXPENSE", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )),
    # 상관견관(event_shape) + 관성 피격(targeted).
    ("CAR_ORG_CONFLICT", dict(
        gods={TenGod.SHANGGUAN: {LuckLayer.SEWOON}, TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )),
    # 형+편관 동반(event_shape) + 관성 피격 형(targeted).
    ("LEG_PENALTY_LIABILITY", dict(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH,
                                target_ten_god=TenGod.QISHA)],
        role=PolarityRole.GI,
    )),
    # 형+병사 운성(event_shape) AND 일지 충(target_activation) — 독립 원인 2개.
    ("HLT_CHRONIC_FLAREUP", dict(
        relations=[
            RelationFact(RelationKind.CHUNG, Pillar4.DAY),
            RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
        ],
        role=PolarityRole.GI, stage=TwelveStage.BYEONG,
    )),
    # 배우자궁(일지) 직접 충 — targeted 단독 경로(독립 1원인 허용, R1 등급 watch 상한).
    ("REL_PARTNER_READJUST", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI,
    )),
    # 문서 공망(event_shape) + 주거궁 활성(target_activation).
    ("MOV_CONTRACT_FAIL", dict(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        void=True, role=PolarityRole.GI,
    )),
    # 충+관성 동반(event_shape) + 사회궁 활성 — 관성 피격이면 targeted도 성립.
    ("SEL_UNWANTED_PLACEMENT", dict(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )),
]


@pytest.mark.parametrize(("risk_id", "kwargs"), _DOMAIN_CASES)
def test_each_domain_generates(engine: RiskEngine, risk_id: str, kwargs: dict) -> None:
    """도메인별 대표 사건 위험이 증거 계약 충족 조합에서 활성 생성된다(7도메인 전수)."""
    ids = {c.risk_id for c in _active(engine.generate(_facts(**kwargs)))}
    assert risk_id in ids


# ── 적대적 fixture (2026-07-15 감수 2차 — 커밋 B 요구 케이스) ──────


def test_generic_gisin_only_no_incident(engine: RiskEngine) -> None:
    """generic 기신(GI_STRONG)만 있는 경우 — 활성 incident가 하나도 없어야 한다."""
    facts = _facts(role=PolarityRole.GI_STRONG)
    active = _active(engine.generate(facts))
    assert all(c.kind is not RiskKind.INCIDENT_RISK for c in active)


def test_specific_absorbs_generic_same_cause(engine: RiskEngine) -> None:
    """동일 원인·동일 family에서 구체 위험이 일반 후보를 흡수한다(특이도 우선).

    재성 피격 + 겁재-재성 동반 → FIN_UNEXPECTED_EXPENSE(3)가 대표,
    FIN_CASHFLOW_PRESSURE(0, 같은 cashflow family·같은 원인)는 흡수돼 활성 제외.
    """
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in engine.generate(facts)}
    assert is_active(cands["FIN_UNEXPECTED_EXPENSE"])
    cfp = cands["FIN_CASHFLOW_PRESSURE"]
    assert cfp.suppressed_by_specificity == "FIN_UNEXPECTED_EXPENSE"
    assert cfp.primary_risk_id == "FIN_UNEXPECTED_EXPENSE"
    assert not is_active(cfp)  # 기록은 보존(부가 설명용), 활성 집계 제외


def test_partner_readjust_absorbs_emotional_clash(engine: RiskEngine) -> None:
    """배우자궁 충 공유 시 관계 재조정(3)이 감정 충돌(기본 2)을 흡수한다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in engine.generate(facts)}
    assert is_active(cands["REL_PARTNER_READJUST"])
    if "REL_EMOTIONAL_CLASH" in cands and cands["REL_EMOTIONAL_CLASH"].eligibility_status \
            in (EligibilityStatus.ELIGIBLE, EligibilityStatus.MITIGATED):
        assert cands["REL_EMOTIONAL_CLASH"].suppressed_by_specificity == (
            "REL_PARTNER_READJUST"
        )


def test_exposure_denied_hard_blocks(engine: RiskEngine) -> None:
    """노출 DENIED는 hard blocker — 후보는 보존되되 BLOCKED로 활성 집계에서 빠진다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in engine.generate(
        facts, exposure_status=ExposureStatus.DENIED,
    )}
    c = cands["FIN_UNEXPECTED_EXPENSE"]
    assert c.eligibility_status is EligibilityStatus.BLOCKED
    assert "exposure_denied" in c.suppression_reasons
    assert not is_active(c)


def test_evidence_contract_targeted_single_cause() -> None:
    """targeted_event_shape 단독 절 — 한 사실이 형태+대상을 겸해도 독립 원인은 1개."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_TES",
        "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
        "triggerRules": [
            # 구조 동반(겁재) + 대상(재성) — targeted_event_shape 성립 조건.
            {"id": "T1", "group": "targeted_event_shape", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "tenGod": "JIECAI", "strength": 0.6},
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "evidenceContract": {
            "anyOf": [{"allOfGroups": ["targeted_event_shape"]}],
            "minIndependentCauses": 1,
        },
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
    )
    cands = _active(solo.generate(facts))
    assert [c.risk_id for c in cands] == ["FIN_TEST_TES"]
    triggers = [e for e in cands[0].evidence if e.role is EvidenceRole.TRIGGER]
    assert len({e.source for e in triggers}) == 1  # 독립 원인 1개(부풀림 없음)


def test_schema_rejects_target_only_targeted_event_shape() -> None:
    """대상만 특정된 일반 관계는 targeted_event_shape가 될 수 없다(감수 3차).

    관계+십성(군) 대상만으로는 부족 — 궁위 지정 또는 사건 구조 십성 동반이 필요하다.
    """
    with pytest.raises(ValueError, match="target_activation"):
        RiskItem.model_validate({
            "riskId": "FIN_TEST_TRO",
            "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
            "triggerRules": [
                {"id": "T1", "group": "targeted_event_shape", "relation": "CHUNG",
                 "relationTargetTenGodGroup": "wealth", "strength": 0.5},
            ],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": False,
        })


def test_no_fallback_when_specific_provenance_mismatch() -> None:
    """구체 provenance(궁위) 불일치 시 하위 일반화 축(십성군)이 룰을 구제하지 못한다.

    사실: 월지 사회궁의 재성 피격 / 룰: 일지 배우자궁 피격(+재성군) → 궁위 불일치로
    미매칭. 궁위 무관 매칭을 원하면 룰 자체가 궁위 조건 없는 일반 룰이어야 한다.
    """
    strict = RiskItem.model_validate({
        "riskId": "FIN_TEST_NF1",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [
            {"id": "T1", "group": "target_activation", "relation": "CHUNG",
             "relationPalace": "day_pillar",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    general = RiskItem.model_validate({
        "riskId": "FIN_TEST_NF2",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [
            {"id": "T1", "group": "target_activation", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},  # 궁위 무관 명시
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [strict, general]
    month_wealth_hit = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.MONTH, target_ten_god=TenGod.ZHENGCAI),
    ])
    ids = {c.risk_id for c in solo.generate(month_wealth_hit)}
    assert "FIN_TEST_NF1" not in ids  # 궁위 불일치 — 십성군 동일로 구제 불가
    assert "FIN_TEST_NF2" in ids  # 일반 룰만 매칭


def test_polarity_only_mitigator_does_not_flip_status() -> None:
    """극성 단독(용신 강함) mitigator는 전역 완화 금지 — 근거만 보존, 상태는 ELIGIBLE."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_PMG",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [{"id": "T1", "tenGod": "JIECAI", "strength": 0.5}],
        "mitigatorRules": [
            {"id": "M_POL", "polarityRoleIn": ["YONG_STRONG"], "strength": 0.6},
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    facts = _facts(gods={TenGod.JIECAI: {LuckLayer.SEWOON}}, role=PolarityRole.YONG_STRONG)
    cands = solo.generate(facts)
    assert len(cands) == 1
    assert EvidenceRole.MITIGATOR in {e.role for e in cands[0].evidence}  # 근거 보존
    assert cands[0].eligibility_status is EligibilityStatus.ELIGIBLE  # 상태 완화 없음
    # 실질 조건(합 — 원인 완화 표현) 동반이면 완화된다.
    item2 = item.model_copy(update={"mitigator_rules": [
        *item.mitigator_rules,
        RiskRuleSpec.model_validate({"id": "M_HAP", "relation": "HAP", "strength": 0.3}),
    ]})
    solo._items = [item2]
    facts2 = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAP, Pillar4.MONTH)],
        role=PolarityRole.YONG_STRONG,
    )
    assert solo.generate(facts2)[0].eligibility_status is EligibilityStatus.MITIGATED


def test_absorbed_candidate_keeps_role_and_evidence(engine: RiskEngine) -> None:
    """흡수는 삭제가 아니라 역할 전환 — 근거·역할(absorbed_role)이 보존된다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in engine.generate(facts)}
    cfp = cands["FIN_CASHFLOW_PRESSURE"]
    assert cfp.absorbed_role == "impact_amplifier"  # 압박 = 대표 사건의 예상 영향
    assert cfp.evidence, "흡수 후보의 근거는 R1 impact/exposure 계산용으로 보존"


def test_cause_atoms_normalization() -> None:
    """cause_atom 정규화 — 관계·대상·기간별 분리와 결정성(순서 무관)을 고정한다."""
    from saju_engines.risk_engine import cause_atoms

    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_ATM",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [
            {"id": "T1", "group": "target_activation", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},
        ],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]

    def _src(facts):
        cands = solo.generate(facts)
        return cands[0].evidence[0].source if cands else None

    base = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
    ])
    # 같은 관계+같은 대상 → 같은 원인 서명(반복 호출 결정성).
    assert _src(base) == _src(base)
    # 같은 관계+다른 대상(편재) → 다른 원인 서명.
    other_target = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.PIANCAI),
    ])
    assert _src(base) != _src(other_target)
    # 같은 대상+다른 기간 → evidence_id가 다르다(기간 접두).
    later = _facts(period="2027", relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
    ])
    c1 = solo.generate(base)[0].evidence[0]
    c2 = solo.generate(later)[0].evidence[0]
    assert c1.source == c2.source and c1.evidence_id != c2.evidence_id
    # 원자 분해 — 복합 서명은 & 로 나뉜다.
    assert cause_atoms("relation:CHUNG:day_pillar:ZHENGCAI&polarity:GI") == {
        "relation:CHUNG:day_pillar:ZHENGCAI", "polarity:GI",
    }
    # 다중 매칭 십성의 서명은 정렬돼 입력 순서와 무관하다.
    grp = RiskItem.model_validate({
        "riskId": "FIN_TEST_ORD",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [{"id": "T1", "tenGodGroup": "wealth", "strength": 0.5}],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo._items = [grp]
    ab = _facts(gods={TenGod.ZHENGCAI: {LuckLayer.SEWOON}, TenGod.PIANCAI: {LuckLayer.SEWOON}})
    ba = _facts(gods={TenGod.PIANCAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}})
    assert _src(ab) == _src(ba) == "ten_god:PIANCAI+ZHENGCAI"


def test_lint_health_reviewed_requires_claim_policy() -> None:
    """감수 승격 건강 incident는 claimCeiling·allowedClaimScope 필수(lint)."""
    file = RiskMappingFile.model_validate({
        "version": "0.0.1", "domain": "health_safety",
        "items": [{
            "riskId": "HLT_TEST_CP",
            "domain": "health_safety", "kind": "incident_risk", "baseImpact": 0.5,
            "triggerRules": [
                {"id": "T1", "group": "event_shape", "relation": "HYEONG",
                 "twelveStageIn": ["BYEONG"]},
                {"id": "T2", "group": "target_activation", "relation": "CHUNG",
                 "relationPalace": "day_pillar"},
            ],
            "minimumEvidence": {
                "triggerCount": 2, "independentSourceCount": 2,
                "requiredGroups": ["event_shape", "target_activation"],
            },
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": True,
        }],
    })
    errors = _lint_risk_mapping("risks/health_safety.json", file)
    assert any("claimCeiling·allowedClaimScope 필수" in e for e in errors)


def test_schema_multi_cause_requires_explicit_policy() -> None:
    """독립 원인 ≥2 강제는 예외 정책 — candidatePolicy·rationale 없으면 스키마 거부.

    후보 생성 조건과 높은 경고 등급 조건의 분리(감수 4차): 구조 충족 + 독립 1원인도
    후보는 생성돼야 하며(R1 watch 상한), 다원인 강제는 위험별 명시 정책만 허용.
    """
    with pytest.raises(ValueError, match="multi_cause_only"):
        RiskItem.model_validate({
            "riskId": "FIN_TEST_MCP",
            "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
            "triggerRules": [
                {"id": "T1", "group": "event_shape", "tenGod": "JIECAI"},
                {"id": "T2", "group": "target_activation", "relation": "CHUNG",
                 "relationTargetTenGodGroup": "wealth"},
            ],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "evidenceContract": {
                "anyOf": [{"allOfGroups": ["event_shape", "target_activation"]}],
                "minIndependentCauses": 2,  # 정책 명시 없음 → 거부
            },
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": False,
        })


def test_lint_reviewed_requires_review_scope() -> None:
    """reviewed:true는 reviewScope 필수 — 사용자 노출 승인과의 혼동 차단(감수 4차)."""
    file = RiskMappingFile.model_validate({
        "version": "0.0.1", "domain": "finance",
        "items": [{
            "riskId": "FIN_TEST_RS",
            "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
            "triggerRules": [{"id": "T1", "group": "activation", "tenGod": "JIECAI"}],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": True,
        }],
    })
    errors = _lint_risk_mapping("risks/finance.json", file)
    assert any("reviewScopes 명시 필수" in e for e in errors)


def test_lint_rule_change_invalidates_review() -> None:
    """감수 무효화 — reviewed:true 항목의 룰을 고치면 해시 불일치로 lint가 실패한다."""
    base = {
        "riskId": "FIN_TEST_HSH",
        "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
        "triggerRules": [{"id": "T1", "group": "activation", "tenGod": "JIECAI"}],
        "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": True,
        "reviewScopes": ["shadow_structure"],
        "reviewVersions": {"shadow_structure": "R0.5"},
    }
    from saju_engines.dictionaries import risk_scope_hash
    stamped = RiskItem.model_validate(base)
    base["reviewHashes"] = {
        "shadow_structure": risk_scope_hash(stamped, "shadow_structure"),
    }
    ok_file = RiskMappingFile.model_validate(
        {"version": "0.0.1", "domain": "finance", "items": [base]},
    )
    assert not any(
        "해시 불일치" in e for e in _lint_risk_mapping("risks/finance.json", ok_file)
    )
    # 감수 후 룰 본문 변경(강도 수정) → 해시 불일치.
    changed = dict(base)
    changed["triggerRules"] = [
        {"id": "T1", "group": "activation", "tenGod": "JIECAI", "strength": 0.9},
    ]
    bad_file = RiskMappingFile.model_validate(
        {"version": "0.0.1", "domain": "finance", "items": [changed]},
    )
    assert any(
        "해시 불일치" in e for e in _lint_risk_mapping("risks/finance.json", bad_file)
    )


def test_schema_rejects_weak_relation_targeted() -> None:
    """파·해는 약한 신호 — 대상 특정만으로 targeted_event_shape가 되지 못한다
    (target_activation로 저작 — 단독 발화 불가, 충·형과 동일 강도 기계 적용 금지)."""
    with pytest.raises(ValueError, match="충·형만"):
        RiskItem.model_validate({
            "riskId": "FIN_TEST_PAW",
            "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
            "triggerRules": [
                {"id": "T1", "group": "targeted_event_shape", "relation": "PA",
                 "relationTargetTenGodGroup": "wealth", "tenGod": "JIECAI",
                 "strength": 0.5},
            ],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": False,
        })


def test_every_reviewed_item_has_positive_fixture(engine: RiskEngine) -> None:
    """reviewed:true 항목별 양성 fixture 필수 — 항목 단위 recall 100% 게이트.

    전체 평균이 아니라 reviewed risk_id마다 명확 양성 케이스가 존재해야 한다
    (_DOMAIN_CASES가 그 원천 — 여기서 누락을 강제 검출한다).
    """
    import json as _json
    reviewed_ids = set()
    for path in sorted((_DICTS / "risks").glob("*.json")):
        data = _json.loads(path.read_text(encoding="utf-8"))
        reviewed_ids |= {i["riskId"] for i in data["items"] if i.get("reviewed")}
    from tests.unit.test_risk_fin_c1 import FIN_POSITIVE_IDS

    covered = {rid for rid, _ in _DOMAIN_CASES} | FIN_POSITIVE_IDS
    assert reviewed_ids <= covered, (
        f"양성 fixture 없는 reviewed 항목: {sorted(reviewed_ids - covered)}"
    )


def test_schema_rejects_hap_targeted_event_shape() -> None:
    """우호 결합(HAP)은 targeted_event_shape가 될 수 없다 — 관계 유형 allowlist."""
    with pytest.raises(ValueError, match="충·형만"):
        RiskItem.model_validate({
            "riskId": "REL_TEST_HAP",
            "domain": "relationship", "kind": "pressure", "baseImpact": 0.4,
            "triggerRules": [
                {"id": "T1", "group": "targeted_event_shape", "relation": "HAP",
                 "relationPalace": "day_pillar", "strength": 0.5},
            ],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "테스트"}],
            "reviewed": False,
        })


def test_layer_repeat_same_cause_but_different_kind_splits() -> None:
    """다층 중첩 cause 계산 — 같은 관계·같은 대상 반복은 원인 1개(중첩은 강도 증가
    소관·R1 layer_convergence), 다른 관계 유형(충 vs 형)이 같은 대상을 치면 원인 2개."""
    item = RiskItem.model_validate({
        "riskId": "FIN_TEST_LYR",
        "domain": "finance", "kind": "incident_risk", "baseImpact": 0.5,
        "triggerRules": [
            {"id": "T_C", "group": "target_activation", "relation": "CHUNG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},
            {"id": "T_H", "group": "target_activation", "relation": "HYEONG",
             "relationTargetTenGodGroup": "wealth", "strength": 0.5},
        ],
        "minimumEvidence": {"triggerCount": 2, "independentSourceCount": 2},
        "manifestations": [{"id": "m1", "ko": "테스트"}],
        "reviewed": False,
    })
    solo = RiskEngine(_DICTS)
    solo._items = [item]
    # 같은 충이 여러 발동으로 반복(계층 중첩의 스냅샷 표현) — 서명 집계로 원인 1개.
    repeat = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
    ])
    cands = solo.generate(repeat)
    assert len(cands) == 1
    assert cands[0].eligibility_status is EligibilityStatus.INSUFFICIENT_EVIDENCE
    # 충 + 형이 같은 대상 — 서로 다른 원인 원자 → 독립 2원인 성립.
    mixed = _facts(relations=[
        RelationFact(RelationKind.CHUNG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
        RelationFact(RelationKind.HYEONG, Pillar4.DAY, target_ten_god=TenGod.ZHENGCAI),
    ])
    active = _active(solo.generate(mixed))
    assert [c.risk_id for c in active] == ["FIN_TEST_LYR"]


def test_single_cause_targeted_candidate_survives(engine: RiskEngine) -> None:
    """단일 원인 생존율 — targeted 경로 충족 시 독립 1원인도 활성 후보로 살아남는다
    (등급 watch 상한은 R1 — 후보 생성 단계에서 죽이지 않는다)."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    active_ids = {c.risk_id for c in _active(engine.generate(facts))}
    assert "FIN_UNEXPECTED_EXPENSE" in active_ids  # 겁재 동반 재성 피격(targeted) 단독


def test_relation_without_target_not_observed(engine: RiskEngine) -> None:
    """유사 음성 — 관계는 있으나 대상 정보가 없으면 대상 요구 사건은 관측되지 않는다."""
    facts = _facts(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],  # 피자극 십성 미상
        role=PolarityRole.GI,
    )
    ids = {c.risk_id for c in engine.generate(facts)}
    assert "FIN_UNEXPECTED_EXPENSE" not in ids


def test_lint_manifestation_prohibited_conflict() -> None:
    """manifestation 문구가 prohibitedClaims와 충돌하면 lint가 거부한다."""
    file = RiskMappingFile.model_validate({
        "version": "0.0.1", "domain": "finance",
        "items": [{
            "riskId": "FIN_TEST_MPC",
            "domain": "finance", "kind": "pressure", "baseImpact": 0.4,
            "triggerRules": [{"id": "T1", "tenGod": "JIECAI"}],
            "minimumEvidence": {"triggerCount": 1, "independentSourceCount": 1},
            "manifestations": [{"id": "m1", "ko": "파산 단정 수준의 손실"}],
            "prohibitedClaims": ["파산 단정"],
            "reviewed": False,
        }],
    })
    errors = _lint_risk_mapping("risks/finance.json", file)
    assert any("prohibitedClaims와 충돌" in e for e in errors)
