"""P2-1D shortlist harness — 7 profile × 331 harness (RELATIONSHIP_VECTOR_CALIBRATION).

리뷰 §6~§10: C0/C1 구조 + 민감 weight 단일 변경 profile 5~8개를 실 명식 harness에 적용해
분포·review flag·경계 사례를 만든다. **자동 최적 profile 선정 없음** — P2-3 감수 자료만
산출. 감사 전용·읽기 전용·production delta 0(합성기 명시 주입·BASELINE=D0).

임계값은 사전 등록(SSOT §3-3, 결과 관찰 전 고정): band collapse 85%·root=1
overactivation max(2×, +10%p)·root≥2 underactivation −20%p 또는 ½. 하드 불변식 외
자동 탈락 없음 — review flag는 중첩 가능.

profile당 변경 최소(구조 1 + factor 1 + weight 1~2, §7). C2 없음(§10). 분모 분리
(331 harness 전용 — fixture·lattice 미합산 §8).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_api.services.relationship_vector_sidecar import synthesize_period_vector
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_emergence_modifier import analyze_marriage_emergence_natal
from saju_engines.marriage_timing_profile import marriage_engine_flags
from saju_engines.relationship_effect_vector import (
    RELATIONSHIP_CALIBRATION_VERSION,
    RelationshipVectorCalibration,
)
from saju_engines.relationship_structure_modifiers import (
    build_relationship_structure_modifiers,
)
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.relationship_effect import AxisStatus

_DICTS = Path(__file__).resolve().parents[3] / "dictionaries"
OUT_MD = Path(__file__).resolve().parent / "P2_1D_SHORTLIST_REPORT.md"
OUT_JSON = Path(__file__).resolve().parent / "p2_1d_results.json"

EXPERIMENT_SPEC_VERSION = "p2.1d.v1"
_TODAY = date(2026, 7, 24)

# 사전 등록 임계값(SSOT §3-3).
_COLLAPSE_SHARE = 0.85
_COLLAPSE_MIN_N = 20
_OVERACT_ABS = 0.10
_UNDERACT_ABS = 0.20
_UNDERACT_RATIO = 0.5

# 331 harness fixture(P1-7과 동일 6 명식 — 성별×음양 stratified).
_FIXTURES = [
    ("F1", BirthInput(calendar_type="solar", birth_date=date(1985, 3, 15),
                      birth_time="14:30", birth_place_name="서울", gender="female")),
    ("M1", BirthInput(calendar_type="solar", birth_date=date(1988, 6, 20),
                      birth_time="09:00", birth_place_name="서울", gender="male")),
    ("F2", BirthInput(calendar_type="solar", birth_date=date(1992, 11, 5),
                      birth_time="22:00", birth_place_name="부산", gender="female")),
    ("M2", BirthInput(calendar_type="solar", birth_date=date(1979, 2, 14),
                      birth_time="06:00", birth_place_name="서울", gender="male")),
    ("M3y", BirthInput(calendar_type="solar", birth_date=date(1990, 1, 10),
                       birth_time="10:00", birth_place_name="서울", gender="male")),
    ("F3y", BirthInput(calendar_type="solar", birth_date=date(1993, 12, 1),
                       birth_time="10:00", birth_place_name="서울", gender="female")),
]


def _base_dicts():
    from saju_engines.relationship_effect_vector import (
        _SEP_WEIGHT,
        _STAB_PRESSURE,
        _STAB_SUPPORT,
    )
    return dict(_STAB_SUPPORT), dict(_STAB_PRESSURE), dict(_SEP_WEIGHT)


def build_profiles() -> dict[str, RelationshipVectorCalibration]:
    """shortlist 7 profile(§6) — profile당 단일 변경(추적 가능)."""
    C = RelationshipVectorCalibration
    sup, prs, sep = _base_dicts()
    # D4: stability.pressure.CHUNG 한 단계 하향(-20%).
    prs_d4 = dict(prs)
    prs_d4["CHUNG"] = round(prs["CHUNG"] * 0.8, 6)
    # D5: separation 지배 weight(CHUNG) 하향(ordering 유지 — 0.8 ≥ 나머지).
    sep_d5 = dict(sep)
    sep_d5["CHUNG"] = round(sep["CHUNG"] * 0.8, 6)
    # D6: support.HAP 상향(+20%).
    sup_d6 = dict(sup)
    sup_d6["HAP"] = round(sup["HAP"] * 1.2, 6)
    return {
        "D0_baseline": C.shared(secondary_factor=0.3, profile_id="D0_baseline"),
        "D1_C1_act_conservative": C.activation_pressure_split(
            activation=0.15, pressure=0.3, profile_id="D1_C1_act_conservative"),
        "D2_C1_prs_conservative": C.activation_pressure_split(
            activation=0.3, pressure=0.15, profile_id="D2_C1_prs_conservative"),
        # D3: CHUNG activation bonus 하향은 dict(S1) — calibration 밖이라 evidence 스케일
        #     필요. 본 harness는 calibration 단위 profile만 다루므로 D3는 별도 노트로 남기고
        #     구조·factor·weight profile(D0~D2·D4~D6)만 331 확장(§7 단일 변경 유지).
        "D4_stab_CHUNG_conservative": C.shared(
            secondary_factor=0.3, profile_id="D4_stab_CHUNG_conservative",
            stability_pressure=prs_d4),
        "D5_sep_conservative": C.shared(
            secondary_factor=0.3, profile_id="D5_sep_conservative",
            separation_weight=sep_d5),
        "D6_HAP_support_up": C.shared(
            secondary_factor=0.3, profile_id="D6_HAP_support_up",
            stability_support=sup_d6),
    }


@dataclass
class PeriodInput:
    fixture: str
    layer: str
    label: str
    proj: object
    natal_mt2: object
    static_modifiers: list
    chart: object


def build_period_inputs() -> list[PeriodInput]:
    """6 명식 채점 → 기간별 합성 입력(projection·natal·modifier). 331 harness 재료."""
    out: list[PeriodInput] = []
    for tag, birth in _FIXTURES:
        chart = calculate(birth.model_copy(update={"reference_date": _TODAY}))
        eng = EventEngineV2(_DICTS, **marriage_engine_flags())
        eng.score(chart, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
        projs = eng.take_relationship_shadow()
        natal_mt2 = analyze_marriage_emergence_natal(chart)
        static_mods = build_relationship_structure_modifiers(
            detect_structure_patterns(chart, dictionaries_dir=_DICTS))
        for proj in projs:
            out.append(PeriodInput(tag, proj.layer, proj.label, proj,
                                   natal_mt2, static_mods, chart))
    return out


def _synth(pi: PeriodInput, cal):
    return synthesize_period_vector(
        pi.proj, pi.chart, pi.natal_mt2, pi.static_modifiers,
        dictionaries_dir=_DICTS, calibration=cal)


def _band(ax):
    return ax.band if ax.status is AxisStatus.EVALUATED else None


def _sign(v):
    if v is None:
        return None
    return "pos" if v > 0 else "neg" if v < 0 else "zero"


def measure(period_inputs, profiles) -> dict:
    """profile × period 벡터 → 분포·root별 strong rate."""
    grid: dict[str, list] = {p: [] for p in profiles}
    for name, cal in profiles.items():
        for pi in period_inputs:
            try:
                v = _synth(pi, cal)
            except Exception:  # noqa: BLE001 — 기간 실패는 감사에서 스킵
                continue
            grid[name].append({
                "fixture": pi.fixture, "layer": pi.layer, "label": pi.label,
                "roots": v.independent_root_trigger_count,
                "act_status": v.axes.activation.status.value,
                "act_band": _band(v.axes.activation),
                "stab_sign": _sign(v.axes.stability.value
                                   if v.axes.stability.status is AxisStatus.EVALUATED
                                   else None),
                "sep_band": _band(v.axes.separation_pressure),
            })
    return grid


def _band_dist(rows) -> dict:
    c = Counter(r["act_band"] for r in rows if r["act_band"] is not None)
    return dict(c)


def _root_strong_rate(rows, root_filter) -> tuple[int, float | None]:
    elig = [r for r in rows
            if r["act_status"] == "evaluated" and root_filter(r["roots"])]
    if not elig:
        return 0, None
    strong = sum(1 for r in elig if r["act_band"] == "strong")
    return len(elig), round(strong / len(elig), 3)


def review_flags(grid) -> dict:
    """사전 등록 임계값(§3-3)으로 profile별 review flag(자동 탈락 아님)."""
    base = grid["D0_baseline"]
    _, base_r1 = _root_strong_rate(base, lambda n: n == 1)
    _, base_r2 = _root_strong_rate(base, lambda n: n >= 2)
    out: dict = {}
    for name, rows in grid.items():
        flags: list[str] = []
        # band collapse(전체 evaluated).
        dist = _band_dist(rows)
        n_eval = sum(dist.values())
        if n_eval >= _COLLAPSE_MIN_N and dist:
            top = max(dist.values()) / n_eval
            if top >= _COLLAPSE_SHARE:
                flags.append("REVIEW_COLLAPSE")
        # root=1 overactivation.
        n1, r1 = _root_strong_rate(rows, lambda n: n == 1)
        if base_r1 is not None and r1 is not None and n1 >= _COLLAPSE_MIN_N:
            thr = max(base_r1 * 2, base_r1 + _OVERACT_ABS)
            if r1 >= thr:
                flags.append("REVIEW_OVERACTIVATION")
        # root≥2 underactivation.
        _, r2 = _root_strong_rate(rows, lambda n: n >= 2)
        if base_r2 is not None and r2 is not None:
            if r2 <= base_r2 - _UNDERACT_ABS or r2 <= base_r2 * _UNDERACT_RATIO:
                flags.append("REVIEW_UNDERACTIVATION")
        out[name] = {
            "status": "PASS" if not flags else "+".join(flags),
            "flags": flags,
            "band_dist": dist, "n_eval": n_eval,
            "root1_strong_rate": r1, "root2plus_strong_rate": r2,
        }
    return {"per_profile": out, "baseline_root1": base_r1, "baseline_root2plus": base_r2}


def boundary_cases(grid, profiles) -> list[dict]:
    """profile disagreement 기반 경계 사례(§8) — 사례 단위 profile 판단 갈림."""
    names = list(profiles)
    # period key로 정렬 정렬.
    by_key: dict[tuple, dict] = {}
    for name in names:
        for r in grid[name]:
            k = (r["fixture"], r["layer"], r["label"])
            by_key.setdefault(k, {})[name] = r
    cases: list[dict] = []
    for k, per in by_key.items():
        if len(per) < len(names):
            continue
        bands = {per[n]["act_band"] for n in names}
        signs = {per[n]["stab_sign"] for n in names}
        seps = {per[n]["sep_band"] for n in names}
        # C0(D0) vs C1(D1/D2) band·sign 차이 우선.
        c0 = per["D0_baseline"]
        disagree = 0
        reasons = []
        if len(bands) > 1:
            disagree += 1
            reasons.append("act_band")
        if len(signs) > 1:
            disagree += 1
            reasons.append("stab_sign")
        if len(seps) > 1:
            disagree += 1
            reasons.append("sep_band")
        if c0["act_band"] != per["D1_C1_act_conservative"]["act_band"]:
            reasons.append("C0!=C1act_band")
        if disagree == 0 and "C0!=C1act_band" not in reasons:
            continue
        cases.append({
            "key": list(k), "roots": c0["roots"], "disagree_axes": disagree,
            "reasons": reasons,
            "profiles": {n: {"act": per[n]["act_band"], "stab": per[n]["stab_sign"],
                             "sep": per[n]["sep_band"]} for n in names},
        })
    cases.sort(key=lambda x: (-x["disagree_axes"], x["key"]))
    return cases


def run(out_md: Path = OUT_MD, out_json: Path = OUT_JSON) -> dict:
    profiles = build_profiles()
    period_inputs = build_period_inputs()
    grid = measure(period_inputs, profiles)
    flags = review_flags(grid)
    boundaries = boundary_cases(grid, profiles)
    n_periods = len(period_inputs)

    md = ["# P2-1D shortlist harness — 7 profile × 331 harness", "",
          f"spec {EXPERIMENT_SPEC_VERSION} · calibration {RELATIONSHIP_CALIBRATION_VERSION} "
          f"· fixture {len(_FIXTURES)}·기간 {n_periods}. **감사 전용·읽기 전용·production "
          "delta 0.** 자동 최적 선정 없음(§10) — P2-3 감수 자료. 임계값 사전 등록"
          "(SSOT §3-3). D3(CHUNG bonus)는 dict(S1) 변경이라 별도(§7 단일 변경 유지 — 본 "
          "harness는 calibration 단위 6 profile).", "",
          "## 0. 사전 등록 임계값(§3-3 — 결과 관찰 전 고정)", "",
          f"- band collapse ≥ {_COLLAPSE_SHARE} (eligible n≥{_COLLAPSE_MIN_N}, EVALUATED만)",
          f"- root=1 overactivation ≥ max(baseline×2, baseline+{_OVERACT_ABS})",
          f"- root≥2 underactivation ≤ baseline−{_UNDERACT_ABS} 또는 baseline×{_UNDERACT_RATIO}",
          f"- baseline root=1 strong {flags['baseline_root1']}·root≥2 strong "
          f"{flags['baseline_root2plus']}", "",
          "## 1. profile별 review flag(자동 탈락 아님·중첩 가능)", "",
          "| profile | status | act band 분포 | root1 strong | root2+ strong |",
          "|---|---|---|--:|--:|"]
    for name, r in flags["per_profile"].items():
        md.append(f"| {name} | {r['status']} | "
                  f"{json.dumps(r['band_dist'], ensure_ascii=False)} "
                  f"| {r['root1_strong_rate']} | {r['root2plus_strong_rate']} |")

    md += ["", "## 2. profile disagreement 경계 사례(§8 — P2-3 감수용 상위 15)", "",
           f"총 {len(boundaries)}건. band/sign/sep 판단이 갈리는 사례.", "",
           "| roots | 갈림축수 | reasons | D0 | D1 | D2 | D4 | D5 | D6 |",
           "|--:|--:|---|---|---|---|---|---|---|"]
    for c in boundaries[:15]:
        p = c["profiles"]

        def _cell(n, p=p):
            return f"{p[n]['act'] or '·'}/{p[n]['stab'] or '·'}"
        md.append(
            f"| {c['roots']} | {c['disagree_axes']} | {','.join(c['reasons'])} "
            f"| {_cell('D0_baseline')} | {_cell('D1_C1_act_conservative')} "
            f"| {_cell('D2_C1_prs_conservative')} | {_cell('D4_stab_CHUNG_conservative')} "
            f"| {_cell('D5_sep_conservative')} | {_cell('D6_HAP_support_up')} |")

    md += ["", "## 3. 관찰(§10·§11 — 자동 채택 없음)", "",
           "- 이 자료는 P2-3 사람 감수용이다. review flag가 붙은 profile도 통계 모양만으로 "
           "제거하지 않는다. C0/C1 최종 채택은 감수에서(activation에 낮은 factor·pressure에 "
           "다른 factor가 여러 의미 사례에서 반복 적절할 때만 C1).",
           "- 하드 불변식·NOT_ADMISSIBLE·production delta는 별도 게이트(FAIL) — 본 harness "
           "profile은 전부 admissible(D5 separation ordering 유지). 분모 분리: 331 harness "
           "전용(fixture·lattice 미합산).", ""]

    payload = {
        "experiment_spec_version": EXPERIMENT_SPEC_VERSION,
        "baseline_calibration_version": RELATIONSHIP_CALIBRATION_VERSION,
        "period_count": n_periods, "profile_count": len(profiles),
        "thresholds": {"collapse_share": _COLLAPSE_SHARE,
                       "collapse_min_n": _COLLAPSE_MIN_N,
                       "overact_abs": _OVERACT_ABS, "underact_abs": _UNDERACT_ABS,
                       "underact_ratio": _UNDERACT_RATIO},
        "review_flags": flags,
        "boundary_case_count": len(boundaries),
    }
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"profiles": len(profiles), "periods": n_periods,
            "boundary_cases": len(boundaries)}


def main() -> int:
    r = run()
    print(f"P2-1D: {r['profiles']} profile · {r['periods']} 기간 · "
          f"boundary {r['boundary_cases']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
