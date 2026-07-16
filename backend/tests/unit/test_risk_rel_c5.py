"""위험 사전 REL 차수(C5 — 감수 16차) 의미론 fixture.

데굴님 REL 차수 불변식(2026-07-15): 관계 위험은 십성·궁위만으로 현실의 상대를
만들어내지 않으며, 동일한 상대·동일한 원인에서 나온 감정 충돌·오해·신뢰 저하·거리감은
하나의 대표 위험과 보조 발현으로 정리한다.

고정 범위: ①관계 대상 역할 분리(배우자궁≠가족궁≠친구 금전) ②같은 상대·같은 원인
확산의 계층 흡수(supporting_manifestation/possible_trajectory) ③다른 상대 병존
④partner exposure 4상태(CONFIRMED/UNKNOWN/DENIED/NOT_APPLICABLE)별 활성·차단
⑤requiresFinancialTie/SharedResponsibility 유도 ⑥FIN-REL 소유권 ⑦궁합·함께보기
질문 대상(is_question_target) 역할 불일치 차단 ⑧C4-f HOS 결과 단계 게이트.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from saju_engines.risk_engine import (
    RelationFact,
    RelationshipContext,
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
    RiskDomain,
    is_active,
    is_exposable,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"

# 커버리지 게이트 연동(test_risk_engine.py) — REL 승격 시 항목별 양성 fixture 원천.
REL_POSITIVE_IDS = {
    "REL_PARTNER_READJUST",
    "REL_EMOTIONAL_CLASH",
    "REL_COMMUNICATION_MISALIGNMENT",
    "REL_TRUST_STABILITY_WEAK",
    "REL_DISTANCE_PRESSURE",
    "REL_FAMILY_BURDEN",
    "REL_PEER_FINANCIAL_ENTANGLEMENT_RISK",
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


# 관계 컨텍스트 상수 — 각 테스트에서 재사용.
_SPOUSE_CONFIRMED = RelationshipContext(
    target_role="spouse", target_id="companion:A",
    exposure_status=ExposureStatus.CONFIRMED,
)
_FAMILY_CONFIRMED = RelationshipContext(
    target_role="family_member", target_id="companion:F",
    exposure_status=ExposureStatus.CONFIRMED, shared_responsibility=True,
)
_FRIEND_MONEY_CONFIRMED = RelationshipContext(
    target_role="friend_peer", target_id="companion:B",
    exposure_status=ExposureStatus.CONFIRMED, financial_tie=True,
)


# ── ① 항목별 양성 recall(승격 게이트 원천) ─────────────────────────

_REL_POSITIVE_CASES: list[tuple[str, dict, list[RelationshipContext]]] = [
    # 배우자궁(일지) 직접 충(targeted) + 배우자 노출 확인.
    ("REL_PARTNER_READJUST", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
        role=PolarityRole.GI,
    ), [_SPOUSE_CONFIRMED]),
    # 겁재 마찰 shape + 대인 기반(비겁군) 충 — 역할 무관 일반 감정 압박.
    # (시주 사용 — 년·월주는 가족궁 targeted라 FAMILY_BURDEN 대표 흡수와 겹친다.)
    ("REL_EMOTIONAL_CLASH", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI,
    ), []),
    # 상관 shape + 표현 채널(식상군) 해 — 전달 어긋남 압박.
    ("REL_COMMUNICATION_MISALIGNMENT", dict(
        gods={TenGod.SHANGGUAN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.SHISHEN)],
        role=PolarityRole.GI,
    ), []),
    # 겁재 구조 약화 + 대인 기반 파 — 신뢰 방어력 취약성.
    ("REL_TRUST_STABILITY_WEAK", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.PA, Pillar4.MONTH,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI,
    ), []),
    # 대인 기반(비겁군) 충 단독 — 거리감 압박(shape 불요 단일 그룹 계약).
    ("REL_DISTANCE_PRESSURE", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.HOUR,
                                target_ten_god=TenGod.BIJIAN)],
        role=PolarityRole.GI,
    ), []),
    # 가족궁(년주) 직접 충(targeted) + 실제 책임 확인.
    ("REL_FAMILY_BURDEN", dict(
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR)],
        role=PolarityRole.GI,
    ), [_FAMILY_CONFIRMED]),
    # 겁재-재성 동반 shape + 재성 피격 + 실제 금전 관계 확인(2독립 원인).
    ("REL_PEER_FINANCIAL_ENTANGLEMENT_RISK", dict(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON},
              TenGod.PIANCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.PIANCAI)],
        role=PolarityRole.GI,
    ), [_FRIEND_MONEY_CONFIRMED]),
]


@pytest.mark.parametrize(("risk_id", "kwargs", "ctxs"), _REL_POSITIVE_CASES)
def test_rel_positive_recall(
    engine: RiskEngine, risk_id: str, kwargs: dict, ctxs: list[RelationshipContext],
) -> None:
    """REL 7항목 전수 — 명확 양성 조합에서 활성 생성(항목별 recall 게이트)."""
    cands = engine.generate(_facts(**kwargs), relationship_contexts=ctxs)
    assert risk_id in _active_ids(cands)


# ── ② 관계 대상 역할 분리 ────────────────────────────────────────


def test_partner_confirmed_matched_and_exposable(engine: RiskEngine) -> None:
    """배우자궁 충 + partner CONFIRMED → 매칭·노출 가능, 상대 서명 기록."""
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        relationship_contexts=[_SPOUSE_CONFIRMED],
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert is_active(ptn) and is_exposable(ptn)
    assert ptn.relationship_alignment == "matched"
    assert ptn.relationship_role == "spouse"
    assert ptn.relationship_target_id == "companion:A"
    assert ptn.exposure_status is ExposureStatus.CONFIRMED


def test_partner_denied_blocked_no_generic_fallback(engine: RiskEngine) -> None:
    """partner DENIED → partner 후보 BLOCKED, 일반 대인 pressure 자동 전환 금지.

    배우자궁 충 신호만으로는(대인 기반 피격·마찰 shape 없음) 다른 REL 후보가 활성으로
    '대체 생성'되지 않아야 한다 — fallback 금지 불변식.
    """
    denied = RelationshipContext(
        target_role="spouse", exposure_status=ExposureStatus.DENIED)
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        relationship_contexts=[denied],
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert ptn.eligibility_status is EligibilityStatus.BLOCKED
    assert "exposure_denied" in ptn.suppression_reasons
    rel_active = {
        c.risk_id for c in cands
        if c.domain is RiskDomain.RELATIONSHIP and is_active(c)
    }
    assert rel_active == set()


def test_partner_not_applicable_blocked(engine: RiskEngine) -> None:
    """partner NOT_APPLICABLE(질문·상품 맥락상 해당 없음) → hard blocker."""
    na = RelationshipContext(
        target_role="spouse", exposure_status=ExposureStatus.NOT_APPLICABLE)
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        relationship_contexts=[na],
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert ptn.eligibility_status is EligibilityStatus.BLOCKED
    assert "exposure_not_applicable" in ptn.suppression_reasons


def test_partner_unknown_structure_retained_but_not_exposable(engine: RiskEngine) -> None:
    """관계 정보 부재(컨텍스트 없음) → UNKNOWN: 구조 보존하되 **비노출**(감수 17차).

    컨텍스트 부재는 관계 부재(DENIED)가 아니므로 후보는 활성 보존한다. 그러나 역할
    특정 항목의 조건부 노출은 관계가 질문 대상이거나 확인된 경우(alignment=matched)
    로 한정 — 총운·재물운에서 partner 후보가 상시 조건부 경고로 반복되는 것을 차단.
    """
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert is_active(ptn)
    assert ptn.relationship_alignment == "unknown"
    assert ptn.exposure_status is ExposureStatus.UNKNOWN
    assert ptn.relationship_target_id is None
    assert not is_exposable(ptn)  # 관계 질문·확인 없이 조건부 노출 금지


def test_partner_unknown_exposable_when_relationship_question(engine: RiskEngine) -> None:
    """연애 질문("올해 연애운?") → 관계가 질문 대상이면 UNKNOWN이라도 조건부 노출.

    질문 대상 컨텍스트(role=dating_partner, 노출 UNKNOWN, is_question_target)는
    matched — "현재 관계가 있다면" 조건부 표현(claimCeilingWhenUnknown=advisory)
    경로가 열린다. 단 is_question_target이 노출을 CONFIRMED로 만들지는 않는다.
    """
    question_ctx = RelationshipContext(
        target_role="dating_partner", exposure_status=ExposureStatus.UNKNOWN,
        is_question_target=True,
    )
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        relationship_contexts=[question_ctx],
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert is_active(ptn) and is_exposable(ptn)
    assert ptn.relationship_alignment == "matched"
    assert ptn.exposure_status is ExposureStatus.UNKNOWN  # 자동 CONFIRMED 금지


def test_family_palace_does_not_create_partner_candidate(engine: RiskEngine) -> None:
    """가족궁(년주) 충 → FAMILY_BURDEN 경로만 — 배우자 재조정 후보 미생성."""
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR)],
               role=PolarityRole.GI),
        relationship_contexts=[_FAMILY_CONFIRMED],
    )
    ids = {c.risk_id for c in cands}
    assert "REL_PARTNER_READJUST" not in ids
    fam = next(c for c in cands if c.risk_id == "REL_FAMILY_BURDEN")
    assert is_active(fam) and fam.relationship_role == "family_member"


# ── ③ 같은 상대·같은 원인 확산의 계층 흡수 ───────────────────────


def test_same_partner_same_cause_single_representative(engine: RiskEngine) -> None:
    """동일 배우자·동일 충 → 대표 1건(PARTNER_READJUST) + 보조 역할로 수렴.

    감정 충돌은 supporting_manifestation, 거리감은 possible_trajectory로 흡수 —
    독립 active family로 복제되지 않는다(REL 차수 핵심 목표).
    """
    cands = engine.generate(
        _facts(
            gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                    target_ten_god=TenGod.BIJIAN)],
            role=PolarityRole.GI,
        ),
        relationship_contexts=[_SPOUSE_CONFIRMED],
    )
    by_id = {c.risk_id: c for c in cands}
    assert is_active(by_id["REL_PARTNER_READJUST"])
    clash = by_id["REL_EMOTIONAL_CLASH"]
    assert clash.suppressed_by_specificity == "REL_PARTNER_READJUST"
    assert clash.absorbed_role == "supporting_manifestation"
    dst = by_id["REL_DISTANCE_PRESSURE"]
    assert dst.suppressed_by_specificity == "REL_PARTNER_READJUST"
    assert dst.absorbed_role == "possible_trajectory"
    active_families = {
        c.risk_family for c in cands
        if c.domain is RiskDomain.RELATIONSHIP and is_active(c)
    }
    assert active_families == {"relationship_adjustment"}


def test_different_targets_coexist(engine: RiskEngine) -> None:
    """다른 상대(배우자 A vs 친구 B)의 위험은 원인을 공유해도 병존한다.

    일지 재성 충 하나가 배우자 재조정(targeted 궁위)과 친구 금전(재성 피격) 모두의
    원인이어도, 서로 다른 target_id·역할이므로 상호 억제 금지(동률 병존 + 상대 상이
    가드). 같은 십성군 fallback이 이를 구제하지 못한다.
    """
    cands = engine.generate(
        _facts(
            gods={TenGod.JIECAI: {LuckLayer.SEWOON},
                  TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                    target_ten_god=TenGod.ZHENGCAI)],
            role=PolarityRole.GI,
        ),
        relationship_contexts=[_SPOUSE_CONFIRMED, _FRIEND_MONEY_CONFIRMED],
    )
    by_id = {c.risk_id: c for c in cands}
    ptn, pfe = by_id["REL_PARTNER_READJUST"], by_id["REL_PEER_FINANCIAL_ENTANGLEMENT_RISK"]
    assert is_active(ptn) and is_active(pfe)
    assert ptn.relationship_target_id == "companion:A"
    assert pfe.relationship_target_id == "companion:B"


# ── ④ 궁합·함께보기(질문 직접 대상) 역할 불일치 ──────────────────


def test_question_target_role_mismatch_blocks_partner_item(engine: RiskEngine) -> None:
    """궁합 질문 대상이 친구인데 배우자 전용 항목 → MISMATCHED(BLOCKED, fallback 금지).

    테마사주·AI채팅 궁합/함께보기: 동반자 관계힌트가 is_question_target 컨텍스트로
    주입된다 — 친구 궁합에서 배우자 재조정 위험을 만들지 않는다.
    """
    friend_target = RelationshipContext(
        target_role="friend_peer", target_id="companion:B",
        exposure_status=ExposureStatus.CONFIRMED, is_question_target=True,
    )
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        relationship_contexts=[friend_target],
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert ptn.eligibility_status is EligibilityStatus.BLOCKED
    assert "relationship_role_mismatch" in ptn.suppression_reasons
    assert not is_exposable(ptn)


def test_non_question_context_mismatch_stays_unknown(engine: RiskEngine) -> None:
    """질문 대상이 아닌 컨텍스트의 역할 불일치는 UNKNOWN — 다른 상대가 있을 수 있다.

    친구 등록만 있는 사용자의 배우자궁 충: 배우자 유무는 미확인이므로 차단이 아니라
    구조 보존(조건부 표현 경로)이다.
    """
    friend_info = RelationshipContext(
        target_role="friend_peer", target_id="companion:B",
        exposure_status=ExposureStatus.CONFIRMED,
    )
    cands = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY)],
               role=PolarityRole.GI),
        relationship_contexts=[friend_info],
    )
    ptn = next(c for c in cands if c.risk_id == "REL_PARTNER_READJUST")
    assert is_active(ptn)
    assert ptn.relationship_alignment == "unknown"


# ── ⑤ 실질 노출 조건(requiresSharedResponsibility/FinancialTie) ───


def test_family_burden_responsibility_axes(engine: RiskEngine) -> None:
    """가족 역할 확인만으로는 CONFIRMED 취급 금지 — 실제 책임 축별 유도.

    책임 미확인(None)=UNKNOWN 강등(조건부 표현), 책임 없음(False)=DENIED(차단).
    """
    facts = _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.YEAR)],
                   role=PolarityRole.GI)
    unknown_resp = RelationshipContext(
        target_role="family_member", exposure_status=ExposureStatus.CONFIRMED)
    fam = next(
        c for c in engine.generate(facts, relationship_contexts=[unknown_resp])
        if c.risk_id == "REL_FAMILY_BURDEN")
    assert is_active(fam)
    assert fam.exposure_status is ExposureStatus.UNKNOWN  # CONFIRMED 강등

    no_resp = RelationshipContext(
        target_role="family_member", exposure_status=ExposureStatus.CONFIRMED,
        shared_responsibility=False)
    fam2 = next(
        c for c in engine.generate(facts, relationship_contexts=[no_resp])
        if c.risk_id == "REL_FAMILY_BURDEN")
    assert fam2.eligibility_status is EligibilityStatus.BLOCKED


def test_peer_financial_requires_tie_confirmed(engine: RiskEngine) -> None:
    """대인 금전 사건은 실제 금전 관계 CONFIRMED 없이는 노출 불가(가장 엄격).

    역할 확인 + 금전 관계 미확인 → 구조 보존·비노출(unknownExposable=false —
    "~일 수 있다면" 우회도 금지). 금전 관계 없음(False) → 차단.
    """
    facts = _facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.PIANCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.PIANCAI)],
        role=PolarityRole.GI,
    )
    tie_unknown = RelationshipContext(
        target_role="friend_peer", exposure_status=ExposureStatus.CONFIRMED)
    pfe = next(
        c for c in engine.generate(facts, relationship_contexts=[tie_unknown])
        if c.risk_id == "REL_PEER_FINANCIAL_ENTANGLEMENT_RISK")
    assert is_active(pfe) and not is_exposable(pfe)

    tie_absent = RelationshipContext(
        target_role="friend_peer", exposure_status=ExposureStatus.CONFIRMED,
        financial_tie=False)
    pfe2 = next(
        c for c in engine.generate(facts, relationship_contexts=[tie_absent])
        if c.risk_id == "REL_PEER_FINANCIAL_ENTANGLEMENT_RISK")
    assert pfe2.eligibility_status is EligibilityStatus.BLOCKED

    pfe3 = next(
        c for c in engine.generate(facts)
        if c.risk_id == "REL_PEER_FINANCIAL_ENTANGLEMENT_RISK")
    assert is_active(pfe3) and not is_exposable(pfe3)  # 컨텍스트 부재=비노출 구조 보존


# ── ⑥ FIN–REL 소유권 ─────────────────────────────────────────────


def test_fin_primary_when_no_peer_exposure(engine: RiskEngine) -> None:
    """금전 신호만 있고 대인 금전 노출이 없으면 FIN이 노출 가능한 주 위험이다.

    REL 대인 금전 사건은 구조 후보로만 보존(비노출) — 같은 원인의 FIN·REL 동시 활성
    시 대표 선정은 R2 Episode 병합 소관(R0.5는 양쪽 구조 보존, 감수 16차 합의).
    """
    cands = engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}, TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGCAI)],
        role=PolarityRole.GI,
    ))
    by_id = {c.risk_id: c for c in cands}
    fin = by_id["FIN_UNEXPECTED_EXPENSE"]
    pfe = by_id["REL_PEER_FINANCIAL_ENTANGLEMENT_RISK"]
    assert is_active(fin) and is_exposable(fin)
    assert is_active(pfe) and not is_exposable(pfe)


def test_independent_causes_fin_rel_coexist(engine: RiskEngine) -> None:
    """독립된 금전 원인과 관계 원인 → FIN·REL 병존(서로 흡수 금지)."""
    cands = engine.generate(
        _facts(
            gods={TenGod.JIECAI: {LuckLayer.SEWOON},
                  TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
            relations=[
                RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                             target_ten_god=TenGod.ZHENGCAI),  # 금전 원인
                RelationFact(RelationKind.CHUNG, Pillar4.DAY),  # 배우자궁 원인
            ],
            role=PolarityRole.GI,
        ),
        relationship_contexts=[_SPOUSE_CONFIRMED, _FRIEND_MONEY_CONFIRMED],
    )
    ids = _active_ids(cands)
    assert {"FIN_UNEXPECTED_EXPENSE", "REL_PARTNER_READJUST",
            "REL_PEER_FINANCIAL_ENTANGLEMENT_RISK"} <= ids


# ── ⑨ 감수 17차 — 커밋 전 필수 확인 조건 fixture ─────────────────


def test_representative_deterministic_under_item_order(engine: RiskEngine) -> None:
    """대표 선택이 사전 항목 순서에 무관하다(결정적 비교자 — 감수 17차 조건 1).

    항목 순서를 역순으로 바꾼 엔진과 원본 엔진이 동일 입력에서 동일한 대표·흡수
    역할·활성 상태를 산출해야 한다.
    """
    reversed_engine = RiskEngine(_DICTS)
    reversed_engine._items = list(reversed(reversed_engine._items))  # noqa: SLF001
    scenarios: list[dict[str, Any]] = [
        dict(gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
             relations=[RelationFact(RelationKind.CHUNG, Pillar4.DAY,
                                     target_ten_god=TenGod.BIJIAN)],
             role=PolarityRole.GI),
        dict(gods={TenGod.JIECAI: {LuckLayer.SEWOON},
                   TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
             relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                     target_ten_god=TenGod.ZHENGCAI)],
             role=PolarityRole.GI),
    ]
    for kwargs in scenarios:
        base = {
            c.risk_id: (c.suppressed_by_specificity, c.absorbed_role, is_active(c))
            for c in engine.generate(
                _facts(**kwargs), relationship_contexts=[_SPOUSE_CONFIRMED])
        }
        flipped = {
            c.risk_id: (c.suppressed_by_specificity, c.absorbed_role, is_active(c))
            for c in reversed_engine.generate(
                _facts(**kwargs), relationship_contexts=[_SPOUSE_CONFIRMED])
        }
        assert base == flipped


def test_god_atom_only_no_cross_target_absorption(engine: RiskEngine) -> None:
    """십성 유입 원자만 공유한 REL 후보끼리는 수렴 금지(감수 17차 조건 2).

    시주 충(감정 충돌 대상)과 월주 파(신뢰 이완 대상)는 서로 다른 현실 상대일 수
    있다 — 공유 원자가 겁재 유입뿐이면 target_id 미확인 상태에서 흡수하지 않는다.
    """
    cands = engine.generate(_facts(
        gods={TenGod.JIECAI: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.CHUNG, Pillar4.HOUR,
                         target_ten_god=TenGod.BIJIAN),
            RelationFact(RelationKind.PA, Pillar4.MONTH,
                         target_ten_god=TenGod.BIJIAN),
        ],
        role=PolarityRole.GI,
    ))
    by_id = {c.risk_id: c for c in cands}
    assert is_active(by_id["REL_EMOTIONAL_CLASH"])
    assert is_active(by_id["REL_TRUST_STABILITY_WEAK"])


def test_question_target_does_not_confirm_financial_tie(engine: RiskEngine) -> None:
    """궁합 질문 대상이라는 사실이 금전 거래·노출을 자동 확인하지 않는다(조건 3).

    친구 궁합(is_question_target)이어도 financial_tie 미확인이면 대인 금전 사건은
    비노출(구조 보존)이다 — 사용자가 돈 거래·공동 비용·보증·정산을 실제로 말한
    경우에만 CONFIRMED가 될 수 있다.
    """
    friend_target = RelationshipContext(
        target_role="friend_peer", target_id="companion:B",
        exposure_status=ExposureStatus.UNKNOWN, is_question_target=True,
    )
    cands = engine.generate(
        _facts(
            gods={TenGod.JIECAI: {LuckLayer.SEWOON},
                  TenGod.PIANCAI: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                    target_ten_god=TenGod.PIANCAI)],
            role=PolarityRole.GI,
        ),
        relationship_contexts=[friend_target],
    )
    pfe = next(c for c in cands
               if c.risk_id == "REL_PEER_FINANCIAL_ENTANGLEMENT_RISK")
    assert is_active(pfe)
    assert pfe.exposure_status is ExposureStatus.UNKNOWN  # 자동 CONFIRMED 금지
    assert not is_exposable(pfe)


def test_family_burden_month_requires_family_target(engine: RiskEngine) -> None:
    """월주 충 + 일반 기신만으로 FAMILY_BURDEN 미생성(조건 4 — 직업 변화 오역 차단).

    월주는 사회궁·직업 환경 의미가 강하다: 관성 피격 월주 충은 가족 부담 trigger가
    아니고, 가족 육친 대상(인성=부모) 피격 provenance가 명시된 발동만 인정한다.
    """
    non_family = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGGUAN)],
               role=PolarityRole.GI),
        relationship_contexts=[_FAMILY_CONFIRMED],
    )
    assert "REL_FAMILY_BURDEN" not in {c.risk_id for c in non_family}

    parent_target = engine.generate(
        _facts(relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                       target_ten_god=TenGod.ZHENGYIN)],
               role=PolarityRole.GI),
        relationship_contexts=[_FAMILY_CONFIRMED],
    )
    fam = next(c for c in parent_target if c.risk_id == "REL_FAMILY_BURDEN")
    assert is_active(fam) and is_exposable(fam)


def test_fin_rel_same_cause_share_link_key(engine: RiskEngine) -> None:
    """같은 원인의 FIN·REL 병존 후보는 연결 키(trigger 원인 원자)를 공유한다(조건 6).

    R1이 independent cause·occurrence를 1회만 계산하고 R2가 episode 대표 1개를
    선택하는 데 쓰는 교차 도메인 연결 재료 — 관계 원자(대상 객체 서명 내장) 공유.
    """
    cands = engine.generate(
        _facts(
            gods={TenGod.JIECAI: {LuckLayer.SEWOON},
                  TenGod.ZHENGCAI: {LuckLayer.SEWOON}},
            relations=[RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                                    target_ten_god=TenGod.ZHENGCAI)],
            role=PolarityRole.GI,
        ),
        relationship_contexts=[_FRIEND_MONEY_CONFIRMED],
    )
    by_id = {c.risk_id: c for c in cands}
    fin, pfe = by_id["FIN_UNEXPECTED_EXPENSE"], by_id["REL_PEER_FINANCIAL_ENTANGLEMENT_RISK"]
    shared = set(fin.trigger_cause_atoms) & set(pfe.trigger_cause_atoms)
    assert any(a.startswith("relation:") for a in shared)


# ── ⑧ C4-f — HOS 결과 단계 게이트(데굴님 후속 조건) ──────────────


def _hiring_outcome_facts():
    """결정·통지 어긋남(해+관성) + 최종 판단 대상(관성) 직접 충."""
    return _facts(
        gods={TenGod.ZHENGGUAN: {LuckLayer.SEWOON}},
        relations=[
            RelationFact(RelationKind.HAE, Pillar4.MONTH,
                         target_ten_god=TenGod.ZHENGGUAN),
            RelationFact(RelationKind.CHUNG, Pillar4.MONTH,
                         target_ten_god=TenGod.ZHENGGUAN),
        ],
        role=PolarityRole.GI,
    )


def test_hos_result_stage_matched(engine: RiskEngine) -> None:
    """채용 + 결과 대기 단계 → HIRING_OUTCOME_SETBACK 적용 가능."""
    cands = engine.generate(
        _hiring_outcome_facts(), exposure_status=ExposureStatus.CONFIRMED,
        selection_context=SelectionContext(
            target_type="employment_hiring", stage="result_wait"),
    )
    hos = next(c for c in cands if c.risk_id == "CAR_HIRING_OUTCOME_SETBACK")
    assert is_active(hos) and hos.selection_alignment == "matched"


def test_hos_application_stage_blocked(engine: RiskEngine) -> None:
    """지원·면접 단계의 통지 어긋남은 결과 위험이 아니다 — MISMATCHED(BLOCKED).

    절차 지연은 HIRING_PROCESS_DELAY 소관(단계 무제한 pressure)으로 유지된다.
    """
    cands = engine.generate(
        _hiring_outcome_facts(), exposure_status=ExposureStatus.CONFIRMED,
        selection_context=SelectionContext(
            target_type="employment_hiring", stage="assessment"),
    )
    hos = next(c for c in cands if c.risk_id == "CAR_HIRING_OUTCOME_SETBACK")
    assert hos.eligibility_status is EligibilityStatus.BLOCKED
    assert "selection_stage_mismatch" in hos.suppression_reasons


def test_hos_unknown_stage_not_exposable(engine: RiskEngine) -> None:
    """채용 확인 + 단계 미확인 → 구조 보존하되 결과 단계 특정 표현 불가(비노출)."""
    cands = engine.generate(
        _hiring_outcome_facts(), exposure_status=ExposureStatus.CONFIRMED,
        selection_context=SelectionContext(target_type="employment_hiring"),
    )
    hos = next(c for c in cands if c.risk_id == "CAR_HIRING_OUTCOME_SETBACK")
    assert is_active(hos)
    assert hos.selection_alignment == "unknown"
    assert not is_exposable(hos)
