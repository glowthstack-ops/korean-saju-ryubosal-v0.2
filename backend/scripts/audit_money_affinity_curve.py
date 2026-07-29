"""OA-7c-S3a — 편재 affinity 반응 곡선(측정 전용, 사전 불변).

0.9→0.8 단일안만 돌리면 0.1 감소가 적절했는지 알 수 없다. 0.05 간격을 포함해
**반응 곡선**을 본다. 편재 조건 540카드와 전체 5,400카드를 분리해 평가한다 —
전체만 보면 편재가 10% 조건이라 효과가 희석된다.
"""

from __future__ import annotations

import collections
import copy
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_relation_shadow import _finalize, _signals  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.constants import ten_god  # noqa: E402
from saju_shared_types.enums import Stem  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
TARGET = "money_small_gain"
VARIANTS = {"M0": 0.90, "M-A1": 0.85, "M-A2": 0.80, "M-A3": 0.75}


def _tg(a: Stem, b: Stem) -> str:
    return "비견" if a == b else ten_god(a, b).value


def run() -> dict:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    acc = {v: {"pj": collections.Counter(), "all": collections.Counter(),
               "pj_gap": [], "new_win": collections.Counter(),
               "series": collections.defaultdict(list)} for v in VARIANTS}

    for i in range(DAYS):
        d = START + dt.timedelta(days=i)
        ctx = M.build_day_context(d)
        day_stem = Stem(ctx.day_stem)
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            tg = _tg(stem, day_stem)
            others = {k: M._score_event(k, e, stem, branch, ctx)
                      for k, e in events.items() if k != TARGET}
            base_order = sorted(others.values(), key=lambda s: -s.probability)
            for name, aff in VARIANTS.items():
                ev = copy.deepcopy(events[TARGET])
                ev["ten_god_affinity"] = {**ev["ten_god_affinity"], "편재": aff}
                s = _finalize(ev, _signals(ev, stem, branch, ctx), TARGET)
                higher = [x for x in base_order if x.probability > s.probability]
                rank = len(higher) + 1
                a = acc[name]
                a["all"]["cards"] += 1
                a["all"]["rank1"] += rank == 1
                a["all"]["top3"] += rank <= 3
                a["all"]["prob_sum"] += s.probability
                winner = TARGET if rank == 1 else base_order[0].event_key
                a["series"][ilju].append(winner)
                if tg == "편재":
                    a["pj"]["cards"] += 1
                    a["pj"]["rank1"] += rank == 1
                    a["pj"]["top3"] += rank <= 3
                    a["pj"]["prob_sum"] += s.probability
                    if rank == 1:
                        a["pj_gap"].append(s.probability - base_order[0].probability)
                    else:
                        a["new_win"][base_order[0].event_key] += 1

    out = {}
    for name, aff in VARIANTS.items():
        a = acc[name]
        pj, al = a["pj"], a["all"]
        tops = [collections.Counter(v).most_common(1)[0][1] / DAYS * 100
                for v in a["series"].values()]
        out[name] = {
            "pyeonjae_affinity": aff,
            "pyeonjae": {
                "cards": pj["cards"],
                "rank1": pj["rank1"], "rank1_pct": round(pj["rank1"] / pj["cards"] * 100, 1),
                "top3_pct": round(pj["top3"] / pj["cards"] * 100, 1),
                "mean_probability": round(pj["prob_sum"] / pj["cards"], 1),
                "mean_gap_when_rank1": round(statistics.mean(a["pj_gap"]), 2)
                if a["pj_gap"] else None,
                "displaced_winners": dict(a["new_win"].most_common(6)),
            },
            "all_cards": {
                "rank1": al["rank1"], "rank1_pct": round(al["rank1"] / al["cards"] * 100, 1),
                "top3_pct": round(al["top3"] / al["cards"] * 100, 1),
                "mean_probability": round(al["prob_sum"] / al["cards"], 1),
            },
            "longitudinal": {
                "top_event_share_mean": round(statistics.mean(tops), 1),
                "top_event_share_p90": round(sorted(tops)[int(len(tops) * 0.9) - 1], 1),
                "top_event_share_max": round(max(tops), 1),
            },
        }
    return out


if __name__ == "__main__":
    data = {"audit_id": "OA-7c-S3a",
            "measurement_stage": "raw_candidate_ranking",
            "superseded_by": "OA-9r (노출 해석 한정 — raw 구조 진단은 유효)",
            "policy_status": "measurement_only",
            "live_behavior_changed": False, "days": DAYS, "variants": run()}
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_money_affinity_curve_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
