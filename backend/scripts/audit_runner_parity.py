#!/usr/bin/env python3
"""OA-11e — 공용 runner ↔ 동결 legacy parity (측정 전용, 라이브 불변).

전체 60,000행 diff 를 먼저 쏟아내면 실제 원인이 묻힌다. **최초 불일치 하나**를
찾아 그 날짜의 입력 state 까지 함께 보여주는 것이 목적이다.

짧은 구간부터 순서대로 올린다 — 91일째 첫 eviction 이 가장 위험한 경계다.

    1일 · 91일 · 181일 · 300일 · 1000일

parity 대상은 legacy 필드명 그대로다. `realized_display_displacement_loss` 같은
새 관측 필드는 비교에서 제외한다 — 새 필드 때문에 동결 artifact 를 갱신하면
기준선이 움직인다.
"""

from __future__ import annotations

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

import legacy_oa10b_runner as LEGACY  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    DailyScheduleState,
    _append_window,
    build_rolling_audit_schedule,
)
from saju_engines.daily_selection_policy_shadow import SelectionPolicy  # noqa: E402

#: legacy 행이 가진 필드만 비교한다. 순서도 legacy 출력 그대로 둔다.
_ROW_FIELDS = (
    "fortune_date", "ilju", "raw_good_winner", "intended_good_representative",
    "realized_good_event", "support_event", "caution_event", "raw_headline",
    "final_headline", "final_headline_family", "selection_reason_codes",
    "display_displacement_loss",
)
_SPANS = (1, 91, 181, 300, 1000)
_BOARD_POLICY = SelectionPolicy(
    global_swap=True, severity_tiers=True, recency_rotation=True
)


