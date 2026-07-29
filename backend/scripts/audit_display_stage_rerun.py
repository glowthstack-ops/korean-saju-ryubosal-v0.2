"""OA-9r — S3a·S3b·S3c 를 **실제 표시 파이프라인** 기준으로 재측정(측정 전용).

정정 배경: OA-9a 가 `cautions[0]`(점수순 주의 1위)을 "주의 슬롯 승자"로 셌다.
라이브 선택기는 주의를 good 과 다른 도메인에서 뽑으므로 편재 카드에서는 money 주의가
표시되지 않는다 — 원시 1위 100% 인 421건에서 **표시는 0건**이었다. 같은 혼동이
S3a·S3b·S3c 에도 있을 수 있어 raw 지표만으로 제품 결론을 내릴 수 없다.

이 스크립트는 선택 로직을 흉내 내지 않는다. `daily_board_trace.trace_board` 가
라이브 순수 함수를 그대로 호출하며, 검증으로 `compute_board` 와 일치를 확인한다.

    A  M-A 반응 곡선을 final_headline 기준으로 다시 닫는다
    B  도메인 수용력에 노출 단계별 통계를 붙인다
    C  money 제거 반사실을 전체 파이프라인으로 다시 실행한다
"""

from __future__ import annotations

import collections
import copy
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
from saju_engines.daily_board_trace import CardTrace, trace_board  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402
from saju_shared_types.constants import ten_god  # noqa: E402
from saju_shared_types.enums import Stem  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
MA_TARGET = "money_small_gain"
MA_VARIANTS = {"M0": 0.90, "M-A1": 0.85, "M-A2": 0.80, "M-A3": 0.75}
#: 같은 사건이 7일 창 안에서 3회 이상 최종 헤드라인이 되는가(체감 반복의 기준).
_WINDOW, _WINDOW_HITS = 7, 3


def _tg(a: Stem, b: Stem) -> str:
    return "비견" if a == b else ten_god(a, b).value


def _variant_events(events: dict[str, dict], aff: float) -> dict[str, dict]:
    patched = copy.deepcopy(events)
    patched[MA_TARGET]["ten_god_affinity"]["편재"] = aff
    return patched


def _window_repeats(series: list[str]) -> int:
    """7일 창 안에서 같은 사건이 3회 이상 나온 창의 수."""
    hits = 0
    for i in range(len(series) - _WINDOW + 1):
        window = collections.Counter(series[i:i + _WINDOW])
        if window.most_common(1)[0][1] >= _WINDOW_HITS:
            hits += 1
    return hits


def _longitudinal(series_by_ilju: dict[str, list[str]]) -> dict[str, float]:
    tops = sorted(collections.Counter(v).most_common(1)[0][1] for v in series_by_ilju.values())
    repeats = [_window_repeats(v) for v in series_by_ilju.values()]
    windows = max(1, DAYS - _WINDOW + 1)
    return {
        "final_headline_p90_pct": round(tops[int(len(tops) * 0.9) - 1] / DAYS * 100, 1),
        "final_headline_max_pct": round(tops[-1] / DAYS * 100, 1),
        "final_headline_mean_pct": round(statistics.mean(tops) / DAYS * 100, 1),
        "window7_repeat3_pct": round(statistics.mean(repeats) / windows * 100, 1),
    }


