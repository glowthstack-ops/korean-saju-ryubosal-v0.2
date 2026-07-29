#!/usr/bin/env python3
"""OA-11d-R0 — S0 재현 parity (측정 전용, 라이브 불변).

이전 OA-11d 수치는 harness drift 로 전부 무효화됐다(good_history 의도/실현 혼동,
board cap 에 비율 전달, schedule 원점 이동, 예열 0일). 이번에는 **OA-10b 와 완전히
같은 shared infrastructure** 에서 S0 를 돌려 공식 결과를 재현하는지 먼저 본다.

S1/S2 는 배선하지 않는다. S0 가 완전히 일치한 뒤에만 같은 runner 의 정책 인자로
분기한다 — 그래야 차이를 정책 변경에 귀속할 수 있다.
"""

from __future__ import annotations

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
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    build_rolling_audit_aggregates,
    contract_mode,
)
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_BOARD_CONTRACT_V1,
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    build_rolling_audit_schedule,
)
from saju_engines.daily_selection_policy_shadow import SelectionPolicy  # noqa: E402

ANCHORS = (
    "2026-04-02", "2027-03-03", "2027-06-01", "2027-08-05", "2027-10-09",
)
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_TOTAL_DAYS = 1000

_ROW_FIELDS = (
    "raw_good_winner", "intended_good_representative", "realized_good_event",
    "support_event", "caution_event", "raw_headline", "final_headline",
    "final_headline_family", "selection_reason_codes", "display_displacement_loss",
)
_ANCHOR_FIELDS = (
    "key_p10", "family_p10", "domain_p10", "count_below_15", "count_equal_14",
    "bottom_6_iljus", "passes",
)


def _policy_fingerprint() -> dict[str, Any]:
    """계약·정책 지문 — 무엇으로 돌렸는지 결과와 함께 남긴다."""
    return {
        "policy": "CURRENT_C10",
        "repeat_history_source": DAILY_HISTORY_CONTRACT_V1.repeat_history_source.value,
        "rolling_contract": DAILY_ROLLING_AUDIT_CONTRACT_V1.version,
        "aggregate_contract": ROLLING_AUDIT_AGGREGATE_CONTRACT_V1.version,
        "aggregate_contract_mode": contract_mode(ROLLING_AUDIT_AGGREGATE_CONTRACT_V1),
        "domain_cap_count": DAILY_BOARD_CONTRACT_V1.domain_cap_count,
        "event_cap_count": DAILY_BOARD_CONTRACT_V1.event_cap_count,
        "schedule_origin": DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat(),
        "history_contract": DAILY_HISTORY_CONTRACT_V1.version,
        "board_contract": DAILY_BOARD_CONTRACT_V1.version,
    }


