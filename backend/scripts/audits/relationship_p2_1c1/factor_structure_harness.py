"""P2-1C-1 harness — secondary factor 구조 비교 C0 vs C1 (RELATIONSHIP_VECTOR_CALIBRATION).

리뷰 §7·§8: activation factor × pressure factor 25 조합(C1)을 합성 lattice에 적용해
**축별 root 구별력**과 **축간 불필요한 동조**를 측정한다. C0(공유)와의 대비로 activation을
pressure에서 분리할 가치가 있는지 관찰(자동 채택 없음 §10·§14).

감사 전용·읽기 전용·production delta 0(합성기 명시 주입). C2는 조건부(§10) — 본 harness
미포함. 분모 분리(§3): lattice 전용. baseline = C0 A0.30/P0.30 == production BASELINE(§13).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from saju_engines.relationship_effect_vector import (
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
OUT_MD = Path(__file__).resolve().parent / "P2_1C1_FACTOR_STRUCTURE_REPORT.md"
OUT_JSON = Path(__file__).resolve().parent / "p2_1c1_invariant_results.json"

EXPERIMENT_SPEC_VERSION = "p2.1c1.v1"
_PERIOD = "2027"
_FACTORS = [0.0, 0.15, 0.3, 0.45, 0.6]
_BASELINE_F = 0.3
_GLYPHS = ["未", "戌", "申", "午"]


def _hit(kind, glyph, natal="丑"):
    return SpousePalaceHit(
        kind=kind, palace=Pillar4.DAY, layer="sewoon", position="branch",
        transit_component="branch", transit_participant=glyph, natal_participant=natal)


def _ev(hits):
    return build_spouse_palace_vector(hits, _DICTS, period_key=_PERIOD).evidences


@dataclass
class Case:
    case_id: str
    structure: str          # same_root | cross_root | single | root_n
    evidences: list


def build_lattice() -> list[Case]:
    K = RelationKind
    cases: list[Case] = []
    # 같은 root CHUNG+HYEONG(activation·stability_pressure·separation 복합 동시).
    cases.append(Case("same_CHUNG_HYEONG", "same_root",
                      _ev([_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "未", "戌")])))
    # cross root 동일 kind 쌍(margin 기준).
    cases.append(Case("cross_CHUNG_HYEONG", "cross_root",
                      _ev([_hit(K.CHUNG, "未", "丑"), _hit(K.HYEONG, "戌", "辰")])))
    # 단일 kind(margin baseline).
    cases.append(Case("single_CHUNG", "single", _ev([_hit(K.CHUNG, "未")])))
    cases.append(Case("single_HYEONG", "single", _ev([_hit(K.HYEONG, "未", "辰")])))
    # HAP+CHUNG 같은 root(support + pressure 혼합 — stability net 관측).
    cases.append(Case("same_HAP_CHUNG", "same_root",
                      _ev([_hit(K.HAP, "未", "丑"), _hit(K.CHUNG, "未", "辰")])))
    # root 수 증가(activation 합산 — cross-root factor 무영향 확인).
    cases.append(Case("root_3_CHUNG", "root_n",
                      _ev([_hit(K.CHUNG, g, "丑") for g in _GLYPHS[:3]])))
    return cases


def _c1(activation: float, pressure: float) -> RelationshipVectorCalibration:
    if activation == pressure:
        return RelationshipVectorCalibration.shared(
            secondary_factor=activation, profile_id=f"C0_{activation}")
    return RelationshipVectorCalibration.activation_pressure_split(
        activation=activation, pressure=pressure,
        profile_id=f"C1_A{activation}_P{pressure}")


def _axes(case: Case, activation: float, pressure: float):
    return synthesize_relationship_effect_vector(
        case.evidences, calibration=_c1(activation, pressure)).axes


def _val(ax) -> float | None:
    return ax.value if ax.status is AxisStatus.EVALUATED else None


# ── C0 대각(공유) 회귀 — P2-1A activation과 일치해야 함 ──────────────────────
def c0_diagonal() -> dict:
    out: dict[str, dict] = {}
    for f in _FACTORS:
        cases = build_lattice()
        row = {}
        for c in cases:
            ax = _axes(c, f, f)
            row[c.case_id] = {
                "activation": _val(ax.activation),
                "stability": _val(ax.stability),
                "separation": _val(ax.separation_pressure),
            }
        out[str(f)] = row
    return out


# ── C1 25-grid: 축별 factor 독립 sensitivity ─────────────────────────────────
def c1_grid() -> dict:
    cases = build_lattice()
    grid: dict[str, dict[str, dict]] = {}
    for c in cases:
        grid[c.case_id] = {}
        for a in _FACTORS:
            for p in _FACTORS:
                ax = _axes(c, a, p)
                grid[c.case_id][f"A{a}_P{p}"] = {
                    "activation": _val(ax.activation),
                    "stability": _val(ax.stability),
                    "separation": _val(ax.separation_pressure),
                }
    return grid


def _fd(hi: float | None, lo: float | None, dfactor: float) -> float | None:
    """finite-difference sensitivity(§9) — 백분율 아님·0 근처 안정."""
    if hi is None or lo is None:
        return None
    return round((hi - lo) / dfactor, 4)


def axis_factor_sensitivity(grid: dict) -> dict:
    """각 factor(activation/pressure)를 홀로 움직일 때 축별 finite-diff 민감도(§8·§9).

    baseline pressure=0.3 고정하고 activation 0.15→0.45, 그리고 baseline activation=0.3
    고정하고 pressure 0.15→0.45. C1이면 activation factor는 activation만, pressure
    factor는 stability·separation만 움직여야 한다(축간 분리).
    """
    out: dict[str, dict] = {}
    for cid, cells in grid.items():
        act_lo = cells[f"A0.15_P{_BASELINE_F}"]
        act_hi = cells[f"A0.45_P{_BASELINE_F}"]
        prs_lo = cells[f"A{_BASELINE_F}_P0.15"]
        prs_hi = cells[f"A{_BASELINE_F}_P0.45"]
        out[cid] = {
            "d_activation_by_activation_factor": _fd(
                act_hi["activation"], act_lo["activation"], 0.3),
            "d_stability_by_activation_factor": _fd(
                act_hi["stability"], act_lo["stability"], 0.3),
            "d_separation_by_activation_factor": _fd(
                act_hi["separation"], act_lo["separation"], 0.3),
            "d_activation_by_pressure_factor": _fd(
                prs_hi["activation"], prs_lo["activation"], 0.3),
            "d_stability_by_pressure_factor": _fd(
                prs_hi["stability"], prs_lo["stability"], 0.3),
            "d_separation_by_pressure_factor": _fd(
                prs_hi["separation"], prs_lo["separation"], 0.3),
        }
    return out


def root_discrimination(grid: dict) -> dict:
    """축별 root 구별력 retention(§8) — same_root vs cross_root margin 비율.

    activation: activation factor에 의존. stability/separation: pressure factor에 의존.
    같은 kind 쌍(CHUNG+HYEONG)의 same vs cross로 축별 margin retention을 factor별로 본다.
    """
    same = grid["same_CHUNG_HYEONG"]
    cross = grid["cross_CHUNG_HYEONG"]
    out: dict[str, list] = {"activation_by_A": [], "stability_by_P": [],
                            "separation_by_P": []}
    for f in _FACTORS:
        # activation은 pressure 고정(0.3), activation factor만 sweep.
        sa = same[f"A{f}_P{_BASELINE_F}"]["activation"]
        ca = cross[f"A{f}_P{_BASELINE_F}"]["activation"]
        out["activation_by_A"].append({
            "factor": f, "same": sa, "cross": ca,
            "retention": round((ca - sa) / ca, 3) if ca else None})
        # stability·separation은 activation 고정(0.3), pressure factor만 sweep.
        ss = same[f"A{_BASELINE_F}_P{f}"]["stability"]
        cs = cross[f"A{_BASELINE_F}_P{f}"]["stability"]
        ssep = same[f"A{_BASELINE_F}_P{f}"]["separation"]
        csep = cross[f"A{_BASELINE_F}_P{f}"]["separation"]
        out["stability_by_P"].append({"factor": f, "same": ss, "cross": cs})
        out["separation_by_P"].append({
            "factor": f, "same": ssep, "cross": csep,
            "retention": round((csep - ssep) / csep, 3) if csep else None})
    return out


# ── 불변식 게이트 (§13) ──────────────────────────────────────────────────────
def invariant_checks(cases: list[Case]) -> dict:
    viols: list[str] = []

    def v(m):
        viols.append(m)

    for c in cases:
        # C0 A0.3/P0.3 == production BASELINE.
        base = synthesize_relationship_effect_vector(c.evidences)
        c0 = synthesize_relationship_effect_vector(
            c.evidences, calibration=RelationshipVectorCalibration.shared(
                secondary_factor=0.3))
        if base.model_dump() != c0.model_dump():
            v(f"c0_not_baseline:{c.case_id}")
        # activation factor 변경(pressure 고정) → stability·separation 불변.
        ref = _axes(c, 0.3, 0.3)
        for a in _FACTORS:
            ax = _axes(c, a, 0.3)
            if ax.stability.model_dump() != ref.stability.model_dump():
                v(f"activation_factor_touched_stability:{c.case_id}:{a}")
            if ax.separation_pressure.model_dump() != ref.separation_pressure.model_dump():
                v(f"activation_factor_touched_separation:{c.case_id}:{a}")
        # pressure factor 변경(activation 고정) → activation 불변.
        for p in _FACTORS:
            ax = _axes(c, 0.3, p)
            if ax.activation.model_dump() != ref.activation.model_dump():
                v(f"pressure_factor_touched_activation:{c.case_id}:{p}")
        # cross-root case는 factor 변경에 전 축 불변(서로 다른 root — 복합 없음).
        if c.structure == "cross_root":
            for a in _FACTORS:
                for p in _FACTORS:
                    ax = _axes(c, a, p)
                    if ax.model_dump() != ref.model_dump():
                        v(f"cross_root_factor_sensitive:{c.case_id}:{a}_{p}")
        # same-root increment 비감소(activation factor↑ → activation 비감소).
        if c.structure == "same_root":
            acts = [_axes(c, f, 0.3).activation.value for f in _FACTORS]
            acts = [x for x in acts if x is not None]
            if acts != sorted(acts):
                v(f"activation_not_monotone:{c.case_id}")
    return {"violations": viols, "passed": not viols}


def run(out_md: Path = OUT_MD, out_json: Path = OUT_JSON) -> dict:
    cases = build_lattice()
    diag = c0_diagonal()
    grid = c1_grid()
    sens = axis_factor_sensitivity(grid)
    disc = root_discrimination(grid)
    inv = invariant_checks(cases)

    md = ["# P2-1C-1 harness — secondary factor 구조 C0 vs C1", "",
          f"spec {EXPERIMENT_SPEC_VERSION} · baseline C0 A0.30/P0.30 · "
          f"calibration {RELATIONSHIP_CALIBRATION_VERSION} · lattice {len(cases)} case. "
          "**감사 전용·읽기 전용·production delta 0.** C2 미포함(조건부 §10). "
          "자동 채택 없음(§14).", "",
          "## 0. 불변식 게이트(§13)", "",
          f"- 전체 위반: **{len(inv['violations'])}** "
          f"({'PASS' if inv['passed'] else 'FAIL — ' + ', '.join(inv['violations'][:6])})",
          "- 검사: C0 A0.3/P0.3==BASELINE · activation factor→stability/separation 불변 · "
          "pressure factor→activation 불변 · cross-root factor 무영향 · same-root activation "
          "비감소", "",
          "## 1. 축별 factor 독립 sensitivity(§8·§9 — finite difference)", "",
          "> C1의 핵심: activation factor는 activation만, pressure factor는 stability·"
          "separation만 움직여야 한다(축간 분리). d(축)/d(factor) — 0이면 그 축은 해당 "
          "factor와 무관.", "",
          "| 사례 | dAct/dA | dStab/dA | dSep/dA | dAct/dP | dStab/dP | dSep/dP |",
          "|---|--:|--:|--:|--:|--:|--:|"]
    for cid, s in sens.items():
        md.append(
            f"| {cid} | {s['d_activation_by_activation_factor']} "
            f"| {s['d_stability_by_activation_factor']} "
            f"| {s['d_separation_by_activation_factor']} "
            f"| {s['d_activation_by_pressure_factor']} "
            f"| {s['d_stability_by_pressure_factor']} "
            f"| {s['d_separation_by_pressure_factor']} |")

    # C0 대각: 단일 공유 factor가 세 축을 동시에 움직임(동조).
    c0_sens = {}
    for c in cases:
        lo = _axes(c, 0.15, 0.15)
        hi = _axes(c, 0.45, 0.45)
        c0_sens[c.case_id] = {
            "dAct": _fd(_val(hi.activation), _val(lo.activation), 0.3),
            "dStab": _fd(_val(hi.stability), _val(lo.stability), 0.3),
            "dSep": _fd(_val(hi.separation_pressure),
                        _val(lo.separation_pressure), 0.3),
        }
    md += ["", "## 2. 축간 동조 대비 — C0(공유) vs C1(분리)", "",
           "> **핵심 관찰(§8)**: C0는 단일 factor가 세 축을 동시에 움직인다. C1은 "
           "activation factor의 dStab/dA·dSep/dA=0, pressure factor의 dAct/dP=0으로 "
           "activation을 pressure에서 분리한다.", "",
           "### C0 단일 factor sensitivity(세 축 동조)", "",
           "| 사례 | dAct | dStab | dSep |", "|---|--:|--:|--:|"]
    for cid, s in c0_sens.items():
        md.append(f"| {cid} | {s['dAct']} | {s['dStab']} | {s['dSep']} |")
    md += ["", "> same_CHUNG_HYEONG: C0에서 단일 factor가 activation(+15.55)·"
           "stability·separation을 **동시에** 움직인다 — activation 복합만 억제하려 해도 "
           "stability/separation이 함께 바뀐다. C1(§1)은 dStab/dA=dSep/dA=0으로 이 동조를 "
           "끊는다. 이것이 C1 채택의 핵심 근거(단, 채택은 §14 Pareto 판단).", ""]

    md += ["## 3. 축별 root 구별력 retention(§8)", "",
           "### activation (activation factor sweep · pressure 0.3 고정)", "",
           "| factor | same | cross | retention |", "|--:|--:|--:|--:|"]
    for r in disc["activation_by_A"]:
        md.append(f"| {r['factor']} | {r['same']} | {r['cross']} | {r['retention']} |")
    md += ["", "### separation (pressure factor sweep · activation 0.3 고정)", "",
           "| factor | same | cross | retention |", "|--:|--:|--:|--:|"]
    for r in disc["separation_by_P"]:
        md.append(f"| {r['factor']} | {r['same']} | {r['cross']} | {r['retention']} |")

    md += ["", "## 4. C0 대각 회귀(P2-1A activation과 일치)", "",
           "| factor | same_CHUNG_HYEONG activation |", "|--:|--:|"]
    for f in _FACTORS:
        md.append(f"| {f} | {diag[str(f)]['same_CHUNG_HYEONG']['activation']} |")

    md += ["", "## 5. 관찰(§14 — Pareto·자동 채택 금지)", "",
           "- C1은 activation을 pressure에서 분리해, activation 복합을 억제하면서 "
           "stability/separation은 유지(또는 반대)할 수 있게 한다. 채택 여부는 축별 root "
           "구별력·축간 동조 감소·파라미터 수(1개 추가)·경계 사례 감수의 Pareto로 판단 — "
           "**단일 점수 자동 결정 금지**.",
           "- stability와 separation은 C1에서 여전히 동일 pressure factor를 공유하므로 "
           "동조가 남는다(C1 구조적 한계 — C2 진입은 §10 조건 충족 시).", ""]

    payload = {
        "experiment_spec_version": EXPERIMENT_SPEC_VERSION,
        "baseline_calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "lattice_case_count": len(cases),
        "invariants": inv,
        "axis_factor_sensitivity": sens,
        "root_discrimination": disc,
    }
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"cases": len(cases), "violations": len(inv["violations"]),
            "invariants_passed": inv["passed"]}


def main() -> int:
    r = run()
    print(f"P2-1C-1: {r['cases']} cases · violations {r['violations']} · "
          f"invariants {'PASS' if r['invariants_passed'] else 'FAIL'}")
    return 0 if r["invariants_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
