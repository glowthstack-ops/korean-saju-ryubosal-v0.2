"""P4-LC 강한 원시 신호 감사 (측정 전용, 라이브 불변).

"원시 70점 이상이면 무조건 유지"는 잘못된 가드다. 72 → 69 이고 대체 사건에도 독립
근거가 있다면 유지할 이유가 약하고, 반대로 78 → 71 이라도 원시만 강한 독립 근거를
가졌다면 보호할 이유가 있다. 그래서 절대점수가 아니라 **강도 밴드와 근거 품질**로
본다.

강도 밴드는 새로 만들지 않는다 — 엔진이 문장 강도에 이미 쓰는 축을 그대로 쓴다:

    s5 >= 85   s4 >= 70   s3 >= 55   s2 < 55

독립 근거 수는 `_ScoredEvent.supporting_groups`(서로 다른 원인 그룹 중 |s| >= 0.35
인 것의 수)를 쓴다. 85+ 게이트가 이미 이 값 >= 2 를 요구하므로 같은 축이다.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    RAW_GOOD_WINNER_SELECTED,
    LongTermPolicy,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

MEASURE_START = dt.date(2026, 7, 1)
WARMUP, DAYS = 90, 270
START = MEASURE_START - dt.timedelta(days=WARMUP)
DOMAIN_CAP = cap_count(60, 0.35)
EVENT_CAP, BUDGET = 10, 7
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
#: 승인된 출시 후보 C4.
_C4 = LongTermPolicy(
    unused_semantic_family=True, unused_event_key=True,
    coverage_floor=16, recovery_prefers_low_loss=False,
)
_STRONG = 70


def strength_band(probability: int) -> str:
    """엔진의 문장 강도 밴드(`_band` 와 같은 임계값)."""
    if probability >= 85:
        return "s5"
    if probability >= 70:
        return "s4"
    if probability >= 55:
        return "s3"
    return "s2"


def _raw_bucket(p: int) -> str:
    return "70-74" if p < 75 else "75-79" if p < 80 else "80+"


def _loss_bucket(x: int) -> str:
    return "0-3p" if x <= 3 else "4-5p" if x <= 5 else "6-7p"


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}

    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)

    rows: list[dict[str, Any]] = []
    changed_total = 0
    downgrades: list[dict[str, Any]] = []

    for i in range(WARMUP + DAYS):
        day = START + dt.timedelta(days=i)
        measured = i >= WARMUP
        ctx = M.build_day_context(day)

        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        pending: dict[str, dict[str, Any]] = {}

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = {
                k: M._score_event(k, e, stem, branch, ctx) for k, e in events.items()
            }
            goods = [
                (s.event_key, s.probability) for s in scored.values()
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            rep = select_good_representative(
                goods, good_history[ilju], BUDGET, policy=_C4,
                family_of=family_of, headline_history=headline_history[ilju],
            )
            if measured and rep.good_selection_reason != RAW_GOOD_WINNER_SELECTED:
                changed_total += 1
                rw = scored[rep.raw_good_winner]
                alt = scored[rep.display_good_representative]
                if rw.probability >= _STRONG:
                    pending[ilju] = {
                        "raw_event": rw.event_key,
                        "raw_probability": rw.probability,
                        "raw_band": strength_band(rw.probability),
                        "raw_supporting_groups": rw.supporting_groups,
                        "alt_event": alt.event_key,
                        "alt_probability": alt.probability,
                        "alt_band": strength_band(alt.probability),
                        "alt_supporting_groups": alt.supporting_groups,
                        "loss": rep.display_displacement_loss,
                    }
            g, c, s = M._select_slots(
                list(scored.values()), seed,
                good_override=rep.display_good_representative,
            )
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            good_history[ilju].append(rep.display_good_representative)

        r = select_board(
            raw, cmap, headline_history, domain_cap=DOMAIN_CAP, event_cap=EVENT_CAP,
            max_displacement_cost=BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        for ilju, row in pending.items():
            # 원시 사건이 최종 헤드라인에서도 빠졌는가(실제 핵심 노출 영향).
            row["final_headline"] = r.selections[ilju].event_key
            row["final_headline_changed"] = r.selections[ilju].event_key != row["raw_event"]
            rows.append(row)
            if row["alt_band"] != row["raw_band"]:
                downgrades.append(row)
        for ilju, sel in r.selections.items():
            headline_history[ilju].append(sel.event_key)

    band_matrix = collections.Counter(
        f"{r['raw_band']}→{r['alt_band']}" for r in rows
    )
    down = [r for r in rows if r["alt_band"] < r["raw_band"]]
    up_or_same = len(rows) - len(down)
    # 지시 §2 의 강화 가드 후보 조건
    hard_cases = [
        r for r in rows
        if r["raw_probability"] >= 75 and r["loss"] >= 5
        and r["raw_supporting_groups"] >= 2 and r["alt_supporting_groups"] < 2
    ]
    return {
        "protocol": {"warmup_days": WARMUP, "measured_days": DAYS,
                     "variant": "P4_LC_C4", "strong_threshold": _STRONG},
        "band_definition": "엔진 `_band` 와 동일 — s5>=85 · s4>=70 · s3>=55 · s2<55",
        "changed_cards_total": changed_total,
        "changed_cards_with_strong_raw": len(rows),
        "strong_share_of_changes_pct": round(len(rows) / max(1, changed_total) * 100, 1),
        "raw_probability_buckets": dict(
            collections.Counter(_raw_bucket(r["raw_probability"]) for r in rows).most_common()),
        "loss_buckets": dict(
            collections.Counter(_loss_bucket(r["loss"]) for r in rows).most_common()),
        "alt_probability": {
            "mean": round(statistics.mean(r["alt_probability"] for r in rows), 1) if rows else 0,
            "min": min((r["alt_probability"] for r in rows), default=0),
            "below_70": sum(1 for r in rows if r["alt_probability"] < 70),
            "below_60": sum(1 for r in rows if r["alt_probability"] < 60),
        },
        "band_transitions": dict(band_matrix.most_common()),
        "band_downgrades": len(down),
        "band_downgrade_pct": round(len(down) / max(1, len(rows)) * 100, 1),
        "band_kept_or_raised": up_or_same,
        "supporting_groups": {
            "raw_mean": round(statistics.mean(r["raw_supporting_groups"] for r in rows), 2)
            if rows else 0,
            "alt_mean": round(statistics.mean(r["alt_supporting_groups"] for r in rows), 2)
            if rows else 0,
            "raw_ge2": sum(1 for r in rows if r["raw_supporting_groups"] >= 2),
            "alt_ge2": sum(1 for r in rows if r["alt_supporting_groups"] >= 2),
            "alt_zero": sum(1 for r in rows if r["alt_supporting_groups"] == 0),
        },
        "final_headline_changed": sum(1 for r in rows if r["final_headline_changed"]),
        "final_headline_kept_raw": sum(1 for r in rows if not r["final_headline_changed"]),
        "most_displaced_raw_events": dict(
            collections.Counter(r["raw_event"] for r in rows).most_common(8)),
        "most_used_alternatives": dict(
            collections.Counter(r["alt_event"] for r in rows).most_common(8)),
        "hard_guard_candidates": {
            "count": len(hard_cases),
            "criteria": "raw>=75 AND loss>=5 AND raw 독립근거>=2 AND alt 독립근거<2",
            "share_of_strong_changes_pct": round(
                len(hard_cases) / max(1, len(rows)) * 100, 1),
            "examples": hard_cases[:5],
        },
        "downgrade_examples": down[:8],
    }


if __name__ == "__main__":
    result = run()
    verdict = {
        "band_downgrade_guard_needed": result["band_downgrades"] > 0,
        "hard_guard_needed": result["hard_guard_candidates"]["count"] > 0,
    }
    data = {
        "audit_id": "P4-LC-STRONG",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "verdict": verdict,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "p4lc_strong_signal_270d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    print("  변경 카드", result["changed_cards_total"],
          "· 그중 raw>=70", result["changed_cards_with_strong_raw"],
          f"({result['strong_share_of_changes_pct']}%)")
    print("  밴드 전이:", result["band_transitions"])
    print("  밴드 하락:", result["band_downgrades"], f"({result['band_downgrade_pct']}%)")
    print("  독립 근거:", result["supporting_groups"])
    print("  대체 점수:", result["alt_probability"])
    print("  강화 가드 후보:", result["hard_guard_candidates"]["count"],
          f"({result['hard_guard_candidates']['share_of_strong_changes_pct']}%)")
    print("  판정:", verdict)
