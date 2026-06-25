#!/usr/bin/env python3
"""신살 numeric shadow 하네스 CLI — 골든 차트 × (세운+대운) 신살 numeric 관측 리포트.

Phase B-1: 신살 numeric sidecar 를 일괄 산출해 legacy 대비 CSV/JSON 으로 저장한다. **검증 도구** —
운영 score/rank/favorability/polarity 는 건드리지 않으며(불변 스냅샷으로 확인), 산출물은
data/shadow_reports/ 에만 쓴다. 용신 operational 하네스(shadow_validation_harness.py)와 독립.

사용:
    python scripts/sinsal_shadow_harness.py \
        --charts data/shadow_charts/charts.jsonl --out-dir data/shadow_reports \
        --domain general --top-n 20
    python scripts/sinsal_shadow_harness.py --dry-run   # 1 차트 smoke

규격: doc/v2_2/SINSAL_MODIFIER_SPEC.md §10-1
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.sinsal_numeric_scoring import sinsal_invariance_snapshot
from saju_engines.sinsal_shadow_report import (
    SINSAL_REPORT_COLUMNS,
    build_sinsal_shadow_report,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_BACKEND = Path(__file__).resolve().parents[1]
_DICTS = _BACKEND / "dictionaries"


def _calculate(birth: BirthInput):
    from saju_api.services.manse_service import calculate
    return calculate(birth)


def _prime_sewoon(result, window: int) -> list:
    """장년기(start_age 20~60) 대운에 속한 세운(LuckPillar)을 window 개까지."""
    lc = result.luck_cycles
    out: list = []
    if lc is None:
        return out
    for dwi in lc.daewoon_table:
        if 20 <= dwi.start_age < 60:
            out += [p for p in (dwi.sewoon or []) if p.label.isdigit()]
    return out[:window]


def _luck_maps(result, year_pillars: list) -> tuple[dict[str, str], dict[str, str]]:
    """세운+대운 period → 간지 / period → 레벨 매핑."""
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
    chart_id: str, birth: BirthInput, year_window: int, domain: str,
) -> tuple[list[dict], dict]:
    """단일 차트: 계산 → 대운+세운 legacy 후보 → 신살 numeric 리포트 + 불변 검증."""
    result = _calculate(birth)
    engine = EventEngineV2(_DICTS)
    dw_cands = engine.score_legacy(result, levels={GanjiLevel.DAEWOON})
    year_pillars = _prime_sewoon(result, year_window)
    yr_cands = engine.score_legacy_years(result, [int(p.label) for p in year_pillars])
    cands = dw_cands + yr_cands
    gbp, level = _luck_maps(result, year_pillars)

    before = sinsal_invariance_snapshot(result, cands)
    rows, summary = build_sinsal_shadow_report(
        result, cands, gbp, chart_id=chart_id, period_level=level, domain=domain,
    )
    after = sinsal_invariance_snapshot(result, cands)
    if before != after:  # 불변 hard fail
        raise SystemExit(f"INVARIANCE VIOLATION on {chart_id}: shadow 산출이 운영값을 변경함")
    return rows, summary


def _load_charts(path: Path) -> list[tuple[str, BirthInput]]:
    out: list[tuple[str, BirthInput]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        rec = json.loads(line)
        out.append((rec["chart_id"], BirthInput(**rec["input"])))
    return out


def _write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(SINSAL_REPORT_COLUMNS))
        w.writeheader()
        w.writerows(rows)


def _magnitude(r: dict) -> float:
    return max(abs(r["favorability_delta"]), r["risk_delta"], r["mitigation_delta"])


def _top_n(rows: list[dict], n: int) -> list[dict]:
    return sorted(rows, key=_magnitude, reverse=True)[:n]


def main() -> None:
    ap = argparse.ArgumentParser(description="신살 numeric shadow 하네스")
    ap.add_argument("--charts", default="data/shadow_charts/charts.jsonl")
    ap.add_argument("--out-dir", default="data/shadow_reports")
    ap.add_argument("--domain", default="general")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--year-window", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="첫 1차트만, 파일 미저장")
    args = ap.parse_args()

    charts = _load_charts(_BACKEND / args.charts)
    if args.dry_run:
        charts = charts[:1]

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for chart_id, birth in charts:
        rows, summary = _process_chart(chart_id, birth, args.year_window, args.domain)
        all_rows += rows
        summaries.append(summary)
        warns = summary["warn_channel"]
        print(f"[{chart_id}] rows={summary['rows']} missing={summary['missing_ganji']} "
              f"WARN(channel={warns}) errors={summary['errors']}")

    total_warn = sum(s["warn_channel"] for s in summaries)
    print(f"\n총 {len(all_rows)}행 / 차트 {len(summaries)}개 / domain={args.domain} / "
          f"WARN channel={total_warn}. top-{args.top_n} |채널| 리뷰 대상:")
    for r in _top_n(all_rows, args.top_n):
        print(f"  {r['chart_id']:20s} {r['level']:8s} {r['period']:11s} {r['ganji']:5s} "
              f"{r['event_key']:20s} occ Δ{r['occurrence_score_delta']:+d} "
              f"fav{r['favorability_delta']:+.2f} risk{r['risk_delta']:.2f} "
              f"mit{r['mitigation_delta']:.2f} [{r['contributions']}]")

    if args.dry_run:
        print("\n(dry-run — 파일 미저장)")
        return
    out_dir = _BACKEND / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(all_rows, out_dir / "sinsal_shadow_report.csv")
    (out_dir / "sinsal_shadow_report.json").write_text(
        json.dumps({"summaries": summaries, "top_n": _top_n(all_rows, args.top_n),
                    "rows": all_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장: {out_dir / 'sinsal_shadow_report.csv'} · "
          f"{out_dir / 'sinsal_shadow_report.json'}")


if __name__ == "__main__":
    main()