def _frozen_rows() -> list[dict[str, Any]]:
    path = _BACKEND / "compiled" / "oa10b_characterization_rows.jsonl"
    if not path.exists():
        raise SystemExit(
            f"{path} 없음 — `python3 scripts/legacy_oa10b_runner.py 1000` 으로 재생성"
        )
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]

    steps, _state = build_rolling_audit_schedule(
        days=_TOTAL_DAYS, policy=C10_POLICY, board_policy=_BOARD,
        family_of=family_of,
    )
    s0_rows = [dict(r) for st in steps for r in st.rows]
    s0_by_key = {(r["fortune_date"], r["ilju"]): r for r in s0_rows}
    baseline = {(r["fortune_date"], r["ilju"]): r for r in _frozen_rows()}

    # ── 대상 anchor 의 창 안 행만 비교하는 것이 아니라, anchor 당 60일주의 그날 행을
    #    비교한다. anchor 5개 x 60일주 = 300행.
    row_mismatch: dict[str, Any] | None = None
    compared = 0
    for iso in ANCHORS:
        for idx in range(60):
            from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            a, b = baseline.get((iso, ilju)), s0_by_key.get((iso, ilju))
            if a is None or b is None:
                row_mismatch = row_mismatch or {
                    "kind": "MISSING_ROW", "anchor": iso, "ilju": ilju,
                }
                continue
            compared += 1
            for field in _ROW_FIELDS:
                if a.get(field) != b.get(field) and row_mismatch is None:
                    row_mismatch = {
                        "kind": "ROW_FIELD", "anchor": iso, "ilju": ilju,
                        "first_different_field": field,
                        "baseline": a.get(field), "s0": b.get(field),
                    }

    # ── board 지문. **state 지문은 R0 에서 직접 대조하지 않는다** — 동결
    #    characterization 은 잘라내지 않은 전체 이력 기준이고 shared runner 는 90일
    #    창으로 절단하므로 지문이 구조적으로 다르다. 전 구간 state parity 는
    #    OA-11e 가 독립 재구성으로 이미 통과했다. 직접 비교하지 않은 항목을 0 으로
    #    표시하면 "R0 에서 state 까지 대조했다" 로 오독된다.
    board_mismatch = None
    frozen_state = json.loads(
        (_ROOT / "doc" / "v2_2" / "audits" / "oa10b_characterization.json")
        .read_text(encoding="utf-8")
    )["daily_state"]
    by_date = {d["fortune_date"]: d for d in frozen_state}
    for step in steps:
        iso = step.fortune_date.isoformat()
        want = by_date.get(iso)
        if want is None:
            continue
        if want["board_fp"] != step.board_fingerprint and board_mismatch is None:
            board_mismatch = {
                "fortune_date": iso,
                "baseline": want["board_fp"], "s0": step.board_fingerprint,
            }

    # ── anchor 집계
    aggregates = build_rolling_audit_aggregates(
        s0_rows, family_of, {k: e["domain"] for k, e in events.items()}
    )
    frozen_agg = json.loads(
        (_BACKEND / "compiled" / "oa10b_anchor_aggregates.json")
        .read_text(encoding="utf-8")
    )
    agg_by_date = {a["anchor_date"]: a for a in frozen_agg["anchors"]}
    s0_by_date = {a["anchor_date"]: a for a in aggregates["anchors"]}
    anchor_mismatch = None
    for iso in ANCHORS:
        want, got = agg_by_date[iso], s0_by_date[iso]
        for field in _ANCHOR_FIELDS:
            if want[field] != got[field] and anchor_mismatch is None:
                anchor_mismatch = {
                    "anchor": iso, "first_different_field": field,
                    "baseline": want[field], "s0": got[field],
                }

    ok = not any((row_mismatch, board_mismatch, anchor_mismatch))
    return {
        "audit_id": "OA-11d-R0",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "note": "S0 재현 전용 — S1/S2 는 배선하지 않았다.",
        "policy_fingerprint": _policy_fingerprint(),
        "anchors": list(ANCHORS),
        "rows_compared": compared,
        "row_mismatch": row_mismatch,
        "state_parity": {
            "status": "INHERITED_FROM_OA11E_VERIFIED_BASELINE",
            "direct_r0_comparison": False,
            "oa11e_full_range_state_parity": True,
            "note": (
                "동결 characterization 은 전체 이력 지문, shared runner 는 90일 창 "
                "지문이라 직접 대조가 불가능하다. OA-11e 가 독립 재구성으로 1,000일 "
                "전 구간 state parity 를 통과했다."
            ),
        },
        "board_fingerprint_mismatch": board_mismatch,
        "anchor_aggregate_mismatch": anchor_mismatch,
        "anchor_snapshot": {
            iso: {f: s0_by_date[iso][f] for f in _ANCHOR_FIELDS} for iso in ANCHORS
        },
        "verdict": "S0_REPRODUCED" if ok else "S0_MISMATCH",
    }


if __name__ == "__main__":
    result = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11d_r0_s0_parity.json"
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name, "→", result["verdict"])
    print(f"  비교 행 {result['rows_compared']}/300")
    for key in ("row_mismatch", "board_fingerprint_mismatch",
                "anchor_aggregate_mismatch"):
        print(f"  {key:28} {result[key] if result[key] else 0}")
    print(f"  state 직접 대조             {result['state_parity']['direct_r0_comparison']}"
          f" (근거: {result['state_parity']['status']})")
    for iso, snap in result["anchor_snapshot"].items():
        print(f"  {iso} key {snap['key_p10']} family {snap['family_p10']} "
              f"domain {snap['domain_p10']} · passes {snap['passes']}")
    _ = dt
