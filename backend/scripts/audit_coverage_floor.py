"""P4-LC — coverage floor 정책 + 장기 재진입·노출 독점 감사 (측정 전용, 라이브 불변).

세 가지를 한 번에 닫는다.

1. `love_deepening` 69.2% 가 **새 독점**인지 **빠져 있던 사건의 일회성 보충**인지.
   "상승 일주 기여율"이 아니라 **사용자 노출 점유·재선택**으로 판정한다.
2. warm-up 을 공식 평가 프로토콜로 통일하고, cold-start 로 만든 두 가드를 정정한다.
   · `raw_good_kept >= 80%` 는 P4-L 목적과 정면 충돌하므로 출시 차단 가드에서 뺀다.
     대신 "과도한 변경 방지"를 직접 재는 가드로 바꾼다.
   · Top-5 는 절대값이 아니라 **warm-up L0 대비 비퇴행**으로 바꾼다.
3. 평균 표시 손실 4.71p 를 3.5p 안으로 되돌리면서 하위 일주 상승을 지키는
   표적형 정책(P4-LC)이 가능한지.

    C0  warm-up L0 (현행 P4)
    C1  L3 family→key 전면 미사용 우선
    C2  P4-LC — coverage < 15 인 일주에만 미사용 우선 + 7p, 그 외 손실 우선 + 4p

90일 lookback 이므로 90일 창에서 빠진 직후 기계적으로 재등장하는지를 보려면 더 긴
구간이 필요하다 — warm-up 90일 + 측정 270일을 재생하고 앞 90일 창도 함께 낸다.
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
    LONGITUDINAL_NORMAL_LOSS_BUDGET,
    LONGITUDINAL_RECOVERY_LOSS_BUDGET,
    LONGITUDINAL_SEMANTIC_COVERAGE_FLOOR,
    RAW_GOOD_WINNER_SELECTED,
    LongTermPolicy,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

MEASURE_START = dt.date(2026, 7, 1)
WARMUP, LONG_DAYS, SHORT_DAYS = 90, 270, 90
START = MEASURE_START - dt.timedelta(days=WARMUP)
DOMAIN_CAP = cap_count(60, 0.35)
EVENT_CAP = 10
BUDGET = 7
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_P10_INDEX = 5
_WATCH = "love_deepening"

_VARIANTS: dict[str, LongTermPolicy] = {
    "C0_warmup_p4": LongTermPolicy(),
    "C1_full_unused_priority": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True
    ),
    "C2_coverage_floor": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True,
        coverage_floor=LONGITUDINAL_SEMANTIC_COVERAGE_FLOOR,
    ),
    # C2 는 회복 모드에서도 0~4p 를 먼저 소진해 상승이 9/11 에 그쳤다.
    # 부족한 일주에 한해 회복 예산 전 구간을 동등하게 열면 어디까지 오르는가.
    "C3_coverage_floor_wide_recovery": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True,
        coverage_floor=LONGITUDINAL_SEMANTIC_COVERAGE_FLOOR,
        recovery_prefers_low_loss=False,
    ),
    # floor 가 목표치(15)와 같으면 경계에 걸린다 — 회복 모드가 "이미 15" 인 일주에서
    # 곧바로 꺼져 다음 날 다시 14 로 내려간다. 여유를 둔 floor 를 함께 본다.
    "C4_floor16_wide_recovery": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True,
        coverage_floor=16, recovery_prefers_low_loss=False,
    ),
    "C5_floor17_wide_recovery": LongTermPolicy(
        unused_semantic_family=True, unused_event_key=True,
        coverage_floor=17, recovery_prefers_low_loss=False,
    ),
}
_SUPPORT_ORIGIN = ("tidy_luck", "rest_recharge", "walk_refresh", "focus_flow", "family_talk")


def _p10(values: list[int]) -> int:
    return sorted(values)[_P10_INDEX]


def _streak(series: list[str], key: str | None = None) -> int:
    best = cur = 0
    prev = None
    for e in series:
        if e == prev and (key is None or e == key):
            cur += 1
        else:
            cur = 1 if (key is None or e == key) else 0
        prev = e
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
        self.headline_history: dict[str, list[str]] = collections.defaultdict(list)
        self.good_history: dict[str, list[str]] = collections.defaultdict(list)
        self.headline_measured: dict[str, list[str]] = collections.defaultdict(list)
        self.raw_kept = 0
        self.rep_changed = 0
        self.display_loss: list[int] = []
        self.change_rows: list[tuple[int, int, int]] = []  # (loss, raw_p, alt_p)
        self.moves = 0
        self.support_promoted = 0
        self.caution_promoted = 0
        self.valence_changed = 0
        self.domain_overflow = 0
        self.event_overflow = 0
        self.replacement = collections.Counter()


def _watch_report(
    acc: _Acc, base: _Acc, window: int, family_of: dict[str, str],
) -> dict[str, Any]:
    """감시 사건이 노출을 독점하는가 — 상승 기여율이 아니라 실제 노출로 판정."""
    per_ilju = {}
    gaps: list[int] = []
    for ilju, series in acc.headline_measured.items():
        s = series[:window]
        idxs = [i for i, e in enumerate(s) if e == _WATCH]
        if not idxs:
            continue
        modal = collections.Counter(s).most_common(1)[0][0]
        per_ilju[ilju] = {
            "count": len(idxs),
            "share_pct": round(len(idxs) / window * 100, 1),
            "max_streak": _streak(s, _WATCH),
            "is_modal_event": modal == _WATCH,
            "reselect_within_7d": sum(
                1 for a, b in zip(idxs, idxs[1:], strict=False) if b - a <= 7),
            "reselect_within_30d": sum(
                1 for a, b in zip(idxs, idxs[1:], strict=False) if b - a <= 30),
            "reselect_within_90d": sum(
                1 for a, b in zip(idxs, idxs[1:], strict=False) if b - a <= 90),
        }
        gaps.extend(b - a for a, b in zip(idxs, idxs[1:], strict=False))

    total = sum(len(s[:window]) for s in acc.headline_measured.values())
    exposure = sum(v["count"] for v in per_ilju.values())
    base_exposure = sum(
        s[:window].count(_WATCH) for s in base.headline_measured.values()
    )
    fam_share = sum(
        1 for s in acc.headline_measured.values() for e in s[:window]
        if family_of.get(e) == family_of.get(_WATCH)
    )
    return {
        "event": _WATCH,
        "window_days": window,
        "iljus_with_exposure": len(per_ilju),
        "total_exposure": exposure,
        "baseline_exposure": base_exposure,
        "exposure_delta": exposure - base_exposure,
        "share_of_all_headlines_pct": round(exposure / max(1, total) * 100, 2),
        "max_per_ilju_share_pct": max(
            (v["share_pct"] for v in per_ilju.values()), default=0.0),
        "iljus_where_modal": sum(1 for v in per_ilju.values() if v["is_modal_event"]),
        "max_streak": max((v["max_streak"] for v in per_ilju.values()), default=0),
        "reselect_within_7d": sum(v["reselect_within_7d"] for v in per_ilju.values()),
        "reselect_within_30d": sum(v["reselect_within_30d"] for v in per_ilju.values()),
        "reselect_within_90d": sum(v["reselect_within_90d"] for v in per_ilju.values()),
        "gap_distribution": dict(collections.Counter(
            "1~7일" if g <= 7 else "8~30일" if g <= 30 else "31~89일" if g < 90
            else "90~99일" if g < 100 else "100일+" for g in gaps
        ).most_common()),
        "median_gap_days": statistics.median(gaps) if gaps else None,
        "semantic_family_share_pct": round(fam_share / max(1, total) * 100, 2),
    }


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}
    acc = {n: _Acc() for n in _VARIANTS}

    for i in range(WARMUP + LONG_DAYS):
        day = START + dt.timedelta(days=i)
        measured = i >= WARMUP
        ctx = M.build_day_context(day)

        scored_by, goods_by, seeds = {}, {}, {}
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
                        a.change_rows.append((
                            rep.display_displacement_loss,
                            rep.raw_good_probability, rep.display_good_probability,
                        ))
                g, c, s = M._select_slots(
                    scored, seeds[ilju], good_override=rep.display_good_representative
                )
                cands = M._headline_candidates(g, s, c, M._band(g, c))
                cmap[ilju] = [
                    HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
                ]
                raw[ilju] = cmap[ilju][0]
                a.good_history[ilju].append(rep.display_good_representative)

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

    base = acc["C0_warmup_p4"]
    base90 = {k: len(set(v[:SHORT_DAYS])) for k, v in base.headline_measured.items()}
    low = sorted(k for k, n in base90.items() if n < 15)

    def _window_stats(a: _Acc, window: int) -> dict[str, Any]:
        uniq_key = {k: len(set(v[:window])) for k, v in a.headline_measured.items()}
        uniq_fam = {
            k: len({family_of.get(e, e) for e in set(v[:window])})
            for k, v in a.headline_measured.items()
        }
        uniq_dom = {
            k: len({events[e]["domain"] for e in set(v[:window])})
            for k, v in a.headline_measured.items()
        }
        tops = sorted(
            collections.Counter(v[:window]).most_common(1)[0][1]
            for v in a.headline_measured.values()
        )
        finals = collections.Counter(
            e for v in a.headline_measured.values() for e in v[:window]
        )
        total = sum(finals.values())
        return {
            "unique_event_key_p10": _p10(list(uniq_key.values())),
            "unique_semantic_family_p10": _p10(list(uniq_fam.values())),
            "unique_domain_count_p10": _p10(list(uniq_dom.values())),
            "iljus_below_15": sum(1 for n in uniq_key.values() if n < 15),
            "p90_pct": round(tops[int(len(tops) * 0.9) - 1] / window * 100, 1),
            "max_pct": round(tops[-1] / window * 100, 1),
            "max_consecutive_days": max(
                _streak(v[:window]) for v in a.headline_measured.values()),
            "window7_repeat3_pct": round(statistics.mean(
                _window_repeat_pct(v[:window]) for v in a.headline_measured.values()), 1),
            "top5_cumulative_pct": round(
                sum(n for _k, n in finals.most_common(5)) / max(1, total) * 100, 1),
        }

    out: dict[str, Any] = {}
    base_top5_90 = _window_stats(base, SHORT_DAYS)["top5_cumulative_pct"]
    cards_long = LONG_DAYS * 60
    for name, a in acc.items():
        short, long = _window_stats(a, SHORT_DAYS), _window_stats(a, LONG_DAYS)
        losses = sorted(a.display_loss)
        buckets = collections.Counter(
            "0~3p" if x <= 3 else f"{x}p" for x in a.display_loss)
        strong = [r for r in a.change_rows if r[1] >= 70]
        weak_alt = [r for r in a.change_rows if r[2] < 60]
        uniq90 = {k: len(set(v[:SHORT_DAYS])) for k, v in a.headline_measured.items()}
        lifted = [k for k in low if uniq90[k] >= 15]
        top_move = a.replacement.most_common(1)[0] if a.replacement else ("", 0)
        gate = {
            "unique_event_key_p10_ge_15": short["unique_event_key_p10"] >= 15,
            "unique_semantic_family_p10_ge_15": short["unique_semantic_family_p10"] >= 15,
            "p90_le_25pct": short["p90_pct"] <= 25.0,
            "max_le_33_3pct": short["max_pct"] <= 33.3,
            "max_streak_le_4": short["max_consecutive_days"] <= 4,
            "window7_repeat3_le_10pct": short["window7_repeat3_pct"] <= 10.0,
        }
        guard = {
            # 정정: 절대 raw_good_kept 대신 '과도한 변경 방지'를 직접 잰다.
            "display_good_change_le_20pct": a.rep_changed / cards_long <= 0.20,
            "mean_display_loss_le_3_5": (
                statistics.mean(losses) if losses else 0.0) <= 3.5,
            "p90_display_loss_le_7": (losses[int(len(losses) * 0.9)] if losses else 0) <= 7,
            "no_over_budget_change": all(x <= BUDGET for x in a.display_loss),
            "no_caution_promotion": a.caution_promoted == 0,
            "no_valence_change": a.valence_changed == 0,
            "support_origin_le_10pct": a.support_promoted / max(1, a.moves) <= 0.10,
            "single_replacement_le_20pct": top_move[1] / max(1, a.moves) <= 0.20,
            # 정정: 절대 52% 대신 warm-up L0 대비 비퇴행.
            "top5_not_worse_than_warmup_L0": short["top5_cumulative_pct"] <= base_top5_90,
            "no_domain_overflow": a.domain_overflow == 0,
            "unique_domain_p10_ge_6": short["unique_domain_count_p10"] >= 6,
        }
        out[name] = {
            "window_90d": short,
            "window_270d": long,
            "display_good": {
                "raw_good_winner_kept_pct": round(a.raw_kept / cards_long * 100, 1),
                "representative_changed_pct": round(a.rep_changed / cards_long * 100, 1),
                "mean_display_loss": round(statistics.mean(losses), 2) if losses else 0.0,
                "median_display_loss": statistics.median(losses) if losses else 0,
                "p75_display_loss": losses[int(len(losses) * 0.75)] if losses else 0,
                "p90_display_loss": losses[int(len(losses) * 0.9)] if losses else 0,
                "max_display_loss": losses[-1] if losses else 0,
                "loss_buckets": dict(sorted(buckets.items())),
                "changes_on_strong_raw_ge70": len(strong),
                "changes_to_weak_alt_lt60": len(weak_alt),
            },
            "low_ilju_recovery_90d": {
                "tracked": len(low),
                "lifted": len(lifted),
                "required": max(0, len(low) - _P10_INDEX),
            },
            "watch_event_90d": _watch_report(a, base, SHORT_DAYS, family_of),
            "watch_event_270d": _watch_report(a, base, LONG_DAYS, family_of),
            "release_gate": gate,
            "release_gate_passed": all(gate.values()),
            "quality_guard": guard,
            "quality_guard_passed": all(guard.values()),
        }
    return {
        "measurement_stage": "display_pipeline",
        "protocol": {
            "warmup_days": WARMUP,
            "measured_days": LONG_DAYS,
            "short_window": SHORT_DAYS,
            "lookback_rule": "D-89 ~ D-1",
            "note": "warm-up 을 공식 평가 프로토콜로 고정한다. cold-start 90일은 초기 "
                    "서비스 canary 로만 보존한다.",
        },
        "policy_constants": {
            "LONGITUDINAL_SEMANTIC_COVERAGE_FLOOR": LONGITUDINAL_SEMANTIC_COVERAGE_FLOOR,
            "LONGITUDINAL_NORMAL_LOSS_BUDGET": LONGITUDINAL_NORMAL_LOSS_BUDGET,
            "LONGITUDINAL_RECOVERY_LOSS_BUDGET": LONGITUDINAL_RECOVERY_LOSS_BUDGET,
        },
        "guard_revisions": {
            "raw_good_kept_ge_80pct": "폐기 — P4-L 목적과 충돌. 참고 지표로만 남긴다.",
            "top5_absolute_52pct": "폐기 — warm-up L0 대비 비퇴행으로 대체",
            "single_lift_event_majority": "판정 보류 — 상승 기여율이 아니라 노출 점유로 본다",
        },
        "low_iljus_from_C0": low,
        "variants": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "P4-LC",
        "policy_status": "shadow_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "p4lc_coverage_floor_270d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, v in result["variants"].items():
        s90, dg, low = v["window_90d"], v["display_good"], v["low_ilju_recovery_90d"]
        print(f"  {name:24} key={s90['unique_event_key_p10']:3} "
              f"fam={s90['unique_semantic_family_p10']:3} "
              f"p90={s90['p90_pct']:5}% 손실={dg['mean_display_loss']:5}p "
              f"상승={low['lifted']:2}/{low['required']:2} "
              f"gate={v['release_gate_passed']} guard={v['quality_guard_passed']}")
