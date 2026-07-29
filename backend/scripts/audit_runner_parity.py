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


def reconstruct_expected_rolling_state_from_frozen_rows(
    rows_by_day: list[list[dict[str, Any]]], keep: int
) -> tuple[list[str], list[dict[str, list[str]]]]:
    """동결 행만으로 기대 rolling state 를 **독립 계산**한다.

    legacy observer 는 잘라내지 않은 전체 이력의 지문을 들고 있어 shared 의 90일
    창 지문과 직접 비교되지 않는다. 그래서 다시 만든다 — 다만 **shared runner 의
    windowing helper 를 쓰지 않는다.** 어떤 값을 창에 넣고 어떤 날짜를 빼는지를
    공유하면 같은 결함을 양쪽이 나눠 갖는 자기비교가 된다. 직렬화 규약
    (`DailyScheduleState.fingerprint`)만 공유한다.

    Returns:
        (날짜별 기대 state 지문, 날짜별 창 길이 요약).
    """
    hist: dict[str, dict[str, list[str]]] = {
        axis: {} for axis in ("intended", "realized", "family", "headline")
    }
    field = {
        "intended": "intended_good_representative",
        "realized": "realized_good_event",
        "family": "final_headline_family",
        "headline": "final_headline",
    }
    fps: list[str] = []
    sizes: list[dict[str, list[str]]] = []
    for day_rows in rows_by_day:
        for axis, key in field.items():
            table = hist[axis]
            for r in day_rows:
                seq = table.setdefault(r["ilju"], [])
                seq.append(r[key])
                # 독립 구현: append 후 창을 넘으면 가장 오래된 하나를 뺀다.
                while len(seq) > keep:
                    seq.pop(0)
        state = DailyScheduleState(
            {k: tuple(v) for k, v in hist["intended"].items()},
            {k: tuple(v) for k, v in hist["realized"].items()},
            {k: tuple(v) for k, v in hist["family"].items()},
            {k: tuple(v) for k, v in hist["headline"].items()},
        )
        fps.append(state.fingerprint())
        sizes.append({
            axis: sorted({len(v) for v in hist[axis].values()})
            for axis in hist
        })
    return fps, sizes


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
    expected_after, window_sizes = (
        reconstruct_expected_rolling_state_from_frozen_rows(by_day, keep)
    )
    # 창 길이 자체도 본다 — 직렬화가 우연히 같은 오류를 공유하는 경우까지 막는다.
    size_bad = next(
        (
            {"day_index": i + 1, "window_sizes": sizes}
            for i, sizes in enumerate(window_sizes)
            if any(s != [min(i + 1, keep)] for s in sizes.values())
        ),
        None,
    )
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
        "window_size_mismatch": size_bad,
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
                        final_bad, size_bad))
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
                   or r["daily_state_after_mismatch"] or r["final_state_mismatch"]
                   or r["window_size_mismatch"])
            print("    최초 불일치:")
            for k, v in (bad or {}).items():
                if k not in ("legacy_row", "shared_row"):
                    print(f"      {k}: {v}")
            break        # 최초 실패에서 멈춘다 — 다음 구간은 의미가 없다
    tag = "-".join(str(x) for x in spans)
    out = (_ROOT / "doc" / "v2_2" / "audits"
           / f"oa11e_runner_parity_{tag}.json")
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
            "expected_state_source": "INDEPENDENT_RECONSTRUCTION_FROM_FROZEN_ROWS",
            "execution_isolation": "SEQUENTIAL_WITH_CACHE_RESET",
            "cache_independence_evidence": (
                "tests/unit/test_daily_schedule_cache_independence.py — 실행 순서 "
                "무관·반복 안정·사전 입력 무변경·cold/warm 일치"
            ),
            "compared_row_fields": list(_ROW_FIELDS),
            "results": results,
        }, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    if any(r["verdict"] != "PARITY_OK" for r in results):
        raise SystemExit(1)
