#!/usr/bin/env python3
"""일주별 오늘의 운세 — 공합(왕지 없는 2자) 반합 제외 실험 측정(2026-10-25 데굴님 "실험 우선").

베타 pool `beta-daily-pool.c10.v2` 공개 창(2026-07-30~08-28, 30일 × 60일주 = 1,800장)을
`HALF_HARMONY_REQUIRES_ROYAL` False/True 두 모드로 렌더해 바뀐 카드 수·확률 변화 폭·top5 이동을
센다. 점수·배포는 바꾸지 않는다(측정 전용). 결과는 var/daily_gonghap_experiment_<날짜>.md.

사용: python scripts/measure_daily_gonghap.py [--from 2026-07-30 --to 2026-08-28]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

os.environ.update({
    "DAILY_BETA_POOL_ENABLED": "true", "DAILY_BETA_POOL_REQUIRED": "true",
    "DAILY_BETA_POOL_VERSION": "beta-daily-pool.c10.v2", "DAILY_BETA_AUDIENCE": "deployment",
    "DAILY_BETA_POOL_EFFECTIVE_FROM": "2026-07-30", "DAILY_BETA_POOL_EFFECTIVE_UNTIL": "2026-08-28",
    "DAILY_BETA_EXPECTED_POOL_FP":
        "f0ce1e0c20c80d892d6a28ac1a286bc2c2cf61fcac0d2209424b6c35f3414f68",
    "DAILY_BETA_EXPECTED_BOOTSTRAP_FP":
        "a499f3424dea1ead18c1f6cbe40f05012e53d9b8d314c025dd6b0951408e53e7",
})

from saju_api.services.daily_beta_registry import build_registry, render  # noqa: E402
from saju_engines import daily_ilju_fortune as dif  # noqa: E402
from saju_engines.daily_beta_pool import KST  # noqa: E402


def _ser(x: Any) -> Any:
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    if isinstance(x, (list, tuple)):
        return [_ser(v) for v in x]
    if isinstance(x, dict):
        return {k: _ser(v) for k, v in x.items()}
    if hasattr(x, "__dict__"):
        return {k: _ser(v) for k, v in vars(x).items()}
    return x


def _boards(days: list[dt.date], require_royal: bool) -> dict[str, dict[str, Any]]:
    dif.HALF_HARMONY_REQUIRES_ROYAL = require_royal
    reg = build_registry()
    out: dict[str, dict[str, Any]] = {}
    for d in days:
        board, audit = render(
            reg, d, now=dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=KST), allow_future=True,
        )
        out[d.isoformat()] = {"fp": audit.get("render_result_fingerprint"), "board": _ser(board)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-07-30")
    ap.add_argument("--to", dest="end", default="2026-08-28")
    args = ap.parse_args()
    s, e = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    days = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
    base = _boards(days, False)
    exp = _boards(days, True)
    changed_days = 0
    changed_cards = 0
    total_cards = 0
    prob_deltas: list[int] = []
    top5_moves = 0
    per_day: list[str] = []
    for d in days:
        k = d.isoformat()
        b, x = base[k]["board"], exp[k]["board"]
        day_changed = base[k]["fp"] != exp[k]["fp"]
        changed_days += int(day_changed)
        fb, fx = b.get("fortunes") or [], x.get("fortunes") or []
        day_cards = 0
        for cb, cx in zip(fb, fx, strict=False):
            total_cards += 1
            if cb != cx:
                day_cards += 1
                for eb, ex in zip(cb.get("events") or [], cx.get("events") or [], strict=False):
                    pb, px = eb.get("probability"), ex.get("probability")
                    if isinstance(pb, int) and isinstance(px, int) and pb != px:
                        prob_deltas.append(px - pb)
        changed_cards += day_cards
        tb, tx = b.get("top5") or {}, x.get("top5") or {}
        moves = sum(1 for key in set(tb) | set(tx) if tb.get(key) != tx.get(key))
        top5_moves += moves
        if day_changed:
            per_day.append(f"| {k} | {day_cards} | {moves} |")
    stamp = dt.date.today().strftime("%Y%m%d")
    out = _BACKEND.parent / "var" / f"daily_gonghap_experiment_{stamp}.md"
    avg = (sum(abs(v) for v in prob_deltas) / len(prob_deltas)) if prob_deltas else 0.0
    lines = [
        "# 일주 운세 공합 제외 실험 — HALF_HARMONY_REQUIRES_ROYAL False→True",
        f"기간 {args.start}~{args.end} · {len(days)}일 × 60일주 = {total_cards}장",
        "",
        f"- 지문 바뀐 날: {changed_days}/{len(days)}",
        f"- 바뀐 카드: {changed_cards}/{total_cards} ({changed_cards / max(total_cards, 1):.1%})",
        f"- 확률 변화: {len(prob_deltas)}건, 평균 |Δ| {avg:.2f}p, "
        f"최대 {max((abs(v) for v in prob_deltas), default=0)}p",
        f"- top5 축 이동(채널 단위): {top5_moves}",
        "", "| 날짜 | 바뀐 카드 | top5 이동 채널 |", "|---|---:|---:|", *per_day,
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"→ {out}")
    json.dump({"changed_days": changed_days, "changed_cards": changed_cards, "total": total_cards,
               "prob_deltas": prob_deltas, "top5_moves": top5_moves},
              open(out.with_suffix(".json"), "w", encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
