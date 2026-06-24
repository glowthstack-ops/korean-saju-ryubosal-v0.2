#!/usr/bin/env python3
"""Shadow Validation Harness CLI — 골든 차트 × (세운+대운) shadow 리포트 산출.

#9a/#9b shadow 를 일괄 산출해 legacy 대비 CSV/JSON 리포트로 저장한다. **검증 도구** —
운영 score/rank/favorability/final/polarity 는 건드리지 않으며(불변 스냅샷으로 확인), 산출물은
data/shadow_reports/ 에만 쓴다.

사용:
    python scripts/shadow_validation_harness.py \
        --charts data/shadow_charts/charts.jsonl --out-dir data/shadow_reports --top-n 20
    python scripts/shadow_validation_harness.py --dry-run   # 1 차트 smoke

규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §13
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from saju_manse_analysis import analyze_chart  # noqa: F401  (계산 경유 확인용)

from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.shadow_report import (
    REPORT_COLUMNS,
    build_shadow_report,
    invariance_snapshot,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[1]
_DICTS = _BACKEND / "dictionaries"


def _calculate(birth: BirthInput):
    """만세 결과 계산(서비스 계층 경유 — manse_service.calculate)."""
    from saju_api.services.manse_service import calculate
    return calculate(birth)


def _prime_sewoon(result, window: int) -> list:
    """장년기(start_age 20~60) 대운에 속한 세운(LuckPillar)을 window 개까지 — YEAR 후보 원천.

    기본 calculate 는 top-level yearly_luck 를 채우지 않으나(=0), 세운은 daewoon_table[].sewoon
    에 중첩돼 있다. 대운(10)과 비교 가능한 규모의 세운 표본을 장년기에서 추린다(날짜 비의존).
    """
    lc = result.luck_cycles
    out: list = []
    if lc is None:
        return out
    for dwi in lc.daewoon_table:
        if 20 <= dwi.start_age < 60:
            out += [p for p in (dwi.sewoon or []) if p.label.isdigit()]
    return out[:window]


def _luck_maps(result, year_pillars: list) -> tuple[dict[str, str], dict[str, str]]:
    """세운+대운 period(label) → 간지 / period → 레벨 매핑(candidate.period exact match)."""
    gbp: dict[str, str] = {}
    level: dict[str, str] = {}
    lc = result.luck_cycles
    if lc is None:
        return gbp, level
    for d in lc.daewoon_table:
        label = f"{d.approx_start_date.year}~{d.approx_end_date.year}"
        gbp[label] = d.ganji
        level[label] = "daewoon"
    for p in year_pillars:
        gbp[p.label] = p.ganji
        level[p.label] = "year"
    return gbp, level


def _process_chart(
    chart_id: str, birth: BirthInput, year_window: int
) -> tuple[list[dict], dict]:
    """단일 차트: 계산 → 대운(score_legacy) + 세운(score_legacy_years) → 리포트 + 불변(#6)."""
    result = _calculate(birth)
    engine = EventEngineV2(_DICTS)
    dw_cands = engine.score_legacy(result, levels={GanjiLevel.DAEWOON})
    year_pillars = _prime_sewoon(result, year_window)
    yr_cands = engine.score_legacy_years(result, [int(p.label) for p in year_pillars])
    cands = dw_cands + yr_cands
    gbp, level = _luck_maps(result, year_pillars)

    before = invariance_snapshot(result, cands)
    rows, summary = build_shadow_report(
        result, cands, gbp, chart_id=chart_id, period_level=level,
    )
    after = invariance_snapshot(result, cands)
    if before != after:  # Guard #6 — hard fail
        raise SystemExit(f"INVARIANCE VIOLATION on {chart_id}: shadow 산출이 운영값을 변경함")
    return rows, summary


def _load_charts(path: Path) -> list[tuple[str, BirthInput]]:
    out: list[tuple[str, BirthInput]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        out.append((rec["chart_id"], BirthInput(**rec["input"])))
    return out


def _write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(REPORT_COLUMNS))
        w.writeheader()
        w.writerows(rows)


def _top_n(rows: list[dict], n: int) -> list[dict]:
    """|score_delta|·|rank_delta_level| 큰 순 top-N(리뷰 대상). 랭킹은 레벨별 기준."""
    def key(r: dict) -> tuple[int, int]:
        return (abs(r["score_delta"]), abs(r["rank_delta_level"] or 0))
    return sorted(rows, key=key, reverse=True)[:n]


def main() -> None:
    ap = argparse.ArgumentParser(description="Shadow Validation Harness")
    ap.add_argument("--charts", default="data/shadow_charts/charts.jsonl")
    ap.add_argument("--out-dir", default="data/shadow_reports")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--year-window", type=int, default=20,
                    help="YEAR(세운) 후보 표본 수 — 장년기(20~60세) 세운에서 추림.")
    ap.add_argument("--dry-run", action="store_true",
                    help="첫 1 차트만 처리하고 파일 미저장(CI smoke).")
    args = ap.parse_args()

    charts = _load_charts(_BACKEND / args.charts)
    if args.dry_run:
        charts = charts[:1]

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for chart_id, birth in charts:
        rows, summary = _process_chart(chart_id, birth, args.year_window)
        all_rows.extend(rows)
        summaries.append(summary)
        print(f"[{chart_id}] rows={summary['rows']} "
              f"missing={summary['missing_ganji']} "
              f"WARN(score={summary['warn_score_delta']},rank={summary['warn_rank_delta']}) "
              f"errors={summary['errors']}")

    top = _top_n(all_rows, args.top_n)
    print(f"\n총 {len(all_rows)}행 / 차트 {len(charts)}개. "
          f"top-{args.top_n} |delta| 리뷰 대상:")
    for r in top:
        print(f"  {r['chart_id']:<18} {r['level']:<8} {r['period']:<12} {r['ganji']} "
              f"{r['event_key']:<22} score Δ{r['score_delta']:+d} "
              f"rankL Δ{r['rank_delta_level']} (G Δ{r['rank_delta_global']}) "
              f"[{r['expression_class']}] {r['warns']}")

    if args.dry_run:
        print("\n--dry-run: 파일 미저장.")
        return

    out_dir = _BACKEND / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(all_rows, out_dir / "shadow_report.csv")
    (out_dir / "shadow_report.json").write_text(
        json.dumps({"summaries": summaries, "top_n": top, "rows": all_rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장: {out_dir}/shadow_report.csv · shadow_report.json")


if __name__ == "__main__":
    main()
