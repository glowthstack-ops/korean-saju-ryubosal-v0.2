"""R1-c1 위험 점수 전수 측정 (감수 30차 — 49항목 shadow scoring 분포·포화·단조성).

목적(데굴님 확정): 점수의 절대값이 아니라 **어떤 축이 상위 후보를 만들고 있으며,
cap과 exposure가 분포를 왜곡하지 않는지**를 전수 코퍼스에서 확인한다.

측정 모집단 2층(§11): ①전체 구조 코퍼스(suppression baseline과 동일 10차트·
year+month — 컨텍스트 없음) ②A/B/C/D profile overlay(같은 코퍼스에 현실 컨텍스트
적용). 두 층은 별도 표로 출력 — profile만으로 전체 분포를 대표하지 않는다.

cohort 6군(비노출 0점의 median 왜곡 금지 — rankable 분포는 D군 기준):
  A structural active / B ELIGIBLE / C context-exposable / D rankable>0 /
  E BLOCKED·INSUFFICIENT / F vulnerability(active)

compound는 전역 동시 후보가 아니라 **연결된 effect graph(shared canonical cause)**
에서만 계산되고, is_question_target은 context confidence에서 제외된다(fixture 고정
— test_risk_scoring_r1a.py). 결정적 출력 — 저장본과의 diff가 회귀 신호.

실행: python scripts/risk_scoring_survey.py
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from risk_shadow_density import _CORPUS, _LEVELS, _build_exposure_profiles  # noqa: E402
from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import EventEngineV2  # noqa: E402
from saju_engines.risk_engine import RiskEngine  # noqa: E402
from saju_engines.risk_scoring import (  # noqa: E402
    CAUSE_SEMANTICS_VERSION,
    RISK_SCORING_VERSION,
    cause_semantics_hash,
    compound_unresolved_counts,
    context_axes,
    context_confidence,
    risk_priority,
    score_shadow,
    scoring_config_hash,
    structural_priority,
)
from saju_shared_types.risk_engine import (  # noqa: E402
    EligibilityStatus,
    RiskCandidate,
    RiskKind,
    is_active,
    is_exposable,
)

_DICTS = _BACKEND / "dictionaries"
_LEVEL_SET = {_LEVELS["year"], _LEVELS["month"]}


def _pctl(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[idx]


def _dist(values: list[float]) -> str:
    return (f"p50 {_pctl(values, 0.5):.3f} · p90 {_pctl(values, 0.9):.3f} · "
            f"max {max(values, default=0.0):.3f} · n={len(values)}")


def _collect(contexts: dict | None) -> list[RiskCandidate]:
    """코퍼스 전체의 점수 채운 후보(차트 단위 score_shadow — 결정적)."""
    base_impacts = RiskEngine(_DICTS).base_impacts()
    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    if contexts:
        engine.set_risk_shadow_contexts(**contexts)
    out: list[RiskCandidate] = []
    for _name, birth in _CORPUS:
        chart = calculate(birth)
        engine.score(chart, levels=_LEVEL_SET)
        out.extend(score_shadow(list(engine.risk_shadow), base_impacts))
    return out


def _cohorts(cands: list[RiskCandidate]) -> dict[str, list[RiskCandidate]]:
    def rankable(c: RiskCandidate) -> float:
        assert c.score_components is not None
        return risk_priority(c.score_components)[1]

    return {
        "A_structural_active": [c for c in cands if is_active(c)],
        "B_eligible": [c for c in cands if c.eligibility_status in (
            EligibilityStatus.ELIGIBLE, EligibilityStatus.MITIGATED)],
        "C_context_exposable": [c for c in cands
                                if is_active(c) and is_exposable(c)],
        "D_rankable_positive": [c for c in cands
                                if is_active(c) and rankable(c) > 0],
        "E_blocked_insufficient": [c for c in cands if c.eligibility_status in (
            EligibilityStatus.BLOCKED, EligibilityStatus.INSUFFICIENT_EVIDENCE)],
        "F_vulnerability_active": [
            c for c in cands
            if is_active(c) and c.kind is RiskKind.VULNERABILITY],
    }


def _report_population(title: str, cands: list[RiskCandidate]) -> None:
    print(f"\n# {title}")
    coh = _cohorts(cands)
    print("## cohort 규모: " + " · ".join(
        f"{k} {len(v)}" for k, v in coh.items()))

    structural = [structural_priority(c.score_components) for c in
                  coh["A_structural_active"] if c.score_components]
    print(f"structural priority(A군): {_dist(structural)}")
    rank_raw = []
    rank_capped = []
    for c in coh["C_context_exposable"]:
        assert c.score_components is not None
        raw, capped = risk_priority(c.score_components)
        rank_raw.append(raw)
        rank_capped.append(capped)
    print(f"rankable raw(C군): {_dist(rank_raw)}")
    print(f"rankable capped(C군): {_dist(rank_capped)}")
    n_nonrank = len(coh["A_structural_active"]) - len(coh["D_rankable_positive"])
    print(f"비rankable(활성·capped=0): {n_nonrank} — rankable 분포"
          f"(D군 {len(coh['D_rankable_positive'])})에 미포함(median 왜곡 방지)")

    # 도메인별 분포(structural=A군 / rankable=D군 분리 — 공식이 달라 직접 비교 금지).
    dom_structural: dict[str, list[float]] = defaultdict(list)
    dom_rankable: dict[str, list[float]] = defaultdict(list)
    for c in coh["A_structural_active"]:
        assert c.score_components is not None
        dom_structural[c.domain.value].append(
            structural_priority(c.score_components))
    for c in coh["D_rankable_positive"]:
        assert c.score_components is not None
        dom_rankable[c.domain.value].append(
            risk_priority(c.score_components)[1])
    print("## 도메인별 structural(A군) / rankable capped(D군)")
    for dom in sorted(set(dom_structural) | set(dom_rankable)):
        print(f"  {dom:14s} structural {_dist(dom_structural.get(dom, []))} | "
              f"rankable {_dist(dom_rankable.get(dom, []))}")

    # 포화 지표(D군 rankable 기준 + A군 축별 cap 도달률).
    d = coh["D_rankable_positive"]
    if d:
        raws = []
        for c in d:
            assert c.score_components is not None
            raws.append(risk_priority(c.score_components)[0])
        n = len(raws)
        print(f"## 포화(D군 n={n}): raw>1 {sum(1 for r in raws if r > 1)}"
              f"({100 * sum(1 for r in raws if r > 1) // n}%) · "
              f"raw>1.2 {sum(1 for r in raws if r > 1.2)} · "
              f"capped=1 {sum(1 for r in raws if min(1.0, r) >= 1.0)}")
    axis_cap: Counter = Counter()
    a = coh["A_structural_active"]
    for c in a:
        comp = c.score_components
        assert comp is not None
        for axis in ("occurrence", "impact", "exposure", "persistence",
                     "compound", "protection"):
            if getattr(comp, axis) >= 1.0:
                axis_cap[axis] += 1
    print("축별 cap(=1.0) 도달(A군): " + (", ".join(
        f"{k} {v}({100 * v // max(1, len(a))}%)"
        for k, v in sorted(axis_cap.items())) or "없음"))

    # 상위 10%(D군 rankable capped) 축 구성 + unresolved 지배 검사.
    unresolved = compound_unresolved_counts(cands)
    unresolved_by_id = {id(c): u for c, u in zip(cands, unresolved, strict=True)}
    if d:
        def _capped(c: RiskCandidate) -> float:
            assert c.score_components is not None
            return risk_priority(c.score_components)[1]

        ranked = sorted(d, key=_capped, reverse=True)
        top = ranked[:max(1, len(ranked) // 10)]
        axes_mean = {axis: sum(
            getattr(c.score_components, axis) for c in top) / len(top)
            for axis in ("occurrence", "impact", "exposure", "persistence",
                         "compound", "protection")}
        print("상위 10%(D군) 축 평균: " + ", ".join(
            f"{k} {v:.3f}" for k, v in axes_mean.items()))
        top_unresolved = sum(1 for c in top if unresolved_by_id[id(c)] > 0)
        print(f"상위 10% 중 unresolved effect 연결 보유: {top_unresolved}/{len(top)}"
              f" — 다수면 가중 확정 보류(감수 기준)")

    # compound·unresolved 진단.
    n_unresolved = sum(1 for u in unresolved if u > 0)
    n_compound = sum(
        1 for c in cands
        if c.score_components is not None and c.score_components.compound > 0)
    print(f"## compound 진단: compound>0 후보 {n_compound} · "
          f"unresolved effect 연결 보유 {n_unresolved}"
          f"({100 * n_unresolved // max(1, len(cands))}%) · "
          f"episode_count_only_violations 0(fixture 강제) · "
          f"void_target_mismatch 0(구조적 — 전역 void)")

    # persistence 진단 — lineage 통계.
    lineages: dict[tuple, set[str]] = defaultdict(set)
    assignments = 0
    for c in cands:
        comp = c.score_components
        assert comp is not None
        if comp.persistence > 0:
            assignments += 1
        # lineage 원천 수 근사: (risk_id, 원자) 단위(episode 없음 코퍼스 호환).
        for atom in c.trigger_cause_atoms:
            lineages[(c.risk_id, atom)].add(c.period_key)
    persistent = sum(1 for periods in lineages.values() if len(periods) > 1)
    print(f"## persistence 진단: unique cause lineages {len(lineages)} · "
          f"다기간 lineage {persistent} · candidate persistence 부여 {assignments}"
          f" — 포트폴리오 원천은 lineage(후보 합산 금지)")

    # confidence 분리.
    struct_conf = [c.confidence for c in coh["A_structural_active"]]
    ctx_conf = [context_confidence(c) for c in coh["A_structural_active"]]
    axis_counts: Counter = Counter()
    for c in coh["A_structural_active"]:
        for state, names in context_axes(c).items():
            axis_counts[state] += len(names)
    print(f"## confidence: structural {_dist(struct_conf)} | "
          f"context {_dist(ctx_conf)}")
    print("context 축 상태 합(A군): " + ", ".join(
        f"{k} {v}" for k, v in sorted(axis_counts.items())))


def main() -> int:
    """전체 구조 코퍼스 + A/B/C/D overlay 전수 측정 리포트."""
    print(f"# R1-c1 위험 점수 전수 측정 — {RISK_SCORING_VERSION}")
    print(f"semantics {CAUSE_SEMANTICS_VERSION} · "
          f"config {scoring_config_hash()} · semantics {cause_semantics_hash()}")
    print("compound=연결된 effect graph(shared canonical cause)만 · "
          "is_question_target=context confidence 제외(fixture 고정)")

    _report_population(
        "모집단 1 — 전체 구조 코퍼스(컨텍스트 없음·suppression baseline 동일)",
        _collect(None))

    for name, ctxs in _build_exposure_profiles():
        _report_population(f"모집단 2 — profile overlay: {name}", _collect(ctxs))

    print("\n## 단조성 검증: 8종 전부 단위 fixture로 고정(test_risk_scoring_r1a"
          " — 원인 추가↛occ 감소·protection↛priority 증가·CONFIRMED→UNKNOWN↛"
          "증가·supporting/vuln↛occ 증가·무관 episode 불변·입력 순서 byte 불변·"
          "same-role episode 추가↛compound 증가·보조 cause 증감↛persistence 감소)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
