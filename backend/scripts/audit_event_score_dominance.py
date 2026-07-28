"""OA-7c-S — 사건 점수 독점 감사(측정 전용).

단순 필드 합산이 아니라 **반사실 기여**로 측정한다. clamp 근처에서는 원시 기여가
커도 최종 probability 변화가 0일 수 있고, 반올림 경계에서는 작은 기여가 순위를 바꾼다.

가설 구분:
    M1 money_small_gain 자체가 높다   base만으로 상위 · relation=0에서도 승률 높음
    M2 경쟁 사건이 낮다               money 절대점수는 보통 · 경쟁이 5~10p 뒤처짐
    M3 둘 다

실행 위치에 독립적이다.
"""

from __future__ import annotations

import collections
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

START, DAYS = dt.date(2026, 7, 1), 90
FOCUS = [
    "money_small_gain", "money_good_deal", "praise_recognition",
    "good_news_arrives", "teamwork_flow", "meet_helper", "love_spark",
    "focus_flow", "family_talk", "small_find",
]


def _counterfactual(event, key, stem, branch, ctx) -> dict[str, int]:
    """요소를 하나씩 뺐을 때 최종 probability 가 얼마나 달라지는가."""
    full = _finalize(event, _signals(event, stem, branch, ctx), key).probability
    no_tg = _finalize(event, _signals(event, stem, branch, ctx, relation_only=True), key)
    no_rel = _finalize(event, _signals(event, stem, branch, ctx, ten_god_only=True), key)
    base_only = _finalize(event, {k: 0.0 for k in _signals(event, stem, branch, ctx)}, key)
    return {
        "full": full,
        "ten_god_effect": full - no_tg.probability,
        "relation_effect": full - no_rel.probability,
        "base_only": base_only.probability,
    }


def run() -> dict:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    stats = {k: collections.defaultdict(list) for k in FOCUS}
    wins = collections.Counter()
    appear = collections.Counter()
    gaps = collections.defaultdict(list)
    rank_hist = {k: collections.Counter() for k in FOCUS}
    clamp_hits = collections.Counter()

    for i in range(DAYS):
        ctx = M.build_day_context(START + dt.timedelta(days=i))
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = sorted(
                (s for s in scored if s.valence == "good" and "good" in s.slots),
                key=lambda s: -s.probability,
            )
            if goods:
                wins[goods[0].event_key] += 1
                if len(goods) > 1:
                    gaps[goods[0].event_key].append(
                        goods[0].probability - goods[1].probability
                    )
            order = {s.event_key: r for r, s in enumerate(sorted(
                scored, key=lambda s: -s.probability), 1)}
            for k in FOCUS:
                if k not in events:
                    continue
                appear[k] += 1
                r = order[k]
                rank_hist[k]["1" if r == 1 else ("2-3" if r <= 3 else
                             ("4-10" if r <= 10 else "11+"))] += 1
                cf = _counterfactual(events[k], k, stem, branch, ctx)
                for name, v in cf.items():
                    stats[k][name].append(v)
                if cf["full"] >= 95 or cf["full"] <= 5:
                    clamp_hits[k] += 1

    out = {}
    for k in FOCUS:
        if k not in events:
            continue
        s = stats[k]
        ev = events[k]
        out[k] = {
            "domain": ev["domain"], "base_weight": ev["base_weight"],
            "expr_confidence": ev["expr_confidence"],
            "has_ten_god_affinity": bool(ev.get("ten_god_affinity")),
            "has_relation_affinity": bool(
                any((ev.get("relation_affinity") or {}).values())
            ),
            "mean_probability": round(statistics.mean(s["full"]), 1),
            "p90_probability": sorted(s["full"])[int(len(s["full"]) * 0.9) - 1],
            "base_only_probability": s["base_only"][0],
            "ten_god_effect_mean": round(statistics.mean(s["ten_god_effect"]), 1),
            "relation_effect_mean": round(statistics.mean(s["relation_effect"]), 1),
            "good_slot_wins": wins.get(k, 0),
            "win_rate_pct": round(wins.get(k, 0) / (DAYS * 60) * 100, 1),
            "mean_gap_to_second": (
                round(statistics.mean(gaps[k]), 2) if gaps.get(k) else None
            ),
            "rank_distribution": dict(rank_hist[k]),
            "clamp_hits": clamp_hits.get(k, 0),
        }
    return out


if __name__ == "__main__":
    data = {"audit_id": "OA-7c-S", "policy_status": "measurement_only",
            "live_behavior_changed": False, "days": DAYS, "cards": DAYS * 60,
            "events": run()}
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_event_score_dominance_90d.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["events"], ensure_ascii=False, indent=1))
