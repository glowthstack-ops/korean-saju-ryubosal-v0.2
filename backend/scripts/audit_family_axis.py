"""OA-6f5 — family 축 정합성 감사 + C11-FINAL 비교 (측정 전용, 라이브 불변).

OA-10b 가 구속 조건이 `key` 가 아니라 `final_headline_semantic_family` 임을 밝혔다
(730 anchor 중 family p10 이 14 인 것이 468, key 는 15인데 family 만 14 인 것이 192).

코드를 읽어 축 불일치를 확인했다:

    coverage(회복 발동 판정)   final headline family 만 센다      ← 출시 지표와 정합
    미사용 판정(family_recent) headline + **good 대표** 를 섞는다  ← 불일치

good 으로 뽑혔다가 보드 재배정에서 밀려 final 에 못 든 family 는 "사용됨"으로 표시돼
다시 우선되지 않는다. 출시 지표는 여전히 그 family 를 갖지 못하는데도.

    C10        현행(축 혼합)
    C11_FINAL  미사용 판정을 final headline 축으로 통일
"""

from __future__ import annotations

import collections
import datetime as dt
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
from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    LongTermPolicy,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

WARMUP, WINDOW = 180, LONGITUDINAL_HISTORY_LOOKBACK_DAYS
FIRST_ANCHOR = dt.date(2026, 1, 1)
ANCHOR_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 365
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP, _BUDGET = cap_count(60, 0.35), 10, 7
_P10, _TARGET = 5, 15

_C10 = LongTermPolicy(
    unused_semantic_family=True, unused_event_key=True,
    coverage_floor=16, recovery_prefers_low_loss=False, band_protection=True,
)
_C11 = LongTermPolicy(
    unused_semantic_family=True, unused_event_key=True,
    coverage_floor=16, recovery_prefers_low_loss=False, band_protection=True,
    unused_axis_final_only=True,
)
VARIANTS = {"C10_mixed_axis": _C10, "C11_final_axis": _C11}

#: 반복 미달 상위 7종(OA-10b) + 정상 대조 3종.
_WATCH = ("戊辰", "庚戌", "丙辰", "乙亥", "癸酉", "甲午", "辛亥")
_CONTROL = ("甲子", "乙丑", "丙寅")


def _replay(policy: LongTermPolicy, family_of: dict[str, str]) -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    #: 축 격차 — good 에는 들어갔으나 final 에는 못 든 사건
    display_only = collections.Counter()
    displaced_by_board = collections.Counter()

    day = FIRST_ANCHOR - dt.timedelta(days=WARMUP + WINDOW)
    for _ in range(WARMUP + WINDOW + ANCHOR_DAYS):
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        chosen_good: dict[str, str] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            rep = select_good_representative(
                goods, good_history[ilju], _BUDGET, policy=policy,
                family_of=family_of, headline_history=headline_history[ilju],
            )
            chosen_good[ilju] = rep.display_good_representative
            g, c, s = M._select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            good_history[ilju].append(rep.display_good_representative)
        r = select_board(
            raw, cmap, headline_history, domain_cap=_DOMAIN_CAP, event_cap=_EVENT_CAP,
            max_displacement_cost=_BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        for ilju, sel in r.selections.items():
            gk = chosen_good[ilju]
            if sel.event_key != gk:
                displaced_by_board[ilju] += 1
                gf, ff = family_of.get(gk, gk), family_of.get(sel.event_key, "")
                recent_final = headline_history[ilju][-WINDOW:]
                if gf not in {family_of.get(k, k) for k in recent_final} and gf != ff:
                    # good 에서는 새 family 였는데 final 에는 반영되지 않았다.
                    display_only[ilju] += 1
            headline_history[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)
    return {
        "headline": dict(headline_history), "good": dict(good_history),
        "display_only": display_only, "displaced": displaced_by_board,
    }


def run() -> dict[str, Any]:
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}

    out: dict[str, Any] = {}
    for name, policy in VARIANTS.items():
        st = _replay(policy, family_of)
        head, good = st["headline"], st["good"]
        daily = []
        axis_gap: list[int] = []
        gap_when_below = 0
        for a in range(ANCHOR_DAYS):
            lo, hi = WARMUP + a, WARMUP + a + WINDOW
            fams, keys = [], []
            for ilju in head:
                w = head[ilju][lo:hi]
                gw = good[ilju][lo:hi]
                ff = {family_of.get(e, e) for e in w}
                gf = {family_of.get(e, e) for e in gw}
                fams.append(len(ff))
                keys.append(len(set(w)))
                axis_gap.append(len(gf) - len(ff))
                if len(ff) < _TARGET and len(gf) >= _TARGET:
                    gap_when_below += 1
            daily.append({
                "anchor_date": (FIRST_ANCHOR + dt.timedelta(days=a)).isoformat(),
                "key_p10": sorted(keys)[_P10],
                "family_p10": sorted(fams)[_P10],
                "passes": sorted(keys)[_P10] >= _TARGET
                and sorted(fams)[_P10] >= _TARGET,
            })
        passing = sum(1 for d in daily if d["passes"])
        watch = {
            ilju: {
                "final_family_90d": len({
                    family_of.get(e, e) for e in head[ilju][WARMUP:WARMUP + WINDOW]
                }),
                "display_family_90d": len({
                    family_of.get(e, e) for e in good[ilju][WARMUP:WARMUP + WINDOW]
                }),
                "board_displaced_days": st["displaced"].get(ilju, 0),
                "new_family_lost_to_board": st["display_only"].get(ilju, 0),
            }
            for ilju in (*_WATCH, *_CONTROL) if ilju in head
        }
        out[name] = {
            "anchors": len(daily),
            "passing": passing,
            "pass_rate_pct": round(passing / max(1, len(daily)) * 100, 1),
            "worst_key_p10": min(d["key_p10"] for d in daily),
            "worst_family_p10": min(d["family_p10"] for d in daily),
            "axis_gap_mean": round(sum(axis_gap) / max(1, len(axis_gap)), 2),
            "axis_gap_max": max(axis_gap),
            "below_target_but_display_ok": gap_when_below,
            "new_family_lost_to_board_total": sum(st["display_only"].values()),
            "watch_iljus": watch,
        }
    return {
        "measurement_stage": "display_pipeline",
        "protocol": {
            "warmup_days": WARMUP, "window_days": WINDOW,
            "anchor_days": ANCHOR_DAYS,
            "first_anchor": FIRST_ANCHOR.isoformat(),
        },
        "axis_finding": (
            "coverage 는 final headline family 로 세지만 미사용 판정은 good 대표 이력을 "
            "섞는다. good 에서 새 family 였다가 보드 재배정에서 밀린 사건이 '사용됨'으로 "
            "표시돼 다시 우선되지 않는다."
        ),
        "variants": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f5",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f5_family_axis.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, v in result["variants"].items():
        print(f"  {name:16} 통과 {v['passing']}/{v['anchors']} ({v['pass_rate_pct']}%) "
              f"· 최악 key {v['worst_key_p10']} family {v['worst_family_p10']} "
              f"· 축 격차 평균 {v['axis_gap_mean']} 최대 {v['axis_gap_max']} "
              f"· family<15인데 display>=15: {v['below_target_but_display_ok']} "
              f"· 보드에서 잃은 새 family {v['new_family_lost_to_board_total']}")
