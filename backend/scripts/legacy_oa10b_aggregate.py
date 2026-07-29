#!/usr/bin/env python3
"""OA-10b aggregate·episode characterization — **동결본**. 리팩터링 대상이 아니다.

`audit_rolling_window.run()` 의 집계·episode 구간을 그대로 옮기고, 입력만 동결된
60,000행으로 바꿨다. 새 공용 helper 를 쓰지 않는다 — 새 helper 가 기존 의미를 잘못
옮긴 경우 양쪽이 똑같이 틀려 parity 를 통과해버린다.

동결하며 확인된 **기존 정의와 흔한 기대의 차이**(그대로 보존한다):

    · `bottom_6_iljus` 는 family 가 아니라 **key** coverage 15 미만 일주다.
      게다가 `sorted(below)[:6]` — 이미 정렬된 상위 6개이며 원래 순서가 아니다.
    · episode 의 최저값은 `minimum_key_p10` 이다. family 가 아니다.
    · `affected_iljus` 는 `sorted({...})` — 이미 정렬된 집합이다.
    · `passes` 는 key AND family 게이트다. domain 은 게이트에 없다.
    · `count_equal_14` 도 key 기준이다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402

# ── 동결된 계약값 (audit_rolling_window.py 와 동일) ───────────────────────
WARMUP_DAYS = 180
WINDOW = 90
FIRST_ANCHOR = dt.date(2026, 1, 1)
ANCHOR_DAYS = 730
_P10 = 5
_TARGET = 15
_RECOVERY_TARGET = 16

AGGREGATE_SCHEMA_VERSION = "oa10b-anchor-aggregate.v1"
EPISODE_SCHEMA_VERSION = "oa10b-failure-episode.v1"


def _fp(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _expiry_profile(window: list[str], family_of: dict[str, str]) -> dict[str, int]:
    """창 안 family 의 만료 예정. index 0 = 가장 오래된 날(D-90)."""
    last_seen: dict[str, int] = {}
    for i, key in enumerate(window):
        last_seen[family_of.get(key, key)] = i
    return last_seen


def schedule_from_rows(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """동결 행에서 일주별 최종 헤드라인 시계열을 만든다(날짜 오름차순)."""
    out: dict[str, list[str]] = {}
    for row in rows:                       # 행은 이미 날짜·일주 순서다
        out.setdefault(row["ilju"], []).append(row["final_headline"])
    return out


def build_aggregates(
    schedule: dict[str, list[str]], family_of: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """동결된 집계·episode 로직 — 원본과 한 줄도 다르지 않아야 한다."""
    events = M.load_daily_dicts().catalog["events"]
    offset = WARMUP_DAYS
    daily: list[dict[str, Any]] = []

    for a in range(ANCHOR_DAYS):
        anchor = FIRST_ANCHOR + dt.timedelta(days=a)
        lo, hi = offset + a, offset + a + WINDOW
        keys, fams, doms = [], [], []
        below: list[str] = []
        risk = 0
        for ilju, series in schedule.items():
            w = series[lo:hi]
            uk = len(set(w))
            uf = len({family_of.get(e, e) for e in set(w)})
            keys.append(uk)
            fams.append(uf)
            doms.append(len({events[e]["domain"] for e in set(w)}))
            if uk < _TARGET:
                below.append(ilju)
            last_seen = _expiry_profile(w, family_of)
            projected = sum(1 for v in last_seen.values() if v >= 7)
            if uf >= _RECOVERY_TARGET and projected < _TARGET:
                risk += 1
        kp, fp, dp = sorted(keys)[_P10], sorted(fams)[_P10], sorted(doms)[_P10]
        daily.append({
            "anchor_date": anchor.isoformat(),
            "key_p10": kp, "family_p10": fp, "domain_p10": dp,
            "count_below_15": len(below),
            "count_equal_14": sum(1 for k in keys if k == 14),
            "bottom_6_iljus": sorted(below)[:6],
            "expiry_at_risk_iljus": risk,
            "passes": kp >= _TARGET and fp >= _TARGET,
            # parity 원자료 — 요약값만으로는 한 단계 이상 움직인 전환을 놓친다.
            "key_min": min(keys), "family_min": min(fams), "domain_min": min(doms),
            "qualifying_ilju_count": sum(1 for k in keys if k >= _TARGET),
        })

    episodes: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for d in daily:
        if d["passes"]:
            if cur:
                episodes.append(cur)
                cur = []
        else:
            cur.append(d)
    if cur:
        episodes.append(cur)

    episode_rows = [
        {
            "episode_id": f"family-coverage:{e[0]['anchor_date']}:{e[-1]['anchor_date']}",
            "episode_start": e[0]["anchor_date"],
            "episode_end": e[-1]["anchor_date"],
            "duration_days": len(e),
            "minimum_key_p10": min(x["key_p10"] for x in e),
            "minimum_key_p10_dates": [
                x["anchor_date"] for x in e
                if x["key_p10"] == min(y["key_p10"] for y in e)
            ],
            "worst_count_below_15": max(x["count_below_15"] for x in e),
            "affected_iljus": sorted({i for x in e for i in x["bottom_6_iljus"]}),
        }
        for e in episodes
    ]
    return daily, episode_rows


def _transitions(daily: list[dict[str, Any]], axis: str) -> dict[str, list[str]]:
    """D-1 → D 전환 날짜 집합. 첫 anchor 는 이전 값이 없어 제외한다."""
    up, down = [], []
    for prev, cur in zip(daily[:-1], daily[1:], strict=True):
        if prev[axis] < _TARGET <= cur[axis]:
            up.append(cur["anchor_date"])
        elif cur[axis] < _TARGET <= prev[axis]:
            down.append(cur["anchor_date"])
    return {"to_15_dates": up, "to_14_dates": down}


def load_frozen_rows() -> list[dict[str, Any]]:
    path = _BACKEND / "compiled" / "oa10b_characterization_rows.jsonl"
    if not path.exists():
        raise SystemExit(
            f"{path} 없음 — `python3 scripts/legacy_oa10b_runner.py 1000` 으로 재생성"
        )
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


if __name__ == "__main__":
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    rows = load_frozen_rows()
    rows_digest = hashlib.sha256(
        (_BACKEND / "compiled" / "oa10b_characterization_rows.jsonl").read_bytes()
    ).hexdigest()

    schedule = schedule_from_rows(rows)
    daily, episodes = build_aggregates(schedule, family_of)

    body: dict[str, Any] = {
        "audit_id": "OA-10b-aggregate-characterization",
        "status": "FROZEN_BASELINE",
        "source_builder_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "source_rows_artifact_sha256": rows_digest,
        "aggregate_schema_version": AGGREGATE_SCHEMA_VERSION,
        "episode_schema_version": EPISODE_SCHEMA_VERSION,
        "official_anchor_first": FIRST_ANCHOR.isoformat(),
        "official_anchor_last": (
            FIRST_ANCHOR + dt.timedelta(days=ANCHOR_DAYS - 1)
        ).isoformat(),
        "official_anchor_count": ANCHOR_DAYS,
        "gate_thresholds": {
            "target": _TARGET, "p10_index": _P10,
            "recovery_target": _RECOVERY_TARGET,
            "gate": "key_p10 >= 15 AND family_p10 >= 15 (domain 은 게이트 아님)",
        },
        # legacy 이름과 실제 의미가 어긋난다. ID 는 parity 를 위해 바꾸지 않고,
        # 무엇이 권위 있는 정의인지만 명문화한다.
        "semantics": {
            "domain_gate_applied": False,
            "episode_minimum_axis": "KEY",
            "bottom_ilju_axis": "KEY",
            "affected_ilju_order": "sorted_unique",
            "episode_id_prefix_semantics": "LEGACY_LABEL_NOT_AUTHORITATIVE",
            "episode_trigger_semantics": (
                "COMBINED_KEY_AND_FAMILY_GATE_FAILURE"
            ),
            "episode_affected_ilju_axis": "KEY",
        },
        "definition_notes": [
            "bottom_6_iljus 는 key coverage 15 미만이며 sorted(below)[:6] 이다",
            "episode 최저값은 minimum_key_p10 이다 — family 가 아니다",
            "affected_iljus 는 sorted({...}) — 이미 정렬된 집합이다",
            "episode_id 의 'family-coverage' 접두사는 권위 있는 의미가 아니다",
        ],
        "legacy_oa10b_output_sha256": hashlib.sha256(
            (_ROOT / "doc" / "v2_2" / "audits" / "oa10b_rolling_window.json")
            .read_bytes()
        ).hexdigest(),
        "anchors": daily,
        "episodes": episodes,
        "transitions": {
            "key": _transitions(daily, "key_p10"),
            "family": _transitions(daily, "family_p10"),
        },
        "summary": {
            "anchors": len(daily),
            "passing": sum(1 for d in daily if d["passes"]),
            "episodes": len(episodes),
            "anchors_in_2025": sum(
                1 for d in daily if d["anchor_date"].startswith("2025")
            ),
            "duplicate_anchors": len(daily) - len({d["anchor_date"] for d in daily}),
        },
    }
    body["anchor_aggregate_fingerprint"] = _fp({
        "schema": AGGREGATE_SCHEMA_VERSION,
        "range": [body["official_anchor_first"], body["official_anchor_last"]],
        "count": ANCHOR_DAYS,
        "gates": body["gate_thresholds"],
        "anchors": daily,
    })
    body["episode_fingerprint"] = _fp({
        "schema": EPISODE_SCHEMA_VERSION, "episodes": episodes,
    })
    # 부분 지문은 서로 독립이다 — episode 지문이 anchor 를 포함하면 episode 가
    # 불변이어도 무관한 anchor 변화로 움직인다.
    body["artifact_sha256"] = _fp(body)
    payload = {**body, "generated_at": dt.datetime.now(dt.UTC).isoformat()}

    out = _BACKEND / "compiled" / "oa10b_anchor_aggregates.json"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("[ok]", out.name)
    s = body["summary"]
    print(f"  anchors {s['anchors']} · 통과 {s['passing']} · episode {s['episodes']}")
    print(f"  2025 anchor {s['anchors_in_2025']} · 중복 {s['duplicate_anchors']}")
    print(f"  aggregate_fp {body['anchor_aggregate_fingerprint'][:16]}")
    print(f"  episode_fp   {body['episode_fingerprint'][:16]}")
    print(f"  artifact_sha {body['artifact_sha256'][:16]}")
    for axis in ("key", "family"):
        t = body["transitions"][axis]
        print(f"  {axis} 전환 ↑{len(t['to_15_dates'])} ↓{len(t['to_14_dates'])}")
