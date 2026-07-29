"""OA-7c-S3b·S3c — 도메인 신호 수용력 + money 제거 반사실(측정 전용).

닫아야 할 질문: money 만 과도한가(1), 다른 사건이 부족한가(2), 둘 다인가(3).

S3b 각 사건이 **몇 종류의 엔진 신호를 받아들이는지** — 사건 수가 아니라 수용 폭
S3c money 도메인을 후보에서만 빼면 누가 올라오는지 — 원인 치료인지 독점자 교체인지
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.constants import ten_god  # noqa: E402
from saju_shared_types.enums import Stem  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90


def _tg_name(a: Stem, b: Stem) -> str:
    return "비견" if a == b else ten_god(a, b).value


def run() -> dict:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]

    # ── S3b 정적 밀도 ──
    density = {}
    for k, e in events.items():
        tg = e.get("ten_god_affinity") or {}
        rel = e.get("relation_affinity") or {}
        density[k] = {
            "domain": e["domain"], "valence": e["valence"],
            "ten_god_defined": len(tg),
            "ten_god_positive": sum(1 for v in tg.values() if v > 0),
            "ten_god_max": max(tg.values()) if tg else 0.0,
            "ten_god_negative": sum(1 for v in tg.values() if v < 0),
            "relation_defined": len([v for v in rel.values() if v]),
            "base_weight": e["base_weight"], "expr_confidence": e["expr_confidence"],
        }

    activation = collections.Counter()
    top10 = collections.Counter()
    top3 = collections.Counter()
    top1 = collections.Counter()
    # 한 십성이 동시에 올리는 사건 수(도메인별)
    spread: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    spread_cards = collections.Counter()
    # ── S3c money 제거 반사실 ──
    new_winner = collections.Counter()
    orig_winner = collections.Counter()
    gap_to_orig: list[int] = []
    non_headline_promoted = collections.Counter()

    for i in range(DAYS):
        ctx = M.build_day_context(START + dt.timedelta(days=i))
        day_stem = Stem(ctx.day_stem)
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            tg = _tg_name(stem, day_stem)
            scored = {k: M._score_event(k, e, stem, branch, ctx) for k, e in events.items()}
            order = sorted(scored.values(), key=lambda s: -s.probability)
            for r, s in enumerate(order, 1):
                if s.probability > 5 + 90 * float(events[s.event_key]["expr_confidence"]) * 0.15:
                    activation[s.event_key] += 1
                if r <= 10:
                    top10[s.event_key] += 1
                if r <= 3:
                    top3[s.event_key] += 1
                if r == 1:
                    top1[s.event_key] += 1

            # 십성 신호가 도메인별 몇 종을 양수로 올리는가
            spread_cards[tg] += 1
            for e in events.values():
                if (e.get("ten_god_affinity") or {}).get(tg, 0.0) > 0:
                    spread[tg][e["domain"]] += 1

            # money 제거 반사실 — good 헤드라인 자격 후보 중에서만
            elig = [
                s for s in order
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            if not elig:
                continue
            orig = elig[0]
            orig_winner[orig.event_key] += 1
            alt = next((s for s in elig if events[s.event_key]["domain"] != "money"), None)
            if alt is None:
                continue
            if orig.event_key != alt.event_key:
                new_winner[alt.event_key] += 1
                gap_to_orig.append(orig.probability - alt.probability)
                if "good" not in events[alt.event_key]["slots"]:
                    non_headline_promoted[alt.event_key] += 1

    cards = DAYS * 60
    for k, v in density.items():
        v["activation_pct"] = round(activation[k] / cards * 100, 1)
        v["top10_pct"] = round(top10[k] / cards * 100, 1)
        v["top3_pct"] = round(top3[k] / cards * 100, 1)
        v["top1_pct"] = round(top1[k] / cards * 100, 1)
        v["activation_to_top3_pct"] = round(
            top3[k] / activation[k] * 100, 1) if activation[k] else 0.0

    by_domain: dict[str, dict] = {}
    for v in density.values():
        dm = by_domain.setdefault(v["domain"], collections.defaultdict(list))
        for f in ("ten_god_defined", "ten_god_positive", "ten_god_max",
                  "relation_defined", "expr_confidence", "top3_pct", "top1_pct"):
            dm[f].append(v[f])
    domain_summary = {
        d: {f: round(statistics.mean(vals), 2) for f, vals in m.items()}
        | {"events": len(m["ten_god_defined"])}
        for d, m in by_domain.items()
    }

    total_new = sum(new_winner.values())
    top5_share = sum(n for _k, n in new_winner.most_common(5)) / max(1, total_new) * 100
    return {
        "cards": cards,
        "S3b_event_density": dict(sorted(
            density.items(), key=lambda x: -x[1]["top1_pct"])),
        "S3b_domain_summary": dict(sorted(
            domain_summary.items(), key=lambda x: -x[1]["top1_pct"])),
        "S3b_ten_god_domain_spread": {
            tg: {"cards": spread_cards[tg],
                 "domains": dict(sorted(c.items(), key=lambda x: -x[1]))}
            for tg, c in sorted(spread.items())
        },
        "S3c_money_removed": {
            "cards_with_change": total_new,
            "new_winners": dict(new_winner.most_common(12)),
            "distinct_new_winners": len(new_winner),
            "top5_cumulative_pct": round(top5_share, 1),
            "mean_probability_drop": round(statistics.mean(gap_to_orig), 2)
            if gap_to_orig else None,
            "support_only_promoted": dict(non_headline_promoted.most_common(5)),
        },
    }


if __name__ == "__main__":
    data = {"audit_id": "OA-7c-S3b/S3c", "policy_status": "measurement_only",
            "live_behavior_changed": False, "days": DAYS, "result": run()}
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_domain_coverage_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
