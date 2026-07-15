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


def test_pressure_only_without_incident(engine: RiskEngine) -> None:
    """압박 신호만 있으면 pressure 후보만 생성되고 사건 위험(incident)은 차단된다."""
    facts = _facts(gods={TenGod.QISHA: {LuckLayer.SEWOON}}, role=PolarityRole.GI)
    cands = engine.generate(facts)
    assert cands, "관살 기신 압박은 pressure 후보를 만든다"
    assert all(c.kind is RiskKind.PRESSURE for c in cands)
    assert any(c.risk_id == "CAR_WORK_OVERLOAD" for c in cands)


def test_single_trigger_blocks_incident(engine: RiskEngine) -> None:
    """사건 위험은 trigger 1개(독립 출처 1개)만으로는 생성이 차단된다."""
    facts = _facts(gods={TenGod.JIECAI: {LuckLayer.SEWOON}}, role=PolarityRole.GI)
    ids = {c.risk_id for c in engine.generate(facts)}
    assert "FIN_UNEXPECTED_EXPENSE" not in ids  # incident — 출처 1개라 차단
    assert "FIN_CASHFLOW_PRESSURE" in ids  # pressure — 1개 허용


def test_two_independent_sources_create_incident(engine: RiskEngine) -> None:
    """서로 독립된 신호 2개(겁재 기신 + 충 발동)면 사건 위험 후보가 생성된다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in engine.generate(facts)}
    assert "FIN_UNEXPECTED_EXPENSE" in cands
    c = cands["FIN_UNEXPECTED_EXPENSE"]
    triggers = [e for e in c.evidence if e.role is EvidenceRole.TRIGGER]
    assert len({e.source for e in triggers}) >= 2
    assert c.domain is RiskDomain.FINANCE
    assert c.score_components is None and c.confidence == 0.0  # R0 미산출 계약
    assert c.exposure_status is ExposureStatus.UNKNOWN  # 기본 — 숫자 대체 금지
    assert c.manifestation_ids  # 발현 형태 제공(노출 미확인 시 조건부 제시 원천)


def test_mitigator_attached_without_deleting_candidate(engine: RiskEngine) -> None:
    """보호 신호(합)는 후보를 삭제하지 않고 mitigator 근거로 동반 보존된다."""
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.CHUNG, Pillar4.DAY),
            RelationFact(RelationKind.HAP, Pillar4.MONTH),
        ],
        role=PolarityRole.GI,
    )
    cands = {c.risk_id: c for c in engine.generate(facts)}
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
    assert solo.generate(facts) == []


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
    # 범용 신호 2개(겁재-재성 동반 없음·대상 충 없음): 극성 GI + 무관 충 → 차단.
    weak = _facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGGUAN)],
        role=PolarityRole.GI,
    )
    assert solo.generate(weak) == []
    # 사건 형태(겁재+재성) + 대상 활성(재성 충) → 생성.
    strong = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    )
    cands = solo.generate(strong)
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
    assert solo.generate(other_hit) == []


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
    # 두 룰 모두 매칭되지만 동일 원인(같은 충) → 출처 1개 → 생성 차단.
    assert solo.generate(facts) == []


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
    assert any("event_shape·target_activation 필수" in e for e in errors)


def test_exposure_status_passthrough(engine: RiskEngine) -> None:
    """호출부가 넘긴 노출 상태(DENIED 등)가 후보에 그대로 실린다."""
    facts = _facts(gods={TenGod.QISHA: {LuckLayer.SEWOON}}, role=PolarityRole.GI)
    cands = engine.generate(facts, exposure_status=ExposureStatus.DENIED)
    assert cands and all(c.exposure_status is ExposureStatus.DENIED for c in cands)


# ── 7도메인 synthetic fixture — 사전 배선 누락 감지 ────────────────

_DOMAIN_CASES: list[tuple[str, dict]] = [
    ("FIN_UNEXPECTED_EXPENSE", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI,
    )),
    ("CAR_ORG_CONFLICT", dict(
        gods={TenGod.SHANGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH)],
        role=PolarityRole.GI,
    )),
    ("LEG_PENALTY_LIABILITY", dict(
        gods={TenGod.QISHA: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HYEONG, Pillar4.MONTH)],
        role=PolarityRole.GI,
    )),
    ("HLT_CHRONIC_FLAREUP", dict(
        relations=[
            RelationFact(RelationKind.CHUNG, Pillar4.DAY),
            RelationFact(RelationKind.HYEONG, Pillar4.MONTH),
        ],
        role=PolarityRole.GI,
    )),
    ("REL_EMOTIONAL_CLASH", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI,
    )),
    ("MOV_CONTRACT_FAIL", dict(
        gods={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        void=True, role=PolarityRole.GI,
    )),
    ("SEL_WAITLIST_DELAY", dict(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.YEAR)],
        void=True, role=PolarityRole.GI,
    )),
]


@pytest.mark.parametrize(("risk_id", "kwargs"), _DOMAIN_CASES)
def test_each_domain_generates(engine: RiskEngine, risk_id: str, kwargs: dict) -> None:
    """도메인별 대표 사건 위험이 독립 출처 2개 조합에서 생성된다(7도메인 전수)."""
    ids = {c.risk_id for c in engine.generate(_facts(**kwargs))}
    assert risk_id in ids
