#!/usr/bin/env python3
"""OA-11b — `FULL_PIPELINE_STATIC_FRONTIER_UPPER_BOUND` (UB0) 와 witness live replay.

불가능 증명용 상계는 **더 느슨해야** 한다. 라이브 `_rebalance_headlines` 는 유효한
이동 대안이 없으면 domain 초과를 남길 수 있으므로, MILP 가 `domain_count <= cap` 을
항상 강제하면 라이브가 허용하는 board 를 모델이 제외한다 — 그러면 `Sigma z < 55` 도
구조적 불가능 증명이 되지 않는다.

UB0 계약:

    · 실제 카드 frontier 만 사용(`slots` 계약 불변, 사전 불변)
    · recovery 후보 항상 허용
    · 날짜·일주당 카드 결과 1개
    · **board domain cap 없음** · live greedy 순서 없음 · event-cap 계층 없음

board 제약이 없으면 일주끼리 완전히 분리되므로 UB0 는 MILP 가 아니라 **정확한 최대
매칭**으로 푼다(날짜 x family 이분 그래프). solver 시간 제한이나 mip gap 문제가
아예 생기지 않는다 — 최적성이 구조적으로 보장된다.

그다음 UB0 witness 를 라이브로 재생한다. 헤드라인 문자열이 달라도 family coverage 는
같을 수 있으므로, 불일치를 다섯 가지로 분리해 센다.
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

WINDOW, BUDGET, TARGET = 90, 7, 15
#: 60 중 15 미만이 5개 이하 <=> p10(=6번째로 작은 값) >= 15.
QUALIFY_MIN = 55
_ILJUS = [f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)]

# ── witness 재생 시 불일치 분류 ───────────────────────────────────────────
RELAXED_TARGET_NOT_GREEDY_REACHABLE = "RELAXED_TARGET_NOT_GREEDY_REACHABLE"
RELAXED_TARGET_CAP_EQUIVALENT = "RELAXED_TARGET_CAP_EQUIVALENT"
RELAXED_TARGET_FAMILY_GAIN_LOST = "RELAXED_TARGET_FAMILY_GAIN_LOST"
RELAXED_TARGET_REPLACED_BY_OTHER_NEW_FAMILY = (
    "RELAXED_TARGET_REPLACED_BY_OTHER_NEW_FAMILY"
)
LIVE_REBALANCE_UNRESOLVED_OVERFLOW = "LIVE_REBALANCE_UNRESOLVED_OVERFLOW"


def _band_ok(top_p: int, alt_p: int) -> bool:
    tb, ab = strength_band(top_p), strength_band(alt_p)
    return ab >= tb or (tb != 4 and tb - ab < 2)


def card_options(scored: list, seed: str, events: dict) -> list[dict[str, Any]]:
    """카드 결정 묶음 전수 — 라이브 재생에 필요한 정보를 통째로 보존한다.

    라이브 재배정기는 임의 family 를 고르는 것이 아니라 **정렬된 후보 목록과 이동
    비용을 입력으로 받는 결정적 greedy** 다. 그래서 후보 목록을 그대로 들고 있는다.
    """
    goods = sorted(
        (s for s in scored if s.valence == "good" and "good" in events[s.event_key]["slots"]),
        key=lambda x: -x.probability,
    )
    if not goods:
        return []
    top = goods[0]
    out: list[dict[str, Any]] = []
    for g in goods:
        loss = top.probability - g.probability
        if loss > BUDGET or not _band_ok(top.probability, g.probability):
            continue
        good, caution, support = M._select_slots(scored, seed, good_override=g.event_key)
        if good.event_key != g.event_key:
            continue   # 의도한 대표가 슬롯 자격이 없어 무효화됨
        cands = M._headline_candidates(good, support, caution, M._band(good, caution))
        out.append({
            "good_representative": good.event_key,
            "support": support.event_key,
            "caution": caution.event_key,
            "candidates": cands,
            "realized_loss": loss,
        })
    return out


def ub0_for_ilju(
    per_day: dict[int, list[dict[str, Any]]], family_of: dict[str, str]
) -> tuple[int, dict[int, tuple[int, int]], list[int]]:
    """이 일주의 UB0 — 날짜 x family 최대 매칭(정확해).

    Returns:
        (도달 family 수, 날짜 → (선택지 idx, 후보 idx), 선택된 실현 손실 목록).
    """
    # (날짜, family) → 최소 실현 손실 선택지. 같은 family 면 손실이 낮은 쪽을 쓴다.
    best: dict[tuple[int, str], tuple[int, int, int]] = {}
    for d, opts in per_day.items():
        for r, o in enumerate(opts):
            for k, cand in enumerate(o["candidates"]):
                fam = family_of.get(cand.event_key, "")
                if not fam:
                    continue
                cur = best.get((d, fam))
                if cur is None or o["realized_loss"] < cur[0]:
                    best[(d, fam)] = (o["realized_loss"], r, k)

    g = nx.Graph()
    left = {f"d{d}" for d in per_day}
    for (d, fam) in best:
        g.add_edge(f"d{d}", f"f{fam}")
    matching = (
        nx.algorithms.bipartite.maximum_matching(g, top_nodes=left)
        if g.number_of_edges() else {}
    )
    picks: dict[int, tuple[int, int]] = {}
    losses: list[int] = []
    for node, other in matching.items():
        if not node.startswith("d"):
            continue
        d = int(node[1:])
        fam = other[1:]
        loss, r, k = best[(d, fam)]
        picks[d] = (r, k)
        losses.append(loss)
    covered = len({v for k_, v in matching.items() if k_.startswith("f")})
    # 매칭되지 않은 날짜는 최소 손실 선택지로 채운다(coverage 에 기여하지 않는다).
    for d, opts in per_day.items():
        if d not in picks and opts:
            r = min(range(len(opts)), key=lambda j: opts[j]["realized_loss"])
            picks[d] = (r, 0)
            losses.append(opts[r]["realized_loss"])
    return covered, picks, losses


def classify(
    target_family: str, live_family: str, new_before: set[str], overflow: bool
) -> str:
    """헤드라인 문자열이 달라도 family coverage 는 같을 수 있다."""
    if overflow:
        return LIVE_REBALANCE_UNRESOLVED_OVERFLOW
    if target_family == live_family:
        return RELAXED_TARGET_CAP_EQUIVALENT
    target_was_new = target_family not in new_before
    live_is_new = live_family not in new_before
    if target_was_new and live_is_new:
        return RELAXED_TARGET_REPLACED_BY_OTHER_NEW_FAMILY
    if target_was_new and not live_is_new:
        return RELAXED_TARGET_FAMILY_GAIN_LOST
    return RELAXED_TARGET_NOT_GREEDY_REACHABLE


def run(anchor: dt.date) -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}

    # ── 전 카드 선택지 수집
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

    # ── UB0 (정확해 — board 제약 없음 → 일주별 분리)
    ub0_cover: dict[str, int] = {}
    witness: dict[str, dict[int, tuple[int, int]]] = {}
    ub0_losses: list[int] = []
    for ilju in _ILJUS:
        cover, picks, losses = ub0_for_ilju(opts[ilju], family_of)
        ub0_cover[ilju] = cover
        witness[ilju] = picks
        ub0_losses += losses
    ub0_vals = sorted(ub0_cover.values())
    ub0_qualify = sum(1 for v in ub0_vals if v >= TARGET)

    # ── witness live replay (날짜별 `_rebalance_headlines` 재생)
    live_families: dict[str, set[str]] = {i: set() for i in _ILJUS}
    reasons: collections.Counter = collections.Counter()
    live_losses: list[int] = []
    overflow_days = 0
    target_changed = 0
    for d in range(WINDOW):
        decisions = {}
        target_fam = {}
        for ilju in _ILJUS:
            picks = witness[ilju].get(d)
            if picks is None or not opts[ilju][d]:
                continue
            r, k = picks
            o = opts[ilju][d][r]
            decisions[ilju] = o["candidates"]
            target_fam[ilju] = family_of.get(o["candidates"][k].event_key, "")
            live_losses.append(o["realized_loss"])
        order = [i for i in _ILJUS if i in decisions]
        selected, _rs, unresolved = M._rebalance_headlines(
            decisions, order, M._DOMAIN_HEADLINE_CAP
        )
        if unresolved:
            overflow_days += 1
        for ilju in order:
            live_fam = family_of.get(selected[ilju].event_key, "")
            before = set(live_families[ilju])
            if target_fam[ilju] != live_fam:
                target_changed += 1
                reasons[classify(target_fam[ilju], live_fam, before, bool(unresolved))] += 1
            if live_fam:
                live_families[ilju].add(live_fam)
    live_vals = sorted(len(v) for v in live_families.values())
    live_qualify = sum(1 for v in live_vals if v >= TARGET)

    verdict = (
        "CARD_FRONTIER_STRUCTURALLY_INFEASIBLE" if ub0_qualify < QUALIFY_MIN
        else "SEQUENTIAL_POLICY_GAP" if live_qualify < QUALIFY_MIN
        else "ACHIEVABLE_UNDER_CURRENT_CONTRACT"
    )
    return {
        "anchor": anchor.isoformat(),
        "window_days": WINDOW,
        "ub0": {
            "method": "exact_bipartite_matching_no_board_constraints",
            "qualifying_iljus": ub0_qualify,
            "family_p10": ub0_vals[5],
            "family_min": ub0_vals[0],
            "family_median": ub0_vals[30],
            "realized_loss_mean": round(statistics.mean(ub0_losses), 2),
            "realized_loss_p90": sorted(ub0_losses)[int(len(ub0_losses) * 0.9)],
        },
        "witness_live_replay": {
            "qualifying_iljus": live_qualify,
            "family_p10": live_vals[5],
            "family_min": live_vals[0],
            "family_median": live_vals[30],
            "realized_loss_mean": round(statistics.mean(live_losses), 2),
            "realized_loss_p90": sorted(live_losses)[int(len(live_losses) * 0.9)],
            "relaxed_target_changed": target_changed,
            "change_reasons": dict(reasons),
            "overflow_days": overflow_days,
        },
        "cut_iterations": 0,
        "solver_status": "EXACT_BY_CONSTRUCTION_NO_MILP",
        "mip_gap": 0.0,
        "verdict": verdict,
    }


if __name__ == "__main__":
    anchors = [dt.date.fromisoformat(a) for a in sys.argv[1:]] or [dt.date(2027, 3, 3)]
    results = [run(a) for a in anchors]
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11b_ub0_static_frontier.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({
            "audit_id": "OA-11b",
            "policy_status": "measurement_only",
            "live_behavior_changed": False,
            "measurement_stage": "final_headline",
            "model_name": "FULL_PIPELINE_STATIC_FRONTIER_UPPER_BOUND",
            "contract": {
                "board_domain_cap": "NOT_ENFORCED",
                "recovery": "ALWAYS_ALLOWED",
                "event_cap_layer": "ABSENT",
                "note": (
                    "라이브가 허용하는 조건부 overflow 를 모델이 제외하지 않도록 board "
                    "제약을 아예 넣지 않았다. 그래서 Sigma z < 55 는 유효한 불가능 "
                    "증명이고, Sigma z >= 55 는 가능성 증명이 아니다."
                ),
            },
            "results": results,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for r in results:
        u, w = r["ub0"], r["witness_live_replay"]
        print(f"  anchor {r['anchor']}")
        print(f"    UB0   자격 {u['qualifying_iljus']}/60 · p10 {u['family_p10']} · "
              f"min {u['family_min']} · 손실 평균 {u['realized_loss_mean']} "
              f"p90 {u['realized_loss_p90']}")
        print(f"    live  자격 {w['qualifying_iljus']}/60 · p10 {w['family_p10']} · "
              f"min {w['family_min']} · 손실 평균 {w['realized_loss_mean']} "
              f"p90 {w['realized_loss_p90']}")
        print(f"    목표 변경 {w['relaxed_target_changed']} · overflow 날짜 "
              f"{w['overflow_days']}")
        for k, v in sorted(w["change_reasons"].items(), key=lambda t: -t[1]):
            print(f"      {k:46} {v}")
        print(f"    판정: {r['verdict']}")
