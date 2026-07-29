"""OA-6f9 — 정확한 카드 결과 frontier와 individual oracle (측정 전용, 라이브 불변).

OA-6f7 의 relaxed oracle 은 후보 모델이 실제 카드 파이프라인보다 넓었다(OA-6f8 에서
확인). 이번에는 **사전과 slot 계약을 전혀 바꾸지 않고** 실제로 가능한 카드 결과를
전수 열거한다.

핵심: `_select_slots` 는 support·caution 을 **good 의 함수로** 결정한다. 따라서
카드 결과의 자유도는 good 대표 하나뿐이고, good 슬롯 자격(`slots` 에 "good")이 있는
사건마다 한 번씩 돌리면 그 카드에서 도달 가능한 결과가 **정확히** 열거된다.

    for g in good-slot-eligible ∩ 예산 ∩ 밴드:
        _select_slots(good_override=g) → (good, support, caution)
        _headline_candidates(...)      → card raw headline

card raw headline 이 support 사건이 될 수 있으므로, good 대표가 못 되는 5종
(family_talk·focus_flow·rest_recharge·tidy_luck·walk_refresh)의 family 도
**support 경로로** 헤드라인에 닿을 수 있다. 그 경로가 실제로 열려 있는지가 이 감사의
핵심 질문이다.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics
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
from saju_engines.daily_selection_policy_shadow import strength_band  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

WINDOW, BUDGET = 90, 7
_TARGET = 15
_WINDOWS = (
    ("failing_2027-06-01", dt.date(2027, 3, 3)),
    ("passing_2026-07-01", dt.date(2026, 4, 2)),
)
#: good 대표가 될 수 없는(본문 역할이 support 인) 헤드라인 자격 사건들.
_SUPPORT_ROLE = ("family_talk", "focus_flow", "rest_recharge", "tidy_luck", "walk_refresh")


def _band_ok(top_p: int, alt_p: int) -> bool:
    tb, ab = strength_band(top_p), strength_band(alt_p)
    return ab >= tb or (tb != 4 and tb - ab < 2)


def card_frontier(
    scored: list, seed: str, events: dict, family_of: dict[str, str]
) -> list[dict[str, Any]]:
    """이 카드에서 실제로 도달 가능한 결과 전수.

    good 슬롯 자격은 `slots` 로 판정한다 — `_select_slots` 가 그렇게 하기 때문이다.
    """
    goods_all = sorted(
        (s for s in scored if s.valence == "good" and "good" in events[s.event_key]["slots"]),
        key=lambda x: -x.probability,
    )
    if not goods_all:
        return []
    top = goods_all[0]
    rows: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for g in goods_all:
        loss = top.probability - g.probability
        if loss > BUDGET or not _band_ok(top.probability, g.probability):
            continue
        good, caution, support = M._select_slots(scored, seed, good_override=g.event_key)
        if good.event_key != g.event_key:
            continue
        cands = M._headline_candidates(good, support, caution, M._band(good, caution))
        head = cands[0]
        key = (head.event_key, family_of.get(head.event_key, ""), head.domain,
               strength_band(head.probability))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "good": good.event_key, "support": support.event_key,
            "caution": caution.event_key,
            "raw_headline": head.event_key,
            "raw_headline_family": family_of.get(head.event_key, ""),
            "raw_headline_domain": head.domain,
            "band": strength_band(head.probability),
            "loss": loss,
            "headline_is_support": head.event_key == support.event_key,
        })
    return rows


def run() -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    watch_families = {family_of[k] for k in _SUPPORT_ROLE}

    out: dict[str, Any] = {}
    for name, start in _WINDOWS:
        # 일주 → 날짜 → 도달 가능 family
        avail: dict[str, dict[int, set[str]]] = collections.defaultdict(dict)
        frontier_sizes: list[int] = []
        support_headline_days = collections.Counter()
        support_family_days: dict[str, collections.Counter] = {
            f: collections.Counter() for f in watch_families
        }
        for i in range(WINDOW):
            ctx = M.build_day_context(start + dt.timedelta(days=i))
            for idx in range(60):
                stem, branch = ganzi_from_index(idx)
                ilju = f"{stem.value}{branch.value}"
                seed = f"{(start + dt.timedelta(days=i)).isoformat()}|{ilju}" \
                       f"|{M.EVENT_SELECTION_COMPAT_SALT}"
                scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
                rows = card_frontier(scored, seed, events, family_of)
                frontier_sizes.append(len(rows))
                fams = {r["raw_headline_family"] for r in rows}
                avail[ilju][i] = fams
                if any(r["headline_is_support"] for r in rows):
                    support_headline_days[ilju] += 1
                for f in watch_families & fams:
                    support_family_days[f][ilju] += 1

        # individual exact oracle = (날짜 × family) 최대 매칭
        result: dict[str, int] = {}
        for ilju, days in avail.items():
            g = nx.Graph()
            left: set[str] = set()
            for i, fams in days.items():
                node = f"d{i}"
                left.add(node)
                for f in fams:
                    g.add_edge(node, f"f{f}")
            m = (nx.algorithms.bipartite.maximum_matching(g, top_nodes=left)
                 if g.number_of_edges() else {})
            result[ilju] = len([k for k in m if k.startswith("f")])
        vals = sorted(result.values())
        out[name] = {
            "window_start": start.isoformat(),
            "frontier_rows_per_card": {
                "mean": round(statistics.mean(frontier_sizes), 2),
                "min": min(frontier_sizes), "max": max(frontier_sizes),
            },
            "individual_exact_oracle": {
                "p10": vals[5], "min": vals[0], "median": vals[30], "max": vals[-1],
                "below_target": sum(1 for v in vals if v < _TARGET),
            },
            "support_headline_reachable_days": {
                "mean_per_ilju": round(
                    statistics.mean(support_headline_days.values()), 1)
                if support_headline_days else 0.0,
                "iljus_with_none": 60 - len(support_headline_days),
            },
            "support_role_family_reach": {
                f: {
                    "iljus_reachable": len(support_family_days[f]),
                    "mean_days_per_reachable_ilju": round(
                        statistics.mean(support_family_days[f].values()), 1)
                    if support_family_days[f] else 0.0,
                }
                for f in sorted(watch_families)
            },
            # 출시 기준은 "전 일주 15 이상"이 아니라 **p10 >= 15** 이다
            # (60개 중 6번째로 작은 값 → 15 미만 일주가 5개 이하).
            "verdict": (
                "CARD_LEVEL_FEASIBLE"
                if vals[5] >= _TARGET
                else "CARD_CONTRACT_STRUCTURALLY_INFEASIBLE"
            ),
        }
    return {
        "measurement_stage": "display_pipeline",
        "note": (
            "`_select_slots` 가 support·caution 을 good 의 함수로 정하므로 카드 결과의 "
            "자유도는 good 대표 하나다. good 슬롯 자격은 `slots` 로 판정한다 — 사전과 "
            "slot 계약을 전혀 바꾸지 않았다."
        ),
        "windows": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f9",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f9_card_frontier.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, w in result["windows"].items():
        i = w["individual_exact_oracle"]
        print(f"  {name}")
        print(f"    frontier 행/카드 {w['frontier_rows_per_card']}")
        print(f"    individual exact oracle p10={i['p10']} min={i['min']} "
              f"max={i['max']} · 15미만 {i['below_target']}")
        print(f"    support 헤드라인 도달일 {w['support_headline_reachable_days']}")
        for f, r in w["support_role_family_reach"].items():
            print(f"      {f:20} 도달 일주 {r['iljus_reachable']}/60 · "
                  f"평균 {r['mean_days_per_reachable_ilju']}일")
        print(f"    판정: {w['verdict']}")
