"""relation_affinity R0~R3 shadow — 90일, 3×30일 구간 분리.

**측정 전용 — 라이브 점수·선택을 바꾸지 않는다.** relation multiplier 는 shadow 에서만
적용되며 운영 경로는 R0(1.0) 고정이다.

사용법: python scripts/audit_relation_shadow.py
"""
import collections
import datetime as dt
import json
import statistics

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count
from saju_engines.daily_board_constraints import rebalance_headlines_with_constraints as rebalance
from saju_engines.daily_relation_shadow import RELATION_VARIANTS, score_event_with_relation
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

dicts = M.load_daily_dicts()
START, DAYS = dt.date(2026, 7, 1), 90
DOMAIN_CAP = cap_count(60, 0.30)
SEG = {"seg1(1-30)": range(0,30), "seg2(31-60)": range(30,60), "seg3(61-90)": range(60,90)}

acc = {v: {"raw_msg":[], "cap_msg":[], "collapse":[], "keys":set(),
           "uniq_per_day":[], "gap":[], "top3_rare":0, "cards":0,
           "seg": {s: {"raw_msg":[], "collapse":[]} for s in SEG}}
       for v in RELATION_VARIANTS}
RARE = {"focus_flow","family_talk","small_find"}

for i in range(DAYS):
    d = START + dt.timedelta(days=i)
    ctx = M.build_day_context(d)
    seg = next(s for s,r in SEG.items() if i in r)
    for vname, mult in RELATION_VARIANTS.items():
        raw_sel, cmap = {}, {}
        by_stem = collections.defaultdict(set)
        rawc = collections.Counter()
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{d.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [score_event_with_relation(k, ev, stem, branch, ctx, multiplier=mult)
                      for k, ev in dicts.catalog["events"].items()]
            good, caution, support = M._select_slots(scored, seed)
            band = M._band(good, caution)
            cands = M._headline_candidates(good, support, caution, band)
            cmap[ilju] = [HeadlineCandidate(c.event_key, c.domain, c.probability) for c in cands]
            raw_sel[ilju] = cmap[ilju][0]
            rawc[good.event_key] += 1
            by_stem[stem.value].add(good.event_key)
            ordered = sorted(scored, key=lambda s: -s.probability)
            if len(ordered) > 1:
                acc[vname]["gap"].append(ordered[0].probability - ordered[1].probability)
            acc[vname]["top3_rare"] += sum(1 for s in ordered[:3] if s.event_key in RARE)
            acc[vname]["cards"] += 1
        a = acc[vname]
        a["raw_msg"].append(rawc.get("money_small_gain",0)/60*100)
        a["seg"][seg]["raw_msg"].append(rawc.get("money_small_gain",0)/60*100)
        coll = sum(1 for v in by_stem.values() if len(v)==1)/len(by_stem)*100
        a["collapse"].append(coll)
        a["seg"][seg]["collapse"].append(coll)
        a["keys"] |= set(rawc)
        a["uniq_per_day"].append(len(rawc))
        r = rebalance(raw_sel, cmap, domain_cap=DOMAIN_CAP, event_cap=60)
        capc = collections.Counter(c.event_key for c in r.selections.values())
        a["cap_msg"].append(capc.get("money_small_gain",0)/60*100)

out = {}
for v, a in acc.items():
    out[v] = {
        "multiplier": RELATION_VARIANTS[v],
        "raw_money_pct": round(statistics.mean(a["raw_msg"]),1),
        "cap_money_pct": round(statistics.mean(a["cap_msg"]),1),
        "stem_collapse_pct": round(statistics.mean(a["collapse"]),1),
        "headline_keys": len(a["keys"]),
        "uniq_events_per_day": round(statistics.mean(a["uniq_per_day"]),1),
        "top1_top2_gap": round(statistics.mean(a["gap"]),2),
        "rare_top3_per_card": round(a["top3_rare"]/a["cards"],3),
        "segments": {s: {"raw_money_pct": round(statistics.mean(x["raw_msg"]),1),
                         "collapse_pct": round(statistics.mean(x["collapse"]),1)}
                     for s,x in a["seg"].items()},
    }
print(json.dumps(out, ensure_ascii=False, indent=1))
