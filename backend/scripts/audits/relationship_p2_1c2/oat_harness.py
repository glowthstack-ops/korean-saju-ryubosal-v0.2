"""P2-1C-2 harness — weight OAT × 구조 anchor (RELATIONSHIP_VECTOR_CALIBRATION).

리뷰 §3~§9: kind_base_bonus·stability(support/pressure)·separation weight를 **한 번에
하나씩**(OAT) ±10%/±20% 변경하며 축별 finite-difference 민감도를 측정한다. 구조 하나에만
적용하면 weight 효과와 구조 효과를 구분할 수 없으므로 세 anchor에서 수행:

  S0 = C0 baseline (A=Stab=Sep 0.30)
  S1 = C1 activation 억제형 (A=0.15 / P=0.30)
  S2 = C1 pressure 억제형 (A=0.30 / P=0.15)

감사 전용·읽기 전용·production delta 0. 자동 채택·자동 clamp 없음(§5·§14). 순서 불허
profile(ordering 위반·음수)은 NOT_ADMISSIBLE로 기록·제외(값 보정 금지).

주입 지점(§4): kind_base_bonus는 S1(dict) — evidence base_relation_strength가 bonus에
선형이므로 대상 kind evidence를 (1+p) 스케일해 등가 perturbation. stability/separation
weight는 S2(합성기 calibration dict) 직접 perturbation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_engines.relationship_effect_vector import (
    _SEP_WEIGHT,
    _STAB_PRESSURE,
    _STAB_SUPPORT,
    RELATIONSHIP_CALIBRATION_VERSION,
    RelationshipVectorCalibration,
    synthesize_relationship_effect_vector,
)
from saju_engines.spouse_palace_activation import (
    SpousePalaceHit,
    build_spouse_palace_vector,
)
from saju_shared_types.event_engine import Pillar4, RelationKind
from saju_shared_types.relationship_effect import AxisStatus

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT_MD = Path(__file__).resolve().parent / "P2_1C2_OAT_REPORT.md"
OUT_JSON = Path(__file__).resolve().parent / "p2_1c2_invariant_results.json"

EXPERIMENT_SPEC_VERSION = "p2.1c2.v1"
_PERIOD = "2027"
_PERTURB = [-0.2, -0.1, 0.0, 0.1, 0.2]
_ACT_KINDS = ["HAP", "CHUNG", "HYEONG", "PA", "HAE"]
_STAB_PARAMS = ["support.HAP", "pressure.CHUNG", "pressure.HYEONG",
                "pressure.PA", "pressure.HAE"]
_SEP_PARAMS = ["CHUNG", "HYEONG", "PA", "HAE"]

# 구조 anchor(§3).
_ANCHORS = ["S0", "S1", "S2"]


def _hit(kind, glyph, natal="丑"):
    return SpousePalaceHit(
        kind=kind, palace=Pillar4.DAY, layer="sewoon", position="branch",
        transit_component="branch", transit_participant=glyph, natal_participant=natal)


def _ev(hits):
    return build_spouse_palace_vector(hits, _DICTS, period_key=_PERIOD).evidences


@dataclass
class Case:
    case_id: str
    structure: str          # same_root | cross_root | single
    evidences: list


def build_lattice() -> list[Case]:
    K = RelationKind
    return [
        Case("same_CHUNG_HYEONG", "same_root",
             _ev([_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "未", "戌")])),
        Case("cross_CHUNG_HYEONG", "cross_root",
             _ev([_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "戌", "辰")])),
        Case("single_CHUNG", "single", _ev([_hit(K.CHUNG, "未")])),
        Case("same_HAP_CHUNG", "same_root",
             _ev([_hit(K.HAP, "未", "丑"), _hit(K.CHUNG, "未", "辰")])),
        # PA·HAE parameter coverage(§2) — 두 kind 같은 root(activation·pressure·
        # separation 전 축 자극).
        Case("same_PA_HAE", "same_root",
             _ev([_hit(K.PA, "未", "丑"), _hit(K.HAE, "未", "戌")])),
    ]


def _kinds_in(case: Case) -> set[str]:
    return {e.relation_kind for e in case.evidences}


def _anchor_cal(anchor: str, **weight_kwargs) -> RelationshipVectorCalibration:
    if anchor == "S0":
        return RelationshipVectorCalibration.shared(
            secondary_factor=0.3, profile_id="S0", **weight_kwargs)
    if anchor == "S1":
        return RelationshipVectorCalibration.activation_pressure_split(
            activation=0.15, pressure=0.3, profile_id="S1", **weight_kwargs)
    return RelationshipVectorCalibration.activation_pressure_split(
        activation=0.3, pressure=0.15, profile_id="S2", **weight_kwargs)


def _scale_kind(evidences: list, kind: str, factor: float) -> list:
    """대상 kind evidence의 base_relation_strength를 factor배(kind_base_bonus 등가 §4)."""
    out = []
    for e in evidences:
        if e.relation_kind == kind:
            out.append(e.model_copy(update={
                "base_relation_strength": round(e.base_relation_strength * factor, 6)}))
        else:
            out.append(e)
    return out


def _perturbed_weights(param: str, mult: float) -> dict:
    """stability/separation weight OAT — 한 항목만 (1+p)배, 나머지 baseline."""
    if param.startswith("support."):
        k = param.split(".", 1)[1]
        d = dict(_STAB_SUPPORT)
        d[k] = round(d[k] * mult, 6)
        return {"stability_support": d}
    if param.startswith("pressure."):
        k = param.split(".", 1)[1]
        d = dict(_STAB_PRESSURE)
        d[k] = round(d[k] * mult, 6)
        return {"stability_pressure": d}
    # separation
    d = dict(_SEP_WEIGHT)
    d[param] = round(d[param] * mult, 6)
    return {"separation_weight": d}


def _sep_admissible(sep: dict) -> bool:
    """separation CHUNG ≥ 나머지 ordering(§5) — 위반이면 NOT_ADMISSIBLE."""
    c = sep["CHUNG"]
    return all(c >= sep[k] for k in ("HYEONG", "PA", "HAE"))


def _val(ax):
    return ax.value if ax.status is AxisStatus.EVALUATED else None


def _axes(evidences, cal):
    return synthesize_relationship_effect_vector(evidences, calibration=cal).axes


def _fd(hi, lo, dp):
    if hi is None or lo is None:
        return None
    return round((hi - lo) / dp, 4)


# ── activation kind bonus OAT ────────────────────────────────────────────────
def activation_bonus_oat() -> dict:
    cases = build_lattice()
    out: dict = {}
    for anchor in _ANCHORS:
        cal = _anchor_cal(anchor)
        out[anchor] = {}
        for kind in _ACT_KINDS:
            for c in cases:
                key = f"{c.case_id}:{kind}"
                vals = {}
                for p in _PERTURB:
                    ev = _scale_kind(c.evidences, kind, 1.0 + p)
                    vals[p] = _val(_axes(ev, cal).activation)
                out[anchor][key] = {
                    "local": _fd(vals[0.1], vals[-0.1], 0.2),
                    "wide": _fd(vals[0.2], vals[-0.2], 0.4),
                    "baseline": vals[0.0],
                }
    return out


# ── stability / separation weight OAT ────────────────────────────────────────
def weight_oat(params: list[str], axis: str) -> dict:
    cases = build_lattice()
    out: dict = {}
    inadmissible: list[dict] = []
    for anchor in _ANCHORS:
        out[anchor] = {}
        for param in params:
            for c in cases:
                key = f"{c.case_id}:{param}"
                vals: dict[float, float | None] = {}
                for p in _PERTURB:
                    w = _perturbed_weights(param, 1.0 + p)
                    # 음수·separation ordering 검사(§5 — 자동 clamp 금지).
                    if axis == "separation" and not _sep_admissible(w["separation_weight"]):
                        inadmissible.append({
                            "anchor": anchor, "param": param, "perturb": p,
                            "reason": "SEPARATION_ORDERING_VIOLATION"})
                        vals[p] = None
                        continue
                    cal = _anchor_cal(anchor, **w)
                    ax = _axes(c.evidences, cal)
                    vals[p] = (_val(ax.stability) if axis == "stability"
                               else _val(ax.separation_pressure))
                out[anchor][key] = {
                    "local": _fd(vals.get(0.1), vals.get(-0.1), 0.2),
                    "wide": _fd(vals.get(0.2), vals.get(-0.2), 0.4),
                    "baseline": vals.get(0.0),
                }
    return {"grid": out, "inadmissible": inadmissible}


# ── parameter coverage matrix (§2) ───────────────────────────────────────────
def coverage_matrix(cases: list[Case], act_oat: dict, stab_oat: dict,
                    sep_oat: dict) -> dict:
    """전체 14 mutable parameter가 자극됐는지 증명(§2) + eligible-case sensitivity(§3).

    exercised = 해당 kind가 존재하는 사례 수. nonzero = 그 사례 중 sensitivity≠0.
    eligible_mean = kind 존재 사례만의 |wide| 평균(§3 — 전체 평균 희석 배제).
    """
    kinds = {c.case_id: _kinds_in(c) for c in cases}
    rows: dict[str, dict] = {}

    def _eligible(grid_s0: dict, param_key_fn, kind: str) -> dict:
        present = [c.case_id for c in cases if kind in kinds[c.case_id]]
        widths = [abs(grid_s0[param_key_fn(cid)]["wide"] or 0.0)
                  for cid in present if param_key_fn(cid) in grid_s0]
        nonzero = any(w > 1e-9 for w in widths)
        return {
            "exercised_case_count": len(present),
            "nonzero_observed": nonzero,
            "eligible_mean_wide": round(sum(widths) / len(widths), 4) if widths else None,
        }

    for k in _ACT_KINDS:
        rows[f"activation.{k}"] = _eligible(
            act_oat["S0"], lambda cid, kk=k: f"{cid}:{kk}", k)
    for param in _STAB_PARAMS:
        k = param.split(".")[-1]
        rows[f"stability.{param}"] = _eligible(
            stab_oat["grid"]["S0"], lambda cid, pp=param: f"{cid}:{pp}", k)
    for k in _SEP_PARAMS:
        rows[f"separation.{k}"] = _eligible(
            sep_oat["grid"]["S0"], lambda cid, kk=k: f"{cid}:{kk}", k)

    uncovered = [p for p, r in rows.items() if r["exercised_case_count"] < 1]
    zero_sens = [p for p, r in rows.items()
                 if r["exercised_case_count"] >= 1 and not r["nonzero_observed"]]
    return {"rows": rows, "uncovered": uncovered, "zero_sensitivity": zero_sens,
            "all_covered": not uncovered}


# ── 구조 cross-check (§8) ─────────────────────────────────────────────────────
def structure_cross_check(act_oat: dict, stab_oat: dict) -> dict:
    """activation-only 구조 차(S0 vs S1)는 stability OAT에 무영향 / pressure 구조 차
    (S0 vs S2)는 activation OAT에 무영향이어야 한다(§8 factor routing 검증)."""
    checks: dict = {}
    # activation bonus OAT: S0 vs S1(activation factor만 다름) → 결과 다를 수 있음(정상,
    # activation은 activation factor 의존). 대신 stability weight OAT는 S0 vs S1 동일해야.
    stab_s0_s1_equal = True
    g = stab_oat["grid"]
    for key in g["S0"]:
        if g["S0"][key]["local"] != g["S1"][key]["local"]:
            stab_s0_s1_equal = False
            break
    # activation bonus OAT: S0 vs S2(pressure factor만 다름) → activation 동일해야.
    act_s0_s2_equal = all(
        act_oat["S0"][key]["local"] == act_oat["S2"][key]["local"]
        for key in act_oat["S0"])
    checks["stability_oat_invariant_to_activation_structure"] = stab_s0_s1_equal
    checks["activation_oat_invariant_to_pressure_structure"] = act_s0_s2_equal
    return checks


# ── 불변식 게이트 (§11) ──────────────────────────────────────────────────────
def invariant_checks(cases: list[Case]) -> dict:
    viols: list[str] = []

    def v(m):
        viols.append(m)

    for c in cases:
        base = synthesize_relationship_effect_vector(c.evidences)
        for anchor in _ANCHORS:
            cal = _anchor_cal(anchor)
            ref = _axes(c.evidences, cal)
            # weight 하나만 변경 → 비대상 축 불변(stability weight는 activation 불변).
            w = _perturbed_weights("pressure.CHUNG", 1.2)
            cal_w = _anchor_cal(anchor, **w)
            ax_w = _axes(c.evidences, cal_w)
            if ax_w.activation.model_dump() != ref.activation.model_dump():
                v(f"stability_weight_touched_activation:{c.case_id}:{anchor}")
            # AxisStatus 불변.
            if ax_w.activation.status is not ref.activation.status:
                v(f"weight_changed_activation_status:{c.case_id}:{anchor}")
            # count 불변.
            full_ref = synthesize_relationship_effect_vector(c.evidences, calibration=cal)
            full_w = synthesize_relationship_effect_vector(c.evidences, calibration=cal_w)
            if full_ref.evidence_count != full_w.evidence_count:
                v(f"weight_changed_evidence_count:{c.case_id}:{anchor}")
        # S0 A0.3 == production BASELINE.
        s0 = _axes(c.evidences, _anchor_cal("S0"))
        if base.axes.model_dump() != s0.model_dump():
            v(f"s0_not_baseline:{c.case_id}")
    return {"violations": viols, "passed": not viols}


def run(out_md: Path = OUT_MD, out_json: Path = OUT_JSON) -> dict:
    cases = build_lattice()
    act_oat = activation_bonus_oat()
    stab_oat = weight_oat(_STAB_PARAMS, "stability")
    sep_oat = weight_oat(_SEP_PARAMS, "separation")
    cross = structure_cross_check(act_oat, stab_oat)
    cov = coverage_matrix(cases, act_oat, stab_oat, sep_oat)
    inv = invariant_checks(cases)

    md = ["# P2-1C-2 harness — weight OAT × 구조 anchor(S0/S1/S2)", "",
          f"spec {EXPERIMENT_SPEC_VERSION} · calibration {RELATIONSHIP_CALIBRATION_VERSION} "
          f"· lattice {len(cases)} case. **감사 전용·읽기 전용·production delta 0.** OAT "
          "한 번에 하나·자동 clamp 없음(§5). anchor: S0(C0 0.3)·S1(C1 A0.15/P0.30)·"
          "S2(C1 A0.30/P0.15).", "",
          "## 0. 불변식 게이트(§11) + coverage(§2)", "",
          f"- 불변식 위반: **{len(inv['violations'])}** "
          f"({'PASS' if inv['passed'] else 'FAIL — ' + ', '.join(inv['violations'][:6])})",
          "- 검사: S0 A0.3==BASELINE · weight 하나 변경 시 비대상 축·status·count 불변",
          f"- **parameter coverage(14종): {'ALL COVERED' if cov['all_covered'] else 'MISSING ' + ', '.join(cov['uncovered'])}**",
          f"- 자극됐으나 sensitivity 0인 param: "
          f"{cov['zero_sensitivity'] if cov['zero_sensitivity'] else '없음'}",
          "",
          "## 0b. parameter coverage matrix(§2·§3)", "",
          "> 14 mutable parameter가 모두 자극됐는지 증명 + eligible-case(kind 존재) 평균 "
          "민감도(전체 평균 희석 배제).", "",
          "| parameter | exercised | nonzero | eligible_mean_|wide| |",
          "|---|--:|:--:|--:|"]
    for p, r in cov["rows"].items():
        md.append(f"| {p} | {r['exercised_case_count']} | "
                  f"{'✔' if r['nonzero_observed'] else '·'} | {r['eligible_mean_wide']} |")
    md += [
          "## 1. 구조 cross-check(§8 — factor routing 검증)", "",
          f"- stability OAT가 activation 구조(S0↔S1)에 불변: "
          f"**{cross['stability_oat_invariant_to_activation_structure']}**",
          f"- activation OAT가 pressure 구조(S0↔S2)에 불변: "
          f"**{cross['activation_oat_invariant_to_pressure_structure']}**",
          "> 두 값이 True면 factor routing 정상(activation 구조 차는 stability weight 효과에 "
          "무영향, pressure 구조 차는 activation bonus 효과에 무영향).", "",
          "## 2. activation kind bonus OAT — S0 sensitivity(local/wide)", "",
          "> parameter delta ≠ final activation delta(§4 — S1 dict bonus는 palace 가중 "
          "통과). local=±10%·wide=±20% finite difference.", "",
          "| 사례:kind | baseline | local | wide |", "|---|--:|--:|--:|"]
    for key, s in act_oat["S0"].items():
        md.append(f"| {key} | {s['baseline']} | {s['local']} | {s['wide']} |")

    md += ["", "## 3. stability weight OAT — S0 sensitivity", "",
           "| 사례:param | baseline(net) | local | wide |", "|---|--:|--:|--:|"]
    for key, s in stab_oat["grid"]["S0"].items():
        md.append(f"| {key} | {s['baseline']} | {s['local']} | {s['wide']} |")

    md += ["", "## 4. separation weight OAT — S0 sensitivity", "",
           "| 사례:param | baseline | local | wide |", "|---|--:|--:|--:|"]
    for key, s in sep_oat["grid"]["S0"].items():
        md.append(f"| {key} | {s['baseline']} | {s['local']} | {s['wide']} |")

    md += ["", "## 5. NOT_ADMISSIBLE profile(§5 — ordering 위반·자동 clamp 금지)", ""]
    inadm = sep_oat["inadmissible"]
    if inadm:
        md += [f"- separation ordering 위반 {len(inadm)}건(제외·미보정):",
               "", "| anchor | param | perturb | reason |", "|---|---|--:|---|"]
        for x in inadm[:12]:
            md.append(f"| {x['anchor']} | {x['param']} | {x['perturb']} | {x['reason']} |")
    else:
        md.append("- 없음 — 전 perturbation admissible(§1: 모든 sensitivity가 양측 "
                  "**central finite difference**·one-sided 없음).")

    md += ["", "## 6. 구조별 weight 민감도 대비(§8 — S0/S1/S2)", "",
           "> 같은 weight perturbation을 세 anchor에 적용. activation bonus는 S0=S2(pressure "
           "구조 차 무관), stability weight는 S0=S1(activation 구조 차 무관)이 정상.", "",
           "### stability pressure.CHUNG local sensitivity(anchor별)", "",
           "| 사례 | S0 | S1 | S2 |", "|---|--:|--:|--:|"]
    for c in cases:
        k = f"{c.case_id}:pressure.CHUNG"
        md.append(f"| {c.case_id} | {stab_oat['grid']['S0'][k]['local']} "
                  f"| {stab_oat['grid']['S1'][k]['local']} "
                  f"| {stab_oat['grid']['S2'][k]['local']} |")

    md += ["", "## 7. 관찰(§9·§10·§14 — Pareto·C2 보류)", "",
           "- 이 결과는 C0/C1 구조 shortlist 확정과 weight 감수 후보 추림에 쓴다. "
           "단일 점수 자동 채택·자동 최적 profile 선정 금지.",
           "- C2 진입(§10)은 stability에 적절한 pressure weight/factor가 separation을 "
           "지속 과대·과소하거나 그 역이 반복될 때만. 축별 finite-diff 값이 다르다는 "
           "사실만으로는 근거 아님(축 단위가 다르므로 derivative 상이는 정상).", ""]

    payload = {
        "experiment_spec_version": EXPERIMENT_SPEC_VERSION,
        "baseline_calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "lattice_case_count": len(cases),
        "invariants": inv,
        "structure_cross_check": cross,
        "coverage": cov,
        "inadmissible_separation_count": len(inadm),
    }
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = inv["passed"] and cov["all_covered"]
    return {"cases": len(cases), "violations": len(inv["violations"]),
            "invariants_passed": passed, "all_covered": cov["all_covered"],
            "cross_check": cross}


def main() -> int:
    r = run()
    print(f"P2-1C-2: {r['cases']} cases · violations {r['violations']} · "
          f"gate {'PASS' if r['invariants_passed'] else 'FAIL'} · "
          f"all_covered {r['all_covered']} · cross_check {r['cross_check']}")
    return 0 if r["invariants_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
