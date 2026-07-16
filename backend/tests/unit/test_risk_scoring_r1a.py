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
               exposure=ExposureStatus.UNKNOWN, **overrides) -> RiskCandidate:
    atoms = sorted({
        a for e in evidence if e.role is EvidenceRole.TRIGGER
        for a in e.source.split("&")
    })
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.FINANCE, kind=RiskKind.INCIDENT_RISK,
        risk_family="syn", period_key=period, evidence=evidence,
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
    """같은 원인을 공유하는 FIN·다른 risk_id 후보 — 표에는 (기간, 원인) 1항목."""
    a = _candidate(risk_id="SYN_A", evidence=[_evidence(_CHUNG, strength=0.5)])
    b = _candidate(risk_id="SYN_B", evidence=[_evidence(_CHUNG, strength=0.4)])
    table = cause_occurrence_table([a, b])
    assert list(table) == [("2026", _CHUNG)]
    assert table[("2026", _CHUNG)] == 0.5  # 최강 strength 1회(결정적)
    # compound 축이 연결을 표현한다(occurrence 중복 가산 아님).
    [sa, sb] = score_shadow([a, b], {})
    assert _comp(sa).compound > 0 and _comp(sb).compound > 0
    lone = _candidate(risk_id="SYN_C", evidence=[
        _evidence("relation:PA:day_pillar:branch:BIJIAN", strength=0.5)])
    [sc] = score_shadow([lone], {})
    assert _comp(sc).compound == 0.0  # 연결 없으면 0


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


def test_persistence_counts_periods_only() -> None:
    ev = lambda p: [_evidence(_CHUNG, strength=0.5, period=p)]  # noqa: E731
    series = [_candidate(period=p, evidence=ev(p)) for p in
              ("2026-01", "2026-02", "2026-03")]
    lone = _candidate(period="2026-07", evidence=ev("2026-07"),
                      risk_id="SYN_LONE")
    scored = score_shadow(series + [lone], {})
    assert _comp(scored[0]).persistence == pytest.approx(2 / 5)
    assert _comp(scored[0]).occurrence == (
        _comp(scored[3]).occurrence)  # 반복이 신호 강도를 재합산 금지
    assert _comp(scored[3]).persistence == 0.0


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
