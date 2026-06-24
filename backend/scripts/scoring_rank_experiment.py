#!/usr/bin/env python3
"""Scoring Phase 1b — adjusted rank 실험 리포트(랭킹 미교체·관찰만).

1a sidecar(operational_adjusted_score)로 가상 랭킹을 계산해 legacy(=score_legacy 반환 순서) 대비
흔들림을 본다. **실제 .score·rank·reduce_candidates·LLM 불변.** A-only/B-only/A+B 분해 + low_op
10/14/15 시뮬(인자 주입·config 불변). 규격: §14-8

사용: python scripts/scoring_rank_experiment.py [--topn 10]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import saju_manse_analysis.yongsin.operational_role_config as cfg

from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.scoring_operational import rank_experiment_sidecar
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[1]
_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
_DICTS = _BACKEND / "dictionaries"

_A = {"conditional_byeong_downgrade": True, "low_operability_yongsin": False}
_B = {"conditional_byeong_downgrade": False, "low_operability_yongsin": True}
_AB = {"conditional_byeong_downgrade": True, "low_operability_yongsin": True}


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
    return s[max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))]


def _dist(vals: list[float]) -> str:
    if not vals:
        return "n=0"
    a = [abs(v) for v in vals]
    return (f"n={len(a)} mean={sum(a) / len(a):.2f} p50={_pct(a, 50):.0f} "
            f"p90={_pct(a, 90):.0f} max={max(a):.0f}")


def _chart_inputs(window: int):
    eng = EventEngineV2(_DICTS)
    charts = [json.loads(line) for line in _CHARTS.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    for c in charts:
        r = _calc(BirthInput(**c["input"]))
        if r.luck_cycles is None:
            continue
        dw = eng.score_legacy(r, levels={GanjiLevel.DAEWOON})
        yp = _prime_sewoon(r, window)
        yr = eng.score_legacy_years(r, [int(p.label) for p in yp])
        gbp = {f"{d.approx_start_date.year}~{d.approx_end_date.year}": d.ganji
               for d in r.luck_cycles.daewoon_table}
        level = {f"{d.approx_start_date.year}~{d.approx_end_date.year}": "daewoon"
                 for d in r.luck_cycles.daewoon_table}
        for p in yp:
            gbp[p.label] = p.ganji
            level[p.label] = "year"
        yield c["chart_id"], r, list(dw) + list(yr), gbp, level


def _aggregate(rows_per_chart: list[tuple[str, list[dict]]], topn: int) -> dict:
    """op_rank_delta_level(순수 operational penalty 효과) 기준 집계 — confound 제거."""
    by_level: dict[str, list[int]] = {"year": [], "daewoon": []}
    left = 0
    left_list: list[tuple] = []
    chart_max: dict[str, int] = {}
    for cid, rows in rows_per_chart:
        for r in rows:
            if r["level"] in by_level:
                by_level[r["level"]].append(r["op_rank_delta_level"])
            chart_max[cid] = max(chart_max.get(cid, 0), abs(r["op_rank_delta_level"]))
            if r["op_left_topn"]:
                left += 1
                left_list.append((cid, r["level"], r["period"], r["event_key"]))
    return {"by_level": by_level, "left": left, "left_list": left_list,
            "chart_max": chart_max}


def _run(inputs, components, coef_override, topn) -> list[tuple[str, list[dict]]]:
    out = []
    for cid, r, cands, gbp, level in inputs:
        rows = rank_experiment_sidecar(r, cands, gbp, level, components=components,
                                       coef_override=coef_override, topn=topn) or []
        out.append((cid, rows))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Scoring 1b adjusted rank 실험")
    ap.add_argument("--topn", type=int, default=cfg.SCORING_OPERATIONAL_RANK_TOPN)
    ap.add_argument("--year-window", type=int, default=20)
    args = ap.parse_args()
    cfg.SCORING_OPERATIONAL_RANK_EXPERIMENT_ENABLED = True

    inputs = list(_chart_inputs(args.year_window))  # 1회 계산 후 재사용.
    print("=" * 72)
    print(f"Scoring 1b adjusted rank 실험 — 차트 {len(inputs)} · topN={args.topn} "
          f"(실제 .score·rank·reduce·LLM 불변)")
    print("※ op_rank_delta = score 베이스라인 대비 순수 operational penalty 효과(confound 제거).")
    print("=" * 72)

    print("[component별 op_rank_delta_level 분포 + op top-N 이탈]")
    for label, comp in (("A-only", _A), ("B-only", _B), ("A+B", _AB)):
        agg = _aggregate(_run(inputs, comp, None, args.topn), args.topn)
        print(f"  {label:<7} year {_dist([float(x) for x in agg['by_level']['year']])}")
        print(f"  {'':<7} daewoon {_dist([float(x) for x in agg['by_level']['daewoon']])}"
              f" | topN 이탈 {agg['left']}")

    print("[low_op 시뮬(인자 주입·config 불변) — rank_delta_level]")
    for label, comp in (("B-only", _B), ("A+B", _AB)):
        for lo in (10, 14, 15):
            agg = _aggregate(_run(inputs, comp, {"low_op_max_penalty": float(lo)},
                                  args.topn), args.topn)
            allv = agg["by_level"]["year"] + agg["by_level"]["daewoon"]
            print(f"  {label:<7} low_op={lo:<3} {_dist([float(x) for x in allv])}"
                  f" | topN 이탈 {agg['left']}")

    print("[A+B 차트별 max |rank shift| 상위 8]")
    agg = _aggregate(_run(inputs, _AB, None, args.topn), args.topn)
    for cid, mx in sorted(agg["chart_max"].items(), key=lambda x: -x[1])[:8]:
        print(f"  {cid:<28} max={mx}")
    print(f"[A+B top-N 이탈 후보 {agg['left']} — 상위 8]")
    for cid, lv, per, ek in agg["left_list"][:8]:
        print(f"  {cid:<24} {lv:<8} {per:<12} {ek}")
    cfg_lo = cfg.SCORING_OPERATIONAL_COEF["low_op_max_penalty"]
    print(f"config 불변 확인: low_op_max_penalty={cfg_lo}")
    print("=" * 72)


if __name__ == "__main__":
    main()
