"""OA-6e — relation × cap 90일 매트릭스. 버킷을 ≤10/11/12/13+ 로 분리한다.

**측정 전용 — 라이브 점수·선택을 바꾸지 않는다.** relation multiplier 는 shadow 에서만
적용되며 운영 경로는 R0(1.0) 고정이다.

사용법: python scripts/audit_relation_cap_matrix.py
"""
import collections
import datetime as dt
import json
import statistics
import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_relation_shadow import score_event_with_relation
from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count, \
    rebalance_headlines_with_constraints as rebalance
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

dicts = M.load_daily_dicts()
START, DAYS = dt.date(2026, 7, 1), 90
DOMAIN_CAP = cap_count(60, 0.30)
RELATIONS = {"R0": 1.00, "R2": 1.50, "R3": 1.75}
CAPS = {"D6": (10, 6), "D7": (10, 7)}
COMBOS = [("R0","D6"), ("R2","D6"), ("R3","D6"), ("R2","D7"), ("R3","D7")]
SEGS = {"seg1": range(0,30), "seg2": range(30,60), "seg3": range(60,90)}

acc = {f"{r}+{c}": {"buckets": collections.Counter(), "maxes": [], "moves": 0,
                    "costs": [], "budget": 0, "ovr": collections.Counter(),
                    "msg_top_days": 0, "ev_unres": 0, "dm_unres": 0,
                    "seg": {s: collections.Counter() for s in SEGS}}
       for r, c in COMBOS}

for i in range(DAYS):
    ctx = M.build_day_context(START + dt.timedelta(days=i))
    seg = next(s for s, rng in SEGS.items() if i in rng)
    boards = {}
    for rname, mult in RELATIONS.items():
        raw, cmap = {}, {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{ctx.the_date.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [score_event_with_relation(k, e, stem, branch, ctx, multiplier=mult)
                      for k, e in dicts.catalog["events"].items()]
            g, c, s = M._select_slots(scored, seed)
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands]
            raw[ilju] = cmap[ilju][0]
        boards[rname] = (raw, cmap)
    for rname, cname in COMBOS:
        raw, cmap = boards[rname]
        cap, budget = CAPS[cname]
        r = rebalance(raw, cmap, domain_cap=DOMAIN_CAP, event_cap=cap,
                      max_displacement_cost=budget)
        cnt = collections.Counter(x.event_key for x in r.selections.values())
        top_event, top_n = cnt.most_common(1)[0]
        a = acc[f"{rname}+{cname}"]
        b = "≤10" if top_n <= 10 else ("11" if top_n == 11 else ("12" if top_n == 12 else "13+"))
        a["buckets"][b] += 1
        a["seg"][seg][b] += 1
        a["maxes"].append(top_n)
        a["moves"] += len(r.moves)
        a["costs"] += [m.displacement_cost for m in r.moves]
        a["budget"] += r.overrides.get("cost_budget_exceeded", 0)
        for k, v in r.overrides.items():
            a["ovr"][k] += v
        if top_event == "money_small_gain":
            a["msg_top_days"] += 1
        a["ev_unres"] += 1 if r.event_overflow else 0
        a["dm_unres"] += 1 if r.domain_overflow else 0

out = {}
for name, a in acc.items():
    c = sorted(a["costs"])
    n = len(c)
    out[name] = {
        "le10": a["buckets"]["≤10"], "eq11": a["buckets"]["11"],
        "eq12": a["buckets"]["12"], "ge13": a["buckets"]["13+"],
        "max_observed": max(a["maxes"]), "mean_max": round(statistics.mean(a["maxes"]),2),
        "p90_max": sorted(a["maxes"])[int(len(a["maxes"])*0.9)-1],
        "moves": a["moves"],
        "cost_mean": round(statistics.mean(c),2) if n else 0,
        "cost_p90": c[max(0,int(n*0.9)-1)] if n else 0,
        "cost_max": max(c) if n else 0,
        "cost_budget_exceeded": a["budget"],
        "money_top_days": a["msg_top_days"],
        "event_cap_unresolved_days": a["ev_unres"],
        "domain_cap_unresolved_days": a["dm_unres"],
        "overrides": dict(a["ovr"]),
        "segments": {s: dict(v) for s, v in a["seg"].items()},
    }
print(json.dumps(out, ensure_ascii=False, indent=1))
