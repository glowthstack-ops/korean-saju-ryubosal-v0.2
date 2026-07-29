"""OA-10a — canonical bootstrap 생성 + 드리프트 검증(측정 전용, 라이브 불변).

`CANONICAL_BOOTSTRAP` 은 새 방식이 아니다. C10 이 출시 기준을 통과한 측정이 이미
`warm-up 90일 → 측정 90일` 구조였고, 그 검증 방식을 배포 초기화 계약으로 공식화한
것이다. **따라서 생성 결과가 self-warmup 감사와 같아야 한다 — 다르면 구현 드리프트다.**

    D-180 ~ D-91   warm-up
    D-90  ~ D-1    canonical history (C10 이 lookback 으로 읽는다)
    D              최초 공개 보드 이후 90일을 측정
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
from saju_engines.daily_canonical_bootstrap import (  # noqa: E402
    BOOTSTRAP_CONTRACT_VERSION,
    C10_POLICY,
    canonical_history,
    generate_bootstrap,
    make_plan,
    verify_lookback_length,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    RAW_GOOD_WINNER_SELECTED,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

#: C10 최초 공개일(테스터 제시 시점). 필요하면 인자로 바꾼다.
ANCHOR = dt.date(*(int(x) for x in (
    (sys.argv[1] if len(sys.argv) > 1 else "2026-07-30").split("-"))))
MEASURE_DAYS = 90
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP, _BUDGET = cap_count(60, 0.35), 10, 7
_P10 = 5


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


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}

    plan = make_plan(ANCHOR)
    rows = generate_bootstrap(plan, family_of)
    verify_lookback_length(plan, rows)

    # canonical 이력을 C10 의 초기 상태로 주입하고 공개일부터 측정한다.
    headline_history: dict[str, list[str]] = {
        k: list(v) for k, v in canonical_history(rows).items()
    }
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    for r in sorted(rows, key=lambda x: (x.fortune_date, x.ilju)):
        if r.is_canonical_history:
            good_history[r.ilju].append(r.display_good_representative)

    measured: dict[str, list[str]] = collections.defaultdict(list)
    raw_kept = rep_changed = 0
    losses: list[int] = []
    band_down = s5_down = 0
    domain_hard = domain_auth = 0
    finals = collections.Counter()
    first7: dict[str, list[str]] = collections.defaultdict(list)
    first30: dict[str, list[str]] = collections.defaultdict(list)

    for i in range(MEASURE_DAYS):
        day = ANCHOR + dt.timedelta(days=i)
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
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
                goods, good_history[ilju], _BUDGET, policy=C10_POLICY,
                family_of=family_of, headline_history=headline_history.get(ilju, []),
            )
            if rep.good_selection_reason == RAW_GOOD_WINNER_SELECTED:
                raw_kept += 1
            elif rep.display_good_representative != rep.raw_good_winner:
                rep_changed += 1
                losses.append(rep.display_displacement_loss)
                from saju_engines.daily_selection_policy_shadow import strength_band
                rb = strength_band(rep.raw_good_probability)
                ab = strength_band(rep.display_good_probability)
                if ab < rb:
                    band_down += 1
                    if rb == 4:
                        s5_down += 1
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
        domain_hard += r.domain_cap_hard_violation
        domain_auth += r.domain_cap_authorized_override
        for ilju, sel in r.selections.items():
            headline_history.setdefault(ilju, []).append(sel.event_key)
            measured[ilju].append(sel.event_key)
            finals[sel.event_key] += 1
            if i < 7:
                first7[ilju].append(sel.event_key)
            if i < 30:
                first30[ilju].append(sel.event_key)

    def _stats(series: dict[str, list[str]], days: int) -> dict[str, Any]:
        uniq = sorted(len(set(v)) for v in series.values())
        fam = sorted(
            len({family_of.get(e, e) for e in set(v)}) for v in series.values()
        )
        dom = sorted(
            len({events[e]["domain"] for e in set(v)}) for v in series.values()
        )
        tops = sorted(collections.Counter(v).most_common(1)[0][1] for v in series.values())
        return {
            "unique_event_key_p10": uniq[_P10],
            "unique_semantic_family_p10": fam[_P10],
            "unique_domain_count_p10": dom[_P10],
            "final_headline_p90_pct": round(tops[int(len(tops) * 0.9) - 1] / days * 100, 1),
            "final_headline_max_pct": round(tops[-1] / days * 100, 1),
            "max_consecutive_days": max(_streak(v) for v in series.values()),
            "window7_repeat3_pct": round(
                statistics.mean(_window_repeat_pct(v) for v in series.values()), 1),
        }

    cards = MEASURE_DAYS * 60
    full = _stats(measured, MEASURE_DAYS)
    gate = {
        "unique_event_key_p10_ge_15": full["unique_event_key_p10"] >= 15,
        "unique_semantic_family_p10_ge_15": full["unique_semantic_family_p10"] >= 15,
        "unique_domain_p10_ge_6": full["unique_domain_count_p10"] >= 6,
        "p90_le_25pct": full["final_headline_p90_pct"] <= 25.0,
        "max_le_33_3pct": full["final_headline_max_pct"] <= 33.3,
        "max_streak_le_4": full["max_consecutive_days"] <= 4,
        "window7_repeat3_le_10pct": full["window7_repeat3_pct"] <= 10.0,
        "mean_loss_le_3_5": (statistics.mean(losses) if losses else 0.0) <= 3.5,
        "no_s5_downgrade": s5_down == 0,
        "no_unauthorized_overflow": domain_hard == 0,
    }
    return {
        "measurement_stage": "display_pipeline",
        "bootstrap": {
            "contract_version": BOOTSTRAP_CONTRACT_VERSION,
            "anchor_date": ANCHOR.isoformat(),
            "start_date": plan.start_date.isoformat(),
            "canonical_start": plan.canonical_start.isoformat(),
            "end_date": plan.end_date.isoformat(),
            "warmup_days": plan.warmup_days,
            "lookback_days": plan.lookback_days,
            "total_days": plan.total_days,
            "rows": len(rows),
            "canonical_rows": sum(1 for r in rows if r.is_canonical_history),
            "is_published": False,
        },
        "measured_window": {
            "days": MEASURE_DAYS,
            "cards": cards,
            **full,
            "top5_cumulative_pct": round(
                sum(n for _k, n in finals.most_common(5)) / cards * 100, 1),
        },
        "onboarding": {
            "first_7d": _stats(first7, 7),
            "first_30d": _stats(first30, 30),
            "representative_changed_pct": round(rep_changed / cards * 100, 1),
            "raw_good_kept_pct": round(raw_kept / cards * 100, 1),
        },
        "display_good": {
            "mean_display_loss": round(statistics.mean(losses), 2) if losses else 0.0,
            "p90_display_loss": sorted(losses)[int(len(losses) * 0.9)] if losses else 0,
            "band_downgrades": band_down,
            "s5_downgrades": s5_down,
        },
        "board_overflow": {
            "domain_cap_hard_violation": domain_hard,
            "domain_cap_authorized_override": domain_auth,
        },
        "release_gate": gate,
        "release_gate_passed": all(gate.values()),
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-10a-BOOTSTRAP",
        "policy_status": "shadow_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa10a_canonical_bootstrap.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    b, m = result["bootstrap"], result["measured_window"]
    print(f"  bootstrap {b['start_date']} ~ {b['end_date']} "
          f"({b['total_days']}일 · {b['rows']}행 · canonical {b['canonical_rows']}행)")
    print(f"  측정 {b['anchor_date']} 부터 {m['days']}일 — "
          f"key={m['unique_event_key_p10']} fam={m['unique_semantic_family_p10']} "
          f"dom={m['unique_domain_count_p10']} p90={m['final_headline_p90_pct']}% "
          f"7일3회={m['window7_repeat3_pct']}%")
    print("  손실:", result["display_good"], "· overflow:", result["board_overflow"])
    print("  초기 7일:", result["onboarding"]["first_7d"])
    print("  게이트:", result["release_gate_passed"],
          [k for k, v in result["release_gate"].items() if not v] or "전부 통과")
