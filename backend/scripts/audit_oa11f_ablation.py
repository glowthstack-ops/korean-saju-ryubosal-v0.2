#!/usr/bin/env python3
"""OA-11f-A2 — 丙辰 downcross ablation (측정 전용).

ledger 가 `first_persistent_coverage_delta = 2026-03-15` 를 지목했고 그 직전 개입이
2026-03-14(rank 2 · loss 1)다. R6·R7 공통이며 손실이 1p 라 손실 예산 문제가 아니다.

의심 개입을 하나씩 **S0 선택으로 치환**하고 anchor 까지 downstream 전체를 다시
재생한다. 순차 정책이므로 해당 행만 바꾸고 끝낼 수 없다.

후보 집합을 丙辰 직접 개입으로 제한하지 않는다 — persistent delta 이전의 cross-ilju
개입도 포함한다.
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
_THRESHOLD = 15
_LIMIT = 6                      # R6

#: 丙辰 직접 개입 5건 — 전부 단일 제거한다. 일부만 시험하고 "어느 하나라도" 로
#: 일반화하면 안 된다(앞선 보고에서 그렇게 잘못 서술했다).
TARGET_INTERVENTION_DATES = (
    "2025-04-18", "2025-04-19", "2025-08-06", "2026-02-12", "2026-03-14",
)
SUPPRESS_SETS: dict[str, set[tuple[str, str]]] = {
    "none": set(),
    **{
        f"drop_{d}": {(d, TARGET)} for d in TARGET_INTERVENTION_DATES
    },
    "drop_all_target": {(d, TARGET) for d in TARGET_INTERVENTION_DATES},
}


def replay(suppress: set[tuple[str, str]], family_of, events) -> dict[str, Any]:
    hh: dict[str, list[str]] = collections.defaultdict(list)
    gh: dict[str, list[str]] = collections.defaultdict(list)
    interventions = 0
    suppressed = 0
    #: 대상 행이 실제로 발생했는지 — 앞선 억제로 경로가 바뀌면 도달하지 않는다.
    reached_dates: set[str] = set()
    suppressed_dates: set[str] = set()
    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= ANCHOR:
        iso = day.isoformat()
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
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
            window = tuple(hh[ilju][-B._LOOKBACK:])
            chosen = None
            families = {family_of.get(k, k) for k in window}
            if (
                len(families) < C10_POLICY.coverage_floor
                and repeat_severity(gh[ilju], raw_key) == SEVERITY_CLEAN
            ):
                options = B._safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window,
                    family_of, loss_limit=_LIMIT,
                )
                chosen = B._pick("B1", options) if options else None
            if chosen is not None and (iso, ilju) in suppress:
                reached_dates.add(iso)
                suppressed_dates.add(iso)
                chosen = None                    # S0 선택으로 치환
                suppressed += 1
            if chosen is not None:
                interventions += 1
                g, c, s = chosen["slots"]
                cands = chosen["cands"]
                pick = chosen["event_key"]
            else:
                rep = select_good_representative(
                    goods, gh[ilju], B._BUDGET, policy=C10_POLICY,
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
        result = select_board(
            raw, cmap, hh, domain_cap=21, event_cap=10,
            max_displacement_cost=B._BUDGET, policy=B._BOARD, today=day.toordinal(),
        )
        for ilju, sel in result.selections.items():
            hh[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)

    cov = {}
    for ilju in B._ILJUS:
        w = tuple(hh[ilju][-B._LOOKBACK:])
        cov[ilju] = {
            "key": len(set(w)),
            "family": len({family_of.get(k, k) for k in w}),
        }
    return {
        "interventions": interventions, "suppressed": suppressed,
        "reached_dates": sorted(reached_dates),
        "suppressed_dates": sorted(suppressed_dates),
        "target": cov[TARGET],
        "family_below_15": sum(1 for v in cov.values() if v["family"] < _THRESHOLD),
        "key_below_15": sum(1 for v in cov.values() if v["key"] < _THRESHOLD),
        "family_p10": sorted(v["family"] for v in cov.values())[5],
        "key_p10": sorted(v["key"] for v in cov.values())[5],
    }


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    out = {
        name: replay(suppress, family_of, events)
        for name, suppress in SUPPRESS_SETS.items()
    }
    # 실행 증명 — lint 성공이 측정 실행 성공을 대신하지 않는다.
    requested = {
        name: sorted(d for d, _i in suppress)
        for name, suppress in SUPPRESS_SETS.items()
    }
    base = out["none"]
    for name, r in out.items():
        req = set(requested[name])
        reached = req & set(r["reached_dates"])
        r["execution_proof_row"] = {
            "requested_target_ids": len(req),
            "reached_target_ids": len(reached),
            "suppressed_target_ids": len(set(r["suppressed_dates"]) & req),
            "unreachable_after_path_change": sorted(req - reached),
            "all_reached_targets_suppressed": (
                reached == (set(r["suppressed_dates"]) & req)
            ),
            "direct_suppression": r["suppressed"],
            "downstream_intervention_delta": (
                r["interventions"] - (base["interventions"] - r["suppressed"])
            ),
        }
    for r in out.values():
        r["target_recovered"] = (
            r["target"]["family"] >= _THRESHOLD and r["target"]["key"] >= _THRESHOLD
        )
        r["family_below_delta_vs_r6"] = r["family_below_15"] - base["family_below_15"]
    return {
        "audit_id": "OA-11f-A2",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "target_ilju": TARGET,
        "anchor": ANCHOR.isoformat(),
        "variant": "R6 (loss <= 6)",
        "note": (
            "의심 개입을 S0 선택으로 치환하고 anchor 까지 downstream 전체를 다시 "
            "재생했다 — 순차 정책이라 해당 행만 바꾸고 끝낼 수 없다."
        ),
        #: 원인 표현은 세 층으로 분리한다 — 결과 손실 / but-for 개입 / 매개 경로.
        #: 셋을 한 필드에 합치면 "복원됐다"가 "메커니즘을 안다"로 오독된다.
        "causal_layers": {
            "outcome_failure": "REPLENISHMENT_OMISSION_ON_2026-03-15",
            "but_for_interventions": sorted(
                n.removeprefix("drop_") for n, r in out.items()
                if n.startswith("drop_") and n != "drop_all_target"
                and r["target_recovered"]
            ),
            "noncausal_tested": sorted(
                n.removeprefix("drop_") for n, r in out.items()
                if n.startswith("drop_") and n != "drop_all_target"
                and not r["target_recovered"]
            ),
            "causal_pathway": "SEE_OA-11f-P",
            "rejected": {
                "BROAD_FIVE_INTERVENTION_CUMULATIVE_EROSION": (
                    "REJECTED — 2025 개입 3건은 단독 제거 시 복원 없음(비인과)"
                ),
                "FUTURE_EVICTION": "REJECTED",
                "MARGIN_0_GUARD": "REJECTED — 원인 불일치",
            },
            "unresolved": {
                "TWO_INTERVENTION_SEQUENTIAL_MEDIATION": (
                    "UNRESOLVED — 두 개입이 같은 매개변수를 각자 복원한 것인지 "
                    "순차 매개인지 OA-11f-P 가 판정한다"
                ),
            },
        },
        "results": out,
        "execution_proof": {
            "requested_ablations": requested,
            "per_run": {n: out[n]["execution_proof_row"] for n in out},
            #: 다중 ablation 에서 requested == executed 를 요구하면 안 된다 — 앞선
            #: 억제로 후속 대상 행 자체가 발생하지 않는다. 성립 조건은 "도달한
            #: 대상은 모두 억제됐다" 다.
            "all_reached_targets_suppressed": all(
                out[n]["execution_proof_row"]["all_reached_targets_suppressed"]
                for n in out
            ),
            "single_ablations_fully_reached": all(
                out[n]["execution_proof_row"]["reached_target_ids"] == 1
                for n in out if len(requested[n]) == 1
            ),
            "downstream_replay_days": (
                ANCHOR - B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
            ).days + 1,
            "note": (
                "단일 제거로 복원된다는 것은 그 개입이 단독으로 하락을 일으키기에 "
                "**충분**했다는 뜻이 아니다 — 제거하면 downstream 경로가 바뀌어 최종 "
                "하락이 사라진다는 뜻이다."
            ),
        },
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_a2_ablation.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for name, x in r["results"].items():
        e = x["execution_proof_row"]
        print(f"    증명 req{e['requested_target_ids']}/reach"
              f"{e['reached_target_ids']}/supp{e['suppressed_target_ids']} "
              f"unreach={e['unreachable_after_path_change']} "
              f"direct={e['direct_suppression']} "
              f"downstreamΔ={e['downstream_intervention_delta']}")
        print(f"  {name:28} 개입 {x['interventions']:4d} 억제 {x['suppressed']} · "
              f"{TARGET} f{x['target']['family']}/k{x['target']['key']} "
              f"복원={x['target_recovered']} · "
              f"below15 f{x['family_below_15']}/k{x['key_below_15']} · "
              f"p10 f{x['family_p10']}/k{x['key_p10']}")
