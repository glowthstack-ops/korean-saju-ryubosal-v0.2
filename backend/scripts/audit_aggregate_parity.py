#!/usr/bin/env python3
"""OA-11f — 새 공용 aggregate builder ↔ 동결 기준선 parity (측정 전용).

동결본과 **의미 로직을 공유하지 않는다.** anchor 필터·percentile 집계·bottom 선별·
pass 계산·episode segmentation·minimum·affected 계산은 모두 독립 구현이다. 새
builder 가 기존 의미를 잘못 옮겼다면 여기서 걸려야 한다.

비교 순서가 중요하다 — 행이 모두 같은데 지문만 다르면 직렬화·메타데이터 문제로
좁힐 수 있다.

    1. 730 anchor 행  2. 요약  3. 전환 4집합  4. 30 episode
    5. anchor 지문     6. episode 지문
"""

from __future__ import annotations

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

import saju_engines.daily_ilju_fortune as M  # noqa: E402
import saju_engines.daily_rolling_audit_aggregate as AGG  # noqa: E402
from saju_engines.daily_rolling_audit_aggregate import (  # noqa: E402
    ROLLING_AUDIT_AGGREGATE_CONTRACT_V1,
    build_rolling_audit_aggregates,
)

_ANCHOR_FIELDS = (
    "anchor_date", "key_p10", "family_p10", "domain_p10", "count_below_15",
    "count_equal_14", "bottom_6_iljus", "expiry_at_risk_iljus", "passes",
    "key_min", "family_min", "domain_min", "qualifying_ilju_count",
)
_EPISODE_FIELDS = (
    "episode_id", "episode_start", "episode_end", "duration_days",
    "minimum_key_p10", "minimum_key_p10_dates", "worst_count_below_15",
    "affected_iljus",
)