def _first_row_mismatch(
    legacy_rows: list[dict[str, Any]], shared_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """최초 불일치 하나 — 전체 diff 보다 먼저 본다."""
    if len(legacy_rows) != len(shared_rows):
        return {
            "kind": "ROW_COUNT",
            "legacy": len(legacy_rows), "shared": len(shared_rows),
        }
    for a, b in zip(legacy_rows, shared_rows, strict=True):
        for field in _ROW_FIELDS:
            if a.get(field) != b.get(field):
                return {
                    "kind": "ROW_FIELD",
                    "fortune_date": a["fortune_date"],
                    "ilju": a["ilju"],
                    "first_different_field": field,
                    "legacy_value": a.get(field),
                    "shared_value": b.get(field),
                    "legacy_row": a,
                    "shared_row": b,
                }
    return None


def _reconstruct_state(
    rows_by_day: list[list[dict[str, Any]]], keep: int
) -> list[str]:
    """legacy 행에서 기대 state 지문을 **shared 와 같은 규약으로** 재구성한다.

    legacy observer 는 잘라내지 않은 전체 이력의 지문을 들고 있어 shared 의 90일
    창 지문과 직접 비교되지 않는다. 행 결과가 같아도 내부 이력이 갈리면 며칠 뒤
    결과가 달라지므로, 같은 규약으로 다시 만들어 비교한다.
    """
    state = DailyScheduleState({}, {}, {}, {})
    out: list[str] = []
    for day_rows in rows_by_day:
        intended, _ = _append_window(
            state.intended_good_history,
            {r["ilju"]: r["intended_good_representative"] for r in day_rows}, keep,
        )
        realized, _ = _append_window(
            state.realized_good_history,
            {r["ilju"]: r["realized_good_event"] for r in day_rows}, keep,
        )
        family, _ = _append_window(
            state.final_headline_family_history,
            {r["ilju"]: r["final_headline_family"] for r in day_rows}, keep,
        )
        headline, _ = _append_window(
            state.final_headline_history,
            {r["ilju"]: r["final_headline"] for r in day_rows}, keep,
        )
        state = DailyScheduleState(intended, realized, family, headline)
        out.append(state.fingerprint())
    return out


def run(span: int) -> dict[str, Any]:
    """한 구간의 parity."""
    family_of = LEGACY.load_family_map()
    legacy = LEGACY.build_schedule_observed(family_of, days=span)
    steps, _state = build_rolling_audit_schedule(
        days=span, policy=C10_POLICY, board_policy=_BOARD_POLICY,
        family_of=family_of,
    )
    shared_rows = [dict(r) for st in steps for r in st.rows]

    row_bad = _first_row_mismatch(legacy.rows, shared_rows)
    board_bad = next(
        (
            {
                "fortune_date": ls["fortune_date"],
                "legacy_board_fp": ls["board_fp"],
                "shared_board_fp": st.board_fingerprint,
            }
            for ls, st in zip(legacy.daily_state, steps, strict=True)
            if ls["board_fp"] != st.board_fingerprint
        ),
        None,
    )
    # 동일 날짜 안에서 60일주가 모두 같은 state 를 읽었는지는 runner 가 assert 로
    # 보장한다. 여기서는 날짜별 eviction 이 legacy 와 같은지 본다. legacy 는 지문만
    # 들고 있으므로 shared 쪽에서 **legacy 와 같은 규약으로** 지문을 다시 만든다.
    evict_bad = None
    for ls, st in zip(legacy.daily_state, steps, strict=True):
        pairs = (
            ("intended_eviction_fp", "intended_evicted_by_ilju"),
            ("realized_eviction_fp", "realized_evicted_by_ilju"),
            ("final_family_eviction_fp", "final_family_evicted_by_ilju"),
        )
        for legacy_key, shared_key in pairs:
            shared_evicted = {
                k: v for k, v in st.eviction_summary[shared_key].items()
                if v is not None
            }
            got = LEGACY._fp({k: shared_evicted[k] for k in sorted(shared_evicted)})
            if ls[legacy_key] != got:
                evict_bad = {
                    "fortune_date": ls["fortune_date"],
                    "axis": legacy_key,
                    "legacy_fp": ls[legacy_key],
                    "shared_fp": got,
                    "shared_evicted_sample": dict(list(shared_evicted.items())[:3]),
                }
                break
        if evict_bad:
            break
    # 내부 이력이 갈렸는데 당일 출력과 eviction 이 우연히 같은 경우를 잡는다.
    keep = DAILY_HISTORY_CONTRACT_V1.lookback_days
    by_day = [legacy.rows[i * 60:(i + 1) * 60] for i in range(span)]
    expected_after = _reconstruct_state(by_day, keep)
    state_bad = next(
        (
            {
                "fortune_date": st.fortune_date.isoformat(),
                "expected_state_after_fp": exp,
                "shared_state_after_fp": st.state_after_fingerprint,
            }
            for exp, st in zip(expected_after, steps, strict=True)
            if exp != st.state_after_fingerprint
        ),
        None,
    )
    before_bad = next(
        (
            {
                "fortune_date": st.fortune_date.isoformat(),
                "expected_state_before_fp": prev,
                "shared_state_before_fp": st.state_before_fingerprint,
            }
            for prev, st in zip(
                [DailyScheduleState({}, {}, {}, {}).fingerprint(), *expected_after[:-1]],
                steps, strict=True,
            )
            if prev != st.state_before_fingerprint
        ),
        None,
    )
    final_bad = (
        None if not expected_after or expected_after[-1] == steps[-1].state_after_fingerprint
        else {"expected": expected_after[-1],
              "shared": steps[-1].state_after_fingerprint}
    )
    return {
        "span_days": span,
        "daily_state_before_mismatch": before_bad,
        "daily_state_after_mismatch": state_bad,
        "final_state_mismatch": final_bad,
        "legacy_rows": len(legacy.rows),
        "shared_rows": len(shared_rows),
        "row_mismatch": row_bad,
        "board_fingerprint_mismatch": board_bad,
        "eviction_mismatch": evict_bad,
        "verdict": (
            "PARITY_OK"
            if not any((row_bad, board_bad, evict_bad, state_bad, before_bad,
                        final_bad))
            else "PARITY_FAILED"
        ),
    }


if __name__ == "__main__":
    spans = [int(a) for a in sys.argv[1:]] or list(_SPANS)
    results = []
    for span in spans:
        r = run(span)
        results.append(r)
        print(f"  {span:>5}일  행 {r['legacy_rows']} vs {r['shared_rows']}  "
              f"→ {r['verdict']}")
        if r["verdict"] != "PARITY_OK":
            bad = (r["row_mismatch"] or r["board_fingerprint_mismatch"]
                   or r["eviction_mismatch"] or r["daily_state_before_mismatch"]
                   or r["daily_state_after_mismatch"] or r["final_state_mismatch"])
            print("    최초 불일치:")
            for k, v in (bad or {}).items():
                if k not in ("legacy_row", "shared_row"):
                    print(f"      {k}: {v}")
            break        # 최초 실패에서 멈춘다 — 다음 구간은 의미가 없다
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11e_runner_parity.json"
    out.write_text(
        json.dumps({
            "audit_id": "OA-11e",
            "policy_status": "measurement_only",
            "live_behavior_changed": False,
            "baseline": {
                "legacy_runner_source_sha256": "artifact 참조",
                "audit_contract": DAILY_ROLLING_AUDIT_CONTRACT_V1.version,
                "origin": DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat(),
            },
            "compared_row_fields": list(_ROW_FIELDS),
            "results": results,
        }, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    if any(r["verdict"] != "PARITY_OK" for r in results):
        raise SystemExit(1)
