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

    # 상한 집중 진단(감수 31차 표기 정정 — count/rate 분리, '포화 없음' 표현
    # 금지: 상한 클리핑 존재 여부와 병적 집중 여부를 구분해 보고한다).
    d = coh["D_rankable_positive"]
    if d:
        raws = []
        for c in d:
            assert c.score_components is not None
            raws.append(risk_priority(c.score_components)[0])
        n = len(raws)

        def _cr(cnt: int) -> str:
            return f"{cnt}건({100.0 * cnt / n:.1f}%)"

        capped_eq_1 = [c for c, r in zip(d, raws, strict=True) if r >= 1.0]
        print(f"## 상한 집중 진단(D군 n={n}):")
        print(f"  raw_gt_1 {_cr(sum(1 for r in raws if r > 1))} · "
              f"raw_gt_1_2 {_cr(sum(1 for r in raws if r > 1.2))} · "
              f"raw_ge_1 {_cr(sum(1 for r in raws if r >= 1.0))} · "
              f"capped_eq_1 {_cr(len(capped_eq_1))}")
        print(f"  raw p90 {_pctl(raws, 0.9):.3f} · p95 {_pctl(raws, 0.95):.3f}"
              f" · p99 {_pctl(raws, 0.99):.3f}")
        print(f"  capped=1 후보 risk_id 다양성: "
              f"{len({c.risk_id for c in capped_eq_1})}종")
        top_n = max(1, n // 10)
        top_raws = sorted(raws, reverse=True)[:top_n]
        ties = top_n - len(set(top_raws))
        print(f"  상위 10% 동점: {ties}/{top_n} · unique raw {len(set(top_raws))}"
              f" — 다수 동점이면 R2 순위 분별력 저하(감수 판단)")
        negatives = sum(1 for r in raws if r < 0)
        print(f"  raw<0 {_cr(negatives)}(D군은 capped>0 정의라 0이어야 정상)")
    # C군은 net raw(음수 가능 — protection 감점) — 별도 보고.
    c_raws = []
    zero_by_protection = 0
    for c in coh["C_context_exposable"]:
        assert c.score_components is not None
        raw, capped = risk_priority(c.score_components)
        c_raws.append(raw)
        if capped == 0.0 and c.score_components.protection > 0 and raw < 0:
            zero_by_protection += 1
    if c_raws:
        nn = len(c_raws)
        print(f"  net_priority_raw(C군): raw<0 {sum(1 for r in c_raws if r < 0)}건"
              f"({100.0 * sum(1 for r in c_raws if r < 0) / nn:.1f}%) · "
              f"capped=0 {sum(1 for r in c_raws if r <= 0)}건 · "
              f"protection로 0 하강 {zero_by_protection}건 — capped 하한 0·raw 보존")
    # 축별 최대값 도달 — exposure 1.0은 clamp가 아니라 CONFIRMED 범주값이므로
    # component saturation과 분리 집계한다.
    a = coh["A_structural_active"]
    axis_cap: Counter = Counter()
    exposure_at_max = 0
    for c in a:
        comp = c.score_components
        assert comp is not None
        if comp.exposure >= 1.0:
            exposure_at_max += 1
        for axis in ("occurrence", "impact", "persistence", "compound",
                     "protection"):
            if getattr(comp, axis) >= 1.0:
                axis_cap[axis] += 1
    print(f"  exposure_at_max_rate(CONFIRMED 범주값 — 포화 아님): "
          f"{exposure_at_max}건({100.0 * exposure_at_max / max(1, len(a)):.1f}%)")
    print("  component_clamped(계산값 cap 도달, A군): " + (", ".join(
        f"{k} {v}건({100.0 * v / max(1, len(a)):.1f}%)"
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
        print("상위 10%(D군) 축 원값 평균(6축 전부): " + ", ".join(
            f"{k} {v:.3f}" for k, v in axes_mean.items()))
        # 가중 기여도 — modifier 공식(감수 32차) 항별 실제 기여: total =
        # E×B×(1+P+C)×(1−prot), B=occ×imp. 분해: base항=E×B×(1−prot),
        # persistence항=E×B×P×(1−prot), compound항=E×B×C×(1−prot),
        # protection 손실=E×B×(1+P+C)×prot(음수 표기).
        terms = {"base(E×B)": 0.0, "persistence항": 0.0, "compound항": 0.0,
                 "-protection손실": 0.0}
        cap_loss = 0.0
        for c in top:
            comp = c.score_components
            assert comp is not None
            eb = comp.exposure * comp.occurrence * comp.impact
            keep = 1.0 - comp.protection
            terms["base(E×B)"] += eb * keep
            terms["persistence항"] += eb * comp.persistence * keep
            terms["compound항"] += eb * comp.compound * keep
            terms["-protection손실"] -= (
                eb * (1.0 + comp.persistence + comp.compound) * comp.protection)
            raw, capped = risk_priority(comp)
            cap_loss += max(0.0, raw - capped)
        print("상위 10% 가중 기여(공식 항별 평균): " + ", ".join(
            f"{k} {v / len(top):+.3f}" for k, v in terms.items())
            + f" · cap-loss 평균 {cap_loss / len(top):.3f}")
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


def _rank_ids(cands: list[RiskCandidate], totals: list[float],
              k: int = 10) -> list[int]:
    order = sorted(range(len(cands)), key=lambda i: (-totals[i], i))
    return order[:k]


def _sensitivity_and_ablation(cands: list[RiskCandidate]) -> None:
    """compound 증분 민감도(0/0.10/0.15/0.25) + exposure UNKNOWN 가중 ablation.

    compound가 풍부한 C overlay를 대상으로 top-10 overlap·순위 역전·상한
    지표를 비교한다 — 가중 확정(R1-c2 감수)의 재료(확정은 데굴님 소관).
    """
    from saju_engines.risk_scoring import compound_family_links
    links = compound_family_links(cands, exposable_only=True)
    active = [(i, c) for i, c in enumerate(cands) if is_active(c)]

    def totals_with(compound_inc: float, unknown_w: float | None) -> list[float]:
        out = []
        for i, c in active:
            comp = c.score_components
            assert comp is not None
            cmp_v = min(1.0, compound_inc * len(links[i]))
            exp_v = comp.exposure
            if unknown_w is not None and exp_v == 0.55:
                exp_v = unknown_w
            raw = (exp_v * comp.occurrence * comp.impact
                   * (1.0 + comp.persistence + cmp_v)
                   * (1.0 - comp.protection))
            out.append(min(1.0, max(0.0, raw)))
        return out

    base = totals_with(0.10, None)
    base_top = _rank_ids([c for _, c in active], base)
    print("\n## compound 증분 민감도(C overlay·기준 0.10 — 0.25는 기각(감수 32차))")
    for inc in (0.0, 0.15, 0.25):
        alt = totals_with(inc, None)
        alt_top = _rank_ids([c for _, c in active], alt)
        overlap = len(set(base_top) & set(alt_top))
        inversions = sum(
            1 for x in range(len(base_top)) for y in range(x + 1, len(base_top))
            if alt[base_top[x]] < alt[base_top[y]]
        )
        n_pos = sum(1 for i, _ in enumerate(active) if totals_with(inc, None)[i] > 0)
        dominant = sum(
            1 for i, c in active
            if c.score_components is not None
            and min(1.0, inc * len(links[i]))
            > max(1.0, c.score_components.persistence)  # (1+per+cmp)에서 cmp 우위
        )
        new_top_entrants = len(set(alt_top) - set(base_top))
        print(f"  inc={inc:.2f}: top10 overlap {overlap}/10 · 기준 top10 내 역전 "
              f"{inversions} · rankable>0 {n_pos} · compound 항이 persistence "
              f"우위 {dominant} · top10 신규 진입 {new_top_entrants}")
    print("## exposure UNKNOWN 가중 ablation(기준 0.55)")
    for w in (1.0, 0.775, 0.3):
        alt = totals_with(0.25, w)
        alt_top = _rank_ids([c for _, c in active], alt)
        overlap = len(set(base_top) & set(alt_top))
        print(f"  unknown_w={w:.3f}: top10 overlap {overlap}/10 · "
              f"rankable>0 {sum(1 for v in alt if v > 0)}")


def _role_audit(cands: list[RiskCandidate]) -> None:
    """effect role taxonomy 감수 재료(감수 32차 — 스탬프 전 필수 audit)."""
    import json
    roles_by_item: dict[str, str] = {}
    for f in sorted((_DICTS / "risks").glob("*.json")):
        for raw in json.loads(f.read_text(encoding="utf-8"))["items"]:
            roles_by_item[raw["riskId"]] = raw["normalizedEffectRole"]
    role_items: dict[str, list[str]] = defaultdict(list)
    for rid, role in roles_by_item.items():
        role_items[role].append(rid)
    singleton = {r for r, ids in role_items.items() if len(ids) == 1}
    shared = {r for r, ids in role_items.items() if len(ids) > 1}
    cross_domain = {
        r for r, ids in role_items.items()
        if len({i.split("_")[0] for i in ids}) > 1}
    print("\n## effect role taxonomy audit(감수 32차)")
    print(f"  항목 {len(roles_by_item)} · role {len(role_items)}종 · "
          f"singleton {len(singleton)} · 공유 {len(shared)} · "
          f"도메인 간 공유 {len(cross_domain)}종({sorted(cross_domain)})")
    print("  공유 role: " + ", ".join(
        f"{r}({len(role_items[r])})" for r in sorted(shared)))
    # shared-cause 연결쌍의 role 분해(같은 기간·원인 공유 쌍 — 방향 무시).
    from saju_engines.risk_scoring import _candidate_atoms, _episode_signature
    same_role = diff_role = unresolved_pairs = 0
    by_period: dict[str, list[RiskCandidate]] = defaultdict(list)
    for c in cands:
        if is_active(c):
            by_period[c.period_key].append(c)
    for group in by_period.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.risk_id == b.risk_id:
                    continue
                if not (_candidate_atoms(a) & _candidate_atoms(b)):
                    continue
                ra = a.normalized_effect_role or a.risk_family
                rb = b.normalized_effect_role or b.risk_family
                if not (_episode_signature(a) and _episode_signature(b)):
                    unresolved_pairs += 1
                elif ra == rb:
                    same_role += 1
                else:
                    diff_role += 1
    print(f"  shared-cause 연결쌍: same-role {same_role} · different-role "
          f"{diff_role} · unresolved {unresolved_pairs}")


def _capped_detail(cands: list[RiskCandidate]) -> None:
    """capped=1 후보 개별 공개(감수 32차 — CAR 3건 등 단일 항목 상한 감수 재료)."""
    rows = []
    for c in cands:
        comp = c.score_components
        if comp is None or not is_active(c):
            continue
        raw, capped = risk_priority(comp)
        if capped >= 1.0:
            rows.append((c, comp, raw))
    print(f"\n## capped=1 후보 상세({len(rows)}건 — 개별 감수 재료)")
    for c, comp, raw in sorted(rows, key=lambda r: (-r[2], r[0].risk_id)):
        atoms = ", ".join(sorted(c.trigger_cause_atoms)[:3])
        print(f"  {c.risk_id}@{c.period_key}: raw {raw:.3f}(cap-loss "
              f"{raw - 1.0:.3f}) · occ {comp.occurrence:.3f} imp {comp.impact:.2f} "
              f"exp {comp.exposure:.2f} per {comp.persistence:.2f} "
              f"cmp {comp.compound:.2f} prot {comp.protection:.2f} · "
              f"원인 [{atoms}]")


def _persistence_span_comparison() -> None:
    """persistence span 5/8/12 비교 + 지속 vs 단기 pairwise(감수 32차)."""
    from saju_shared_types.risk_engine import RiskScoreComponents

    def rankable(occ, imp, per, span_run):
        per_v = min(1.0, max(0.0, (span_run[1] - 1) / span_run[0]))
        comp = RiskScoreComponents(
            occurrence=occ, impact=imp, exposure=1.0,
            persistence=per_v, compound=0.0, protection=0.0)
        return risk_priority(comp)[1]

    print("\n## persistence span 비교·pairwise(감수 32차 — 기대 순서 명시)")
    for span in (5, 8, 12):
        strong_short = rankable(0.8, 0.7, 0.0, (span, 1))
        weak_persistent = rankable(0.2, 0.6, 0.0, (span, 6))  # 6개월 연속
        mid_persistent = rankable(0.5, 0.6, 0.0, (span, 4))  # 3+1개월 연속
        print(f"  span={span}: 강한 단기 {strong_short:.3f} vs 약한 6개월 지속 "
              f"{weak_persistent:.3f}(기대: 단기 우위 "
              f"{'PASS' if strong_short > weak_persistent else 'FAIL'}) · "
              f"중간 4개월 지속 {mid_persistent:.3f}"
              f"({'단기 우위' if strong_short > mid_persistent else '지속 우위'})")


def _protection_pairwise() -> None:
    """protection 비례 완화 pairwise(감수 32차 — 감점의 음수 양산 해소 검증)."""
    from saju_shared_types.risk_engine import RiskScoreComponents

    def total(prot):
        comp = RiskScoreComponents(
            occurrence=0.5, impact=0.6, exposure=1.0,
            persistence=0.0, compound=0.0, protection=prot)
        return risk_priority(comp)[1]

    print("\n## protection pairwise(비례 완화)")
    none_p, weak_p, strong_p = total(0.0), total(0.3), total(0.8)
    print(f"  보호 없음 {none_p:.3f} > 약한 보호 {weak_p:.3f} > 강한 보호 "
          f"{strong_p:.3f} — "
          f"{'PASS' if none_p > weak_p > strong_p > 0 else 'FAIL'}"
          f"(강한 보호도 0으로 소거하지 않음 — 완화이지 삭제 아님)")


def _unknown_local_sensitivity(cands: list[RiskCandidate]) -> None:
    """UNKNOWN 가중 국소 민감도(감수 33차 §8 — 0.55 주변 안정성).

    승인 기준(데굴님): 0.50↔0.60 top-25 overlap ≥ 85% · 특정 도메인 상위 진입
    급증 없음 · 약한 UNKNOWN이 강한 CONFIRMED를 반복 추월하지 않음.
    """
    active = [c for c in cands if is_active(c)]

    def totals(w: float) -> list[float]:
        out = []
        for c in active:
            comp = c.score_components
            assert comp is not None
            exp_v = w if comp.exposure == 0.55 else comp.exposure
            out.append(min(1.0, exp_v * comp.occurrence * comp.impact
                           * (1.0 + comp.persistence + comp.compound)
                           * (1.0 - comp.protection)))
        return out

    base = totals(0.55)
    base25 = set(_rank_ids(active, base, k=25))
    base50 = set(_rank_ids(active, base, k=50))
    unknown_only = [v for c, v in zip(active, base, strict=True)
                    if c.score_components is not None
                    and c.score_components.exposure == 0.55 and v > 0]
    print("\n## UNKNOWN 가중 국소 민감도(기준 0.55 — 감수 33차)")
    print(f"  UNKNOWN-only cohort(양수): n={len(unknown_only)} · "
          f"p50 {_pctl(unknown_only, 0.5):.3f} · p90 {_pctl(unknown_only, 0.9):.3f}")
    pass_5060 = None
    for w in (0.40, 0.50, 0.60, 0.70):
        alt = totals(w)
        o25 = len(base25 & set(_rank_ids(active, alt, k=25)))
        o50 = len(base50 & set(_rank_ids(active, alt, k=50)))
        crossings = sum(
            1 for i, c in enumerate(active)
            if c.score_components is not None
            and c.score_components.exposure == 0.55
            and (base[i] > 0) != (alt[i] > 0))
        overtakes = 0
        conf_max = max((base[i] for i, c in enumerate(active)
                        if c.score_components is not None
                        and c.score_components.exposure == 1.0), default=0.0)
        overtakes = sum(
            1 for i, c in enumerate(active)
            if c.score_components is not None
            and c.score_components.exposure == 0.55 and alt[i] > conf_max)
        print(f"  w={w:.2f}: top25 overlap {o25}/25({100 * o25 // 25}%) · "
              f"top50 {o50}/50 · threshold crossing {crossings} · "
              f"CONFIRMED 최고점 추월 UNKNOWN {overtakes}")
        if w in (0.50, 0.60):
            ok = o25 >= 22  # ≥85%(22/25)
            pass_5060 = ok if pass_5060 is None else (pass_5060 and ok)
    print(f"  승인 기준(0.50↔0.60 top-25 ≥85%): "
          f"{'PASS' if pass_5060 else 'FAIL'}")


def _shared_cause_pair_table(cands: list[RiskCandidate]) -> None:
    """different-role shared-cause 연결쌍의 unique 조합 표(감수 33차 §5 —
    같은 원인의 다른 표현인지, 실제 다른 결과인지 항목쌍 단위 감수 재료)."""
    from saju_engines.risk_scoring import _candidate_atoms, _episode_signature
    pairs: Counter = Counter()
    by_period: dict[str, list[RiskCandidate]] = defaultdict(list)
    for c in cands:
        if is_active(c):
            by_period[c.period_key].append(c)
    for group in by_period.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.risk_id == b.risk_id:
                    continue
                if not (_candidate_atoms(a) & _candidate_atoms(b)):
                    continue
                if not (_episode_signature(a) and _episode_signature(b)):
                    continue
                ra = a.normalized_effect_role or a.risk_family or ""
                rb = b.normalized_effect_role or b.risk_family or ""
                if ra == rb:
                    continue
                key = tuple(sorted((f"{a.risk_id}[{ra}]", f"{b.risk_id}[{rb}]")))
                pairs[key] += 1
    print(f"\n## shared-cause different-role 연결쌍(unique 조합 "
          f"{len(pairs)} — 감수 재료)")
    for (x, y), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:4d}× {x} ↔ {y}")


def _multi_context_audit() -> None:
    """ByContext 필요 항목 자동 탐색(감수 33차 §7) — context branch 2+ 항목."""
    import json
    print("\n## ByContext 자동 탐색(context branch 2+ 항목)")
    found = 0
    for f in sorted((_DICTS / "risks").glob("*.json")):
        for raw in json.loads(f.read_text(encoding="utf-8"))["items"]:
            branches = raw.get("applicableHealthContextTypes", [])
            if len(branches) >= 2:
                has = bool(raw.get("normalizedEffectRoleByContext"))
                print(f"  {raw['riskId']}: branches={branches} · "
                      f"ByContext {'저작됨' if has else '단일 base role'}")
                found += 1
    if not found:
        print("  없음 — TRL 1건으로 충분")


def _transition_overlay(cands: list[RiskCandidate]) -> None:
    """교운기 overlay(감수 36차 — R1-T): 커널값 3단(교운일 1.0/±1년 0.368/
    ±2년 0.135 — 이벤트 엔진 kernel SSOT 산출값)으로 상승률·순위 영향·포화를
    실측한다. 기존 baseline(무보정)은 그대로 보존·비교."""
    from datetime import date as _date

    from saju_engines.event_scoring import daewoon_transition_weight
    from saju_engines.risk_scoring import score_shadow as _ss
    # 커널 SSOT 검증 산출(교운일 2026-06-01 기준).
    jiao = [_date(2026, 6, 1)]
    kernel = {
        "교운일": daewoon_transition_weight(_date(2026, 6, 1), jiao),
        "±1년": daewoon_transition_weight(_date(2027, 6, 1), jiao),
        "±2년": daewoon_transition_weight(_date(2028, 6, 1), jiao),
    }
    base_impacts = RiskEngine(_DICTS).base_impacts()
    raw_cands = [c.model_copy(update={
        "score_components": None, "confidence": 0.0, "transition_bonus": 0.0,
    }) for c in cands]
    plain = _ss(raw_cands, base_impacts)
    plain_active = [c for c in plain if is_active(c)]
    plain_totals = []
    for c in plain_active:
        assert c.score_components is not None
        plain_totals.append(risk_priority(c.score_components)[1])
    plain_top = _rank_ids(plain_active, plain_totals)
    print("\n## 교운기 overlay(커널 SSOT — 이벤트 엔진 함수 공유)")
    jiao_active: list[RiskCandidate] = []
    jiao_totals: list[float] = []
    for label, w in kernel.items():
        periods = {c.period_key for c in raw_cands}
        boosted = _ss(raw_cands, base_impacts,
                      transition_weights=dict.fromkeys(periods, w))
        b_active = [c for c in boosted if is_active(c)]
        totals = []
        rises = []
        dominant = 0
        for pc, bc in zip(plain_active, b_active, strict=True):
            assert pc.score_components and bc.score_components
            p_raw, _ = risk_priority(pc.score_components,
                                     transition_bonus=pc.transition_bonus)
            b_raw, b_cap = risk_priority(bc.score_components,
                                         transition_bonus=bc.transition_bonus)
            totals.append(b_cap)
            if p_raw > 0:
                rises.append(b_raw / p_raw - 1.0)
            if bc.transition_bonus > max(bc.score_components.persistence,
                                         bc.score_components.compound):
                dominant += 1
        top = _rank_ids(b_active, totals)
        overlap = len(set(plain_top) & set(top))
        n_sat = sum(1 for v in totals if v >= 1.0)
        print(f"  {label}(w={w:.3f}): 평균 상승률 "
              f"{100 * sum(rises) / max(1, len(rises)):.1f}% · top10 overlap "
              f"{overlap}/10(신규 {10 - overlap}) · transition이 최대 modifier "
              f"{dominant} · capped=1 {n_sat}")
        if label == "교운일":
            jiao_active, jiao_totals = b_active, totals

    # 조건2(감수 37차) — 교운일 최악점에서 상한 도달·top10 신규 진입 개별 공개.
    def _rank_map(totals: list[float]) -> dict[int, int]:
        order = sorted(range(len(totals)), key=lambda i: (-totals[i], i))
        return {idx: rank + 1 for rank, idx in enumerate(order)}

    plain_rank = _rank_map(plain_totals)
    jiao_rank = _rank_map(jiao_totals)
    print("\n### 교운일 capped=1 상세(조건2 — 개별 감수 재료)")
    for i, bc in enumerate(jiao_active):
        assert bc.score_components is not None
        raw, cap = risk_priority(bc.score_components,
                                 transition_bonus=bc.transition_bonus)
        if cap < 1.0:
            continue
        comp = bc.score_components
        print(f"  {bc.risk_id} [{bc.domain.value}] {bc.period_key}: "
              f"raw {raw:.3f} · occ {comp.occurrence:.2f} × imp "
              f"{comp.impact:.2f} × exp {comp.exposure:.2f} · trans_bonus "
              f"+{bc.transition_bonus:.3f} · pers {comp.persistence:.2f} · "
              f"comp {comp.compound:.2f} · prot {comp.protection:.2f} · "
              f"무교운 rank {plain_rank[i]} → 교운일 rank {jiao_rank[i]}")
    jiao_top = _rank_ids(jiao_active, jiao_totals)
    print("### 교운일 top10 신규 진입 상세(조건2)")
    for i in jiao_top:
        if i in plain_top:
            continue
        bc = jiao_active[i]
        assert bc.score_components is not None
        raw, _cap = risk_priority(bc.score_components,
                                  transition_bonus=bc.transition_bonus)
        p_comp = plain_active[i].score_components
        assert p_comp is not None
        p_raw, _ = risk_priority(p_comp)
        print(f"  {bc.risk_id} [{bc.domain.value}] {bc.period_key}: rank "
              f"{plain_rank[i]} → {jiao_rank[i]} · raw {p_raw:.3f} → "
              f"{raw:.3f} · trans_bonus +{bc.transition_bonus:.3f} · "
              f"sensitivity {bc.transition_sensitivity}")

    # 조건3(감수 37차) — MAX_BONUS 민감도: bonus가 MAX_BONUS에 선형 비례하므로
    # 교운일(w=1.0) bonus를 비율 재스케일해 0.30/0.40/0.50 비교(재점수 불필요).
    from saju_engines.risk_scoring import _TRANSITION_MAX_BONUS as _MB
    print("\n### MAX_BONUS 민감도(감수 39차 — 0.20 **확정**, 0.30 보조"
          " 비교·0.40/0.50 기각, 교운일 w=1.0 최악점)")
    for mb in (0.20, 0.30, 0.40, 0.50):
        scale = mb / _MB
        totals_mb = []
        rises_mb = []
        dominant_mb = 0
        for pc, bc in zip(plain_active, jiao_active, strict=True):
            assert pc.score_components and bc.score_components
            bonus = bc.transition_bonus * scale
            p_raw, _ = risk_priority(pc.score_components)
            b_raw, b_cap = risk_priority(bc.score_components,
                                         transition_bonus=bonus)
            totals_mb.append(b_cap)
            if p_raw > 0:
                rises_mb.append(b_raw / p_raw - 1.0)
            if bonus > max(bc.score_components.persistence,
                           bc.score_components.compound):
                dominant_mb += 1
        top_mb = _rank_ids(jiao_active, totals_mb)
        print(f"  MAX_BONUS={mb:.2f}: 평균 상승률 "
              f"{100 * sum(rises_mb) / max(1, len(rises_mb)):.1f}% · top10 "
              f"overlap(무교운 대비) {len(set(plain_top) & set(top_mb))}/10 · "
              f"transition이 최대 modifier {dominant_mb} · "
              f"capped=1 {sum(1 for v in totals_mb if v >= 1.0)}")


def _transition_sensitivity_audit() -> None:
    """조건4(감수 37차) — transitionSensitivity 저작 audit 표.

    기준은 도메인이 아니라 **상태 전환성**(대운 전환기에 실제로 더 잘
    발생하는 성격의 사건인가). high 전량 + medium 목록을 감수 재료로 공개
    — 확정·조정은 데굴님 소관(shadow_temporal 스탬프 전 감수 대상).
    """
    import json
    rows: list[tuple[str, str, str, str, str]] = []
    for f in sorted((_DICTS / "risks").glob("*.json")):
        for raw in json.loads(f.read_text(encoding="utf-8"))["items"]:
            rows.append((raw.get("transitionSensitivity", "none"),
                         raw["riskId"], f.stem, raw["kind"],
                         raw["normalizedEffectRole"]))
    counts = Counter(r[0] for r in rows)
    print("\n## transitionSensitivity 저작 audit(조건4 — 상태 전환성 기준)")
    print("  분포: " + " · ".join(
        f"{lv} {counts.get(lv, 0)}" for lv in ("high", "medium", "low",
                                               "none")))
    print("  ### high 전체(전환기 가속 사건인지 개별 감수)")
    for lv, rid, dom, kind, role in sorted(rows):
        if lv == "high":
            print(f"    {rid} [{dom}] kind={kind} role={role}")
    med = [rid for lv, rid, *_ in sorted(rows) if lv == "medium"]
    print(f"  medium {len(med)}종: " + ", ".join(med))


def _pairwise_golden() -> None:
    """§6 pairwise golden — 기대 순서를 명시해 감수한다(구조 vs exposure 경쟁)."""
    from saju_engines.risk_scoring import risk_priority as _rp

    def rankable(occ: float, imp: float, exp: float) -> float:
        from saju_shared_types.risk_engine import RiskScoreComponents
        comp = RiskScoreComponents(
            occurrence=occ, impact=imp, exposure=exp,
            persistence=0.0, compound=0.0, protection=0.0)
        return _rp(comp)[1]

    print("\n## pairwise golden(기대 순서 명시 — 감수 대상)")
    same_conf = rankable(0.5, 0.6, 1.0)
    same_unknown = rankable(0.5, 0.6, 0.55)
    print(f"  같은 구조: CONFIRMED {same_conf:.3f} > 허용 UNKNOWN "
          f"{same_unknown:.3f} > 비노출 0.000 — "
          f"{'PASS' if same_conf > same_unknown > 0 else 'FAIL'}")
    strong_unknown = rankable(0.8, 0.7, 0.55)
    weak_conf = rankable(0.3, 0.4, 1.0)
    print(f"  강한 구조+허용 UNKNOWN {strong_unknown:.3f} vs 약한 구조+CONFIRMED "
          f"{weak_conf:.3f} → 기대: 구조 우위 유지 — "
          f"{'PASS' if strong_unknown > weak_conf else 'FAIL'}")
    near_unknown = rankable(0.55, 0.6, 0.55)
    near_conf = rankable(0.5, 0.6, 1.0)
    print(f"  근접 구조(0.55 vs 0.5)+노출 차이: UNKNOWN {near_unknown:.3f} vs "
          f"CONFIRMED {near_conf:.3f} → 기대: 근접 구조에선 확인된 현실이 우선 — "
          f"{'PASS' if near_conf > near_unknown else 'FAIL'}")


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

    c_overlay: list[RiskCandidate] | None = None
    for name, ctxs in _build_exposure_profiles():
        cands = _collect(ctxs)
        _report_population(f"모집단 2 — profile overlay: {name}", cands)
        if name == "C_high_exposure":
            c_overlay = cands

    assert c_overlay is not None
    _role_audit(c_overlay)
    _shared_cause_pair_table(c_overlay)
    _multi_context_audit()
    _capped_detail(c_overlay)
    _sensitivity_and_ablation(c_overlay)
    _unknown_local_sensitivity(c_overlay)
    _transition_overlay(c_overlay)
    _transition_sensitivity_audit()
    _pairwise_golden()
    _persistence_span_comparison()
    _protection_pairwise()

    print("\n## 단조성 검증: 8종 전부 단위 fixture로 고정(test_risk_scoring_r1a"
          " — 원인 추가↛occ 감소·protection↛priority 증가·CONFIRMED→UNKNOWN↛"
          "증가·supporting/vuln↛occ 증가·무관 episode 불변·입력 순서 byte 불변·"
          "same-role episode 추가↛compound 증가·보조 cause 증감↛persistence 감소)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
