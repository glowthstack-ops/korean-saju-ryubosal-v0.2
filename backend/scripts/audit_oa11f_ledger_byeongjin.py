#!/usr/bin/env python3
"""OA-11f-L — 丙辰 일별 contribution ledger (측정 전용).

coverage 는 90일 창의 **고유 값 개수**다. 따라서 다음 단순식은 쓸 수 없다.

    coverage_today = coverage_yesterday + entering - evicted

같은 family/key 가 창 안에 여러 번 있을 수 있어, 하나가 빠져도 다른 occurrence 가
남으면 coverage 는 줄지 않는다. 그래서 refcount(multiset)를 유지하고 고유 값
집합의 차이로 변화를 계산한다.

    unique_removed = uniques_before - uniques_after
    unique_added   = uniques_after - uniques_before

coverage 계산에는 `history_committed` 만 쓴다. preboard·postboard 는 원인 설명용이다.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
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
VARIANTS = {"S0": None, "R6": 6, "R7": 7}
_THRESHOLD = 15


def _uniques(window: tuple[str, ...], family_of) -> tuple[set[str], set[str]]:
    """(key 고유 집합, family 고유 집합)."""
    return set(window), {family_of.get(k, k) for k in window}


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]

    hh = {n: collections.defaultdict(list) for n in VARIANTS}
    gh = {n: collections.defaultdict(list) for n in VARIANTS}
    ledger: dict[str, list[dict[str, Any]]] = {n: [] for n in VARIANTS}
    interventions: dict[str, list[dict[str, Any]]] = {n: [] for n in VARIANTS}
    # cross-ilju: 그날 어느 일주에 개입이 있었는지
    day_interventions: dict[str, dict[str, list[str]]] = {n: {} for n in VARIANTS}

    day = B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= ANCHOR:
        iso = day.isoformat()
        ctx = M.build_day_context(day)
        for name, limit in VARIANTS.items():
            raw: dict[str, HeadlineCandidate] = {}
            cmap: dict[str, list[HeadlineCandidate]] = {}
            preboard: dict[str, str] = {}
            touched: list[str] = []
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
                window = tuple(hh[name][ilju][-B._LOOKBACK:])
                chosen = None
                if limit is not None:
                    families = {family_of.get(k, k) for k in window}
                    if (
                        len(families) < C10_POLICY.coverage_floor
                        and repeat_severity(gh[name][ilju], raw_key) == SEVERITY_CLEAN
                    ):
                        options = B._safe_candidates(
                            scored, seed, events, ranked, raw_key, raw_p, window,
                            family_of, loss_limit=limit,
                        )
                        chosen = B._pick("B1", options) if options else None
                if chosen is not None:
                    touched.append(ilju)
                    g, c, s = chosen["slots"]
                    cands = chosen["cands"]
                    pick = chosen["event_key"]
                    if ilju == TARGET:
                        interventions[name].append({
                            "date": iso, "event": pick, "rank": chosen["rank"],
                            "loss": chosen["loss"],
                            "family_delta": chosen["fam_cov"],
                            "key_delta": chosen["key_cov"],
                        })
                else:
                    rep = select_good_representative(
                        goods, gh[name][ilju], B._BUDGET, policy=C10_POLICY,
                        family_of=family_of, headline_history=hh[name][ilju],
                    )
                    g, c, s = M._select_slots(
                        scored, seed, good_override=rep.display_good_representative
                    )
                    cands = M._headline_candidates(g, s, c, M._band(g, c))
                    pick = rep.display_good_representative
                cmap[ilju] = [
                    HeadlineCandidate(x.event_key, x.domain, x.probability)
                    for x in cands
                ]
                raw[ilju] = cmap[ilju][0]
                preboard[ilju] = cmap[ilju][0].event_key
                gh[name][ilju].append(pick)
            day_interventions[name][iso] = touched
            result = select_board(
                raw, cmap, hh[name], domain_cap=21, event_cap=10,
                max_displacement_cost=B._BUDGET, policy=B._BOARD,
                today=day.toordinal(),
            )
            # ── 丙辰 ledger (refcount 기반)
            before = tuple(hh[name][TARGET][-B._LOOKBACK:])
            k_before, f_before = _uniques(before, family_of)
            committed = result.selections[TARGET].event_key
            merged = (*hh[name][TARGET], committed)
            after = tuple(merged[-B._LOOKBACK:])
            k_after, f_after = _uniques(after, family_of)
            expired = (
                merged[-B._LOOKBACK - 1] if len(merged) > B._LOOKBACK else None
            )
            ledger[name].append({
                "date": iso,
                "selected_preboard_event": preboard[TARGET],
                "selected_preboard_family": family_of.get(
                    preboard[TARGET], preboard[TARGET]
                ),
                "realized_postboard_event": committed,
                "history_committed_key": committed,
                "history_committed_family": family_of.get(committed, committed),
                "board_displaced": preboard[TARGET] != committed,
                "expired_key": expired,
                "expired_family": (
                    family_of.get(expired, expired) if expired else None
                ),
                "key_unique_removed": sorted(k_before - k_after),
                "key_unique_added": sorted(k_after - k_before),
                "family_unique_removed": sorted(f_before - f_after),
                "family_unique_added": sorted(f_after - f_before),
                "key_coverage": len(k_after),
                "family_coverage": len(f_after),
                "window_len": len(after),
                "history_fingerprint": hashlib.sha256(
                    "|".join(after).encode("utf-8")
                ).hexdigest()[:16],
                "intervened_today": TARGET in touched,
                "other_iljus_intervened_today": len(
                    [i for i in touched if i != TARGET]
                ),
            })
            for ilju, sel in result.selections.items():
                hh[name][ilju].append(sel.event_key)
        day += dt.timedelta(days=1)

    # ── 분기 시점 다섯 가지
    def divergence(variant: str) -> dict[str, Any]:
        s0, v = ledger["S0"], ledger[variant]
        out: dict[str, Any] = dict.fromkeys((
            "first_selection_divergence", "first_history_commit_divergence",
            "first_transient_coverage_delta", "first_persistent_coverage_delta",
            "final_downcross_date",
        ))
        deltas: list[tuple[str, bool]] = []
        for a, b in zip(s0, v, strict=True):
            if out["first_selection_divergence"] is None and (
                a["selected_preboard_event"] != b["selected_preboard_event"]
            ):
                out["first_selection_divergence"] = a["date"]
            if out["first_history_commit_divergence"] is None and (
                a["history_committed_key"] != b["history_committed_key"]
            ):
                out["first_history_commit_divergence"] = a["date"]
            differs = (
                a["family_coverage"] != b["family_coverage"]
                or a["key_coverage"] != b["key_coverage"]
            )
            deltas.append((a["date"], differs))
            if differs and out["first_transient_coverage_delta"] is None:
                out["first_transient_coverage_delta"] = a["date"]
            if (
                a["family_coverage"] >= _THRESHOLD > b["family_coverage"]
                or a["key_coverage"] >= _THRESHOLD > b["key_coverage"]
            ):
                out["final_downcross_date"] = a["date"]
        # persistent = 이후 끝까지 0 으로 복원되지 않는 최초 차이
        for i, (date, differs) in enumerate(deltas):
            if differs and all(d for _dt, d in deltas[i:]):
                out["first_persistent_coverage_delta"] = date
                break
        return out

    # ── anchor 시점 마지막 고유 기여자
    def last_unique_contributor(variant: str) -> dict[str, Any]:
        rows = ledger[variant]
        window = [r for r in rows][-B._LOOKBACK:]
        key_counts: collections.Counter = collections.Counter(
            r["history_committed_key"] for r in window
        )
        fam_counts: collections.Counter = collections.Counter(
            r["history_committed_family"] for r in window
        )
        sole_key = [
            r["date"] for r in window if key_counts[r["history_committed_key"]] == 1
        ]
        sole_fam = [
            r["date"] for r in window
            if fam_counts[r["history_committed_family"]] == 1
        ]
        return {
            "sole_key_contributor_days": len(sole_key),
            "sole_family_contributor_days": len(sole_fam),
            "last_sole_key_date": sole_key[-1] if sole_key else None,
            "last_sole_family_date": sole_fam[-1] if sole_fam else None,
        }

    return {
        "audit_id": "OA-11f-L",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "target_ilju": TARGET,
        "anchor": ANCHOR.isoformat(),
        "coverage_window": (
            f"{(ANCHOR - dt.timedelta(days=90)).isoformat()} ~ "
            f"{(ANCHOR - dt.timedelta(days=1)).isoformat()}"
        ),
        "replay_range": (
            f"{B.DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat()} ~ "
            f"{ANCHOR.isoformat()}"
        ),
        "refcount_note": (
            "coverage 는 고유 값 개수다. entering-evicted 단순식이 아니라 고유 집합 "
            "차이(unique_added/removed)로 계산했다."
        ),
        "anchor_coverage": {
            n: {
                "family": ledger[n][-1]["family_coverage"],
                "key": ledger[n][-1]["key_coverage"],
            }
            for n in VARIANTS
        },
        "divergence": {v: divergence(v) for v in ("R6", "R7")},
        "target_interventions": {n: interventions[n] for n in VARIANTS},
        "last_unique_contributor": {
            n: last_unique_contributor(n) for n in VARIANTS
        },
        "ledger_tail": {
            n: ledger[n][-12:] for n in VARIANTS
        },
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_l_ledger_byeongjin.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    print("  anchor coverage", r["anchor_coverage"])
    for v, d in r["divergence"].items():
        print(f"  {v} 분기 {d}")
    for n, ivs in r["target_interventions"].items():
        print(f"  {TARGET} {n} 개입 {len(ivs)}건 "
              f"{[(x['date'], x['rank'], x['loss']) for x in ivs]}")
    print("  마지막 고유 기여", r["last_unique_contributor"])
