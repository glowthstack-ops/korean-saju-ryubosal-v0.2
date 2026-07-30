#!/usr/bin/env python3
"""OA-11d — projection trace 가 선택 경로를 흔들지 않는지 (연속 전체 구간).

trace 는 매일 계산되므로 숨은 mutation 이 있으면 이후 날짜에 누적된다. 그래서 5개
anchor 의 300행만 보지 않고 **같은 원점에서 시작한 연속 전체 구간**을 비교한다.

    A = C10 / trace OFF / bypass OFF
    B = C10 / trace ON  / bypass OFF
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
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    build_rolling_audit_schedule,
)
from saju_engines.daily_selection_policy_shadow import SelectionPolicy  # noqa: E402

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_LAST_ANCHOR = dt.date(2027, 10, 9)
ANCHORS = ("2026-04-02", "2027-03-03", "2027-06-01", "2027-08-05", "2027-10-09")


def _days() -> int:
    """원점부터 마지막 anchor 까지(포함)."""
    return (_LAST_ANCHOR - DAILY_ROLLING_AUDIT_CONTRACT_V1.origin).days + 1


def _strip(steps) -> list[list[dict[str, Any]]]:
    """trace 를 제외한 행 — 나머지는 완전히 같아야 한다."""
    return [
        [{k: v for k, v in r.items() if k != "oa11d_trace"} for r in st.rows]
        for st in steps
    ]


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    domain_of = {k: e["domain"] for k, e in events.items()}
    days = _days()
    off_policy = replace(C10_POLICY, family_deficit_clean_bypass=False)

    a_steps, _a = build_rolling_audit_schedule(
        days=days, policy=C10_POLICY, board_policy=_BOARD, family_of=family_of,
        compute_projection_trace=False,
    )
    b_steps, _b = build_rolling_audit_schedule(
        days=days, policy=off_policy, board_policy=_BOARD, family_of=family_of,
        compute_projection_trace=True,
    )

    first_row = next(
        (
            {"fortune_date": x.fortune_date.isoformat(), "index": i}
            for x, y in zip(a_steps, b_steps, strict=True)
            for i, (p, q) in enumerate(
                zip(_strip([x])[0], _strip([y])[0], strict=True)
            )
            if p != q
        ),
        None,
    )
    first_board = next(
        (
            x.fortune_date.isoformat()
            for x, y in zip(a_steps, b_steps, strict=True)
            if x.board_fingerprint != y.board_fingerprint
        ),
        None,
    )
    first_state = next(
        (
            x.fortune_date.isoformat()
            for x, y in zip(a_steps, b_steps, strict=True)
            if x.state_after_fingerprint != y.state_after_fingerprint
            or x.state_before_fingerprint != y.state_before_fingerprint
        ),
        None,
    )
    trace_leak = sum(
        1 for st in a_steps for r in st.rows if "oa11d_trace" in r
    )

    # ── trace 내부 정합성
    status = collections.Counter()
    source = collections.Counter()
    unavailable_reason = collections.Counter()
    call_violation = 0
    event_mismatch = 0
    total_trace = 0
    for st in b_steps:
        for r in st.rows:
            t = r.get("oa11d_trace")
            if t is None:
                continue
            total_trace += 1
            status[t["projection_status"]] += 1
            source[t["projection_source"]] += 1
            if t.get("unavailable_reason"):
                unavailable_reason[t["unavailable_reason"]] += 1
            if t["projected_top1_event_key"] != t["raw_top_event_key"]:
                event_mismatch += 1
            expected = 0 if t["projection_source"] == "REUSED_ACTUAL_CARD" else 1
            if t["counterfactual_select_slots_calls"] != expected:
                call_violation += 1

    # ── 5 anchor 집계
    contract = derive_diagnostic_contract(
        anchor_days=(_LAST_ANCHOR - dt.date(2026, 1, 1)).days + 1
    )
    a_rows = [dict(r) for st in a_steps for r in st.rows]
    b_rows = [
        {k: v for k, v in r.items() if k != "oa11d_trace"}
        for st in b_steps for r in st.rows
    ]
    a_agg = build_rolling_audit_aggregates(a_rows, family_of, domain_of, contract)
    b_agg = build_rolling_audit_aggregates(b_rows, family_of, domain_of, contract)
    a_by = {x["anchor_date"]: x for x in a_agg["anchors"]}
    b_by = {x["anchor_date"]: x for x in b_agg["anchors"]}
    agg_mismatch = [iso for iso in ANCHORS if a_by[iso] != b_by[iso]]

    ok = not any((
        first_row, first_board, first_state, trace_leak, event_mismatch,
        call_violation, agg_mismatch,
    ))
    return {
        "audit_id": "OA-11d-trace-inertness",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "range": {
            "origin": DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat(),
            "last_anchor": _LAST_ANCHOR.isoformat(),
            "days": days, "rows": days * 60,
        },
        "first_row_mismatch": first_row,
        "first_board_fingerprint_mismatch": first_board,
        "first_state_fingerprint_mismatch": first_state,
        "trace_leaked_into_trace_off_run": trace_leak,
        "projection_event_mismatch": event_mismatch,
        "counterfactual_call_violation": call_violation,
        "anchor_aggregate_mismatch": agg_mismatch,
        "trace_totals": {
            "rows": total_trace,
            "status": dict(status),
            "source": dict(source),
            "unavailable_reason": dict(unavailable_reason),
            "status_sums_to_rows": sum(status.values()) == total_trace,
            "source_sums_to_rows": sum(source.values()) == total_trace,
        },
        "verdict": "TRACE_INERT" if ok else "TRACE_NOT_INERT",
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11d_trace_inertness.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name, "→", r["verdict"])
    print(f"  구간 {r['range']['origin']} ~ {r['range']['last_anchor']} "
          f"({r['range']['days']}일 · {r['range']['rows']}행)")
    for key in ("first_row_mismatch", "first_board_fingerprint_mismatch",
                "first_state_fingerprint_mismatch",
                "trace_leaked_into_trace_off_run", "projection_event_mismatch",
                "counterfactual_call_violation", "anchor_aggregate_mismatch"):
        print(f"  {key:36} {r[key] if r[key] else 0}")
    t = r["trace_totals"]
    print(f"  trace {t['rows']}행 · status {t['status']}")
    print(f"    source {t['source']} · unavailable {t['unavailable_reason']}")
    if r["verdict"] != "TRACE_INERT":
        raise SystemExit(1)
