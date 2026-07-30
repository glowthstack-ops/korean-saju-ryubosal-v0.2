#!/usr/bin/env python3
"""OA-11f-F — 2026-04-02 단일 anchor 퇴행 포렌식 (측정 전용).

R6 는 family gate 를 5/5 로 닫았지만 **이미 통과했던** 2026-04-02 에서
family qualifying 59→58 · key_below_15 1→2 로 후퇴했다. R7 에서는 같은 anchor 에
퇴행이 없었다.

`p10` 과 `qualifying` 은 대체 가능한 지표가 아니다 — 전자는 하위 꼬리 대표값의
게이트, 후자는 이미 양호했던 일주를 문턱 아래로 밀지 않는지 보는 안전장치다.
그래서 어떤 일주가 어떤 교환으로 내려갔는지 일주 단위로 특정한다.

S0 · R6 · R7 을 같은 루프에서 병행 재생한다(각자 독립 이력).
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_oa11f_b_online_replay as B  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    repeat_severity,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

ANCHOR = dt.date(2026, 4, 2)
_END = ANCHOR - dt.timedelta(days=1)          # 창 마지막 날까지 재생
VARIANTS = {"S0": None, "R6": 6, "R7": 7}


class _Run:
    def __init__(self, name: str, limit: int | None) -> None:
        self.name = name
        self.limit = limit
        self.hh: dict[str, list[str]] = collections.defaultdict(list)
        self.gh: dict[str, list[str]] = collections.defaultdict(list)
        self.lineage: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        self.interventions = 0


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    runs = {n: _Run(n, lim) for n, lim in VARIANTS.items()}

    first_sel_div: dict[str, str | None] = {"R6": None, "R7": None}
    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= _END:
        ctx = M.build_day_context(day)
        picks: dict[str, dict[str, str]] = {n: {} for n in runs}
        for name, r in runs.items():
            raw: dict[str, HeadlineCandidate] = {}
            cmap: dict[str, list[HeadlineCandidate]] = {}
            for idx, ilju in enumerate(B._ILJUS):
                stem, branch = ganzi_from_index(idx)
                seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
                scored = [
                    M._score_event(k, e, stem, branch, ctx) for k, e in events.items()
                ]
                goods = [
                    (s.event_key, s.probability) for s in scored
                    if s.valence == "good"
                    and "good" in (events[s.event_key].get("headline_slots")
                                   or events[s.event_key]["slots"])
                ]
                if not goods:
                    continue
                ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
                raw_key, raw_p = ranked[0]
                window = tuple(r.hh[ilju][-B._LOOKBACK:])
                families = {family_of.get(k, k) for k in window}
                chosen = None
                if r.limit is not None:
                    deficit = len(families) < C10_POLICY.coverage_floor
                    clean = repeat_severity(r.gh[ilju], raw_key) == SEVERITY_CLEAN
                    if deficit and clean:
                        options = B._safe_candidates(
                            scored, seed, events, ranked, raw_key, raw_p, window,
                            family_of, loss_limit=r.limit,
                        )
                        chosen = B._pick("B1", options) if options else None
                if chosen is not None:
                    r.interventions += 1
                    g, c, s = chosen["slots"]
                    cands = chosen["cands"]
                    pick = chosen["event_key"]
                    r.lineage[ilju].append({
                        "date": day.isoformat(), "selection": pick,
                        "rank": chosen["rank"], "loss": chosen["loss"],
                        "family_delta": chosen["fam_cov"],
                        "key_delta": chosen["key_cov"],
                        "family_qual_delta": chosen["fam_qual"],
                        "key_qual_delta": chosen["key_qual"],
                    })
                else:
                    rep = select_good_representative(
                        goods, r.gh[ilju], B._BUDGET, policy=C10_POLICY,
                        family_of=family_of, headline_history=r.hh[ilju],
                    )
                    g, c, s = M._select_slots(
                        scored, seed, good_override=rep.display_good_representative
                    )
                    cands = M._headline_candidates(g, s, c, M._band(g, c))
                    pick = rep.display_good_representative
                cmap[ilju] = [
                    HeadlineCandidate(x.event_key, x.domain, x.probability)
                    for x in cands
                ]
                raw[ilju] = cmap[ilju][0]
                r.gh[ilju].append(pick)
                picks[name][ilju] = pick
            result = select_board(
                raw, cmap, r.hh, domain_cap=21, event_cap=10,
                max_displacement_cost=B._BUDGET, policy=B._BOARD,
                today=day.toordinal(),
            )
            for ilju, sel in result.selections.items():
                r.hh[ilju].append(sel.event_key)
        for variant in ("R6", "R7"):
            if first_sel_div[variant] is None and picks[variant] != picks["S0"]:
                first_sel_div[variant] = day.isoformat()
        day += dt.timedelta(days=1)

    def coverage(r: _Run) -> dict[str, dict[str, int]]:
        out = {}
        for ilju in B._ILJUS:
            w = tuple(r.hh[ilju][-B._LOOKBACK:])
            out[ilju] = {
                "key": len(set(w)),
                "family": len({family_of.get(k, k) for k in w}),
            }
        return out

    cov = {n: coverage(r) for n, r in runs.items()}
    crossings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for variant in ("R6", "R7"):
        down_f, up_f, down_k, up_k = [], [], [], []
        for ilju in B._ILJUS:
            a, b = cov["S0"][ilju], cov[variant][ilju]
            row = {"ilju": ilju, "s0": a, variant.lower(): b}
            if a["family"] >= 15 > b["family"]:
                down_f.append(row)
            elif a["family"] < 15 <= b["family"]:
                up_f.append(row)
            if a["key"] >= 15 > b["key"]:
                down_k.append(row)
            elif a["key"] < 15 <= b["key"]:
                up_k.append(row)
        crossings[variant] = {
            "family_dropped_below_15": down_f,
            "family_rose_to_15": up_f,
            "key_dropped_below_15": down_k,
            "key_rose_to_15": up_k,
        }

    affected = sorted({
        r["ilju"] for v in crossings.values() for k, rows in v.items()
        if "dropped" in k for r in rows
    })
    return {
        "audit_id": "OA-11f-F",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "anchor": ANCHOR.isoformat(),
        "window": f"{(ANCHOR - dt.timedelta(days=90)).isoformat()} ~ {_END.isoformat()}",
        "interventions": {n: r.interventions for n, r in runs.items()},
        "first_selection_divergence": first_sel_div,
        "threshold_crossings": crossings,
        "affected_iljus": affected,
        "affected_lineage": {
            ilju: {
                n: runs[n].lineage.get(ilju, []) for n in ("R6", "R7")
            }
            for ilju in affected
        },
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_f_forensic_20260402.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    print("  개입", r["interventions"], "· 최초 선택 분기", r["first_selection_divergence"])
    for variant, c in r["threshold_crossings"].items():
        print(f"  {variant}")
        for key, rows in c.items():
            if rows:
                print(f"    {key}: "
                      + ", ".join(
                          f"{x['ilju']} {x['s0']}→{x[variant.lower()]}" for x in rows
                      ))
    print("  영향 일주", r["affected_iljus"])
    for ilju, lin in r["affected_lineage"].items():
        for variant, rows in lin.items():
            print(f"    {ilju} {variant} 개입 {len(rows)}건 "
                  f"{[(x['date'], x['rank'], x['loss']) for x in rows[:4]]}")
