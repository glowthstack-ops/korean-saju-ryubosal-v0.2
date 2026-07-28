"""OA-7c-L — 일주별 90일 종단 반복 감사(측정 전용).

사용자는 하루에 60장을 보지 않는다. **자기 일주 한 장을 매일 본다.** 따라서 보드
최대점유율보다 일주별 종단 반복이 더 직접적인 제품 지표다.

사건 반복과 표현 반복을 나눈다 — `money_small_gain`이 자주 나와도 매번 절약·자원
재활용·혜택 발견으로 다르게 읽히면 체감은 다르다.

실행 위치에 독립적이다(모듈 파일 기준 경로).

사용법: python backend/scripts/audit_ilju_longitudinal.py
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
from saju_engines.daily_board_constraints import (  # noqa: E402
    HeadlineCandidate,
    cap_count,
    rebalance_headlines_with_constraints as rebalance,
)
from saju_engines.daily_relation_shadow import score_event_with_relation  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
DOMAIN_CAP = cap_count(60, 0.30)
#: (이름, relation 배수, event cap, 손실 예산) — v1 선택 계약 고정.
LAYERS = [
    ("L0 R0+domain", 1.00, 60, None),
    ("L1 R2+domain", 1.50, 60, None),
    ("L2 R3+domain", 1.75, 60, None),
    ("L3 R2+D7", 1.50, 10, 7),
    ("L4 R3+D7", 1.75, 10, 7),
]


def _streak(seq: list[str]) -> int:
    best = cur = 1
    for a, b in zip(seq, seq[1:], strict=False):
        cur = cur + 1 if a == b else 1
        best = max(best, cur)
    return best if seq else 0


def _window_repeats(seq: list[str], size: int = 7) -> dict[str, int]:
    out = collections.Counter()
    for i in range(len(seq) - size + 1):
        top = collections.Counter(seq[i:i + size]).most_common(1)[0][1]
        for k in (2, 3, 4):
            if top >= k:
                out[f"ge{k}"] += 1
    return dict(out)


def run() -> dict:
    dicts = M.load_daily_dicts()
    series: dict[str, dict[str, list]] = {
        name: collections.defaultdict(list) for name, *_ in LAYERS
    }
    fam_series: dict[str, dict[str, list]] = {
        name: collections.defaultdict(list) for name, *_ in LAYERS
    }
    for i in range(DAYS):
        ctx = M.build_day_context(START + dt.timedelta(days=i))
        scored_by_mult: dict[float, tuple] = {}
        for name, mult, cap, budget in LAYERS:
            if mult not in scored_by_mult:
                raw, cmap, seeds = {}, {}, {}
                for idx in range(60):
                    stem, branch = ganzi_from_index(idx)
                    ilju = f"{stem.value}{branch.value}"
                    seed = (
                        f"{ctx.the_date.isoformat()}|{ilju}|"
                        f"{M.EVENT_SELECTION_COMPAT_SALT}"
                    )
                    scored = [
                        score_event_with_relation(k, e, stem, branch, ctx, multiplier=mult)
                        for k, e in dicts.catalog["events"].items()
                    ]
                    g, c, s = M._select_slots(scored, seed)
                    cands = M._headline_candidates(g, s, c, M._band(g, c))
                    cmap[ilju] = [
                        HeadlineCandidate(x.event_key, x.domain, x.probability)
                        for x in cands
                    ]
                    raw[ilju] = cmap[ilju][0]
                    seeds[ilju] = seed
                scored_by_mult[mult] = (raw, cmap, seeds)
            raw, cmap, seeds = scored_by_mult[mult]
            r = rebalance(
                raw, cmap, domain_cap=DOMAIN_CAP, event_cap=cap,
                max_displacement_cost=budget,
            )
            for ilju, chosen in r.selections.items():
                series[name][ilju].append(chosen.event_key)
                _mode, fam = M.resolve_narrative(dicts, chosen.event_key, seeds[ilju])
                fam_series[name][ilju].append(f"{chosen.event_key}|{fam}")

    report = {}
    for name, *_ in LAYERS:
        per = series[name]
        uniq = [len(set(v)) for v in per.values()]
        tops = [collections.Counter(v).most_common(1)[0][1] / DAYS * 100 for v in per.values()]
        money = [
            collections.Counter(v).get("money_small_gain", 0) / DAYS * 100
            for v in per.values()
        ]
        streaks = [_streak(v) for v in per.values()]
        wins = [_window_repeats(v) for v in per.values()]
        fam_streaks = [_streak(v) for v in fam_series[name].values()]
        diff_fam = []
        for ilju, keys in per.items():
            fams = fam_series[name][ilju]
            pairs = collections.defaultdict(set)
            for k, f in zip(keys, fams, strict=True):
                pairs[k].add(f)
            multi = sum(1 for k, fs in pairs.items() if len(fs) > 1)
            diff_fam.append(multi / max(1, len(pairs)) * 100)
        worst = sorted(
            per, key=lambda i: -collections.Counter(per[i]).most_common(1)[0][1]
        )[:10]
        report[name] = {
            "unique_events": {
                "mean": round(statistics.mean(uniq), 1),
                "median": statistics.median(uniq),
                "min": min(uniq),
                "p10": sorted(uniq)[max(0, int(len(uniq) * 0.1) - 1)],
            },
            "top_event_share_pct": {
                "mean": round(statistics.mean(tops), 1),
                "p90": round(sorted(tops)[int(len(tops) * 0.9) - 1], 1),
                "max": round(max(tops), 1),
            },
            "money_share_pct": {
                "mean": round(statistics.mean(money), 1),
                "p90": round(sorted(money)[int(len(money) * 0.9) - 1], 1),
                "max": round(max(money), 1),
            },
            "longest_same_event_streak": {
                "median": statistics.median(streaks),
                "p90": sorted(streaks)[int(len(streaks) * 0.9) - 1],
                "max": max(streaks),
            },
            "seven_day_window_repeats_per_ilju": {
                k: round(statistics.mean([w.get(k, 0) for w in wins]), 1)
                for k in ("ge2", "ge3", "ge4")
            },
            "narrative": {
                "longest_same_family_streak_median": statistics.median(fam_streaks),
                "longest_same_family_streak_max": max(fam_streaks),
                "same_event_multi_family_pct": round(statistics.mean(diff_fam), 1),
            },
            "worst_10_iljus": worst,
        }
    return report


if __name__ == "__main__":
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_ilju_longitudinal_90d.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "audit_id": "OA-7c-L",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "days": DAYS, "iljus": 60, "cards": DAYS * 60,
        "layers": run(),
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["layers"], ensure_ascii=False, indent=1))