class _Acc:
    """한 변형(또는 조건)의 단계별 누적기."""

    def __init__(self) -> None:
        self.raw_rank1 = collections.Counter()
        self.raw_top3 = collections.Counter()
        self.slot_good_selected = collections.Counter()
        self.slot_caution_selected = collections.Counter()
        self.slot_support_selected = collections.Counter()
        self.raw_headline = collections.Counter()
        self.final_headline = collections.Counter()
        self.final_headline_domain = collections.Counter()
        self.slot_good_domain = collections.Counter()
        self.slot_support_domain = collections.Counter()
        self.slot_caution_domain = collections.Counter()
        self.raw_top3_domain = collections.Counter()
        self.raw_headline_domain = collections.Counter()
        self.board_cap_displaced = 0
        self.final_probability: list[int] = []
        self.series: dict[str, list[str]] = collections.defaultdict(list)

    def add(self, t: CardTrace) -> None:
        self.raw_rank1[t.raw_rank1] += 1
        for k in t.raw_top3:
            self.raw_top3[k] += 1
        for d in t.raw_top3_domains:
            self.raw_top3_domain[d] += 1
        self.slot_good_selected[t.slot_good_selected] += 1
        self.slot_caution_selected[t.slot_caution_selected] += 1
        self.slot_support_selected[t.slot_support_selected] += 1
        self.slot_good_domain[t.slot_good_domain] += 1
        self.slot_caution_domain[t.slot_caution_domain] += 1
        self.slot_support_domain[t.slot_support_domain] += 1
        self.raw_headline[t.raw_headline] += 1
        self.raw_headline_domain[t.raw_headline_domain] += 1
        self.final_headline[t.final_headline] += 1
        self.final_headline_domain[t.final_headline_domain] += 1
        self.final_probability.append(t.final_headline_probability)
        self.board_cap_displaced += int(t.board_cap_displaced)
        self.series[t.ilju].append(t.final_headline)


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    money_keys = {k for k, e in events.items() if e["domain"] == "money"}

    ma_acc = {name: _Acc() for name in MA_VARIANTS}
    ma_events = {name: _variant_events(events, aff) for name, aff in MA_VARIANTS.items()}
    #: M0 대비 최종 헤드라인이 바뀐 카드와 그 대체 사건
    ma_changed = {name: collections.Counter() for name in MA_VARIANTS}
    ma_changed_from = {name: collections.Counter() for name in MA_VARIANTS}
    #: 편재 조건 카드만 따로
    ma_pyeonjae = {name: _Acc() for name in MA_VARIANTS}

    removed_acc = _Acc()
    removed_changed = collections.Counter()
    removed_support_promoted = collections.Counter()
    removed_prob_drop: list[int] = []

    verified_days = 0

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
        ctx = M.build_day_context(day)
        day_stem = Stem(ctx.day_stem)

        scored_by_variant: dict[str, dict[str, list]] = {n: {} for n in MA_VARIANTS}
        removed_scored: dict[str, list] = {}
        pyeonjae_iljus: set[str] = set()

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            if _tg(stem, day_stem) == "편재":
                pyeonjae_iljus.add(ilju)
            for name, ev in ma_events.items():
                scored_by_variant[name][ilju] = [
                    M._score_event(k, e, stem, branch, ctx) for k, e in ev.items()
                ]
            removed_scored[ilju] = [
                s for s in scored_by_variant["M0"][ilju] if s.event_key not in money_keys
            ]

        traces = {n: trace_board(scored_by_variant[n], day) for n in MA_VARIANTS}
        removed_traces = trace_board(removed_scored, day)

        # 검증 — M0 추적이 라이브 보드와 일치하는가(감사 재구현 드리프트 방지)
        board = M.compute_board(ctx, dicts)
        if all(
            traces["M0"][f.ilju].final_headline == str(f.headline_event_key)
            for f in board.fortunes
        ):
            verified_days += 1

        base = traces["M0"]
        for name, tr in traces.items():
            for ilju, t in tr.items():
                ma_acc[name].add(t)
                if ilju in pyeonjae_iljus:
                    ma_pyeonjae[name].add(t)
                if name != "M0" and t.final_headline != base[ilju].final_headline:
                    ma_changed[name][t.final_headline] += 1
                    ma_changed_from[name][base[ilju].final_headline] += 1

        for ilju, t in removed_traces.items():
            removed_acc.add(t)
            if t.final_headline != base[ilju].final_headline:
                removed_changed[t.final_headline] += 1
                removed_prob_drop.append(
                    base[ilju].final_headline_probability - t.final_headline_probability
                )
                if "good" not in events[t.final_headline]["slots"]:
                    removed_support_promoted[t.final_headline] += 1

    cards = DAYS * 60

    def _money_share(counter: collections.Counter) -> float:
        total = sum(counter.values())
        return round(counter.get("money", 0) / max(1, total) * 100, 1)

    def _ma_row(name: str) -> dict[str, Any]:
        a, p = ma_acc[name], ma_pyeonjae[name]
        pj_cards = sum(p.final_headline.values())
        return {
            "pyeonjae_affinity": MA_VARIANTS[name],
            "raw_rank1_cards": a.raw_rank1[MA_TARGET],
            "slot_good_selected_cards": a.slot_good_selected[MA_TARGET],
            "raw_headline_cards": a.raw_headline[MA_TARGET],
            "final_headline_cards": a.final_headline[MA_TARGET],
            "final_headline_money_share_pct": _money_share(a.final_headline_domain),
            "board_cap_displaced_cards": a.board_cap_displaced,
            "pyeonjae_slot_good_money_share_pct": _money_share(p.slot_good_domain),
            "pyeonjae_final_headline_money_share_pct": _money_share(p.final_headline_domain),
            "pyeonjae_cards": pj_cards,
            "changed_final_headline_cards": sum(ma_changed[name].values()),
            "replacement_final_headline": dict(ma_changed[name].most_common(6)),
            "displaced_from": dict(ma_changed_from[name].most_common(6)),
            **_longitudinal(a.series),
        }

    # ── B 도메인 수용력(노출 단계별) ──
    a0 = ma_acc["M0"]
    domains = sorted({e["domain"] for e in events.values()})
    domain_table = {
        d: {
            "raw_top3_slots": a0.raw_top3_domain.get(d, 0),
            "slot_good_selected": a0.slot_good_domain.get(d, 0),
            "slot_support_selected": a0.slot_support_domain.get(d, 0),
            "slot_caution_selected": a0.slot_caution_domain.get(d, 0),
            "raw_headline": a0.raw_headline_domain.get(d, 0),
            "final_headline": a0.final_headline_domain.get(d, 0),
            "final_headline_pct": round(a0.final_headline_domain.get(d, 0) / cards * 100, 2),
            "good_events": sum(
                1 for e in events.values() if e["domain"] == d and e["valence"] == "good"),
            "headline_eligible_events": sum(
                1 for e in events.values() if e["domain"] == d
                and "good" in (e.get("headline_slots") or e["slots"])),
        }
        for d in domains
    }

    # ── G1 착수 전 관측값(편재 카드) ──
    p0 = ma_pyeonjae["M0"]
    money_good_keys = sorted(
        k for k in money_keys if events[k]["valence"] == "good"
    )
    g1_baseline = {
        "pyeonjae_cards": sum(p0.final_headline.values()),
        "slot_good_money_share_pct": _money_share(p0.slot_good_domain),
        "final_headline_money_share_pct": _money_share(p0.final_headline_domain),
        "slot_good_selected_by_money_event": {
            k: p0.slot_good_selected.get(k, 0) for k in money_good_keys
        },
        "raw_top3_all_money_pct": None,  # raw 지표는 OA-9a 에 있다(단계 혼용 방지)
        "note": "family 접기 반사실은 OA-9d(G1) shadow 에서 측정한다 — 여기서는 관측값만 낸다.",
    }

    total_removed_change = sum(removed_changed.values())
    top5 = sum(n for _k, n in removed_changed.most_common(5))
    return {
        "cards": cards,
        "measurement_stage": "display_pipeline",
        "live_board_verified_days": verified_days,
        "days": DAYS,
        "A_ma_curve_display": {name: _ma_row(name) for name in MA_VARIANTS},
        "B_domain_exposure": dict(sorted(
            domain_table.items(), key=lambda x: -x[1]["final_headline"])),
        "C_money_removed_display": {
            "changed_final_headline_cards": total_removed_change,
            "distinct_final_headline_replacements": len(removed_changed),
            "final_headline_replacements": dict(removed_changed.most_common(12)),
            "top5_cumulative_pct": round(top5 / max(1, total_removed_change) * 100, 1),
            "support_only_promoted_to_final_headline": dict(
                removed_support_promoted.most_common(6)),
            "mean_final_probability_drop": round(statistics.mean(removed_prob_drop), 2)
            if removed_prob_drop else None,
            "board_cap_displaced_cards": removed_acc.board_cap_displaced,
            "board_cap_displaced_cards_base": a0.board_cap_displaced,
            "final_headline_domain": dict(removed_acc.final_headline_domain.most_common()),
            **_longitudinal(removed_acc.series),
        },
        "G1_baseline_observations": g1_baseline,
    }


if __name__ == "__main__":
    data = {
        "audit_id": "OA-9r",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        # 90일 전 구간을 현행 계약으로 통일해 잰다(날짜 경계 혼합이면 변형 비교가 흐려진다).
        "dictionary_contract": "dict.v1.11 uniform",
        "supersedes": "OA-7c-S3a/S3b/S3c 의 노출 해석(raw 단계 기준이었다)",
        "days": DAYS,
        "result": run(),
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa9r_display_stage_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
