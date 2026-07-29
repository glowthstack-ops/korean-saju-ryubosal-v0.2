"""OA-9d-min — G1 전제(sibling 다중 표)의 축소 반사실(측정 전용, 라이브 불변).

G1 전제: 같은 재성 신호가 여러 positive money sibling 에게 완전한 표를 주어 표시
단계에서도 다중 후보 편향을 만든다.

OA-9r 관측이 이미 이를 흔든다 — 편재 카드 540건에서 good 슬롯을 얻은 money 사건은
`money_small_gain` 537건뿐이고 `money_good_deal` 은 **0건**이다. 이미 한 사건만
표를 가져간다.

여기서는 그 관측을 반사실로 확정한다. 접기는 **완전 제거** 형태로 한다 —
비대표 sibling 을 후보에서 통째로 빼는 것이 G1 이 할 수 있는 최대치이므로,
여기서 변화가 없으면 더 약한 형태(good 슬롯 자격만 제한)도 변화가 없다.

    FOLD_STRICT  같은 semantic_group + 같은 primary_evidence_family
    FOLD_WIDE    같은 primary_evidence_family (semantic_group 무시 — 넓은 해석)
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

import saju_engines.daily_g0_shadow as G  # noqa: E402
import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_board_trace import trace_board  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
_WINDOW, _WINDOW_HITS = 7, 3


def _fold_groups(taxonomy: dict, events: dict, wide: bool) -> dict[str, list[str]]:
    """접기 그룹 — 헤드라인 자격이 있는 good 사건만 대상이다."""
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for key, t in sorted(taxonomy.items()):
        if t["polarity"] != "good" or t["headline_role"] != "full":
            continue
        ev = events[key]
        if "good" not in (ev.get("headline_slots") or ev["slots"]):
            continue
        gk = t["primary_evidence_family"] if wide else (
            f"{t['semantic_group']}|{t['primary_evidence_family']}"
        )
        groups[gk].append(key)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def _fold(scored: list, groups: dict[str, list[str]]) -> tuple[list, int]:
    """카드에서 비대표 sibling 을 제거한다. 반환: (남은 후보, 접힌 그룹 수)."""
    by_key = {s.event_key: s for s in scored}
    drop: set[str] = set()
    contested = 0
    for members in groups.values():
        present = [by_key[k] for k in members if k in by_key]
        if len(present) < 2:
            continue
        contested += 1
        best = max(present, key=lambda s: (s.probability, s.event_key))
        drop.update(s.event_key for s in present if s.event_key != best.event_key)
    return [s for s in scored if s.event_key not in drop], contested


def _longitudinal(series: dict[str, list[str]]) -> dict[str, float]:
    tops = sorted(collections.Counter(v).most_common(1)[0][1] for v in series.values())
    windows = max(1, DAYS - _WINDOW + 1)
    repeats = []
    for v in series.values():
        hits = sum(
            1 for i in range(len(v) - _WINDOW + 1)
            if collections.Counter(v[i:i + _WINDOW]).most_common(1)[0][1] >= _WINDOW_HITS
        )
        repeats.append(hits)
    return {
        "final_headline_p90_pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1),
        "final_headline_max_pct": round(tops[-1] / DAYS * 100, 1),
        "window7_repeat3_pct": round(statistics.mean(repeats) / windows * 100, 1),
        "distinct_event_keys_p10": sorted(len(set(v)) for v in series.values())[
            max(0, int(len(series) * 0.1) - 1)
        ],
    }


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = G.load_taxonomy()["events"]

    variants = {
        "FOLD_STRICT": _fold_groups(taxonomy, events, wide=False),
        "FOLD_WIDE": _fold_groups(taxonomy, events, wide=True),
    }

    base_series: dict[str, list[str]] = collections.defaultdict(list)
    series = {n: collections.defaultdict(list) for n in variants}
    contested_cards = dict.fromkeys(variants, 0)
    changed_slot_good = dict.fromkeys(variants, 0)
    changed_raw_headline = dict.fromkeys(variants, 0)
    changed_final_headline = dict.fromkeys(variants, 0)
    replacement = {n: collections.Counter() for n in variants}
    prob_loss = {n: [] for n in variants}

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
        ctx = M.build_day_context(day)

        base_scored: dict[str, list] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            base_scored[f"{stem.value}{branch.value}"] = [
                M._score_event(k, e, stem, branch, ctx) for k, e in events.items()
            ]
        base = trace_board(base_scored, day)
        for ilju, t in base.items():
            base_series[ilju].append(t.final_headline)

        for name, groups in variants.items():
            folded: dict[str, list] = {}
            for ilju, scored in base_scored.items():
                kept, contested = _fold(scored, groups)
                folded[ilju] = kept
                if contested:
                    contested_cards[name] += 1
            tr = trace_board(folded, day)
            for ilju, t in tr.items():
                series[name][ilju].append(t.final_headline)
                b = base[ilju]
                if t.slot_good_selected != b.slot_good_selected:
                    changed_slot_good[name] += 1
                if t.raw_headline != b.raw_headline:
                    changed_raw_headline[name] += 1
                if t.final_headline != b.final_headline:
                    changed_final_headline[name] += 1
                    replacement[name][t.final_headline] += 1
                    prob_loss[name].append(
                        b.final_headline_probability - t.final_headline_probability
                    )

    cards = DAYS * 60
    base_long = _longitudinal(base_series)
    return {
        "cards": cards,
        "measurement_stage": "display_pipeline",
        "fold_groups": {
            n: {k: v for k, v in sorted(g.items())} for n, g in variants.items()
        },
        "F0_baseline": base_long,
        "variants": {
            n: {
                "contested_cards": contested_cards[n],
                "contested_pct": round(contested_cards[n] / cards * 100, 1),
                "changed_slot_good_selected": changed_slot_good[n],
                "changed_raw_headline": changed_raw_headline[n],
                "changed_final_headline": changed_final_headline[n],
                "changed_final_headline_pct": round(
                    changed_final_headline[n] / cards * 100, 2),
                "replacement_final_headline": dict(replacement[n].most_common(8)),
                "mean_probability_loss": round(statistics.mean(prob_loss[n]), 2)
                if prob_loss[n] else None,
                **_longitudinal(series[n]),
                "delta_final_headline_p90_pp": round(
                    _longitudinal(series[n])["final_headline_p90_pct"]
                    - base_long["final_headline_p90_pct"], 1),
                "delta_window7_repeat3_pp": round(
                    _longitudinal(series[n])["window7_repeat3_pct"]
                    - base_long["window7_repeat3_pct"], 1),
            }
            for n in variants
        },
    }


if __name__ == "__main__":
    result = run()
    strict = result["variants"]["FOLD_STRICT"]
    verdict = {
        "hypothesis": "같은 evidence family 의 sibling 이 표시 단계에서 독립적으로 표를 얻는다",
        "final_headline_changed": strict["changed_final_headline"],
        "delta_final_headline_p90_pp": strict["delta_final_headline_p90_pp"],
        "delta_window7_repeat3_pp": strict["delta_window7_repeat3_pp"],
        "status": (
            "REJECTED_BY_DISPLAY_PIPELINE_EVIDENCE"
            if strict["changed_final_headline"] == 0
            or abs(strict["delta_final_headline_p90_pp"]) < 1.0
            else "NOT_REJECTED"
        ),
        "reason": "sibling candidates do not independently acquire display tickets",
        "note": "접기를 **완전 제거** 형태로 돌린 상한 측정이다 — 더 약한 형태"
                "(good 슬롯 자격만 제한)는 이보다 변화가 작을 수밖에 없다.",
    }
    data = {
        "audit_id": "OA-9d-min",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "days": DAYS,
        "verdict": verdict,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa9d_family_fold_min_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name, "→", verdict["status"])