def _fp(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_frozen() -> dict[str, Any]:
    path = _BACKEND / "compiled" / "oa10b_anchor_aggregates.json"
    if not path.exists():
        raise SystemExit(
            f"{path} 없음 — `python3 scripts/legacy_oa10b_aggregate.py` 로 생성"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_rows() -> list[dict[str, Any]]:
    path = _BACKEND / "compiled" / "oa10b_characterization_rows.jsonl"
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def _first_anchor_mismatch(frozen, shared, anchors_by_date) -> dict | None:
    for a, b in zip(frozen, shared, strict=True):
        for field in _ANCHOR_FIELDS:
            if a.get(field) != b.get(field):
                idx = frozen.index(a)
                return {
                    "comparison_stage": "ANCHOR_ROW",
                    "anchor_date": a["anchor_date"],
                    "first_different_field": field,
                    "frozen_value": a.get(field),
                    "shared_value": b.get(field),
                    "previous_anchor": (
                        {k: frozen[idx - 1][k]
                         for k in ("anchor_date", "key_p10", "family_p10")}
                        if idx else None
                    ),
                }
    return None


def _first_episode_mismatch(frozen, shared, by_date) -> dict | None:
    if len(frozen) != len(shared):
        return {
            "comparison_stage": "EPISODE_COUNT",
            "frozen_value": len(frozen), "shared_value": len(shared),
        }
    for a, b in zip(frozen, shared, strict=True):
        for field in _EPISODE_FIELDS:
            if a.get(field) != b.get(field):
                # segmentation 문제와 최저값 문제를 구분할 수 있게 구간을 편다.
                span = [
                    {k: by_date[d][k] for k in ("anchor_date", "key_p10",
                                                "family_p10", "passes")}
                    for d in sorted(by_date)
                    if a["episode_start"] <= d <= a["episode_end"]
                ]
                return {
                    "comparison_stage": "EPISODE",
                    "episode_id": a["episode_id"],
                    "first_different_field": field,
                    "frozen_value": a.get(field),
                    "shared_value": b.get(field),
                    "episode_span_daily": span[:10],
                }
    return None


def run() -> dict[str, Any]:
    frozen = _load_frozen()
    rows = _load_rows()
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]
    domain_of = {k: e["domain"] for k, e in events.items()}

    result = build_rolling_audit_aggregates(rows, family_of, domain_of)
    by_date = {a["anchor_date"]: a for a in frozen["anchors"]}

    anchor_bad = _first_anchor_mismatch(
        frozen["anchors"], result["anchors"], by_date
    )
    summary_bad = (
        None if frozen["summary"] == result["summary"]
        else {"comparison_stage": "SUMMARY",
              "frozen_value": frozen["summary"], "shared_value": result["summary"]}
    )
    trans_bad = next(
        (
            {"comparison_stage": "TRANSITION", "axis": axis, "direction": key,
             "frozen_value": frozen["transitions"][axis][key][:5],
             "shared_value": result["transitions"][axis][key][:5],
             "frozen_count": len(frozen["transitions"][axis][key]),
             "shared_count": len(result["transitions"][axis][key])}
            for axis in ("key", "family")
            for key in ("to_15_dates", "to_14_dates")
            if frozen["transitions"][axis][key] != result["transitions"][axis][key]
        ),
        None,
    )
    episode_bad = _first_episode_mismatch(
        frozen["episodes"], result["episodes"], by_date
    )

    anchor_fp = _fp({
        "schema": frozen["aggregate_schema_version"],
        "range": [frozen["official_anchor_first"], frozen["official_anchor_last"]],
        "count": frozen["official_anchor_count"],
        "gates": frozen["gate_thresholds"],
        "anchors": result["anchors"],
    })
    episode_fp = _fp({
        "schema": frozen["episode_schema_version"], "episodes": result["episodes"],
    })
    fp_bad = {
        k: v for k, v in (
            ("anchor_fingerprint", (
                frozen["anchor_aggregate_fingerprint"], anchor_fp)),
            ("episode_fingerprint", (frozen["episode_fingerprint"], episode_fp)),
        ) if v[0] != v[1]
    }

    stages = (anchor_bad, summary_bad, trans_bad, episode_bad,
              fp_bad if fp_bad else None)
    return {
        "audit_id": "OA-11f",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        # 증거 사슬 — frozen rows + frozen legacy builder → 동결 지문,
        # shared runner output + shared builder → 같은 지문.
        "aggregate_contract_version": ROLLING_AUDIT_AGGREGATE_CONTRACT_V1.version,
        "aggregate_schema_version": frozen["aggregate_schema_version"],
        "episode_schema_version": frozen["episode_schema_version"],
        "shared_aggregate_builder_source_sha256": hashlib.sha256(
            Path(AGG.__file__).read_bytes()
        ).hexdigest(),
        "frozen_artifact_sha256": frozen["artifact_sha256"],
        "frozen_rows_artifact_sha256": frozen["source_rows_artifact_sha256"],
        "frozen_legacy_builder_sha256": frozen["source_builder_sha256"],
        # 부분 지문이 무엇을 덮는지 — 진단 범위를 명시한다.
        "anchor_aggregate_fingerprint_scope": "ANCHOR_PAYLOAD_PLUS_AGGREGATE_SCHEMA",
        "episode_fingerprint_scope": "EPISODE_PAYLOAD_PLUS_EPISODE_SCHEMA",
        "artifact_sha256_scope": (
            "FULL_ARTIFACT_INCLUDING_SEMANTICS_EXCLUDING_GENERATED_AT"
        ),
        "boundary_fixture_suite": (
            "tests/unit/test_rolling_audit_aggregate_boundaries.py"
        ),
        "anchor_row_mismatch": anchor_bad,
        "summary_mismatch": summary_bad,
        "transition_mismatch": trans_bad,
        "episode_mismatch": episode_bad,
        "fingerprint_mismatch": fp_bad or None,
        "verdict": "PARITY_OK" if not any(stages) else "PARITY_FAILED",
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_aggregate_parity.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("[ok]", out.name, "→", r["verdict"])
    for stage in ("anchor_row_mismatch", "summary_mismatch", "transition_mismatch",
                  "episode_mismatch", "fingerprint_mismatch"):
        print(f"  {stage:24} {r[stage] if r[stage] else 0}")
    if r["verdict"] != "PARITY_OK":
        raise SystemExit(1)
