#!/usr/bin/env python3
"""OA-11f-B — 안전 후보 풀의 **온라인** 도달성 (측정 전용, 정책 미채택).

OA-11f-A 는 행 단위 한계효과만 봤다. 문턱 이득 후보가 anchor 마다 10~18건이고
필요한 순증가가 1·1·3·1 이지만, 그것만으로 닫힌다고 말할 수 없다 — 앞선 선택이
이후 후보의 delta 를 바꾸고 eviction·board 가 상쇄한다(S1 에서 실현 34건이 순증가
0 이 된 것과 같은 구조).

이 감사는 새 정책 개발이 아니라, candidate/slot 계약을 확장하기 전에 필요한
**마지막 반증 단계**다.

    S0  기존 C10 (대조군 — selector 를 끄면 C10 과 같아야 한다)
    B1  threshold-first  online
    B2  coverage-first   online
    B3  optimistic safe local bound (production 후보 아님)

`SAFETY_BLOCKED` 후보는 어떤 모드에서도 쓰지 않는다 — 안전 가드를 완화했을 때의
가능성을 보는 감사가 아니다.
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

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    build_rolling_audit_aggregates,
    derive_diagnostic_contract,
)
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_BOARD_CONTRACT_V1,
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    CardCandidateBundle,
    ProjectionStatus,
    derive_top1_family_projection,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    SelectionPolicy,
    repeat_severity,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_ILJUS = [
    f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)
]
ANCHORS = ("2026-04-02", "2027-03-03", "2027-06-01", "2027-08-05", "2027-10-09")
_LAST = dt.date(2027, 10, 9)
_LOOKBACK = DAILY_HISTORY_CONTRACT_V1.lookback_days
_BUDGET = DAILY_BOARD_CONTRACT_V1.displacement_loss_budget
_QUALIFY = 15
MODES = ("S0", "B1", "B2", "B3")


def _next_counts(window: tuple[str, ...], addition: str, family_of) -> tuple[int, int]:
    merged = (*window, addition)
    if len(merged) > _LOOKBACK:
        merged = merged[-_LOOKBACK:]
    return len(set(merged)), len({family_of.get(k, k) for k in merged})


def _safe_candidates(
    scored, seed, events, ranked, raw_key, raw_p, window, family_of
) -> list[dict[str, Any]]:
    """기존 후보열 중 안전 가드를 모두 통과한 후보의 한계효과."""
    rg, rc, rs = M._select_slots(scored, seed, good_override=raw_key)
    if rg.event_key != raw_key:
        return []
    rcands = M._headline_candidates(rg, rs, rc, M._band(rg, rc))
    base_key, base_fam = _next_counts(window, rcands[0].event_key, family_of)
    top_band = strength_band(raw_p)
    out: list[dict[str, Any]] = []
    for rank, (key, prob) in enumerate(ranked, start=1):
        if key == raw_key:
            continue
        loss = raw_p - prob
        band = strength_band(prob)
        if loss > _BUDGET or (top_band == 4 and band < top_band) or (
            top_band - band >= 2
        ):
            continue                              # SAFETY_BLOCKED — 쓰지 않는다
        g, c, s = M._select_slots(scored, seed, good_override=key)
        if g.event_key != key:
            continue
        cands = M._headline_candidates(g, s, c, M._band(g, c))
        projection = derive_top1_family_projection(
            raw_top_event_key=key,
            card_candidates=CardCandidateBundle(
                good_event_key=g.event_key, slots=(g, c, s),
                headline_candidates=tuple(cands),
            ),
            family_of=family_of,
        )
        if projection.status is not ProjectionStatus.PROJECTED:
            continue
        cand_key, cand_fam = _next_counts(window, cands[0].event_key, family_of)
        fam_qual = int(cand_fam >= _QUALIFY) - int(base_fam >= _QUALIFY)
        key_qual = int(cand_key >= _QUALIFY) - int(base_key >= _QUALIFY)
        fam_cov = cand_fam - base_fam
        key_cov = cand_key - base_key
        if fam_cov <= 0 or key_cov < 0 or key_qual < 0:
            continue                              # 순이득 없거나 key 위험
        out.append({
            "rank": rank, "event_key": key, "slots": (g, c, s), "cands": cands,
            "fam_qual": fam_qual, "fam_cov": fam_cov,
            "key_qual": key_qual, "key_cov": key_cov, "loss": loss,
            "preboard_family": projection.family,
        })
    return out


def _pick(mode: str, options: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not options:
        return None
    if mode == "B1":            # 즉시 문턱 우선
        return min(options, key=lambda o: (
            -o["fam_qual"], -o["fam_cov"], -o["key_qual"], -o["key_cov"],
            o["rank"], o["event_key"],
        ))
    if mode == "B2":            # coverage 우선(13→14 도 포함)
        return min(options, key=lambda o: (
            -o["fam_cov"], -o["fam_qual"], -o["key_qual"], -o["key_cov"],
            o["rank"], o["event_key"],
        ))
    # B3 — 감사 목적함수를 가장 크게. production 후보가 아니며 lookahead 도
    # 쓰지 않으므로 참 상한이 아니라 **로컬** 낙관 경계다.
    return min(options, key=lambda o: (
        -(o["fam_qual"] * 10 + o["fam_cov"]), -o["key_qual"], -o["key_cov"],
        o["loss"], o["rank"], o["event_key"],
    ))


def replay(mode: str, family_of, events) -> dict[str, Any]:
    """canonical 연속 재생 — anchor 별 독립 실행이 아니다."""
    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    stats: collections.Counter = collections.Counter()
    rows_out: list[dict[str, Any]] = []
    day = DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    while day <= _LAST:
        ctx = M.build_day_context(day)
        raw_sel: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        pending: dict[str, dict[str, Any]] = {}
        intended: dict[str, str] = {}
        for idx, ilju in enumerate(_ILJUS):
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
            ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
            raw_key, raw_p = ranked[0]
            window = tuple(headline_history[ilju][-_LOOKBACK:])
            families = {family_of.get(k, k) for k in window}
            deficit = (
                C10_POLICY.coverage_floor is not None
                and len(families) < C10_POLICY.coverage_floor
            )
            clean = repeat_severity(good_history[ilju], raw_key) == SEVERITY_CLEAN
            chosen = None
            if mode != "S0" and deficit and clean:
                options = _safe_candidates(
                    scored, seed, events, ranked, raw_key, raw_p, window, family_of
                )
                stats["rows_with_options"] += bool(options)
                chosen = _pick(mode, options)
            if chosen is not None:
                stats["selected"] += 1
                stats["immediate_threshold_gain"] += chosen["fam_qual"] > 0
                stats["coverage_only_gain"] += chosen["fam_qual"] == 0
                g, c, s = chosen["slots"]
                cands = chosen["cands"]
                intended[ilju] = chosen["event_key"]
                pending[ilju] = {
                    "expected_family": chosen["preboard_family"],
                    "fam_qual": chosen["fam_qual"],
                }
            else:
                rep = select_good_representative(
                    goods, good_history[ilju], _BUDGET, policy=C10_POLICY,
                    family_of=family_of, headline_history=headline_history[ilju],
                )
                g, c, s = M._select_slots(
                    scored, seed, good_override=rep.display_good_representative
                )
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                intended[ilju] = rep.display_good_representative
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw_sel[ilju] = cmap[ilju][0]
            good_history[ilju].append(intended[ilju])
            rows_out.append({
                "fortune_date": day.isoformat(), "ilju": ilju,
                "final_headline": None,
            })
        result = select_board(
            raw_sel, cmap, headline_history,
            domain_cap=DAILY_BOARD_CONTRACT_V1.domain_cap_count,
            event_cap=DAILY_BOARD_CONTRACT_V1.event_cap_count,
            max_displacement_cost=_BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        base = len(rows_out) - len(raw_sel)
        for offset, ilju in enumerate(i for i in _ILJUS if i in raw_sel):
            sel = result.selections[ilju]
            rows_out[base + offset]["final_headline"] = sel.event_key
            fam = family_of.get(sel.event_key, sel.event_key)
            if ilju in pending:
                if fam != pending[ilju]["expected_family"]:
                    stats["board_erased_gain"] += 1
                elif pending[ilju]["fam_qual"] > 0:
                    stats["threshold_gain_survived_board"] += 1
            headline_history[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)
    return {"rows": rows_out, "stats": dict(stats)}


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    domain_of = {k: e["domain"] for k, e in events.items()}
    contract = derive_diagnostic_contract(
        anchor_days=(_LAST - dt.date(2026, 1, 1)).days + 1
    )

    out: dict[str, Any] = {}
    for mode in MODES:
        res = replay(mode, family_of, events)
        agg = build_rolling_audit_aggregates(
            res["rows"], family_of, domain_of, contract
        )
        by = {a["anchor_date"]: a for a in agg["anchors"]}
        fam_q = agg["family_qualifying_count_by_anchor"]
        out[mode] = {
            "stats": res["stats"],
            "anchors": {
                iso: {
                    "family_p10": by[iso]["family_p10"],
                    "family_qualifying": fam_q[iso],
                    "key_p10": by[iso]["key_p10"],
                    "key_below_15": by[iso]["count_below_15"],
                    "domain_p10": by[iso]["domain_p10"],
                }
                for iso in ANCHORS
            },
        }
    s0 = out["S0"]["anchors"]
    verdict = {}
    for mode in ("B1", "B2", "B3"):
        a = out[mode]["anchors"]
        verdict[mode] = {
            "family_gate_all": all(
                a[i]["family_p10"] >= 15 and a[i]["family_qualifying"] >= 55
                for i in ANCHORS
            ),
            "no_regression": all(
                a[i]["family_qualifying"] >= s0[i]["family_qualifying"]
                and a[i]["key_p10"] >= s0[i]["key_p10"]
                and a[i]["key_below_15"] <= s0[i]["key_below_15"]
                for i in ANCHORS
            ),
        }
    return {
        "audit_id": "OA-11f-B",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "note": (
            "SAFETY_BLOCKED 후보는 어떤 모드에서도 쓰지 않는다. B3 는 lookahead 를 "
            "쓰지 않으므로 참 상한이 아니라 로컬 낙관 경계다."
        ),
        "modes": out,
        "verdict": verdict,
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_b_online_replay.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for mode in MODES:
        m = r["modes"][mode]
        print(f"  {mode}  {m['stats']}")
        for iso, a in m["anchors"].items():
            print(f"      {iso} family {a['family_p10']}/{a['family_qualifying']} "
                  f"key {a['key_p10']}/{a['key_below_15']}")
    print("  판정:", r["verdict"])
