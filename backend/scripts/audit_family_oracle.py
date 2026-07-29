"""OA-6f7 — individual / global family oracle (측정 전용, 라이브 불변).

OA-6f6 이 콘텐츠 카탈로그 상한(R0/R1)을 기각했다. 남은 질문은 둘이다.

    individual oracle < 15   그 일주 자체로 15종이 불가능한가
                             → LOCAL_TEMPORAL_REACHABILITY_CEILING
    global      < 55         보드 capacity 경쟁으로 55개 일주를 동시에 못 채우는가
                             → GLOBAL_CAPACITY_CONFLICT
    global >= 55, C10 < 55   선택기가 기회를 못 쓰는가
                             → SELECTION_ALLOCATION_GAP

**individual** 은 이분 매칭으로 정확히 푼다 — 90일 각각에서 하루 1개를 골라 서로 다른
family 를 최대 몇 개까지 모을 수 있는가는 (날짜 × family) 최대 매칭이다. 서로 다른
family 를 고르면 event_key 도 달라지므로 cooldown 은 구속하지 않는다.

**global** 은 완전 MILP 대신 deficit-first 탐욕으로 **하한**을 구한다. 하한이 이미
55 를 넘으면 "구조적으로 불가능"은 기각된다. 다만 이 탐욕은 good 후보 위에서 직접
배정하므로 라이브 파이프라인(`_select_slots` → `_headline_candidates` →
`_rebalance_headlines`)을 통과한 witness 가 아니다. **"달성 가능" 확정에는 witness
를 라이브 순수 함수로 재생하는 단계가 남는다.**
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
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import networkx as nx  # noqa: E402

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import cap_count  # noqa: E402
from saju_engines.daily_selection_policy_shadow import strength_band  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

WINDOW, BUDGET = 90, 7
_DOMAIN_CAP, _EVENT_CAP = cap_count(60, 0.35), 10
_TARGET, _QUALIFY = 15, 55
_WINDOWS = (
    ("failing_2027-06-01", dt.date(2027, 3, 3)),
    ("passing_2026-07-01", dt.date(2026, 4, 2)),
)
_WATCH = ("戊辰", "庚戌", "丙辰", "乙亥", "癸酉", "甲午", "辛亥", "甲子", "乙丑", "丙寅")


def _band_ok(top_p: int, alt_p: int) -> bool:
    tb, ab = strength_band(top_p), strength_band(alt_p)
    return ab >= tb or (tb != 4 and tb - ab < 2)


def _candidates(start: dt.date, events: dict, family_of: dict[str, str]):
    """일주 → 날짜 → [(event_key, prob, domain, loss)] — 예산·밴드를 통과한 good 후보."""
    out: dict[str, dict[int, list[tuple[str, int, str, int]]]] = collections.defaultdict(dict)
    for i in range(WINDOW):
        ctx = M.build_day_context(start + dt.timedelta(days=i))
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = sorted(
                (s for s in scored
                 if s.valence == "good"
                 and "good" in (events[s.event_key].get("headline_slots")
                                or events[s.event_key]["slots"])),
                key=lambda x: -x.probability,
            )
            top = goods[0]
            out[ilju][i] = [
                (g.event_key, g.probability, events[g.event_key]["domain"],
                 top.probability - g.probability)
                for g in goods
                if top.probability - g.probability <= BUDGET
                and _band_ok(top.probability, g.probability)
            ]
    return out


def individual_oracle(cand, family_of: dict[str, str]) -> dict[str, int]:
    """일주별 최대 고유 family 수 — (날짜 × family) 최대 이분 매칭."""
    result: dict[str, int] = {}
    for ilju, days in cand.items():
        g = nx.Graph()
        left: set[str] = set()
        for i, rows in days.items():
            node = f"d{i}"
            left.add(node)
            for key, _p, _d, _loss in rows:
                g.add_edge(node, f"f{family_of[key]}")
        if not g.number_of_edges():
            result[ilju] = 0
            continue
        m = nx.algorithms.bipartite.maximum_matching(g, top_nodes=left)
        result[ilju] = len([k for k in m if k.startswith("f")])
    return result


def global_greedy(cand, family_of: dict[str, str]) -> dict[str, Any]:
    """deficit-first 탐욕 — global oracle 의 **하한**.

    결손이 큰 일주가 먼저 미사용 family 를 가져간다. domain·event cap 과 cooldown 을
    지키며, 새 family 가 불가능하면 손실 최소 후보로 물러난다.
    """
    seen: dict[str, set[str]] = collections.defaultdict(set)
    hist: dict[str, list[str]] = collections.defaultdict(list)
    losses: list[int] = []
    for i in range(WINDOW):
        domains: collections.Counter[str] = collections.Counter()
        evs: collections.Counter[str] = collections.Counter()
        for ilju in sorted(cand, key=lambda x: (len(seen[x]), x)):
            rows = cand[ilju].get(i) or []
            if not rows:
                continue
            past = hist[ilju][-6:]
            prev = hist[ilju][-1] if hist[ilju] else None

            def usable(
                key: str, dom: str, *, _past=past, _prev=prev, _evs=evs, _dom=domains
            ) -> bool:
                if key == _prev or _past.count(key) >= 2:
                    return False
                return _evs[key] + 1 <= _EVENT_CAP and _dom[dom] + 1 <= _DOMAIN_CAP

            fresh = [
                c for c in rows
                if family_of[c[0]] not in seen[ilju] and usable(c[0], c[2])
            ]
            pool = fresh or [c for c in rows if usable(c[0], c[2])] or rows
            pick = min(pool, key=lambda c: (c[3], c[0]))
            seen[ilju].add(family_of[pick[0]])
            hist[ilju].append(pick[0])
            domains[pick[2]] += 1
            evs[pick[0]] += 1
            losses.append(pick[3])
    counts = sorted(len(v) for v in seen.values())
    return {
        "qualifying_iljus": sum(1 for v in counts if v >= _TARGET),
        "family_p10": counts[5],
        "family_min": counts[0],
        "family_median": counts[30],
        "mean_loss": round(sum(losses) / max(1, len(losses)), 2),
        "per_ilju": {k: len(v) for k, v in seen.items()},
    }


def run() -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}

    out: dict[str, Any] = {}
    for name, start in _WINDOWS:
        cand = _candidates(start, events, family_of)
        ind = individual_oracle(cand, family_of)
        glo = global_greedy(cand, family_of)
        vals = sorted(ind.values())
        out[name] = {
            "window_start": start.isoformat(),
            "individual_oracle": {
                "p10": vals[5], "min": vals[0], "median": vals[30], "max": vals[-1],
                "below_target": sum(1 for v in vals if v < _TARGET),
                "watch": {w: ind[w] for w in _WATCH if w in ind},
            },
            "global_greedy_lower_bound": {
                k: v for k, v in glo.items() if k != "per_ilju"
            },
            "verdict": (
                "LOCAL_TEMPORAL_REACHABILITY_CEILING"
                if any(v < _TARGET for v in vals)
                else "SELECTION_ALLOCATION_GAP"
                if glo["qualifying_iljus"] >= _QUALIFY
                else "GLOBAL_CAPACITY_CONFLICT"
            ),
        }
    return {
        "measurement_stage": "display_pipeline",
        "target_family_count": _TARGET,
        "qualifying_iljus_required": _QUALIFY,
        "caveat": (
            "global 은 deficit-first 탐욕의 **하한**이다. good 후보 위에서 직접 배정하므로 "
            "라이브 파이프라인(_select_slots → _headline_candidates → _rebalance_headlines)"
            "을 통과한 witness 가 아니다. '달성 가능' 확정에는 witness 의 라이브 재생이 남는다."
        ),
        "windows": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f7",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f7_family_oracle.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, w in result["windows"].items():
        i, g = w["individual_oracle"], w["global_greedy_lower_bound"]
        print(f"  {name}")
        print(f"    individual oracle  p10={i['p10']} min={i['min']} max={i['max']} "
              f"· 15미만 {i['below_target']}")
        print(f"    global 탐욕 하한   >=15 일주 {g['qualifying_iljus']}/60 "
              f"· family p10={g['family_p10']} 최소={g['family_min']} "
              f"· 평균 손실 {g['mean_loss']}p")
        print(f"    판정: {w['verdict']}")
