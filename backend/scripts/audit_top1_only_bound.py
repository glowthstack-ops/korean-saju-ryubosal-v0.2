#!/usr/bin/env python3
"""OA-11c — `TOP1_ONLY_STATIC_UPPER_BOUND` 와 UB0 목표 후보 rank 분포.

정책 분기점이 되는 감사다.

    UB0   : 카드 안에서 **임의 순위** 헤드라인 후보를 고를 수 있다고 가정한 상계.
            라이브에는 그 자유도가 없다.
    TOP1  : good 대표만 최적으로 고르고, 헤드라인은 **각 카드의 cands[0]** 로 고정.
            즉 **현행 계약이 실제로 가진 자유도만** 쓴 상계.

판정:

    TOP1 < 55  → good 대표 배분만으로는 구조적으로 부족.
                 C10 의 `_longterm_key` 를 아무리 고쳐도 목표를 안정적으로 못 채운다.
                 cut-generation 도 의미가 없다 — 라이브에 k>0 선택 변수가 없다.
    TOP1 >= 55 → arbitrary lower-rank 선택은 필수가 아니다. C10 종단 allocator 추적으로.

두 상계 모두 board cap 미적용 · recovery 항상 허용이다(라이브가 허용하는 조건부
overflow 를 모델이 실수로 제외하지 않기 위해).
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
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import networkx as nx  # noqa: E402

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from audit_ub0_static_frontier import (  # noqa: E402
    TARGET,
    WINDOW,
    card_options,
    classify,
)
from saju_engines.daily_selection_policy_shadow import strength_band  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

QUALIFY_MIN = 55
_ILJUS = [f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)]
#: 이전에 문제가 된 다섯 family(본문 역할이 support 인 사건들의 family).
_WATCH = ("close_conversation", "concentration", "rest", "tidying", "walk")


def _match_count(
    per_day: dict[int, list[dict[str, Any]]],
    family_of: dict[str, str],
    *,
    top_only: bool,
) -> tuple[int, dict[int, tuple[int, int]], list[int], set[str]]:
    """날짜 x family 최대 매칭 — board 제약이 없으므로 이것이 정확해다.

    Args:
        per_day: 날짜 → 카드 선택지.
        family_of: 사건 → semantic family.
        top_only: True 면 각 선택지의 `cands[0]` 만 헤드라인으로 인정한다.

    Returns:
        (도달 family 수, 날짜 → (선택지, 후보) , 실현 손실들, 도달 family 집합).
    """
    best: dict[tuple[int, str], tuple[int, int, int]] = {}
    for d, opts in per_day.items():
        for r, o in enumerate(opts):
            limit = 1 if top_only else len(o["candidates"])
            for k in range(limit):
                fam = family_of.get(o["candidates"][k].event_key, "")
                if not fam:
                    continue
                cur = best.get((d, fam))
                if cur is None or o["realized_loss"] < cur[0]:
                    best[(d, fam)] = (o["realized_loss"], r, k)

    g = nx.Graph()
    left = {f"d{d}" for d in per_day}
    for d, fam in best:
        g.add_edge(f"d{d}", f"f{fam}")
    matching = (
        nx.algorithms.bipartite.maximum_matching(g, top_nodes=left)
        if g.number_of_edges() else {}
    )
    picks: dict[int, tuple[int, int]] = {}
    losses: list[int] = []
    fams: set[str] = set()
    for node, other in matching.items():
        if not node.startswith("d"):
            continue
        d, fam = int(node[1:]), other[1:]
        loss, r, k = best[(d, fam)]
        picks[d] = (r, k)
        losses.append(loss)
        fams.add(fam)
    for d, opts in per_day.items():
        if d not in picks and opts:
            r = min(range(len(opts)), key=lambda j: opts[j]["realized_loss"])
            picks[d] = (r, 0)
            losses.append(opts[r]["realized_loss"])
    return len(fams), picks, losses, fams


def _rank_bucket(k: int) -> str:
    return f"rank_{k}" if k <= 2 else "rank_3plus"


def run(anchor: dt.date) -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}

    opts: dict[str, dict[int, list[dict[str, Any]]]] = {i: {} for i in _ILJUS}
    for d in range(WINDOW):
        day = anchor + dt.timedelta(days=d)
        ctx = M.build_day_context(day)
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            opts[ilju][d] = card_options(scored, seed, events)

    ub0: dict[str, int] = {}
    top1: dict[str, int] = {}
    witness: dict[str, dict[int, tuple[int, int]]] = {}
    ub0_losses: list[int] = []
    top1_losses: list[int] = []
    ub0_fams: dict[str, set[str]] = {}
    top1_fams: dict[str, set[str]] = {}
    for ilju in _ILJUS:
        c, picks, losses, fams = _match_count(opts[ilju], family_of, top_only=False)
        ub0[ilju], witness[ilju], ub0_fams[ilju] = c, picks, fams
        ub0_losses += losses
        c2, _p2, losses2, fams2 = _match_count(opts[ilju], family_of, top_only=True)
        top1[ilju], top1_fams[ilju] = c2, fams2
        top1_losses += losses2

    # ── UB0 목표 후보 rank 분포 (변경 유형별)
    rank_by_class: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    live_rank_by_class: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    detail: dict[str, list[float]] = collections.defaultdict(list)
    valence_same = 0
    eligible = 0
    total_changed = 0
    live_families: dict[str, set[str]] = {i: set() for i in _ILJUS}
    all_target_ranks: collections.Counter = collections.Counter()

    for d in range(WINDOW):
        decisions, target = {}, {}
        for ilju in _ILJUS:
            pick = witness[ilju].get(d)
            if pick is None or not opts[ilju][d]:
                continue
            r, k = pick
            decisions[ilju] = opts[ilju][d][r]["candidates"]
            target[ilju] = (r, k)
            all_target_ranks[_rank_bucket(k)] += 1
        order = [i for i in _ILJUS if i in decisions]
        selected, _rs, unresolved = M._rebalance_headlines(
            decisions, order, M._DOMAIN_HEADLINE_CAP
        )
        for ilju in order:
            r, k = target[ilju]
            cands = decisions[ilju]
            tgt, live = cands[k], selected[ilju]
            live_k = next(
                (n for n, c in enumerate(cands) if c.event_key == live.event_key), -1
            )
            tfam = family_of.get(tgt.event_key, "")
            lfam = family_of.get(live.event_key, "")
            before = set(live_families[ilju])
            if tfam != lfam:
                total_changed += 1
                cls = classify(tfam, lfam, before, bool(unresolved))
                rank_by_class[cls][_rank_bucket(k)] += 1
                live_rank_by_class[cls][_rank_bucket(max(live_k, 0))] += 1
                detail[f"{cls}|prob_gap"].append(tgt.probability - live.probability)
                detail[f"{cls}|support_gap"].append(
                    tgt.supporting_groups - live.supporting_groups
                )
                detail[f"{cls}|band_drop"].append(
                    strength_band(live.probability) - strength_band(tgt.probability)
                )
                detail[f"{cls}|target_family_unused"].append(
                    1.0 if tfam not in before else 0.0
                )
                detail[f"{cls}|live_family_already_used"].append(
                    1.0 if lfam in before else 0.0
                )
                valence_same += int(tgt.valence == live.valence)
                eligible += int("headline" in tgt.headline_slots)
            if lfam:
                live_families[ilju].add(lfam)

    ub0_v = sorted(ub0.values())
    top1_v = sorted(top1.values())
    ub0_q = sum(1 for v in ub0_v if v >= TARGET)
    top1_q = sum(1 for v in top1_v if v >= TARGET)

    # ── family 별 rank0 도달 가능성
    watch: dict[str, dict[str, int]] = {}
    for fam in _WATCH:
        watch[fam] = {
            "iljus_reachable_ub0": sum(1 for i in _ILJUS if fam in ub0_fams[i]),
            "iljus_reachable_top1": sum(1 for i in _ILJUS if fam in top1_fams[i]),
        }
    rank_only = sorted({
        f for i in _ILJUS for f in (ub0_fams[i] - top1_fams[i])
    })

    verdict = (
        "GOOD_REPRESENTATIVE_ALLOCATION_ALONE_STRUCTURALLY_INSUFFICIENT"
        if top1_q < QUALIFY_MIN
        else "GOOD_REPRESENTATIVE_ALLOCATION_GAP"
    )
    return {
        "anchor": anchor.isoformat(),
        "ub0": {
            "qualifying_iljus": ub0_q, "family_p10": ub0_v[5], "family_min": ub0_v[0],
            "realized_loss_mean": round(statistics.mean(ub0_losses), 2),
        },
        "top1_only": {
            "qualifying_iljus": top1_q, "family_p10": top1_v[5], "family_min": top1_v[0],
            "realized_loss_mean": round(statistics.mean(top1_losses), 2),
        },
        "ub0_target_rank_distribution_all": dict(all_target_ranks),
        "ub0_target_rank_by_change_class": {
            k: dict(v) for k, v in rank_by_class.items()
        },
        "live_chosen_rank_by_change_class": {
            k: dict(v) for k, v in live_rank_by_class.items()
        },
        "change_detail_means": {
            k: round(statistics.mean(v), 3) for k, v in sorted(detail.items()) if v
        },
        "changed_total": total_changed,
        "changed_same_valence": valence_same,
        "changed_target_headline_eligible": eligible,
        "watch_families": watch,
        "families_reachable_only_with_rank_gt0": rank_only,
        "verdict": verdict,
    }


if __name__ == "__main__":
    anchors = [dt.date.fromisoformat(a) for a in sys.argv[1:]] or [dt.date(2027, 3, 3)]
    results = [run(a) for a in anchors]
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11c_top1_only_bound.json"
    out.write_text(
        json.dumps({
            "audit_id": "OA-11c",
            "policy_status": "measurement_only",
            "live_behavior_changed": False,
            "measurement_stage": "final_headline",
            "results": results,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for r in results:
        u, t = r["ub0"], r["top1_only"]
        print(f"  anchor {r['anchor']}")
        print(f"    UB0(임의 rank) 자격 {u['qualifying_iljus']}/60 p10 {u['family_p10']} "
              f"min {u['family_min']} 손실 {u['realized_loss_mean']}")
        print(f"    TOP1(rank0 고정) 자격 {t['qualifying_iljus']}/60 p10 {t['family_p10']} "
              f"min {t['family_min']} 손실 {t['realized_loss_mean']}")
        print(f"    UB0 목표 rank 분포 {r['ub0_target_rank_distribution_all']}")
        for cls, dist in r["ub0_target_rank_by_change_class"].items():
            print(f"      {cls:44} 목표 {dist}")
            print(f"      {'':44} 라이브 {r['live_chosen_rank_by_change_class'][cls]}")
        print(f"    rank>0 로만 도달하는 family: {r['families_reachable_only_with_rank_gt0']}")
        for fam, w in r["watch_families"].items():
            print(f"      {fam:20} UB0 {w['iljus_reachable_ub0']}/60 · "
                  f"TOP1 {w['iljus_reachable_top1']}/60")
        print(f"    판정: {r['verdict']}")
