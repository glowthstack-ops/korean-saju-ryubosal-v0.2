"""OA-6f6 — family 도달 가능성(R0/R1)과 결손일 사유 분해 (측정 전용, 라이브 불변).

OA-10b 가 남긴 질문: `family p10 = 14` 가 **콘텐츠 상한**인가 **선택기 실패**인가.

    R0  catalog reachable    그 90일에 한 번이라도 good 헤드라인 후보였던 family
    R1  local final reachable + 7p 예산 + 밴드 보호를 통과할 수 있는 family
    사유 분해              coverage < 16 인 일주-일에서 왜 새 family 를 못 넣었나

taxonomy 총량도 함께 낸다 — 전체 family 수가 적으면 90일 창에서 15개를 채우는 것
자체가 빡빡하다.
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
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SelectionPolicy,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

WINDOW, BUDGET = 90, 7
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP = cap_count(60, 0.35), 10
_TARGET, _RECOVERY = 15, 16
#: (이름, 창 시작일). OA-10b 의 최장 실패 구간과 통과 구간.
_WINDOWS = (
    ("failing_2027-06-01", dt.date(2027, 3, 3)),
    ("passing_2026-07-01", dt.date(2026, 4, 2)),
)
_WATCH = ("戊辰", "庚戌", "丙辰", "乙亥", "癸酉", "甲午", "辛亥")
_CONTROL = ("甲子", "乙丑", "丙寅")


def _load() -> tuple[dict, dict[str, str]]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    return events, {k: t["semantic_family"] for k, t in tax.items()}


def _headline_slots(e: dict) -> list[str]:
    return e.get("headline_slots") or e["slots"]


def taxonomy_census(events: dict, family_of: dict[str, str]) -> dict[str, Any]:
    """헤드라인 경로별 family 총량 — 15 라는 목표의 절대 상한을 정한다."""
    fam_members = collections.defaultdict(list)
    for k, f in family_of.items():
        fam_members[f].append(k)
    good = {family_of[k] for k, e in events.items() if "good" in _headline_slots(e)}
    caution = {family_of[k] for k, e in events.items() if "caution" in _headline_slots(e)}
    support_only = {
        family_of[k] for k, e in events.items() if _headline_slots(e) == ["support"]
    }
    return {
        "taxonomy_total_families": len(fam_members),
        "headline_eligible_families": len(good | caution),
        "good_headline_families": len(good),
        "caution_headline_families": len(caution),
        "support_only_families": len(support_only - good - caution),
        "multi_event_families": sorted(f for f, v in fam_members.items() if len(v) > 1),
        "singleton_families": sum(1 for v in fam_members.values() if len(v) == 1),
        "good_headline_family_list": sorted(good),
    }


def _band_ok(top_p: int, alt_p: int) -> bool:
    tb, ab = strength_band(top_p), strength_band(alt_p)
    return ab >= tb or (tb != 4 and tb - ab < 2)


def reachability(start: dt.date, events: dict, family_of: dict[str, str]) -> dict[str, Any]:
    """R0 · R1 — 90일 창에서 일주별로 도달 가능한 family 수."""
    r0: dict[str, set[str]] = collections.defaultdict(set)
    r1: dict[str, set[str]] = collections.defaultdict(set)
    for i in range(WINDOW):
        ctx = M.build_day_context(start + dt.timedelta(days=i))
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = sorted(
                (s for s in scored
                 if s.valence == "good" and "good" in _headline_slots(events[s.event_key])),
                key=lambda x: -x.probability,
            )
            top = goods[0]
            for g in goods:
                r0[ilju].add(family_of[g.event_key])
                if top.probability - g.probability <= BUDGET and _band_ok(
                    top.probability, g.probability
                ):
                    r1[ilju].add(family_of[g.event_key])
    a = sorted(len(v) for v in r0.values())
    b = sorted(len(v) for v in r1.values())
    return {
        "R0_p10": a[5], "R0_min": a[0], "R0_median": a[30], "R0_max": a[-1],
        "R1_p10": b[5], "R1_min": b[0], "R1_median": b[30], "R1_max": b[-1],
        "R0_below_target": sum(1 for x in a if x < _TARGET),
        "R1_below_target": sum(1 for x in b if x < _TARGET),
        "watch": {
            w: {"R0": len(r0[w]), "R1": len(r1[w])}
            for w in (*_WATCH, *_CONTROL) if w in r0
        },
    }


def deficit_breakdown(
    start: dt.date, events: dict, family_of: dict[str, str]
) -> dict[str, Any]:
    """coverage < 16 인 일주-일에서 왜 새 family 를 넣지 못했는가.

    warm-up 90일을 먼저 돌린 뒤 측정 90일을 센다.
    """
    hh: dict[str, list[str]] = collections.defaultdict(list)
    gh: dict[str, list[str]] = collections.defaultdict(list)
    reason = collections.Counter()
    deficit = 0
    board_families: list[int] = []

    for i in range(WINDOW * 2):
        day = start - dt.timedelta(days=WINDOW) + dt.timedelta(days=i)
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            goods = sorted(
                (s for s in scored
                 if s.valence == "good" and "good" in _headline_slots(events[s.event_key])),
                key=lambda x: -x.probability,
            )
            rep = select_good_representative(
                [(s.event_key, s.probability) for s in goods], gh[ilju], BUDGET,
                policy=C10_POLICY, family_of=family_of, headline_history=hh[ilju],
            )
            if i >= WINDOW:
                cov = {family_of.get(k, k) for k in hh[ilju][-WINDOW:]}
                if len(cov) < _RECOVERY:
                    deficit += 1
                    top = goods[0]
                    unused = [
                        g for g in goods
                        if family_of[g.event_key] not in cov
                        and top.probability - g.probability <= BUDGET
                    ]
                    if not unused:
                        reason["NO_UNUSED_FAMILY_IN_BUDGET"] += 1
                    elif family_of[rep.display_good_representative] not in cov:
                        reason["UNUSED_FAMILY_SELECTED_AS_GOOD"] += 1
                    elif any(_band_ok(top.probability, g.probability) for g in unused):
                        reason["UNUSED_FAMILY_AVAILABLE_BUT_NOT_CHOSEN"] += 1
                    else:
                        reason["UNUSED_FAMILY_BAND_BLOCKED"] += 1
            g, c, s = M._select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            gh[ilju].append(rep.display_good_representative)
        r = select_board(
            raw, cmap, hh, domain_cap=_DOMAIN_CAP, event_cap=_EVENT_CAP,
            max_displacement_cost=BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        if i >= WINDOW:
            board_families.append(
                len({family_of.get(x.event_key, x.event_key)
                     for x in r.selections.values()})
            )
        for ilju, sel in r.selections.items():
            hh[ilju].append(sel.event_key)

    total = max(1, deficit)
    return {
        "coverage_deficit_ilju_days": deficit,
        "reasons": dict(reason.most_common()),
        "reason_pct": {k: round(v / total * 100, 1) for k, v in reason.most_common()},
        "board_families_per_day": {
            "mean": round(sum(board_families) / max(1, len(board_families)), 1),
            "min": min(board_families, default=0),
            "max": max(board_families, default=0),
        },
    }


def run() -> dict[str, Any]:
    events, family_of = _load()
    return {
        "measurement_stage": "display_pipeline",
        "taxonomy_census": taxonomy_census(events, family_of),
        "windows": {
            name: {
                "window_start": start.isoformat(),
                "reachability": reachability(start, events, family_of),
                "deficit_breakdown": deficit_breakdown(start, events, family_of),
            }
            for name, start in _WINDOWS
        },
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f6",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f6_family_reachability.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    c = result["taxonomy_census"]
    print(f"  family 총 {c['taxonomy_total_families']} · 헤드라인 가능 "
          f"{c['headline_eligible_families']} · good {c['good_headline_families']} · "
          f"caution {c['caution_headline_families']}")
    for name, w in result["windows"].items():
        r, d = w["reachability"], w["deficit_breakdown"]
        print(f"  {name}: R0 p10={r['R0_p10']} R1 p10={r['R1_p10']} "
              f"(R0<15: {r['R0_below_target']} · R1<15: {r['R1_below_target']})")
        print(f"     결손 {d['coverage_deficit_ilju_days']} 일주-일 · {d['reason_pct']}")
        print(f"     하루 보드 family: {d['board_families_per_day']}")
