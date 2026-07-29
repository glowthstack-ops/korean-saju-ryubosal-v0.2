"""P4-L — 장기 다양성 선택 shadow (L0~L3, 측정 전용, 라이브 불변).

OA-6f4 가 원인을 닫았다: 하위 15개 일주 **전부**에서 90일 내내 미선택된 good 후보가
7p 안에 여러 날 존재했다(예: 丙辰 의 `treat_received` 31일). 차단 사유는 전부
`HIGHER_CLEAN_CANDIDATE_PREFERRED` — 점수·사건 부족이 아니라 **P4 가 7일 축만 보고
90일 축의 미사용 후보를 놓친다**.

    L0  현재 P4
    L1  최근 90일 미사용 event_key 우선
    L2  최근 90일 미사용 semantic_family 우선
    L3  미사용 family → 미사용 key 계층

**미래 정보를 쓰지 않는다.** 각 날짜는 D-89 ~ D-1 만 본다. 그래서 180일을 날짜순으로
재생하고 앞 90일은 warm-up 으로 버린 뒤 뒤 90일만 집계한다 — 감사 구간 전체의 최종
빈도를 참조하면 미래 누수가 된다.

`event_key` 고유 수만 오르고 `semantic_family` 고유 수가 그대로면 형제 교체이므로
통과로 인정하지 않는다.
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

MEASURE_START, DAYS = dt.date(2026, 7, 1), 90
WARMUP = 90
START = MEASURE_START - dt.timedelta(days=WARMUP)
DOMAIN_CAP = cap_count(60, 0.35)
EVENT_CAP = 10
BUDGET = 7
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_P10_INDEX = 5

_VARIANTS: dict[str, LongTermPolicy] = {
    "L0_p4": LongTermPolicy(),
    "L1_unused_event_key": LongTermPolicy(unused_event_key=True),
    "L2_unused_semantic_family": LongTermPolicy(unused_semantic_family=True),
    "L3_family_then_key": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True
    ),
    # 지시 9장의 처방 — 미사용 우선을 hard priority 로 두지 않고 손실 구간 안에서만
    # 적용한다(0~3p 는 미사용 우선 · 그 밖은 기존 점수 순).
    "L4_band3_family_then_key": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True, loss_band=3
    ),
    "L5_band4_family_then_key": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True, loss_band=4
    ),
}
_SUPPORT_ORIGIN = ("tidy_luck", "rest_recharge", "walk_refresh", "focus_flow", "family_talk")


def _p10(values: list[int]) -> int:
    return sorted(values)[_P10_INDEX]


def _streak(series: list[str]) -> int:
    best = cur = 1
    for a, b in zip(series, series[1:], strict=False):
        cur = cur + 1 if a == b else 1
        best = max(best, cur)
    return best


def _window_repeat_pct(series: list[str]) -> float:
    n = len(series) - 6
    if n <= 0:
        return 0.0
    return sum(
        1 for i in range(n)
        if collections.Counter(series[i:i + 7]).most_common(1)[0][1] >= 3
    ) / n * 100


class _Acc:
    def __init__(self) -> None:
        #: 이력은 warm-up 을 포함한 전체(정책 입력용)
        self.headline_history: dict[str, list[str]] = collections.defaultdict(list)
        self.good_history: dict[str, list[str]] = collections.defaultdict(list)
        #: 집계는 측정 구간만
        self.headline_measured: dict[str, list[str]] = collections.defaultdict(list)
        self.good_measured: dict[str, list[str]] = collections.defaultdict(list)
        self.raw_kept = 0
        self.rep_changed = 0
        self.display_loss: list[int] = []
        self.moves = 0
        self.move_costs: list[int] = []
        self.replacement = collections.Counter()
        self.support_promoted = 0
        self.caution_promoted = 0
        self.valence_changed = 0
        self.domain_overflow = 0
        self.event_overflow = 0
        self.final = collections.Counter()


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}

    acc = {n: _Acc() for n in _VARIANTS}

    for i in range(WARMUP + DAYS):
        day = START + dt.timedelta(days=i)
        measured = i >= WARMUP
        ctx = M.build_day_context(day)

        scored_by: dict[str, list] = {}
        goods_by: dict[str, list[tuple[str, int]]] = {}
        seeds: dict[str, str] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seeds[ilju] = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            scored_by[ilju] = scored
            goods_by[ilju] = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]

        for name, policy in _VARIANTS.items():
            a = acc[name]
            raw: dict[str, HeadlineCandidate] = {}
            cmap: dict[str, list[HeadlineCandidate]] = {}
            for ilju, scored in scored_by.items():
                rep = select_good_representative(
                    goods_by[ilju], a.good_history[ilju], BUDGET,
                    policy=policy, family_of=family_of,
                    headline_history=a.headline_history[ilju],
                )
                if measured:
                    if rep.good_selection_reason == RAW_GOOD_WINNER_SELECTED:
                        a.raw_kept += 1
                    elif rep.display_good_representative != rep.raw_good_winner:
                        a.rep_changed += 1
                        a.display_loss.append(rep.display_displacement_loss)
                g, c, s = M._select_slots(
                    scored, seeds[ilju],
                    good_override=rep.display_good_representative,
                )
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                cmap[ilju] = [
                    HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
                ]
                raw[ilju] = cmap[ilju][0]
                a.good_history[ilju].append(rep.display_good_representative)
                if measured:
                    a.good_measured[ilju].append(rep.display_good_representative)

            r = select_board(
                raw, cmap, a.headline_history, domain_cap=DOMAIN_CAP,
                event_cap=EVENT_CAP, max_displacement_cost=BUDGET,
                policy=_BOARD, today=day.toordinal(),
            )
            if measured:
                a.domain_overflow += r.domain_overflow
                a.event_overflow += r.event_overflow
                for m in r.moves:
                    a.moves += 1
                    a.move_costs.append(m.displacement_cost)
                    a.replacement[m.destination_event] += 1
                    if m.destination_event in _SUPPORT_ORIGIN:
                        a.support_promoted += 1
                    if events[m.destination_event]["valence"] == "caution":
                        a.caution_promoted += 1
                    if (events[m.source_event]["valence"]
                            != events[m.destination_event]["valence"]):
                        a.valence_changed += 1
            for ilju, sel in r.selections.items():
                a.headline_history[ilju].append(sel.event_key)
                if measured:
                    a.headline_measured[ilju].append(sel.event_key)
                    a.final[sel.event_key] += 1

    # ── 기준선(L0)에서 15 미만 일주 확정 → 같은 집합을 전 변형에서 추적 ──
    base = acc["L0_p4"]
    base_unique = {k: len(set(v)) for k, v in base.headline_measured.items()}
    low_iljus = sorted(k for k, n in base_unique.items() if n < 15)

    out: dict[str, Any] = {}
    for name, a in acc.items():
        uniq_key = {k: len(set(v)) for k, v in a.headline_measured.items()}
        uniq_fam = {
            k: len({family_of.get(e, e) for e in set(v)})
            for k, v in a.headline_measured.items()
        }
        uniq_dom = {
            k: len({events[e]["domain"] for e in set(v)})
            for k, v in a.headline_measured.items()
        }
        good_uniq_key = {k: len(set(v)) for k, v in a.good_measured.items()}
        good_uniq_fam = {
            k: len({family_of.get(e, e) for e in set(v)})
            for k, v in a.good_measured.items()
        }
        tops = sorted(
            collections.Counter(v).most_common(1)[0][1]
            for v in a.headline_measured.values()
        )
        lifted = [k for k in low_iljus if uniq_key[k] >= 15]
        lifted_family = [k for k in lifted if uniq_fam[k] > base_unique_fam(base, k, family_of)]
        lift_events = collections.Counter()
        lift_families = collections.Counter()
        for k in lifted:
            new_keys = set(a.headline_measured[k]) - set(base.headline_measured[k])
            for e in new_keys:
                lift_events[e] += 1
                lift_families[family_of.get(e, e)] += 1
        top_move = a.replacement.most_common(1)[0] if a.replacement else ("", 0)
        top5 = sum(n for _k, n in a.final.most_common(5))
        cards = DAYS * 60
        gate = {
            "unique_event_key_p10_ge_15": _p10(list(uniq_key.values())) >= 15,
            "unique_semantic_family_p10_ge_15": _p10(list(uniq_fam.values())) >= 15,
            "p90_le_25pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1) <= 25.0,
            "max_le_33_3pct": round(tops[-1] / DAYS * 100, 1) <= 33.3,
            "max_streak_le_4": max(
                _streak(v) for v in a.headline_measured.values()) <= 4,
            "window7_repeat3_le_10pct": round(statistics.mean(
                _window_repeat_pct(v) for v in a.headline_measured.values()), 1) <= 10.0,
        }
        guard = {
            "mean_display_loss_le_3_5": (
                statistics.mean(a.display_loss) if a.display_loss else 0.0) <= 3.5,
            "p90_display_loss_le_7": (sorted(a.display_loss)[int(len(a.display_loss) * 0.9)]
                                      if a.display_loss else 0) <= 7,
            "raw_good_kept_ge_80pct": a.raw_kept / cards >= 0.80,
            "support_origin_le_10pct": a.support_promoted / max(1, a.moves) <= 0.10,
            "no_caution_promotion": a.caution_promoted == 0,
            "no_valence_change": a.valence_changed == 0,
            "single_replacement_le_20pct": top_move[1] / max(1, a.moves) <= 0.20,
            "top5_le_52pct": round(top5 / cards * 100, 1) <= 52.0,
            "no_domain_overflow": a.domain_overflow == 0,
            "event_overflow_not_worse": a.event_overflow <= max(
                13, acc["L0_p4"].event_overflow),
            "unique_domain_p10_ge_6": _p10(list(uniq_dom.values())) >= 6,
        }
        out[name] = {
            "final_headline": {
                "unique_event_key_p10": _p10(list(uniq_key.values())),
                "unique_semantic_family_p10": _p10(list(uniq_fam.values())),
                "unique_domain_count_p10": _p10(list(uniq_dom.values())),
                "unique_event_key_median": statistics.median(uniq_key.values()),
                "iljus_below_15": sum(1 for n in uniq_key.values() if n < 15),
                "p90_pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1),
                "max_pct": round(tops[-1] / DAYS * 100, 1),
                "max_consecutive_days": max(
                    _streak(v) for v in a.headline_measured.values()),
                "window7_repeat3_pct": round(statistics.mean(
                    _window_repeat_pct(v) for v in a.headline_measured.values()), 1),
            },
            "display_good_representative": {
                "unique_event_key_p10": _p10(list(good_uniq_key.values())),
                "unique_semantic_family_p10": _p10(list(good_uniq_fam.values())),
                "raw_good_winner_kept_pct": round(a.raw_kept / cards * 100, 1),
                "representative_changed_pct": round(a.rep_changed / cards * 100, 1),
                "mean_display_loss": round(
                    statistics.mean(a.display_loss), 2) if a.display_loss else 0.0,
                "p90_display_loss": sorted(a.display_loss)[int(len(a.display_loss) * 0.9)]
                if a.display_loss else 0,
            },
            "low_ilju_recovery": {
                "tracked_iljus": len(low_iljus),
                "lifted_to_15_or_more": len(lifted),
                "required": max(0, len(low_iljus) - _P10_INDEX),
                "lift_events": dict(lift_events.most_common(8)),
                "lift_semantic_families": dict(lift_families.most_common(8)),
                "largest_lift_event_share_pct": round(
                    lift_events.most_common(1)[0][1] / max(1, len(lifted)) * 100, 1)
                if lift_events else 0.0,
                "lifted_with_new_family": len(lifted_family),
            },
            "board": {
                "moves": a.moves,
                "mean_move_loss": round(
                    statistics.mean(a.move_costs), 2) if a.move_costs else 0.0,
                "support_origin_promoted_pct": round(
                    a.support_promoted / max(1, a.moves) * 100, 1),
                "largest_single_replacement_pct": round(
                    top_move[1] / max(1, a.moves) * 100, 1),
                "top5_cumulative_pct": round(top5 / cards * 100, 1),
                "domain_overflow": a.domain_overflow,
                "event_overflow": a.event_overflow,
            },
            "release_gate": gate,
            "release_gate_passed": all(gate.values()),
            "quality_guard": guard,
            "quality_guard_passed": all(guard.values()),
        }
    return {
        "cards": DAYS * 60,
        "measurement_stage": "display_pipeline",
        "warmup_days": WARMUP,
        "measured_window": [MEASURE_START.isoformat(),
                            (MEASURE_START + dt.timedelta(days=DAYS - 1)).isoformat()],
        "lookback_rule": "D-89 ~ D-1 (미래 정보 미사용)",
        "low_iljus_from_L0": low_iljus,
        "variants": out,
    }


def base_unique_fam(base: _Acc, ilju: str, family_of: dict[str, str]) -> int:
    return len({family_of.get(e, e) for e in set(base.headline_measured[ilju])})


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "P4-L",
        "policy_status": "shadow_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "days": DAYS,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "p4l_longterm_diversity_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, v in result["variants"].items():
        f, low = v["final_headline"], v["low_ilju_recovery"]
        print(f"  {name:26} key_p10={f['unique_event_key_p10']:3} "
              f"fam_p10={f['unique_semantic_family_p10']:3} "
              f"dom_p10={f['unique_domain_count_p10']:2} "
              f"p90={f['p90_pct']:5}% 7일3회={f['window7_repeat3_pct']:5}% "
              f"상승={low['lifted_to_15_or_more']:2}/{low['required']:2} "
              f"gate={v['release_gate_passed']} guard={v['quality_guard_passed']}")
