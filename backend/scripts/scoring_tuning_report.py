#!/usr/bin/env python3
"""Scoring Phase 1a 계수 튜닝 리포트 — 33차트 flag-on sidecar 분포 집계.

byeong_max_penalty/low_op_max_penalty/adjusted_floor_ratio 가 과하거나 약하지 않은지 판단용.
**실제 .score·랭킹 불변 — adjusted_score 는 리포트용.** Phase 1b 랭킹 실험은 이 리포트 이후 결정.
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §14

사용: python scripts/scoring_tuning_report.py [--year-window 20]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.scoring_operational import apply_operational_scoring
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[1]
_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
_DICTS = _BACKEND / "dictionaries"


def _calc(birth: BirthInput):
    from saju_api.services.manse_service import calculate
    return calculate(birth)


def _prime_sewoon(result, window: int) -> list:
    lc = result.luck_cycles
    out: list = []
    if lc is None:
        return out
    for dwi in lc.daewoon_table:
        if 20 <= dwi.start_age < 60:
            out += [p for p in (dwi.sewoon or []) if p.label.isdigit()]
    return out[:window]


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _dist(vals: list[float]) -> str:
    if not vals:
        return "n=0"
    return (f"n={len(vals)} mean={sum(vals) / len(vals):.1f} "
            f"p50={_pct(vals, 50):.1f} p90={_pct(vals, 90):.1f} max={max(vals):.1f}")


def _rank_shift(rows: list[dict]) -> list[int]:
    """레벨 풀 안에서 legacy vs adjusted 가상 rank_delta(level) — 실제 랭킹 불변."""
    by_legacy = sorted(rows, key=lambda r: -r["legacy_score"])
    by_adj = sorted(rows, key=lambda r: -r["operational_adjusted_score"])
    lr = {id(r): i + 1 for i, r in enumerate(by_legacy)}
    ar = {id(r): i + 1 for i, r in enumerate(by_adj)}
    return [ar[id(r)] - lr[id(r)] for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description="Scoring 1a 계수 튜닝 리포트")
    ap.add_argument("--year-window", type=int, default=20)
    args = ap.parse_args()

    cfg.SCORING_OPERATIONAL_SHADOW_ENABLED = True
    cfg.SCORING_OPERATIONAL_COMPONENTS = {
        "conditional_byeong_downgrade": True, "low_operability_yongsin": True}
    coef = cfg.SCORING_OPERATIONAL_COEF
    eng = EventEngineV2(_DICTS)
    charts = [json.loads(line) for line in _CHARTS.read_text(encoding="utf-8").splitlines()
              if line.strip()]

    pen_a: list[float] = []
    pen_b: list[float] = []
    deltas: list[float] = []          # abs(delta) for adjusted (penalized) rows
    floor_hits = 0
    scored = 0                        # ganji 있는 후보 수
    overlap = 0                       # A+B 동시
    per_chart: dict[str, list[float]] = {}
    by_level: dict[str, list[float]] = {"year": [], "daewoon": []}
    rank_abs: dict[str, list[int]] = {"year": [], "daewoon": []}
    rank_warn = 0
    top: list[tuple] = []

    for c in charts:
        cid = c["chart_id"]
        r = _calc(BirthInput(**c["input"]))
        if r.luck_cycles is None:
            continue
        dw = eng.score_legacy(r, levels={GanjiLevel.DAEWOON})
        yp = _prime_sewoon(r, args.year_window)
        yr = eng.score_legacy_years(r, [int(p.label) for p in yp])
        gbp = {f"{d.approx_start_date.year}~{d.approx_end_date.year}": d.ganji
               for d in r.luck_cycles.daewoon_table}
        level = {f"{d.approx_start_date.year}~{d.approx_end_date.year}": "daewoon"
                 for d in r.luck_cycles.daewoon_table}
        for p in yp:
            gbp[p.label] = p.ganji
            level[p.label] = "year"

        side = apply_operational_scoring(r, list(dw) + list(yr), gbp)
        # rank shift: 레벨별로 분리.
        per_level_rows: dict[str, list[dict]] = {"year": [], "daewoon": []}
        for s in side:
            if s.get("missing_ganji"):
                continue
            scored += 1
            d = -s["operational_score_delta"]      # 감점 크기(양수)
            pa = s["penalties"].get("conditional_byeong_downgrade", 0.0)
            pb = s["penalties"].get("low_operability_yongsin", 0.0)
            if pa:
                pen_a.append(pa)
            if pb:
                pen_b.append(pb)
            if pa and pb:
                overlap += 1
            if d > 0:
                deltas.append(d)
                per_chart.setdefault(cid, []).append(d)
                if lv := level.get(s["period"], ""):
                    by_level.setdefault(lv, []).append(d)
                if s["operational_adjusted_score"] == math.ceil(
                        s["legacy_score"] * coef["adjusted_floor_ratio"]):
                    floor_hits += 1
                top.append((d, cid, s["period"], s["event_key"], pa, pb))
            per_level_rows.setdefault(level.get(s["period"], ""), []).append(s)

        for lv, rows in per_level_rows.items():
            if lv not in ("year", "daewoon") or len(rows) < 2:
                continue
            pool = len(rows)
            thr = max(coef.get("rank_warn_abs", 3), math.ceil(pool * 0.05))
            for rd in _rank_shift(rows):
                rank_abs[lv].append(abs(rd))
                if abs(rd) >= thr:
                    rank_warn += 1

    floor_ratio = (floor_hits / scored * 100) if scored else 0.0
    print("=" * 72)
    print(f"Scoring 1a 계수 튜닝 리포트 — 차트 {len(charts)} · 채점 후보 {scored}")
    print(f"계수: byeong={coef['byeong_max_penalty']} low_op={coef['low_op_max_penalty']} "
          f"op_thr={coef['op_threshold']} floor_ratio={coef['adjusted_floor_ratio']}")
    print("=" * 72)
    print(f"1. A conditional_byeong_downgrade 감점:  {_dist(pen_a)}")
    print(f"   B low_operability_yongsin 감점:       {_dist(pen_b)}")
    print(f"2. total |operational_score_delta|:      {_dist(deltas)}")
    print(f"3. floor clamp hit: {floor_hits}/{scored} = {floor_ratio:.1f}% "
          f"({'무난' if floor_ratio < 3 else '검토' if floor_ratio < 10 else '과함'})")
    print("4. 차트별 평균/최대 감점(상위 8):")
    for cid, v in sorted(per_chart.items(), key=lambda x: -max(x[1]))[:8]:
        print(f"   {cid:<28} avg={sum(v) / len(v):.1f} max={max(v):.0f} n={len(v)}")
    print(f"5. level별 감점: year {_dist(by_level['year'])}")
    print(f"             daewoon {_dist(by_level['daewoon'])}")
    print(f"6. 가상 rank_delta(level, |값|): year {_dist([float(x) for x in rank_abs['year']])}")
    print(f"                            daewoon {_dist([float(x) for x in rank_abs['daewoon']])}")
    print(f"   rank WARN(상대임계 ≥max(3,5%pool)): {rank_warn}")
    print("7. top-8 감점 후보:")
    for d, cid, per, ek, pa, pb in sorted(top, reverse=True)[:8]:
        print(f"   −{d:.0f}  {cid:<24} {per:<12} {ek:<20} A={pa:.1f} B={pb:.1f}")
    print(f"8. A+B 중복 감점 후보: {overlap}")
    print("=" * 72)


if __name__ == "__main__":
    main()
