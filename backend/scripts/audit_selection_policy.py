"""OA-6f2 — 선택 활용 최적화 shadow (P0~P3, 측정 전용, 라이브 불변).

F4@7p 는 후보 부족이 아니라 **후보 활용 손실**을 남겼다:
eligible p10 17 · within-budget p10 16 인데 selected p10 은 14.
미해소 478건 중 사건 부재는 27건(5.6%)뿐이다.

    P0  F4@7p 그대로(greedy, no-re-move) — `rebalance_with_cooldown` 을 그대로 호출
    P1  같은 제약, 전역 배정 + augmenting swap
    P2  P1 + 반복 위반 강도 계층화
    P3  P2 + 최근 사용량 기반 후보 활용

제약을 느슨하게 만들지 않는다 — domain cap · event cap · 손실 예산 7p 는 전부 동일하다.
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
from saju_engines.daily_cooldown_shadow import (  # noqa: E402
    COOLDOWN_WINDOW,
    LOSS_BUDGET_EXCEEDED,
    rebalance_with_cooldown,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_NAMES,
    SelectionPolicy,
    repeat_severity,
    select_board,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
DOMAIN_CAP = cap_count(60, 0.35)   # F4 의 '약한' 캡
EVENT_CAP = 10
BUDGET = 7

#: P4 — 슬롯 선발 단계에서 반복을 피한다.
#: OA-6f2 실측: 헤드라인 후보는 카드당 2개(90.4%)·1개(9.6%)뿐이다. 반면 **슬롯 선발
#: 이전**에는 7p 안에 good 헤드라인 자격 사건이 평균 4.39개 있다. 즉 후보가 얕은 게
#: 아니라 슬롯 선발이 후보를 2개로 접는다. P1~P3 이 고유 p10 을 못 올린 이유다.
_P4 = "P4_good_slot_cooldown"

_POLICIES: dict[str, SelectionPolicy | None] = {
    "P0_f4_greedy": None,  # None = 기존 구현을 그대로 호출(기준선 보장)
    "P1_global_swap": SelectionPolicy(global_swap=True),
    "P2_severity_tiers": SelectionPolicy(global_swap=True, severity_tiers=True),
    "P3_recency_rotation": SelectionPolicy(
        global_swap=True, severity_tiers=True, recency_rotation=True
    ),
    _P4: SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True),
}

_SUPPORT_ORIGIN = ("tidy_luck", "rest_recharge", "walk_refresh", "focus_flow", "family_talk")


class _Acc:
    def __init__(self) -> None:
        self.series: dict[str, list[str]] = collections.defaultdict(list)
        self.final = collections.Counter()
        self.domain = collections.Counter()
        self.moves = 0
        self.costs: list[int] = []
        self.triggered = 0
        self.moved = 0
        self.unresolved = 0
        self.reasons = collections.Counter()
        self.uplift = collections.Counter()
        self.replacement = collections.Counter()
        self.support_promoted = 0
        self.caution_promoted = 0
        self.valence_changed = 0
        self.domain_overflow = 0
        self.event_overflow = 0
        self.chain_displaced = 0
        self.weaker_repeat = 0
        self.severity_hist = collections.Counter()
        self.eligible: dict[str, set[str]] = collections.defaultdict(set)
        self.within_budget: dict[str, set[str]] = collections.defaultdict(set)
        self.near_miss = collections.Counter()


def _streak(series: list[str]) -> int:
    best = cur = 1
    for a, b in zip(series, series[1:], strict=False):
        cur = cur + 1 if a == b else 1
        best = max(best, cur)
    return best


def _window_repeat_pct(series: list[str]) -> float:
    windows = len(series) - COOLDOWN_WINDOW + 1
    if windows <= 0:
        return 0.0
    return sum(
        1 for i in range(windows)
        if collections.Counter(series[i:i + COOLDOWN_WINDOW]).most_common(1)[0][1] >= 3
    ) / windows * 100


def _entropy(counts: collections.Counter) -> float:
    """선택 분포의 정규화 엔트로피(0~1) — 후보를 고르게 쓰는가."""
    import math
    total = sum(counts.values())
    if total <= 1 or len(counts) <= 1:
        return 0.0
    h = -sum((n / total) * math.log(n / total) for n in counts.values())
    return round(h / math.log(len(counts)), 3)


def _longitudinal(acc: _Acc) -> dict[str, Any]:
    series = list(acc.series.values())
    tops = sorted(collections.Counter(v).most_common(1)[0][1] for v in series)
    distinct = sorted(len(set(v)) for v in series)
    return {
        "final_headline_p90_pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1),
        "final_headline_max_pct": round(tops[-1] / DAYS * 100, 1),
        "iljus_over_30pct": sum(1 for t in tops if t / DAYS > 0.30),
        "selected_unique_p10": distinct[max(0, len(distinct) // 10 - 1)],
        "selected_unique_median": distinct[len(distinct) // 2],
        "max_consecutive_days": max(_streak(v) for v in series),
        "window7_repeat3_pct": round(
            statistics.mean(_window_repeat_pct(v) for v in series), 1),
        "selection_entropy_mean": round(statistics.mean(
            _entropy(collections.Counter(v)) for v in series), 3),
    }


def _release_gate(long: dict[str, Any]) -> dict[str, bool]:
    return {
        "selected_unique_p10_ge_15": long["selected_unique_p10"] >= 15,
        "p90_le_25pct": long["final_headline_p90_pct"] <= 25.0,
        "max_le_33_3pct": long["final_headline_max_pct"] <= 33.3,
        "max_streak_le_4": long["max_consecutive_days"] <= 4,
        "window7_repeat3_le_15pct": long["window7_repeat3_pct"] <= 15.0,
    }


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]

    acc = {n: _Acc() for n in _POLICIES}
    history = {n: collections.defaultdict(list) for n in _POLICIES}

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
        ctx = M.build_day_context(day)

        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        scored_by: dict[str, list] = {}
        seeds: dict[str, str] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            seeds[ilju] = seed
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            scored_by[ilju] = scored
            g, c, s = M._select_slots(scored, seed)
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands]
            raw[ilju] = cmap[ilju][0]

        # P4 — 슬롯 선발 단계에서 반복을 피한 뒤 헤드라인 후보를 다시 만든다.
        p4_raw: dict[str, HeadlineCandidate] = {}
        p4_cmap: dict[str, list[HeadlineCandidate]] = {}
        for ilju, scored in scored_by.items():
            past = history[_P4].get(ilju, ())
            goods = sorted(
                (x for x in scored
                 if x.valence == "good"
                 and "good" in (events[x.event_key].get("headline_slots")
                                or events[x.event_key]["slots"])),
                key=lambda x: -x.probability,
            )
            top = goods[0].probability if goods else 0
            pick = next(
                (x.event_key for x in goods
                 if top - x.probability <= BUDGET
                 and repeat_severity(past, x.event_key) == 0),
                None,
            )
            g, c, s = M._select_slots(scored, seeds[ilju], good_override=pick)
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            p4_cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            p4_raw[ilju] = p4_cmap[ilju][0]

        for name, policy in _POLICIES.items():
            a = acc[name]
            hist = history[name]
            if policy is None:
                r = rebalance_with_cooldown(
                    raw, cmap, hist, domain_cap=DOMAIN_CAP, event_cap=EVENT_CAP,
                    max_displacement_cost=BUDGET,
                )
                chain_displaced = weaker = 0
            else:
                use_raw, use_cmap = (
                    (p4_raw, p4_cmap) if name == _P4 else (raw, cmap)
                )
                r = select_board(
                    use_raw, use_cmap, hist, domain_cap=DOMAIN_CAP, event_cap=EVENT_CAP,
                    max_displacement_cost=BUDGET, policy=policy,
                    today=day.toordinal(),
                )
                chain_displaced, weaker = r.displaced_by_chain, r.accepted_weaker_repeat

            a.triggered += r.cooldown_triggered
            a.moved += r.cooldown_moved
            a.unresolved += r.cooldown_unresolved
            a.chain_displaced += chain_displaced
            a.weaker_repeat += weaker
            a.domain_overflow += r.domain_overflow
            a.event_overflow += r.event_overflow
            for u in r.unresolved_cards:
                a.reasons[u.reason] += 1
                if u.reason == LOSS_BUDGET_EXCEEDED and u.required_uplift_to_fit is not None:
                    up = u.required_uplift_to_fit
                    a.uplift[
                        "+1p 이내" if up <= 1 else "+2p 이내" if up <= 2
                        else "+3p 이내" if up <= 3 else "+4~5p" if up <= 5 else "+6p 이상"
                    ] += 1
                    if up <= 3 and u.best_alternative_event_key:
                        a.near_miss[u.best_alternative_event_key] += 1
            for m in r.moves:
                a.moves += 1
                a.costs.append(m.displacement_cost)
                a.replacement[m.destination_event] += 1
                if m.destination_event in _SUPPORT_ORIGIN:
                    a.support_promoted += 1
                if events[m.destination_event]["valence"] == "caution":
                    a.caution_promoted += 1
                if events[m.source_event]["valence"] != events[m.destination_event]["valence"]:
                    a.valence_changed += 1
            for ilju, cands in (p4_cmap if name == _P4 else cmap).items():
                top = cands[0].probability
                for cd in cands:
                    a.eligible[ilju].add(cd.event_key)
                    if top - cd.probability <= BUDGET:
                        a.within_budget[ilju].add(cd.event_key)
            for ilju, sel in r.selections.items():
                sev = repeat_severity(hist.get(ilju, ()), sel.event_key)
                a.severity_hist[SEVERITY_NAMES[sev]] += 1
                a.series[ilju].append(sel.event_key)
                a.final[sel.event_key] += 1
                a.domain[sel.domain] += 1
                history[name][ilju].append(sel.event_key)

    cards = DAYS * 60
    out: dict[str, Any] = {}
    base = acc["P0_f4_greedy"]
    base_long = _longitudinal(base)
    for name, a in acc.items():
        long = _longitudinal(a)
        used = {k for s in a.series.values() for k in s}
        eligible_all = {k for s in a.eligible.values() for k in s}
        within_all = {k for s in a.within_budget.values() for k in s}
        top5 = sum(n for _k, n in a.final.most_common(5))
        top_move = a.replacement.most_common(1)[0] if a.replacement else ("", 0)
        out[name] = {
            "cooldown_triggered_cards": a.triggered,
            "cooldown_moved_cards": a.moved,
            "cooldown_unresolved_cards": a.unresolved,
            "partition_holds": a.moved + a.unresolved == a.triggered,
            "unresolved_rate_of_triggered_cards": round(
                a.unresolved / max(1, a.triggered) * 100, 1),
            "unresolved_reasons": dict(a.reasons.most_common()),
            "required_uplift_distribution": dict(a.uplift.most_common()),
            "recoverable_within_3p_alternatives": dict(a.near_miss.most_common(8)),
            "moves": a.moves,
            "chain_displaced_cards": a.chain_displaced,
            "accepted_weaker_repeat": a.weaker_repeat,
            "mean_probability_loss": round(statistics.mean(a.costs), 2) if a.costs else 0.0,
            "p90_probability_loss": sorted(a.costs)[int(len(a.costs) * 0.9) - 1]
            if a.costs else 0,
            "severity_distribution": dict(a.severity_hist.most_common()),
            "candidate_utilization": {
                "eligible_unique_keys": len(eligible_all),
                "within_budget_unique_keys": len(within_all),
                "actually_selected_keys": len(used),
                "never_selected_within_budget": sorted(within_all - used),
                "utilization_pct": round(len(used) / max(1, len(within_all)) * 100, 1),
            },
            "final_headline_top10": dict(a.final.most_common(10)),
            "final_headline_top5_cumulative_pct": round(top5 / max(1, cards) * 100, 1),
            "final_headline_domain": dict(a.domain.most_common()),
            "replacement_top8": dict(a.replacement.most_common(8)),
            "largest_single_replacement_pct": round(
                top_move[1] / max(1, a.moves) * 100, 1),
            "support_origin_promoted_pct": round(
                a.support_promoted / max(1, a.moves) * 100, 1),
            "caution_promoted": a.caution_promoted,
            "valence_changed_moves": a.valence_changed,
            "domain_overflow": a.domain_overflow,
            "event_overflow": a.event_overflow,
            **long,
            "delta_p90_pp": round(
                long["final_headline_p90_pct"] - base_long["final_headline_p90_pct"], 1),
            "delta_selected_unique_p10": (
                long["selected_unique_p10"] - base_long["selected_unique_p10"]),
            "release_gate": _release_gate(long),
            "release_gate_passed": all(_release_gate(long).values()),
            "quality_guard": {
                "mean_loss_not_worse_than_p0": a.costs
                and statistics.mean(a.costs) <= statistics.mean(base.costs) + 0.01,
                "p90_loss_le_7": (sorted(a.costs)[int(len(a.costs) * 0.9) - 1]
                                  if a.costs else 0) <= 7,
                "support_promoted_le_10pct": a.support_promoted / max(1, a.moves) <= 0.10,
                "no_caution_promotion": a.caution_promoted == 0,
                "no_valence_change": a.valence_changed == 0,
                "single_replacement_le_20pct": top_move[1] / max(1, a.moves) <= 0.20,
                "top5_not_worse_than_f0": round(top5 / max(1, cards) * 100, 1) <= 55.8,
                "no_cap_overflow": a.domain_overflow == 0 and a.event_overflow == 0,
            },
        }
    return {
        "cards": cards,
        "measurement_stage": "display_pipeline",
        "fixed_baseline": {
            "relation": "R0", "candidate_hash": "live v1 frozen", "OA-8b": "ON",
            "G0": "OFF", "domain_cap": DOMAIN_CAP, "event_cap": EVENT_CAP,
            "loss_budget": BUDGET,
        },
        "variants": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f2",
        "policy_status": "shadow_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "days": DAYS,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f2_selection_policy_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, v in result["variants"].items():
        g = v["quality_guard"]
        print(f"  {name:22} p90={v['final_headline_p90_pct']:5}% "
              f"고유p10={v['selected_unique_p10']:3} 7일3회={v['window7_repeat3_pct']:5}% "
              f"연속={v['max_consecutive_days']} "
              f"미해소={v['unresolved_rate_of_triggered_cards']:5}% "
              f"gate={v['release_gate_passed']} guard={all(g.values())}")
