"""R1-b 위험 점수 표본 리포트 (감수 27차 — RISK_ENGINE.md §5, 데굴님 §9·§10).

감수 목표는 절대 점수가 아니라 네 관계다: **같은 원인은 하나로 계산되고, 다른
대상이나 다른 작동 방식은 분리되며, 현실 exposure는 구조 발생 근거를 바꾸지 않고,
반복·복합·보호 축이 occurrence를 다시 복제하지 않는다.**

표본마다 §9 필드(identity·eligibility·exposable·cause rows·6축·structural/rankable
raw·capped·confidence)와 **예상 불변식의 PASS/FAIL**을 출력한다. 결정적 출력 —
저장본(doc/v2_2/RISK_SCORING_SAMPLE_R1B.md)과의 diff가 회귀 신호다.

실행: python scripts/risk_scoring_sample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_engines.risk_engine import (  # noqa: E402
    RelationFact,
    RiskEngine,
    SelectionContext,
    build_raw_period_facts,
)
from saju_engines.risk_scoring import (  # noqa: E402
    RISK_SCORING_VERSION,
    cause_occurrence_table,
    compound_family_links,
    risk_priority,
    score_shadow,
    structural_priority,
)
from saju_shared_types.event_engine import (  # noqa: E402
    LuckLayer,
    Pillar4,
    PolarityRole,
    RelationKind,
    TenGod,
)
from saju_shared_types.risk_engine import (  # noqa: E402
    EvidenceRole,
    ExposureStatus,
    RiskCandidate,
    RiskDomain,
    RiskEvidence,
    RiskKind,
    is_exposable,
)

_DICTS = _BACKEND / "dictionaries"
_CHUNG = "relation:CHUNG:month_pillar:branch:ZHENGCAI"
_HYEONG = "relation:HYEONG:month_pillar:branch:ZHENGCAI"
_CHUNG_DAY = "relation:CHUNG:day_pillar:branch:ZHENGGUAN"

_checks: list[tuple[str, bool]] = []


def _expect(label: str, ok: bool) -> None:
    _checks.append((label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


def _ev(source: str, *, strength=0.5, role=EvidenceRole.TRIGGER,
        layer="sewoon", period="2026") -> RiskEvidence:
    return RiskEvidence(
        evidence_id=f"{period}|{source}", code="SMP", period_key=period,
        layer=layer, source=source, strength=strength, role=role,
        source_group="event_shape", target_domain=RiskDomain.FINANCE,
    )


def _cand(*, risk_id="SMP_RISK", family="smp", period="2026", evidence,
          exposure=ExposureStatus.UNKNOWN, kind=RiskKind.INCIDENT_RISK,
          **overrides) -> RiskCandidate:
    atoms = sorted({a for e in evidence if e.role is EvidenceRole.TRIGGER
                    for a in e.source.split("&")})
    return RiskCandidate(
        risk_id=risk_id, domain=RiskDomain.FINANCE, kind=kind,
        risk_family=family, period_key=period, evidence=evidence,
        exposure_status=exposure, trigger_cause_atoms=atoms, **overrides)


def _row(c: RiskCandidate) -> str:
    comp = c.score_components
    assert comp is not None
    raw, capped = risk_priority(comp)
    return (
        f"    {c.risk_id}@{c.period_key}"
        f"{'/' + c.selection_episode_id if c.selection_episode_id else ''} "
        f"elig={c.eligibility_status.value} exposable={is_exposable(c)} | "
        f"occ={comp.occurrence:.3f} imp={comp.impact:.2f} exp={comp.exposure:.2f} "
        f"per={comp.persistence:.2f} cmp={comp.compound:.2f} "
        f"prot={comp.protection:.2f} | structural={structural_priority(comp):.3f} "
        f"rankable raw={raw:.3f} capped={capped:.3f} conf={c.confidence:.2f}"
    )


def sample_cause_identity() -> None:
    """§10-1: 관계·비관계 cause identity — 같은 원인 1, 다른 대상·방식 분리."""
    print("\n## 표본 1 — cause identity(관계 원자 + 비관계 전역 namespace)")
    a = _cand(risk_id="SMP_A", family="fam_a", evidence=[_ev(_CHUNG)])
    b = _cand(risk_id="SMP_B", family="fam_b", evidence=[_ev(_CHUNG_DAY)])
    c = _cand(risk_id="SMP_C", family="fam_c", evidence=[_ev(_HYEONG)])
    d = _cand(risk_id="SMP_D", family="fam_d",
              evidence=[_ev(_CHUNG, layer="daewoon+sewoon")])
    g = _cand(risk_id="SMP_G", family="fam_g", evidence=[
        _ev("ten_god:ZHENGCAI"), _ev("void"), _ev("stage:병")])
    for s in score_shadow([a, b, c, d, g], {}):
        print(_row(s))
    _expect("같은 충+다른 대상 → cause row 2",
            len(cause_occurrence_table([a, b])) == 2)
    _expect("같은 대상+다른 관계(충/형) → cause row 2",
            len(cause_occurrence_table([a, c])) == 2)
    _expect("같은 대상·관계 다층 → cause row 1(+supporting layer)",
            len(cause_occurrence_table([a, d])) == 1)
    _expect("비관계 전역 원자(ten_god/void/stage) → 각자 row(계약 통과)",
            len(cause_occurrence_table([g])) == 3)
    try:
        cause_occurrence_table([_cand(evidence=[_ev("pattern:new_thing")])])
        _expect("미상 namespace 거부", False)
    except ValueError:
        _expect("미상 namespace 거부", True)


def sample_exposure_policy() -> None:
    """§10-2: exposure 정책 — CONFIRMED > 허용 UNKNOWN > 비노출 0."""
    print("\n## 표본 2 — exposure 정책(rankable 가중)")
    ev = [_ev(_CHUNG)]
    rows = [
        _cand(evidence=ev, exposure=ExposureStatus.CONFIRMED),
        _cand(evidence=ev, exposure=ExposureStatus.UNKNOWN,
              exposure_requirement="required_for_warning"),
        _cand(evidence=ev, exposure=ExposureStatus.UNKNOWN,
              exposure_requirement="confirmed_required"),
        _cand(evidence=ev, exposure=ExposureStatus.DENIED),
        _cand(evidence=ev, selection_context_conflict=True),
        _cand(evidence=ev, kind=RiskKind.VULNERABILITY),
    ]
    scored = score_shadow(rows, {"SMP_RISK": 0.6})
    for s in scored:
        print(_row(s))
    exps = [s.score_components.exposure for s in scored
            if s.score_components is not None]
    _expect("CONFIRMED(1.0) > 허용 UNKNOWN(0.55) > 나머지 0",
            exps[0] == 1.0 and exps[1] == 0.55
            and all(x == 0.0 for x in exps[2:]))
    _expect("DENIED도 구조 진단은 보존(structural > 0)",
            scored[3].score_components is not None
            and structural_priority(scored[3].score_components) > 0)


def sample_structural_invariance() -> None:
    """§10-3: CONFIRMED↔DENIED 전환 — structural 불변·rankable만 변화."""
    print("\n## 표본 3 — structural exposure 불변")

    def pair(exposure):
        return [_cand(risk_id="SMP_A", family="fam_a", exposure=exposure,
                      evidence=[_ev(_CHUNG)]),
                _cand(risk_id="SMP_B", family="fam_b", exposure=exposure,
                      evidence=[_ev(_CHUNG, strength=0.4)])]

    conf, den = pair(ExposureStatus.CONFIRMED), pair(ExposureStatus.DENIED)
    sc = score_shadow(conf, {"SMP_A": 0.6, "SMP_B": 0.5})
    sd = score_shadow(den, {"SMP_A": 0.6, "SMP_B": 0.5})
    for s in (*sc, *sd):
        print(_row(s))
    assert sc[0].score_components and sd[0].score_components
    _expect("structural priority 동일",
            structural_priority(sc[0].score_components)
            == structural_priority(sd[0].score_components))
    _expect("구조 compound 연결(exposure 무관) 동일",
            compound_family_links(conf, exposable_only=False)
            == compound_family_links(den, exposable_only=False))
    _expect("rankable compound: CONFIRMED만 양수",
            sc[0].score_components.compound > 0
            and sd[0].score_components.compound == 0.0)


def sample_compound_effects() -> None:
    """§10-4: compound — alias·supporting·vuln 0, 독립 exposable 효과만."""
    print("\n## 표본 4 — compound 독립 효과군")
    base = _cand(risk_id="SMP_A", family="fam_a", evidence=[_ev(_CHUNG)])
    alias = _cand(risk_id="SMP_A2", family="fam_a",
                  evidence=[_ev(_CHUNG, strength=0.4)])
    absorbed = _cand(risk_id="SMP_B", family="fam_b",
                     evidence=[_ev(_CHUNG, strength=0.4)],
                     suppressed_by_specificity="SMP_A",
                     primary_risk_id="SMP_A",
                     absorbed_role="supporting_manifestation")
    vuln = _cand(risk_id="SMP_V", family="fam_v", kind=RiskKind.VULNERABILITY,
                 evidence=[_ev(_CHUNG, strength=0.4)])
    indep = _cand(risk_id="SMP_C", family="fam_c",
                  evidence=[_ev(_CHUNG, strength=0.4)])
    for label, others, want in (
        ("같은 family alias", [alias], 0.0),
        ("흡수 supporting", [absorbed], 0.0),
        ("비노출 vulnerability", [vuln], 0.0),
        ("독립 exposable 다른 family", [indep], 0.25),
    ):
        [s, *_] = score_shadow([base, *others], {})
        assert s.score_components is not None
        print(_row(s))
        _expect(f"compound({label}) = {want}",
                s.score_components.compound == want)


def sample_persistence() -> None:
    """§10-5: persistence — 연속 vs 간헐 vs 연도 경계 vs 상위 layer 직렬화."""
    print("\n## 표본 5 — persistence(연속성·직렬화 구분)")

    def month_series(risk_id, months, layer="wolwoon"):
        return [_cand(risk_id=risk_id, period=p,
                      evidence=[_ev(_CHUNG, period=p, layer=layer)])
                for p in months]

    contiguous = month_series("SMP_RUN", ("2026-01", "2026-02", "2026-03"))
    intermittent = month_series("SMP_GAP", ("2026-01", "2026-06", "2026-11"))
    boundary = month_series("SMP_BND", ("2026-12", "2027-01", "2027-02"))
    serialized = month_series(
        "SMP_SER", tuple(f"2026-{m:02d}" for m in range(1, 13)), layer="sewoon")
    scored = score_shadow(
        contiguous + intermittent + boundary + serialized, {})
    for s in (scored[0], scored[3], scored[6], scored[9]):
        print(_row(s))
    per = [s.score_components.persistence for s in scored
           if s.score_components is not None]
    _expect("연속 3개월 = 0.4", per[0] == 0.4)
    _expect("간헐 3회 = 0.0(run 1)", per[3] == 0.0)
    _expect("연도 경계(12→01→02)도 연속 3 = 0.4", per[6] == 0.4)
    _expect("세운 원인 12개월 직렬화 = 0.0(native 발동 아님)", per[9] == 0.0)
    _expect("직렬화가 occurrence를 바꾸지 않음",
            scored[9].score_components is not None
            and scored[0].score_components is not None
            and scored[9].score_components.occurrence
            == scored[0].score_components.occurrence)


def sample_shared_cause_multi_episode() -> None:
    """§10-6: D-golden — 시험 2 episode 같은 원인: 후보 2·cause row 1·평가 동일."""
    print("\n## 표본 6 — 다중 selection episode 공유 원인(엔진 실후보)")
    engine = RiskEngine(_DICTS)
    facts = build_raw_period_facts(
        period_key="2026", layer=LuckLayer.SEWOON,
        ten_god_layers={TenGod.ZHENGYIN: {LuckLayer.SEWOON}},
        relations=[RelationFact(RelationKind.HAE, Pillar4.MONTH,
                                target_ten_god=TenGod.ZHENGYIN)],
        void_active=True, polarity_role=PolarityRole.GI, twelve_stage=None)
    cands = engine.generate(facts, selection_contexts=[
        SelectionContext(target_type="examination", stage="result_wait",
                         exposure_status=ExposureStatus.CONFIRMED,
                         episode_id="exam_1"),
        SelectionContext(target_type="examination", stage="result_wait",
                         exposure_status=ExposureStatus.CONFIRMED,
                         episode_id="exam_2"),
    ])
    rdl = [c for c in cands if c.risk_id == "SEL_RESULT_DELAY_PRESSURE"]
    scored = score_shadow(rdl, engine.base_impacts())
    for s in scored:
        print(_row(s))
    table = cause_occurrence_table(rdl)
    shared = set(rdl[0].trigger_cause_atoms) & set(rdl[1].trigger_cause_atoms)
    _expect("후보 = 2(episode별 보존)", len(rdl) == 2)
    _expect("공유 원인의 cause row = 기간당 1",
            all(("2026", a) in table for a in shared) and bool(shared))
    _expect("두 후보 occurrence 동일(1회 계산 참조)",
            scored[0].score_components is not None
            and scored[1].score_components is not None
            and scored[0].score_components.occurrence
            == scored[1].score_components.occurrence)
    _expect("compound가 episode 수로 증가하지 않음(같은 risk_id·family)",
            all(s.score_components is not None
                and s.score_components.compound == 0.0 for s in scored))


def sample_protection() -> None:
    """§10-7: protection — 현재 보호만, occurrence 불변·미래 회복 미반영."""
    print("\n## 표본 7 — protection vs recovery")
    bare = _cand(evidence=[_ev(_CHUNG)])
    protected = _cand(evidence=[
        _ev(_CHUNG),
        _ev("relation:HAP:month_pillar:branch:ZHENGYIN", strength=0.4,
            role=EvidenceRole.MITIGATOR)])
    polarity_only = _cand(evidence=[
        _ev(_CHUNG),
        _ev("polarity:YONG", strength=0.9, role=EvidenceRole.MITIGATOR,
            layer="period")])
    scored = score_shadow([bare, protected, polarity_only], {"SMP_RISK": 0.6})
    for s in scored:
        print(_row(s))
    assert all(s.score_components is not None for s in scored)
    _expect("보호 조건이 occurrence를 낮추지 않음",
            scored[0].score_components.occurrence  # type: ignore[union-attr]
            == scored[1].score_components.occurrence)  # type: ignore[union-attr]
    _expect("실질 mitigator → protection > 0 → net priority 완화",
            scored[1].score_components.protection > 0  # type: ignore[union-attr]
            and risk_priority(scored[1].score_components)[0]  # type: ignore[arg-type]
            < risk_priority(scored[0].score_components)[0])  # type: ignore[arg-type]
    _expect("극성 단독 mitigator → protection 0(전역 완화 금지)",
            scored[2].score_components.protection == 0.0)  # type: ignore[union-attr]
    print("    (미래 회복 창은 R0.5 후보에 존재하지 않음 — recovery는 R2 "
          "recovery_window 소관, 현재 축 어디에도 반영 경로 없음: 구조적 보장)")


def main() -> int:
    """표본 7종 리포트 + 예상 불변식 검증 결과를 출력한다."""
    print(f"# R1-b 위험 점수 표본 리포트 — {RISK_SCORING_VERSION}")
    print("감수 대상 = 절대 점수가 아니라 표본별 예상 불변식(PASS/FAIL).")
    sample_cause_identity()
    sample_exposure_policy()
    sample_structural_invariance()
    sample_compound_effects()
    sample_persistence()
    sample_shared_cause_multi_episode()
    sample_protection()
    n_fail = sum(1 for _, ok in _checks if not ok)
    print(f"\n## 종합: {len(_checks)}개 불변식 중 FAIL {n_fail}건")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
