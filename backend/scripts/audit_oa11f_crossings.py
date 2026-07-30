#!/usr/bin/env python3
"""OA-11f-X — 5 anchor 전수 개별 일주 문턱 교차 감사 (측정 전용).

`anchor qualifying 감소 = 0` 은 **순합** 지표라 상승 일주가 하락 일주를 상쇄한다.
실제로 R7 은 2026-04-02 에서 丙辰 하락을 壬戌 상승으로 가려 aggregate 기준을
통과했다. 그래서 개별 일주 교차를 전 anchor·양 축에서 직접 센다.

S0 · R6 · R7 을 같은 루프에서 병행 재생하고(각자 독립 이력) 각 anchor 시점의
per-ilju coverage 를 스냅샷한다.
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

ANCHORS = tuple(dt.date.fromisoformat(a) for a in B.ANCHORS)
VARIANTS = {"S0": None, "R6": 6, "R7": 7}
_THRESHOLD = 15


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]

    hh = {n: collections.defaultdict(list) for n in VARIANTS}
    gh = {n: collections.defaultdict(list) for n in VARIANTS}
    interventions: collections.Counter = collections.Counter()
    snaps: dict[str, dict[str, dict[str, dict[str, int]]]] = {}

    anchor_set = {a.isoformat() for a in ANCHORS}
    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= max(ANCHORS):
        iso = day.isoformat()
        if iso in anchor_set:
            snaps[iso] = {
                name: {
                    ilju: {
                        "key": len(set(tuple(hh[name][ilju][-B._LOOKBACK:]))),
                        "family": len({
                            family_of.get(k, k)
                            for k in tuple(hh[name][ilju][-B._LOOKBACK:])
                        }),
                    }
                    for ilju in B._ILJUS
                }
                for name in VARIANTS
            }
        ctx = M.build_day_context(day)
        for name, limit in VARIANTS.items():
            raw: dict[str, HeadlineCandidate] = {}
            cmap: dict[str, list[HeadlineCandidate]] = {}
            for idx, ilju in enumerate(B._ILJUS):
                stem, branch = ganzi_from_index(idx)
                seed = f"{iso}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
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
                window = tuple(hh[name][ilju][-B._LOOKBACK:])
                chosen = None
                if limit is not None:
                    families = {family_of.get(k, k) for k in window}
                    if (
                        len(families) < C10_POLICY.coverage_floor
                        and repeat_severity(gh[name][ilju], raw_key) == SEVERITY_CLEAN
                    ):
                        options = B._safe_candidates(
                            scored, seed, events, ranked, raw_key, raw_p, window,
                            family_of, loss_limit=limit,
                        )
                        chosen = B._pick("B1", options) if options else None
                if chosen is not None:
                    interventions[name] += 1
                    g, c, s = chosen["slots"]
                    cands = chosen["cands"]
                    pick = chosen["event_key"]
                else:
                    rep = select_good_representative(
                        goods, gh[name][ilju], B._BUDGET, policy=C10_POLICY,
                        family_of=family_of, headline_history=hh[name][ilju],
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
                gh[name][ilju].append(pick)
            result = select_board(
                raw, cmap, hh[name], domain_cap=21, event_cap=10,
                max_displacement_cost=B._BUDGET, policy=B._BOARD,
                today=day.toordinal(),
            )
            for ilju, sel in result.selections.items():
                hh[name][ilju].append(sel.event_key)
        day += dt.timedelta(days=1)

    per_anchor: dict[str, Any] = {}
    totals: collections.Counter = collections.Counter()
    for iso, snap in snaps.items():
        rows = []
        for ilju in B._ILJUS:
            s0 = snap["S0"][ilju]
            for variant in ("R6", "R7"):
                v = snap[variant][ilju]
                for axis in ("family", "key"):
                    if s0[axis] >= _THRESHOLD > v[axis]:
                        direction = "downcross"
                    elif s0[axis] < _THRESHOLD <= v[axis]:
                        direction = "upcross"
                    else:
                        continue
                    rows.append({
                        # 축별 독립 레코드 — family 와 key 는 기여 event 가 다를 수
                        # 있어 한 줄로 합치지 않는다.
                        "ilju": ilju, "variant": variant, "axis": axis,
                        "direction": direction,
                        "s0": s0[axis], "variant_value": v[axis],
                        # 15→14 와 18→14 는 둘 다 downcross 지만 위험도가 다르다.
                        "crossing_margin": v[axis] - _THRESHOLD,
                        "coverage_delta": v[axis] - s0[axis],
                    })
                    totals[f"{variant}_{axis}_{direction}"] += 1
        # R6·R7 공통 여부
        keyset = collections.defaultdict(set)
        for r in rows:
            keyset[(r["ilju"], r["axis"], r["direction"])].add(r["variant"])
        for r in rows:
            # 결과가 같다고 원인이 같은 것은 아니다. ledger·ablation 전에는
            # COMMON_CAUSE 로 표현하지 않는다.
            r["shared_outcome"] = len(
                keyset[(r["ilju"], r["axis"], r["direction"])]
            ) == 2
            r["shared_first_divergence"] = "unresolved"
            r["shared_intervention_lineage"] = "unresolved"
        per_anchor[iso] = rows
    return {
        "audit_id": "OA-11f-X",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "threshold": _THRESHOLD,
        "interventions_to_last_anchor": dict(interventions),
        "reinforced_criterion": [
            "family_downcross_count = 0", "key_downcross_count = 0",
            "family qualifying 감소 = 0", "key below_15 증가 = 0",
        ],
        "totals": dict(totals),
        "per_anchor_crossings": per_anchor,
        "shared_semantics": {
            "shared_outcome": "같은 anchor·ilju·axis 에서 R6·R7 모두 하락한 결과",
            "not_implied": (
                "COMMON_CAUSE 가 아니다 — 서로 다른 개입 경로가 같은 결과를 만들 수 "
                "있다. shared_first_divergence·shared_intervention_lineage 는 "
                "ledger·ablation 후에만 확정한다."
            ),
        },
        "shared_downcross_outcomes": sorted({
            (r["ilju"], r["axis"])
            for rows in per_anchor.values() for r in rows
            if r["direction"] == "downcross" and r["shared_outcome"]
        }),
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_x_crossings.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    print("  개입(마지막 anchor 까지)", r["interventions_to_last_anchor"])
    print("  합계", r["totals"])
    for iso, rows in r["per_anchor_crossings"].items():
        down = [x for x in rows if x["direction"] == "downcross"]
        up = [x for x in rows if x["direction"] == "upcross"]
        print(f"  {iso}  하락 {len(down)} · 상승 {len(up)}")
        for x in down:
            print(f"      ↓ {x['variant']} {x['ilju']} {x['axis']} "
                  f"{x['s0']}→{x['variant_value']} "
                  f"(margin {x['crossing_margin']}, delta {x['coverage_delta']}) "
                  f"공통결과={x['shared_outcome']}")
    print("  공통 결과 하락", r["shared_downcross_outcomes"])
