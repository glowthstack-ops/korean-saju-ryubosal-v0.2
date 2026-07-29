"""OA-6f8 — oracle witness 의 라이브 파이프라인 재생 (측정 전용, 라이브 불변).

OA-6f7 의 탐욕 배정은 good 후보 위에서 직접 배정한 것이라 실제 계약의 feasible
schedule 이 아니다. witness 가 지정한 good 대표를 **입력으로만** 주고
`_select_slots → _headline_candidates → _rebalance_headlines` 를 날짜순으로 다시
실행해, 목표 family 가 final 까지 살아남는지 본다.

witness 의 목표 family 가 final 에 없더라도 **강제로 복원하지 않는다** — 라이브
결과를 그대로 받는다. 그래야 어디서 잃는지가 드러난다.

    AUDIT_ORACLE_WITNESS · publishable=false · future_aware=true
oracle 은 90일 전체를 미리 보고 만든 것이라 프로덕션 선택이나 canonical pool 에
그대로 쓸 수 없다.
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
    SelectionPolicy,
    select_board,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

WINDOW, BUDGET = 90, 7
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP = cap_count(60, 0.35), 10
_TARGET, _QUALIFY = 15, 55
_WINDOWS = (
    ("failing_2027-06-01", dt.date(2027, 3, 3)),
    ("passing_2026-07-01", dt.date(2026, 4, 2)),
)

REALIZED = "WITNESS_REPLAY_REALIZED"
NOT_SLOT_FEASIBLE = "WITNESS_CANDIDATE_NOT_SLOT_FEASIBLE"
LOST_AT_CARD = "WITNESS_FAMILY_LOST_AT_CARD_HEADLINE"
LOST_AT_BOARD = "WITNESS_FAMILY_LOST_AT_BOARD_REBALANCE"
ALREADY_PRESENT = "WITNESS_FAMILY_ALREADY_PRESENT"


def _band_ok(top_p: int, alt_p: int) -> bool:
    tb, ab = strength_band(top_p), strength_band(alt_p)
    return ab >= tb or (tb != 4 and tb - ab < 2)


def _scored_days(start: dt.date, events: dict) -> list[dict[str, list]]:
    """90일 × 60일주의 점수. 두 단계(탐욕·재생)가 같은 입력을 쓰게 한 번만 만든다."""
    out = []
    for i in range(WINDOW):
        ctx = M.build_day_context(start + dt.timedelta(days=i))
        day = {}
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            day[f"{stem.value}{branch.value}"] = [
                M._score_event(k, e, stem, branch, ctx) for k, e in events.items()
            ]
        out.append(day)
    return out


def _good_pool(scored: list, events: dict) -> list:
    goods = sorted(
        (s for s in scored
         if s.valence == "good"
         and "good" in (events[s.event_key].get("headline_slots")
                        or events[s.event_key]["slots"])),
        key=lambda x: -x.probability,
    )
    top = goods[0]
    return [
        g for g in goods
        if top.probability - g.probability <= BUDGET
        and _band_ok(top.probability, g.probability)
    ]


def greedy_witness(
    days: list[dict[str, list]], events: dict, family_of: dict[str, str]
) -> list[dict[str, str]]:
    """OA-6f7 과 같은 deficit-first 탐욕 — 일주별 목표 good 후보를 낸다."""
    seen: dict[str, set[str]] = collections.defaultdict(set)
    hist: dict[str, list[str]] = collections.defaultdict(list)
    plan: list[dict[str, str]] = []
    for day in days:
        domains: collections.Counter[str] = collections.Counter()
        evs: collections.Counter[str] = collections.Counter()
        picks: dict[str, str] = {}
        for ilju in sorted(day, key=lambda x: (len(seen[x]), x)):
            pool = _good_pool(day[ilju], events)
            past, prev = hist[ilju][-6:], (hist[ilju][-1] if hist[ilju] else None)

            def usable(g, _p=past, _v=prev, _e=evs, _d=domains) -> bool:
                if g.event_key == _v or _p.count(g.event_key) >= 2:
                    return False
                return (_e[g.event_key] + 1 <= _EVENT_CAP
                        and _d[g.domain] + 1 <= _DOMAIN_CAP)

            fresh = [g for g in pool
                     if family_of[g.event_key] not in seen[ilju] and usable(g)]
            take = fresh or [g for g in pool if usable(g)] or pool
            top = pool[0].probability
            pick = min(take, key=lambda g: (top - g.probability, g.event_key))
            picks[ilju] = pick.event_key
            seen[ilju].add(family_of[pick.event_key])
            hist[ilju].append(pick.event_key)
            domains[pick.domain] += 1
            evs[pick.event_key] += 1
        plan.append(picks)
    return plan


def replay(
    start: dt.date, days: list[dict[str, list]], plan: list[dict[str, str]],
    events: dict, family_of: dict[str, str],
) -> dict[str, Any]:
    """witness 를 good_override 로만 주고 라이브 순수 함수로 재생한다."""
    history: dict[str, list[str]] = collections.defaultdict(list)
    reasons = collections.Counter()
    losses: list[int] = []
    raw_kept = 0
    band_down = s5_down = valence_changed = 0
    domain_hard = domain_auth = 0

    for i, day_scores in enumerate(days):
        day = start + dt.timedelta(days=i)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        stage: dict[str, dict[str, Any]] = {}
        for ilju, scored in day_scores.items():
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            target = plan[i][ilju]
            pool = _good_pool(scored, events)
            top = pool[0]
            good, caution, support = M._select_slots(
                scored, seed, good_override=target
            )
            cands = M._headline_candidates(good, support, caution, M._band(good, caution))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            tf = family_of[target]
            recent = {family_of.get(k, k) for k in history[ilju][-WINDOW:]}
            stage[ilju] = {
                "target": target, "target_family": tf,
                "slot_ok": good.event_key == target,
                "card_ok": family_of.get(cmap[ilju][0].event_key, "") == tf,
                "already": tf in recent,
                "loss": top.probability - good.probability,
                "raw_top": top.event_key,
            }
            if good.event_key == top.event_key:
                raw_kept += 1
            else:
                losses.append(top.probability - good.probability)
                tb, ab = strength_band(top.probability), strength_band(good.probability)
                if ab < tb:
                    band_down += 1
                    if tb == 4:
                        s5_down += 1
                if top.valence != good.valence:
                    valence_changed += 1

        r = select_board(
            raw, cmap, history, domain_cap=_DOMAIN_CAP, event_cap=_EVENT_CAP,
            max_displacement_cost=BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        domain_hard += r.domain_cap_hard_violation
        domain_auth += r.domain_cap_authorized_override
        for ilju, sel in r.selections.items():
            st = stage[ilju]
            ff = family_of.get(sel.event_key, "")
            if st["already"]:
                reasons[ALREADY_PRESENT] += 1
            elif not st["slot_ok"]:
                reasons[NOT_SLOT_FEASIBLE] += 1
            elif not st["card_ok"]:
                reasons[LOST_AT_CARD] += 1
            elif ff != st["target_family"]:
                reasons[LOST_AT_BOARD] += 1
            else:
                reasons[REALIZED] += 1
            history[ilju].append(sel.event_key)

    counts = sorted(
        len({family_of.get(e, e) for e in v}) for v in history.values()
    )
    keys = sorted(len(set(v)) for v in history.values())
    total = max(1, sum(reasons.values()))
    return {
        "qualifying_iljus": sum(1 for v in counts if v >= _TARGET),
        "family_p10": counts[5], "family_min": counts[0], "family_median": counts[30],
        "key_p10": keys[5],
        "mean_loss": round(statistics.mean(losses), 2) if losses else 0.0,
        "p90_loss": sorted(losses)[int(len(losses) * 0.9)] if losses else 0,
        "raw_winner_kept_pct": round(raw_kept / (WINDOW * 60) * 100, 1),
        "band_downgrades": band_down, "s5_downgrades": s5_down,
        "valence_changed": valence_changed,
        "domain_cap_hard_violation": domain_hard,
        "domain_cap_authorized_override": domain_auth,
        "stage_reasons": dict(reasons.most_common()),
        "stage_reason_pct": {
            k: round(v / total * 100, 1) for k, v in reasons.most_common()
        },
    }


def run() -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}

    out: dict[str, Any] = {}
    for name, start in _WINDOWS:
        days = _scored_days(start, events)
        plan = greedy_witness(days, events, family_of)
        res = replay(start, days, plan, events, family_of)
        lost_card = res["stage_reasons"].get(LOST_AT_CARD, 0)
        lost_board = res["stage_reasons"].get(LOST_AT_BOARD, 0)
        res["verdict"] = (
            "SELECTION_ALLOCATION_GAP_CONFIRMED"
            if res["qualifying_iljus"] >= _QUALIFY
            else "BOARD_REBALANCE_ALLOCATION_GAP"
            if lost_board >= lost_card
            else "CARD_STAGE_MODEL_TOO_OPTIMISTIC"
        )
        out[name] = {"window_start": start.isoformat(), **res}
    return {
        "measurement_stage": "display_pipeline",
        "generation_source": "AUDIT_ORACLE_WITNESS",
        "publishable": False,
        "future_aware": True,
        "qualifying_iljus_required": _QUALIFY,
        "windows": out,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f8",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f8_witness_replay.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    for name, w in result["windows"].items():
        print(f"  {name}")
        print(f"    >=15 일주 {w['qualifying_iljus']}/60 · family p10={w['family_p10']} "
              f"최소={w['family_min']} · key p10={w['key_p10']}")
        print(f"    손실 평균 {w['mean_loss']}p p90 {w['p90_loss']}p · "
              f"raw 유지 {w['raw_winner_kept_pct']}% · s5 하락 {w['s5_downgrades']} · "
              f"valence 변경 {w['valence_changed']}")
        print(f"    단계 사유 {w['stage_reason_pct']}")
        print(f"    판정: {w['verdict']}")
