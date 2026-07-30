#!/usr/bin/env python3
"""OA-11d-S1 — canonical 연속 schedule 에서 S1 인과 funnel (측정 전용, 라이브 불변).

두 실행이 **같은 canonical schedule**에서 나오고 bypass flag 하나만 다르다.

    S0 = trace ON + bypass OFF
    S1 = trace ON + bypass ON

anchor 별로 state 를 새로 만들거나 첫 anchor 를 빈 state 로 시작하면 다시 harness
drift 다. 그래서 공식 원점(2025-04-06)부터 연속 재생하고, cold-start 행
(이력 90일 미만)은 공식 수치에서 배제한다.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    build_rolling_audit_aggregates,
    derive_diagnostic_contract,
)
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    build_rolling_audit_schedule,
)
from saju_engines.daily_selection_policy_shadow import SelectionPolicy  # noqa: E402

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
ANCHORS = ("2026-04-02", "2027-03-03", "2027-06-01", "2027-08-05", "2027-10-09")
_LAST = dt.date(2027, 10, 9)
_LOOKBACK = DAILY_HISTORY_CONTRACT_V1.lookback_days

# ── 상호 배타 분류 ────────────────────────────────────────────────────────
NO_FAMILY_DEFICIT = "NO_FAMILY_DEFICIT"
NOT_CLEAN = "NOT_CLEAN"
RAW_TOP_CARD_NOT_AVAILABLE = "RAW_TOP_CARD_NOT_AVAILABLE"
AMBIGUOUS = "AMBIGUOUS"
PROJECTED_FAMILY_ALREADY_SEEN = "PROJECTED_FAMILY_ALREADY_SEEN"
BYPASS_NO_SELECTION_CHANGE = "BYPASS_NO_SELECTION_CHANGE"
SELECTION_CHANGED_TO_NON_NEW_FAMILY = "SELECTION_CHANGED_TO_NON_NEW_FAMILY"
NEW_FAMILY_SELECTED_BUT_CHANGED_BY_BOARD = (
    "NEW_FAMILY_SELECTED_BUT_CHANGED_BY_BOARD"
)
NEW_FAMILY_REALIZED = "NEW_FAMILY_REALIZED"
SELECTED_PREBOARD_FAMILY_AMBIGUOUS = "SELECTED_PREBOARD_FAMILY_AMBIGUOUS"

_ENTRY_DROPS = (
    NO_FAMILY_DEFICIT, NOT_CLEAN, RAW_TOP_CARD_NOT_AVAILABLE, AMBIGUOUS,
    PROJECTED_FAMILY_ALREADY_SEEN,
)
_POST_BYPASS = (
    BYPASS_NO_SELECTION_CHANGE, SELECTION_CHANGED_TO_NON_NEW_FAMILY,
    NEW_FAMILY_SELECTED_BUT_CHANGED_BY_BOARD, NEW_FAMILY_REALIZED,
    SELECTED_PREBOARD_FAMILY_AMBIGUOUS,
)


def classify(trace: dict[str, Any]) -> str:
    """행 하나를 정확히 하나의 분류로 — 진입 전 탈락과 우회 후 결과를 섞지 않는다."""
    if not trace["family_deficit_active"]:
        return NO_FAMILY_DEFICIT
    if not trace["raw_top_repeat_clean"]:
        return NOT_CLEAN
    status = trace["projection_status"]
    if status == "UNAVAILABLE":
        return RAW_TOP_CARD_NOT_AVAILABLE
    if status == "AMBIGUOUS":
        return AMBIGUOUS
    if not trace["projected_family_is_new"]:
        return PROJECTED_FAMILY_ALREADY_SEEN
    # 여기까지 오면 우회가 열렸다.
    if not trace["selection_changed_from_raw_top"]:
        return BYPASS_NO_SELECTION_CHANGE
    if trace["selected_preboard_family_status"] != "PROJECTED":
        # 단일 확정이 안 되면 board 문제로 분류하지 않는다.
        return SELECTED_PREBOARD_FAMILY_AMBIGUOUS
    if not trace["selected_preboard_family_is_new"]:
        return SELECTION_CHANGED_TO_NON_NEW_FAMILY
    if trace.get("realized_final_family") != trace["selected_preboard_family"]:
        return NEW_FAMILY_SELECTED_BUT_CHANGED_BY_BOARD
    return NEW_FAMILY_REALIZED


def _run(policy, family_of, days: int):
    return build_rolling_audit_schedule(
        days=days, policy=policy, board_policy=_BOARD, family_of=family_of,
        compute_projection_trace=True,
    )


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    domain_of = {k: e["domain"] for k, e in events.items()}
    days = (_LAST - DAILY_ROLLING_AUDIT_CONTRACT_V1.origin).days + 1

    off = replace(C10_POLICY, family_deficit_clean_bypass=False)
    on = replace(C10_POLICY, family_deficit_clean_bypass=True)
    s0_steps, _a = _run(off, family_of, days)
    s1_steps, _b = _run(on, family_of, days)

    def rows(steps):
        return {
            (st.fortune_date.isoformat(), r["ilju"]): r
            for st in steps for r in st.rows
        }

    s0, s1 = rows(s0_steps), rows(s1_steps)

    # ── S0 가 R0 baseline 과 일치하는지(anchor 300행)
    frozen_path = _BACKEND / "compiled" / "oa10b_characterization_rows.jsonl"
    baseline = {}
    if frozen_path.exists():
        with frozen_path.open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                baseline[(r["fortune_date"], r["ilju"])] = r
    fields = (
        "raw_good_winner", "intended_good_representative", "realized_good_event",
        "support_event", "caution_event", "raw_headline", "final_headline",
        "final_headline_family", "selection_reason_codes",
        "display_displacement_loss",
    )
    s0_baseline_mismatch = sum(
        1 for key, row in s0.items()
        if key[0] in ANCHORS and key in baseline
        and any(baseline[key].get(f) != row.get(f) for f in fields)
    )

    # ── 이력 길이 90일 확인 (cold-start 배제) — 각 anchor 의 측정 창 전체
    window_days: set[str] = set()
    for iso in ANCHORS:
        anchor_day = dt.date.fromisoformat(iso)
        window_days |= {
            (anchor_day - dt.timedelta(days=n)).isoformat()
            for n in range(1, _LOOKBACK + 1)
        }
    short_history = sum(
        1 for key, row in s0.items()
        if key[0] in window_days
        and row["oa11d_trace"]["state_before_history_len"] != _LOOKBACK
    )

    # ── 범위 누출은 **최초 분기 이전** 행에서만 판정한다.
    #
    # 진입 전 탈락 행이 S0 와 달라지는 것은 대개 이전 날짜의 우회가 이력을 바꿔
    # 하류로 전파된 결과다 — 정당한 전파를 누출로 세면 안 된다. 두 실행의
    # state_before 가 같은 날짜까지만 비교한다.
    first_divergence = None
    for st_a, st_b in zip(s0_steps, s1_steps, strict=True):
        if st_a.state_before_fingerprint != st_b.state_before_fingerprint:
            first_divergence = st_a.fortune_date.isoformat()
            break
    leak = 0
    leak_scope_days = 0
    for st_a, st_b in zip(s0_steps, s1_steps, strict=True):
        if st_a.state_before_fingerprint != st_b.state_before_fingerprint:
            break                    # 이후는 전파 구간 — 누출 판정 대상이 아니다
        leak_scope_days += 1
        for a_row, b_row in zip(st_a.rows, st_b.rows, strict=True):
            if classify(b_row["oa11d_trace"]) not in _ENTRY_DROPS:
                continue
            if any(a_row.get(f) != b_row.get(f) for f in fields):
                leak += 1

    # ── anchor 별 funnel — anchor **당일**이 아니라 그 anchor 의 측정 창
    #    (D-90 ~ D-1)을 센다. family_p10 이 그 창으로 계산되므로 S1 개입이
    #    실제로 일어나는 구간이 여기다. 당일만 세면 개입을 전혀 못 본다.
    funnel: dict[str, dict[str, int]] = {}
    for iso in ANCHORS:
        anchor_day = dt.date.fromisoformat(iso)
        window = {
            (anchor_day - dt.timedelta(days=n)).isoformat()
            for n in range(1, _LOOKBACK + 1)
        }
        counter: collections.Counter = collections.Counter()
        for key, b in s1.items():
            if key[0] not in window:
                continue
            t = b["oa11d_trace"]
            if t["state_before_history_len"] != _LOOKBACK:
                counter["EXCLUDED_COLD_START"] += 1
                continue
            counter[classify(t)] += 1
        bypassed = sum(counter[k] for k in _POST_BYPASS)
        counter["BYPASSED_TOTAL"] = bypassed
        funnel[iso] = dict(counter)

    # ── 교차 불변식
    invariant_violations = [
        iso for iso, f in funnel.items()
        if f.get("BYPASSED_TOTAL", 0) != sum(
            f.get(k, 0) for k in _POST_BYPASS
        )
    ]

    # ── 집계
    contract = derive_diagnostic_contract(
        anchor_days=(_LAST - dt.date(2026, 1, 1)).days + 1
    )

    def agg(rowmap):
        plain = [
            {k: v for k, v in r.items() if k != "oa11d_trace"}
            for _key, r in sorted(rowmap.items())
        ]
        return build_rolling_audit_aggregates(plain, family_of, domain_of, contract)

    a_agg, b_agg = agg(s0), agg(s1)
    a_by = {x["anchor_date"]: x for x in a_agg["anchors"]}
    b_by = {x["anchor_date"]: x for x in b_agg["anchors"]}
    a_fam = a_agg["family_qualifying_count_by_anchor"]
    b_fam = b_agg["family_qualifying_count_by_anchor"]

    table = {}
    for iso in ANCHORS:
        table[iso] = {
            "s0_family_p10": a_by[iso]["family_p10"],
            "s1_family_p10": b_by[iso]["family_p10"],
            "s0_family_qualifying": a_fam[iso],
            "s1_family_qualifying": b_fam[iso],
            "family_qualifying_delta": b_fam[iso] - a_fam[iso],
            "s0_key_p10": a_by[iso]["key_p10"],
            "s1_key_p10": b_by[iso]["key_p10"],
            "s0_key_below_15": a_by[iso]["count_below_15"],
            "s1_key_below_15": b_by[iso]["count_below_15"],
            "s0_domain_p10": a_by[iso]["domain_p10"],
            "s1_domain_p10": b_by[iso]["domain_p10"],
        }

    family_pass = all(
        t["s1_family_p10"] >= 15 and t["s1_family_qualifying"] >= 55
        for t in table.values()
    )
    no_regress = all(
        t["family_qualifying_delta"] >= 0
        and t["s1_key_p10"] >= t["s0_key_p10"]
        and t["s1_key_below_15"] <= t["s0_key_below_15"]
        for t in table.values()
    )
    legacy_pass = {
        iso: (t["s1_key_p10"] >= 15 and t["s1_family_p10"] >= 15)
        for iso, t in table.items()
    }
    return {
        "audit_id": "OA-11d-S1",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "protocol": {
            "schedule_origin": DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat(),
            "days": days,
            "s0": "trace ON + bypass OFF",
            "s1": "trace ON + bypass ON",
            "note": "같은 canonical 연속 schedule · bypass flag 하나만 다르다.",
        },
        "s0_baseline_row_mismatch": s0_baseline_mismatch,
        "window_rows_with_short_history": short_history,
        "funnel_scope": "ANCHOR_MEASUREMENT_WINDOW_D_MINUS_90_TO_D_MINUS_1",
        "first_divergence_date": first_divergence,
        "scope_leak_judged_days": leak_scope_days,
        "scope_leak_rows": leak,
        "funnel_invariant_violations": invariant_violations,
        "anchor_funnel": funnel,
        "anchor_table": table,
        "verdict": {
            "FAMILY_CAUSAL_CLOSABILITY": (
                "PASS" if family_pass and no_regress else "FAIL"
            ),
            "family_gate_all_anchors": family_pass,
            "no_regression": no_regress,
            "OVERALL_LEGACY_GATE_PASS": legacy_pass,
        },
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11d_s1_funnel.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    print(f"  S0 baseline 행 불일치 {r['s0_baseline_row_mismatch']} · "
          f"이력 90일 미만 {r['window_rows_with_short_history']} · "
          f"범위 누출 {r['scope_leak_rows']} · "
          f"불변식 위반 {r['funnel_invariant_violations']}")
    print(f"  최초 분기 {r['first_divergence_date']} · "
          f"누출 판정 구간 {r['scope_leak_judged_days']}일")
    for iso, t in r["anchor_table"].items():
        print(f"  {iso}  family {t['s0_family_p10']}→{t['s1_family_p10']} "
              f"qual {t['s0_family_qualifying']}→{t['s1_family_qualifying']} "
              f"({t['family_qualifying_delta']:+d}) · "
              f"key {t['s0_key_p10']}→{t['s1_key_p10']}")
        f = r["anchor_funnel"][iso]
        print(f"      bypass {f.get('BYPASSED_TOTAL', 0)} · "
              f"realized {f.get('NEW_FAMILY_REALIZED', 0)} · "
              f"already_seen {f.get('PROJECTED_FAMILY_ALREADY_SEEN', 0)} · "
              f"not_avail {f.get('RAW_TOP_CARD_NOT_AVAILABLE', 0)} · "
              f"ambig {f.get('AMBIGUOUS', 0)}")
    print("  판정:", r["verdict"]["FAMILY_CAUSAL_CLOSABILITY"],
          "· legacy", r["verdict"]["OVERALL_LEGACY_GATE_PASS"])
