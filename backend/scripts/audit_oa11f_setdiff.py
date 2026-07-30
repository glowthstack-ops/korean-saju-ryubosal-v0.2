#!/usr/bin/env python3
"""OA-11f-D — 丙辰 anchor 고유 집합 양방향 차분과 provenance (측정 전용).

coverage 차이가 1 이어도 `S0 에만 값 하나` 가 아니다.

    |S0 \\ V| - |V \\ S0| = 1

이므로 (1,0) · (2,1) · (3,2) 모두 가능하다. 그래서 양방향을 모두 산출한다.
R6·R7 이 같은 coverage 14 에 도달했더라도 서로 다른 값 교환을 거쳤을 수 있으므로
S0↔R6 · S0↔R7 · R6↔R7 세 쌍을 모두 비교한다.

비대칭 값에 한해 창 안 occurrence 를 역추적한다 — 90일 전체 사건을 다 출력하지 않고
원인 후보를 먼저 좁힌다.
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

TARGET = "丙辰"
ANCHOR = dt.date(2026, 4, 2)
VARIANTS = {"S0": None, "R6": 6, "R7": 7}


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]

    hh = {n: collections.defaultdict(list) for n in VARIANTS}
    gh = {n: collections.defaultdict(list) for n in VARIANTS}
    # 丙辰 일별 기록 — 전 구간 보존(창 밖 provenance 도 필요할 수 있다).
    daily: dict[str, list[dict[str, Any]]] = {n: [] for n in VARIANTS}

    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= ANCHOR:
        iso = day.isoformat()
        ctx = M.build_day_context(day)
        for name, limit in VARIANTS.items():
            raw: dict[str, HeadlineCandidate] = {}
            cmap: dict[str, list[HeadlineCandidate]] = {}
            preboard = ""
            intervened = False
            others = 0
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
                    g, c, s = chosen["slots"]
                    cands = chosen["cands"]
                    pick = chosen["event_key"]
                    if ilju == TARGET:
                        intervened = True
                    else:
                        others += 1
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
                if ilju == TARGET:
                    preboard = cmap[ilju][0].event_key
                gh[name][ilju].append(pick)
            result = select_board(
                raw, cmap, hh[name], domain_cap=21, event_cap=10,
                max_displacement_cost=B._BUDGET, policy=B._BOARD,
                today=day.toordinal(),
            )
            committed = result.selections[TARGET].event_key
            daily[name].append({
                "date": iso, "preboard": preboard, "committed": committed,
                "family": family_of.get(committed, committed),
                "board_displaced": preboard != committed,
                "intervened": intervened, "other_iljus_intervened": others,
            })
            for ilju, sel in result.selections.items():
                hh[name][ilju].append(sel.event_key)
        day += dt.timedelta(days=1)

    # ── anchor 시점 창
    window_rows = {n: daily[n][-B._LOOKBACK:] for n in VARIANTS}
    uniq = {
        n: {
            "key": {r["committed"] for r in window_rows[n]},
            "family": {r["family"] for r in window_rows[n]},
        }
        for n in VARIANTS
    }

    def occurrences(name: str, axis: str, value: str) -> list[str]:
        field = "committed" if axis == "key" else "family"
        return [r["date"] for r in window_rows[name] if r[field] == value]

    pairs: dict[str, Any] = {}
    for a, b in (("S0", "R6"), ("S0", "R7"), ("R6", "R7")):
        entry: dict[str, Any] = {}
        for axis in ("key", "family"):
            only_a = sorted(uniq[a][axis] - uniq[b][axis])
            only_b = sorted(uniq[b][axis] - uniq[a][axis])
            entry[axis] = {
                f"only_{a.lower()}": [
                    {
                        "value": v, "refcount": len(occurrences(a, axis, v)),
                        "dates": occurrences(a, axis, v),
                    }
                    for v in only_a
                ],
                f"only_{b.lower()}": [
                    {
                        "value": v, "refcount": len(occurrences(b, axis, v)),
                        "dates": occurrences(b, axis, v),
                    }
                    for v in only_b
                ],
                "coverage": {a: len(uniq[a][axis]), b: len(uniq[b][axis])},
                "identical_sets": uniq[a][axis] == uniq[b][axis],
            }
        pairs[f"{a}_vs_{b}"] = entry

    # ── 최초 committed-value 분기
    div: dict[str, Any] = {}
    for variant in ("R6", "R7"):
        first_commit = first_uniqset = None
        s0_keys: set[str] = set()
        v_keys: set[str] = set()
        for a, b in zip(daily["S0"], daily[variant], strict=True):
            if first_commit is None and a["committed"] != b["committed"]:
                first_commit = {
                    "date": a["date"],
                    "s0_preboard": a["preboard"], "s0_committed": a["committed"],
                    "variant_preboard": b["preboard"],
                    "variant_committed": b["committed"],
                    "preboard_same": a["preboard"] == b["preboard"],
                    "s0_board_displaced": a["board_displaced"],
                    "variant_board_displaced": b["board_displaced"],
                    "variant_intervened": b["intervened"],
                    "other_iljus_intervened": b["other_iljus_intervened"],
                    "classification_hint": (
                        "CROSS_ILJU_BOARD_COUPLING"
                        if a["preboard"] == b["preboard"]
                        else "SELECTOR_OR_AVAILABILITY_DIVERGENCE"
                    ),
                }
            s0_keys.add(a["committed"])
            v_keys.add(b["committed"])
            if first_uniqset is None and s0_keys != v_keys:
                first_uniqset = a["date"]
        div[variant] = {
            "first_committed_value_divergence": first_commit,
            "first_unique_set_divergence": first_uniqset,
        }

    return {
        "audit_id": "OA-11f-D",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "target_ilju": TARGET,
        "anchor": ANCHOR.isoformat(),
        "coverage_window": (
            f"{window_rows['S0'][0]['date']} ~ {window_rows['S0'][-1]['date']}"
        ),
        "set_cardinality_note": (
            "coverage 차이 1 은 |S0\\V| - |V\\S0| = 1 일 뿐이다 — 단일 누락 값을 "
            "뜻하지 않으므로 양방향을 모두 낸다."
        ),
        "pairwise_diff": pairs,
        "divergence": div,
        "target_intervention_dates": {
            n: [r["date"] for r in daily[n] if r["intervened"]] for n in VARIANTS
        },
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_d_setdiff.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for pair, e in r["pairwise_diff"].items():
        print(f"  {pair}")
        for axis, d in e.items():
            keys = [k for k in d if k.startswith("only_")]
            print(f"    {axis} coverage {d['coverage']} 동일집합={d['identical_sets']}")
            for k in keys:
                for v in d[k]:
                    print(f"      {k}: {v['value']} ×{v['refcount']} {v['dates']}")
    for variant, d in r["divergence"].items():
        print(f"  {variant} 최초 unique-set 분기 {d['first_unique_set_divergence']}")
        print(f"    최초 committed 분기 {d['first_committed_value_divergence']}")
