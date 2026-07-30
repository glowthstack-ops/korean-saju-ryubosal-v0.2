#!/usr/bin/env python3
"""OA-11f-Q — B selector 의 품질·안전 감사 (selector 미변경, 측정 전용).

5-anchor 결과를 보고 selector 를 고친 뒤 730-anchor 를 돌리면 그것은 독립 검증이
아니라 추가 최적화 데이터가 된다. 그래서 이 감사는 **selector 를 손대지 않고**
측정만 한다.

품질 지표는 503개 개입이 발생한 **917일 canonical replay 전체**를 분모로 쓴다.
307행 진단 표본을 품질 분모로 재사용하지 않는다.

이득 상쇄는 당일 board 까지만 확정한다. eviction 과 downstream 을 억지로 분리하면
불완전한 추정이 되므로 `UNRESOLVED_DOWNSTREAM_OFFSET` 으로 묶고, 순효과는
730-anchor 집계에서 본다.
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

import audit_oa11f_b_online_replay as B  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    repeat_severity,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

_BUDGET = B._BUDGET


def _pct(values: list[int], q: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * q))]


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]

    hh: dict[str, list[str]] = collections.defaultdict(list)
    gh: dict[str, list[str]] = collections.defaultdict(list)
    # S0 를 같은 루프에서 병행 재생해 범위 누출을 행 단위로 판정한다.
    s0_hh: dict[str, list[str]] = collections.defaultdict(list)
    s0_gh: dict[str, list[str]] = collections.defaultdict(list)

    counts: collections.Counter = collections.Counter()
    losses: list[int] = []
    ranks: collections.Counter = collections.Counter()
    frontier_ranks: collections.Counter = collections.Counter()
    leak: collections.Counter = collections.Counter()
    gain: collections.Counter = collections.Counter()
    diverged = False

    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= B._LAST:
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        s0_raw: dict[str, HeadlineCandidate] = {}
        s0_cmap: dict[str, list[HeadlineCandidate]] = {}
        pending: dict[str, dict[str, Any]] = {}
        for idx, ilju in enumerate(B._ILJUS):
            stem, branch = ganzi_from_index(idx)
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            if not goods:
                continue
            counts["total_rows"] += 1
            ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
            raw_key, raw_p = ranked[0]

            # ── B 경로
            window = tuple(hh[ilju][-B._LOOKBACK:])
            families = {family_of.get(k, k) for k in window}
            deficit = len(families) < C10_POLICY.coverage_floor
            clean = repeat_severity(gh[ilju], raw_key) == SEVERITY_CLEAN
            options: list[dict[str, Any]] = []
            if deficit and clean:
                counts["deficit_and_clean_rows"] += 1
                options = B._safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window, family_of
                )
                if options:
                    counts["candidate_available_rows"] += 1
            chosen = B._pick("B1", options) if options else None
            if chosen is not None:
                counts["intervention_rows"] += 1
                losses.append(chosen["loss"])
                ranks[min(chosen["rank"], 6)] += 1
                frontier_ranks[
                    min(1 + sorted(o["rank"] for o in options).index(chosen["rank"]), 6)
                ] += 1
                # 안전 가드 재검증 — selector 가 이미 걸렀지만 독립 확인한다.
                band = strength_band(raw_p - chosen["loss"])
                top_band = strength_band(raw_p)
                if chosen["loss"] > _BUDGET:
                    counts["loss_budget_violation"] += 1
                elif chosen["loss"] == _BUDGET:
                    counts["at_budget"] += 1
                elif chosen["loss"] >= _BUDGET - 1:
                    counts["near_budget"] += 1
                if top_band == 4 and band < top_band:
                    counts["s5_protection_violation"] += 1
                if top_band - band >= 2:
                    counts["two_band_drop_violation"] += 1
                if chosen["key_cov"] < 0 or chosen["key_qual"] < 0:
                    counts["key_guard_violation"] += 1
                g, c, s = chosen["slots"]
                cands = chosen["cands"]
                pick = chosen["event_key"]
                pending[ilju] = {"expected": chosen["preboard_family"]}
            else:
                rep = select_good_representative(
                    goods, gh[ilju], _BUDGET, policy=C10_POLICY,
                    family_of=family_of, headline_history=hh[ilju],
                )
                g, c, s = M._select_slots(
                    scored, seed, good_override=rep.display_good_representative
                )
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                pick = rep.display_good_representative
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            gh[ilju].append(pick)

            # ── S0 경로(범위 누출 판정용). 분기 이후에는 이력이 갈라지므로
            #    최초 분기 이전 구간에서만 mismatch 를 센다.
            s0_rep = select_good_representative(
                goods, s0_gh[ilju], _BUDGET, policy=C10_POLICY,
                family_of=family_of, headline_history=s0_hh[ilju],
            )
            sg, sc, ss = M._select_slots(
                scored, seed, good_override=s0_rep.display_good_representative
            )
            s0_cands = M._headline_candidates(sg, ss, sc, M._band(sg, sc))
            s0_cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability)
                for x in s0_cands
            ]
            s0_raw[ilju] = s0_cmap[ilju][0]
            s0_gh[ilju].append(s0_rep.display_good_representative)

            if not diverged and chosen is None and pick != (
                s0_rep.display_good_representative
            ):
                # 개입하지 않았는데 선택이 다르다 → 조건별로 분류
                if not deficit:
                    leak["mismatch_no_deficit"] += 1
                elif not clean:
                    leak["mismatch_not_clean"] += 1
                elif not options:
                    leak["mismatch_no_positive_candidate"] += 1
                else:
                    leak["mismatch_unclassified"] += 1

        result = select_board(
            raw, cmap, hh, domain_cap=21, event_cap=10,
            max_displacement_cost=_BUDGET, policy=B._BOARD, today=day.toordinal(),
        )
        s0_result = select_board(
            s0_raw, s0_cmap, s0_hh, domain_cap=21, event_cap=10,
            max_displacement_cost=_BUDGET, policy=B._BOARD, today=day.toordinal(),
        )
        for ilju, sel in result.selections.items():
            fam = family_of.get(sel.event_key, sel.event_key)
            if ilju in pending:
                if fam == pending[ilju]["expected"]:
                    gain["GAIN_SURVIVED_SAME_DAY_BOARD"] += 1
                else:
                    gain["GAIN_ERASED_BY_BOARD"] += 1
            hh[ilju].append(sel.event_key)
        for ilju, sel in s0_result.selections.items():
            s0_hh[ilju].append(sel.event_key)
        if not diverged and any(
            result.selections[i].event_key != s0_result.selections[i].event_key
            for i in result.selections
        ):
            diverged = True
        day += dt.timedelta(days=1)

    available = counts["candidate_available_rows"]
    intervention = counts["intervention_rows"]
    return {
        "audit_id": "OA-11f-Q",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "selector": "UNCHANGED_FROM_OA11F_B (B1)",
        "denominator_scope": "full_917_day_canonical_replay",
        "selector_order_sensitivity": (
            "NOT_OBSERVED_IN_70_MULTI_CANDIDATE_SAMPLE"
        ),
        "intervention": {
            "total_rows": counts["total_rows"],
            "deficit_and_clean_rows": counts["deficit_and_clean_rows"],
            "candidate_available_rows": available,
            "intervention_rows": intervention,
            "intervention_rate_all_pct": round(
                100 * intervention / max(1, counts["total_rows"]), 3
            ),
            "candidate_available_rate_pct": round(
                100 * available / max(1, counts["deficit_and_clean_rows"]), 2
            ),
            "intervention_rate_when_available_pct": round(
                100 * intervention / max(1, available), 2
            ),
            "invariant_available_equals_intervention": available == intervention,
        },
        "original_candidate_rank": {
            (f"rank_{k}" if k < 6 else "rank_gt_5"): v
            for k, v in sorted(ranks.items())
        },
        "safe_frontier_rank": {
            (f"rank_{k}" if k < 6 else "rank_gt_5"): v
            for k, v in sorted(frontier_ranks.items())
        },
        "display_displacement_loss": {
            "n": len(losses),
            "p50": _pct(losses, 0.50), "p75": _pct(losses, 0.75),
            "p90": _pct(losses, 0.90), "p95": _pct(losses, 0.95),
            "p99": _pct(losses, 0.99), "max": max(losses) if losses else None,
            "mean": round(statistics.mean(losses), 3) if losses else None,
            "budget": _BUDGET,
            "at_budget": counts["at_budget"],
            "near_budget": counts["near_budget"],
            "loss_budget_violation": counts["loss_budget_violation"],
            "representation": "integer probability points (정수 — tolerance 불필요)",
        },
        "safety_violations": {
            "s5_protection": counts["s5_protection_violation"],
            "two_band_drop": counts["two_band_drop_violation"],
            "loss_budget": counts["loss_budget_violation"],
            "key_guard": counts["key_guard_violation"],
        },
        "scope_leakage": {
            **dict(leak),
            "total": sum(leak.values()),
            "note": (
                "한 행이 여러 조건에 해당할 수 있어 개별 수의 합을 전체 행 수로 "
                "표현하지 않는다. 최초 분기 이전 구간에서만 판정한다."
            ),
        },
        "gain_offsets": {
            **dict(gain),
            "UNRESOLVED_DOWNSTREAM_OFFSET": (
                "eviction·downstream 상쇄는 억지로 분리하지 않는다 — 순효과는 "
                "730-anchor 집계에서 본다"
            ),
        },
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_q_quality.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    i = r["intervention"]
    print(f"  전체 {i['total_rows']} · deficit·CLEAN {i['deficit_and_clean_rows']} · "
          f"후보 있음 {i['candidate_available_rows']} · 개입 {i['intervention_rows']}")
    print(f"  개입률 전체 {i['intervention_rate_all_pct']}% · "
          f"후보 존재율 {i['candidate_available_rate_pct']}% · "
          f"후보 있을 때 개입 {i['intervention_rate_when_available_pct']}% · "
          f"불변식 {i['invariant_available_equals_intervention']}")
    print(f"  원 후보 rank {r['original_candidate_rank']}")
    print(f"  손실 {r['display_displacement_loss']}")
    print(f"  안전 위반 {r['safety_violations']}")
    print(f"  범위 누출 {r['scope_leakage']}")
    print(f"  이득 {dict(list(r['gain_offsets'].items())[:2])}")
