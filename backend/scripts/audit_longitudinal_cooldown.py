"""OA-6f — 일주별 종단 cooldown shadow (F0~F4 × 손실예산, 측정 전용).

OA-9r 이 확정한 문제: 하루 보드 단면은 이미 균형에 가깝다(final headline money 29.0%
· work 27.7%). 남는 것은 **같은 일주가 시간축에서 같은 사건을 반복**하는 것이다.

    F0  현재 라이브 — domain cap only
    F1  board event cap D6 (event_cap 10 · 예산 6p)
    F2  board event cap D7 (event_cap 10 · 예산 7p)
    F3  일주별 7일 event-key cooldown
    F4  약한 board cap + cooldown (한 선택기에서 동시 처리)

핵심 비교는 F2(하루 보드에서 한 사건이 여러 일주를 점유) 대 F3(한 사용자가 여러 날
같은 사건을 봄)다.

90일을 **순차 재생**한다 — cooldown 상태는 그 변형이 실제로 고른 이력에 의존하므로,
변형마다 자기 이력을 들고 가야 한다. 기준선 이력을 빌려 쓰면 측정이 무의미해진다.

고정 기준선: relation R0 · candidate hash live v1 · G0 OFF · domain cap 라이브 · OA-8b ON.
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
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
DOMAIN_CAP = cap_count(60, 0.30)          # 18 — 라이브 정책
WEAK_DOMAIN_CAP = cap_count(60, 0.35)     # 21 — F4 의 '약한' 캡
BOARD_EVENT_CAP = 10
BUDGETS = (5, 6, 7)

#: (이름, domain_cap, event_cap, cooldown 사용 여부)
_VARIANTS: tuple[tuple[str, int, int | None, bool], ...] = (
    ("F0_live_domain_cap", DOMAIN_CAP, None, False),
    ("F1_board_event_cap_D6", DOMAIN_CAP, BOARD_EVENT_CAP, False),
    ("F2_board_event_cap_D7", DOMAIN_CAP, BOARD_EVENT_CAP, False),
    ("F3_ilju_cooldown", DOMAIN_CAP, None, True),
    ("F4_weak_cap_plus_cooldown", WEAK_DOMAIN_CAP, BOARD_EVENT_CAP, True),
)
#: F1/F2 는 예산이 이름에 고정돼 있다(D6=6p · D7=7p). 나머지는 예산 축을 훑는다.
_FIXED_BUDGET = {"F1_board_event_cap_D6": 6, "F2_board_event_cap_D7": 7}

#: support 본문 역할에서 헤드라인으로 올라오는 사건 — filler 승격 감시 대상.
_SUPPORT_ORIGIN = ("tidy_luck", "rest_recharge", "walk_refresh", "focus_flow", "family_talk")


class _Acc:
    """한 조합의 90일 누적."""

    def __init__(self) -> None:
        self.series: dict[str, list[str]] = collections.defaultdict(list)
        self.final_headline = collections.Counter()
        self.final_domain = collections.Counter()
        self.moves = 0
        self.costs: list[int] = []
        self.codes = collections.Counter()
        # 상호 배타적 카드 분할 — 분모를 섞지 않는다.
        self.cooldown_triggered = 0
        self.cooldown_moved = 0
        self.unresolved = 0
        self.unresolved_reasons = collections.Counter()
        self.cap_only_moves = 0
        self.uplift_hist = collections.Counter()
        self.uplift_alternatives = collections.Counter()
        # 후보 깊이 — 일주별 90일 누적
        self.eligible_keys: dict[str, set[str]] = collections.defaultdict(set)
        self.within_budget_keys: dict[str, set[str]] = collections.defaultdict(set)
        self.replacement = collections.Counter()
        self.support_origin_promoted = 0
        self.caution_origin_promoted = 0
        self.same_domain_move = 0
        self.cross_domain_move = 0
        self.same_family_move = 0
        self.band_changed = 0
        self.domain_overflow = 0
        self.event_overflow = 0


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
    hits = sum(
        1 for i in range(windows)
        if collections.Counter(
            series[i:i + COOLDOWN_WINDOW]
        ).most_common(1)[0][1] >= 3
    )
    return hits / windows * 100


def _longitudinal(acc: _Acc) -> dict[str, Any]:
    series = list(acc.series.values())
    tops = sorted(collections.Counter(v).most_common(1)[0][1] for v in series)
    distinct = sorted(len(set(v)) for v in series)
    streaks = [_streak(v) for v in series]
    repeats = [_window_repeat_pct(v) for v in series]
    return {
        "final_headline_p90_pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1),
        "final_headline_max_pct": round(tops[-1] / DAYS * 100, 1),
        "iljus_over_30pct": sum(1 for t in tops if t / DAYS > 0.30),
        "distinct_event_keys_p10": distinct[max(0, int(len(distinct) * 0.1) - 1)],
        "distinct_event_keys_median": distinct[len(distinct) // 2],
        "max_consecutive_days": max(streaks),
        "mean_consecutive_days": round(statistics.mean(streaks), 2),
        "window7_repeat3_pct": round(statistics.mean(repeats), 1),
    }


def _release_gate(long: dict[str, Any]) -> dict[str, bool]:
    """사용자가 고정한 출시 기준 — 통과 여부를 감사가 스스로 밝힌다."""
    return {
        "distinct_p10_ge_15": long["distinct_event_keys_p10"] >= 15,
        "p90_le_25pct": long["final_headline_p90_pct"] <= 25.0,
        "max_le_33_3pct": long["final_headline_max_pct"] <= 33.3,
        "max_streak_le_4": long["max_consecutive_days"] <= 4,
        "window7_repeat3_le_15pct": long["window7_repeat3_pct"] <= 15.0,
    }


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy_path = _BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json"
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))["events"]

    combos: list[tuple[str, int, int | None, bool, int]] = []
    for name, dcap, ecap, cool in _VARIANTS:
        if name in _FIXED_BUDGET:
            combos.append((name, dcap, ecap, cool, _FIXED_BUDGET[name]))
        elif name == "F0_live_domain_cap":
            combos.append((name, dcap, ecap, cool, 7))  # 라이브는 예산 개념이 없다
        else:
            for b in BUDGETS:
                combos.append((f"{name}@{b}p", dcap, ecap, cool, b))

    acc = {c[0]: _Acc() for c in combos}
    history = {c[0]: collections.defaultdict(list) for c in combos}

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
        ctx = M.build_day_context(day)

        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        scored_cands: dict[str, list] = {}
        band_of: dict[str, str] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            g, c, s = M._select_slots(scored, seed)
            band_of[ilju] = M._band(g, c)
            cands = M._headline_candidates(g, s, c, band_of[ilju])
            scored_cands[ilju] = cands
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]

        # F0 기준선은 **라이브 재배정기 그 자체**여야 한다 — shadow 알고리즘으로
        # 근사하면 기준선이 어긋나 모든 delta 가 오염된다.
        live_pick, live_reasons, _unres = M._rebalance_headlines(
            scored_cands, list(raw), M._DOMAIN_HEADLINE_CAP,
        )

        for name, dcap, ecap, cool, budget in combos:
            a = acc[name]
            if name == "F0_live_domain_cap":
                for ilju, sel in live_pick.items():
                    a.series[ilju].append(sel.event_key)
                    a.final_headline[sel.event_key] += 1
                    a.final_domain[sel.domain] += 1
                    if live_reasons.get(ilju):
                        a.moves += 1
                continue
            hist = history[name] if cool else {}
            r = rebalance_with_cooldown(
                raw, cmap, hist, domain_cap=dcap, event_cap=ecap,
                max_displacement_cost=budget,
            )
            a.domain_overflow += r.domain_overflow
            a.event_overflow += r.event_overflow
            a.cooldown_triggered += r.cooldown_triggered
            a.cooldown_moved += r.cooldown_moved
            a.unresolved += r.cooldown_unresolved
            a.cap_only_moves += r.cap_only_moves
            for u in r.unresolved_cards:
                a.unresolved_reasons[u.reason] += 1
                if u.reason == LOSS_BUDGET_EXCEEDED and u.required_uplift_to_fit is not None:
                    up = u.required_uplift_to_fit
                    bucket = ("+1p 이내" if up <= 1 else "+2p 이내" if up <= 2
                              else "+3p 이내" if up <= 3 else "+4~5p" if up <= 5
                              else "+6p 이상")
                    a.uplift_hist[bucket] += 1
                    if up <= 3 and u.best_alternative_event_key:
                        a.uplift_alternatives[u.best_alternative_event_key] += 1
            for code, n in collections.Counter(r.codes.values()).items():
                a.codes[code] += n
            # 후보 깊이 — 카드에 실제 등장한 헤드라인 후보 전체 대 예산 안 후보
            for ilju, cands in cmap.items():
                top = cands[0].probability
                for c in cands:
                    a.eligible_keys[ilju].add(c.event_key)
                    if top - c.probability <= budget:
                        a.within_budget_keys[ilju].add(c.event_key)
            for m in r.moves:
                a.moves += 1
                a.costs.append(m.displacement_cost)
                a.replacement[m.destination_event] += 1
                if m.destination_domain == m.source_domain:
                    a.same_domain_move += 1
                else:
                    a.cross_domain_move += 1
                st, dt_ = taxonomy.get(m.source_event, {}), taxonomy.get(m.destination_event, {})
                if st.get("semantic_group") and st.get("semantic_group") == dt_.get(
                    "semantic_group"
                ):
                    a.same_family_move += 1
                if dt_.get("headline_role") == "support_only" or (
                    m.destination_event in _SUPPORT_ORIGIN
                ):
                    a.support_origin_promoted += 1
                if events[m.destination_event]["valence"] == "caution":
                    a.caution_origin_promoted += 1
                if events[m.source_event]["valence"] != events[m.destination_event]["valence"]:
                    a.band_changed += 1
            for ilju, sel in r.selections.items():
                a.series[ilju].append(sel.event_key)
                a.final_headline[sel.event_key] += 1
                a.final_domain[sel.domain] += 1
                if cool:
                    history[name][ilju].append(sel.event_key)

    out: dict[str, Any] = {}
    base_long = _longitudinal(acc["F0_live_domain_cap"])
    for name, *_rest in combos:
        a = acc[name]
        long = _longitudinal(a)
        total_final = sum(a.final_headline.values())
        top5 = sum(n for _k, n in a.final_headline.most_common(5))
        out[name] = {
            "moves": a.moves,
            "moved_pct": round(a.moves / (DAYS * 60) * 100, 1),
            "mean_probability_loss": round(statistics.mean(a.costs), 2) if a.costs else 0.0,
            "p90_probability_loss": sorted(a.costs)[int(len(a.costs) * 0.9) - 1]
            if a.costs else 0,
            "cooldown_triggered_cards": a.cooldown_triggered,
            "cooldown_moved_cards": a.cooldown_moved,
            "cooldown_unresolved_cards": a.unresolved,
            "cap_only_moves": a.cap_only_moves,
            "not_triggered_cards": DAYS * 60 - a.cooldown_triggered,
            "partition_holds": (
                a.cooldown_moved + a.unresolved == a.cooldown_triggered
            ),
            "unresolved_rate_of_all_cards": round(a.unresolved / (DAYS * 60) * 100, 1),
            "unresolved_rate_of_triggered_cards": round(
                a.unresolved / max(1, a.cooldown_triggered) * 100, 1),
            "unresolved_reasons": dict(a.unresolved_reasons.most_common()),
            "required_uplift_distribution": dict(a.uplift_hist.most_common()),
            "recoverable_within_3p_alternatives": dict(
                a.uplift_alternatives.most_common(10)),
            "candidate_depth": {
                "eligible_unique_p10": sorted(
                    len(v) for v in a.eligible_keys.values()
                )[max(0, len(a.eligible_keys) // 10 - 1)] if a.eligible_keys else 0,
                "within_budget_unique_p10": sorted(
                    len(v) for v in a.within_budget_keys.values()
                )[max(0, len(a.within_budget_keys) // 10 - 1)] if a.within_budget_keys else 0,
            },
            "codes": dict(a.codes.most_common()),
            "same_domain_move": a.same_domain_move,
            "cross_domain_move": a.cross_domain_move,
            "same_semantic_family_move": a.same_family_move,
            "support_origin_promoted": a.support_origin_promoted,
            "caution_origin_promoted": a.caution_origin_promoted,
            "valence_changed_moves": a.band_changed,
            "domain_overflow": a.domain_overflow,
            "event_overflow": a.event_overflow,
            "final_headline_top10": dict(a.final_headline.most_common(10)),
            "final_headline_top5_cumulative_pct": round(top5 / max(1, total_final) * 100, 1),
            "final_headline_domain": dict(a.final_domain.most_common()),
            "replacement_top8": dict(a.replacement.most_common(8)),
            **long,
            "delta_p90_pp": round(
                long["final_headline_p90_pct"] - base_long["final_headline_p90_pct"], 1),
            "delta_window7_repeat3_pp": round(
                long["window7_repeat3_pct"] - base_long["window7_repeat3_pct"], 1),
            "release_gate": _release_gate(long),
            "release_gate_passed": all(_release_gate(long).values()),
        }
    return {
        "cards": DAYS * 60,
        "measurement_stage": "display_pipeline",
        "fixed_baseline": {
            "relation": "R0", "candidate_hash": "live v1 frozen", "G0": "OFF",
            "domain_cap": DOMAIN_CAP, "weak_domain_cap": WEAK_DOMAIN_CAP,
            "board_event_cap": BOARD_EVENT_CAP, "OA-8b": "ON",
        },
        "variants": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f",
        "policy_status": "shadow_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "days": DAYS,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f_longitudinal_cooldown_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, v in result["variants"].items():
        print(f"  {name:32} p90={v['final_headline_p90_pct']:5}% "
              f"7일3회={v['window7_repeat3_pct']:5}% 이동={v['moves']:5} "
              f"트리거={v['cooldown_triggered_cards']:5} "
              f"미해소={v['unresolved_rate_of_triggered_cards']:5}%(트리거기준) "
              f"gate={v['release_gate_passed']}")
