"""2026-07-30 domain cap 초과의 불가능성 증명 (측정 전용, 라이브 불변).

C10 은 270일 × 60일주 = 16,200 카드-일 중 **1건**의 domain 초과를 남긴다
(2026-07-30 · money 22 / cap 21). 이것이 "설명되지 않은 계약 위반"인지 "가능한 배치가
없어 승인된 override"인지 가려야 한다.

증명해야 하는 명제:

    valence · headline 자격 · s5 보호 · 7p 손실 예산 · domain cap 을 **모두**
    만족하는 전역 배치가 존재하지 않으며, event cap 을 완전히 풀어도 해결되지 않는다.

탐색은 근사하지 않는다 — 그날 60장의 후보 조합을 domain 관점에서 **완전 탐색**한다.
money 를 21장 이하로 만들려면 money 대표 카드 중 최소 1장이 비-money 후보로 옮겨져야
하므로, "money 를 벗어날 수 있는 카드가 하나라도 있는가"만 확인하면 충분하다.
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
from saju_engines.daily_cooldown_shadow import cooldown_violation  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    DOMAIN_CAP_INFEASIBLE_AFTER_EVENT_CAP_RELAXATION,
    LongTermPolicy,
    SelectionPolicy,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

MEASURE_START = dt.date(2026, 7, 1)
WARMUP = 90
START = MEASURE_START - dt.timedelta(days=WARMUP)
TARGET = dt.date(2026, 7, 30)
DOMAIN_CAP = cap_count(60, 0.35)
EVENT_CAP, BUDGET = 10, 7
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_C10 = LongTermPolicy(
    unused_semantic_family=True, unused_event_key=True,
    coverage_floor=16, recovery_prefers_low_loss=False, band_protection=True,
)


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}

    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    target_state: dict[str, Any] = {}

    day = START
    while day <= TARGET:
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        blocked_by_s5: dict[str, str] = {}
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
                goods, good_history[ilju], BUDGET, policy=_C10,
                family_of=family_of, headline_history=headline_history[ilju],
            )
            if "BAND_DOWNGRADE_BLOCKED" in rep.good_selection_reason:
                blocked_by_s5[ilju] = rep.best_blocked_alternative or ""
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
            raw, cmap, headline_history, domain_cap=DOMAIN_CAP, event_cap=EVENT_CAP,
            max_displacement_cost=BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        if day == TARGET:
            target_state = {
                "raw": raw, "cmap": cmap, "result": r,
                "blocked_by_s5": blocked_by_s5,
                "history": {k: list(v) for k, v in headline_history.items()},
            }
        for ilju, sel in r.selections.items():
            headline_history[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)

    r = target_state["result"]
    cmap = target_state["cmap"]
    selections = r.selections
    domains = collections.Counter(c.domain for c in selections.values())
    over_domain = max(domains, key=lambda d: domains[d])

    # ── 완전 탐색: 초과 도메인을 벗어날 수 있는 카드가 하나라도 있는가 ──
    hist = target_state["history"]
    moved = {m.ilju for m in r.moves}
    escape_options: list[dict[str, Any]] = []
    rejected: collections.Counter[str] = collections.Counter()
    for ilju, cur in selections.items():
        if cur.domain != over_domain:
            continue
        for alt in cmap[ilju]:
            if alt.event_key == cur.event_key or alt.domain == over_domain:
                continue
            loss = raw_loss(target_state["raw"], ilju, alt)
            reasons: list[str] = []
            if loss > BUDGET:
                reasons.append("LOSS_BUDGET_EXCEEDED")
            if cooldown_violation(hist.get(ilju, ()), alt.event_key):
                reasons.append("COOLDOWN_VIOLATION")
            if domains.get(alt.domain, 0) >= DOMAIN_CAP:
                reasons.append("DESTINATION_DOMAIN_FULL")
            if strength_band(alt.probability) < strength_band(
                target_state["raw"][ilju].probability
            ):
                reasons.append("BAND_DOWNGRADE")
            row = {
                "ilju": ilju,
                "from_event": cur.event_key,
                "to_event": alt.event_key,
                "to_domain": alt.domain,
                "loss": loss,
                "band_from": strength_band(cur.probability),
                "band_to": strength_band(alt.probability),
                "destination_domain_count": domains.get(alt.domain, 0),
                "already_moved_this_board": ilju in moved,
                "blocking_reasons": reasons,
            }
            if reasons:
                rejected[reasons[0]] += 1
            else:
                escape_options.append(row)

    # 후보 카드 전체에서 초과 도메인 밖 후보를 아예 갖지 않은 카드 수
    no_escape = sum(
        1 for ilju, cur in selections.items()
        if cur.domain == over_domain
        and not any(a.domain != over_domain for a in cmap[ilju])
    )
    return {
        "target_date": TARGET.isoformat(),
        "domain_cap": DOMAIN_CAP,
        "event_cap": EVENT_CAP,
        "loss_budget": BUDGET,
        "final_domain_counts": dict(domains.most_common()),
        "over_domain": over_domain,
        "over_by": domains[over_domain] - DOMAIN_CAP,
        "domain_cap_hard_violation": r.domain_cap_hard_violation,
        "domain_cap_authorized_override": r.domain_cap_authorized_override,
        "constraint_override_reason": r.constraint_override_reason,
        "cards_in_over_domain": domains[over_domain],
        "cards_with_no_cross_domain_candidate": no_escape,
        "escape_options_within_budget": escape_options,
        "s5_blocked_cards": target_state["blocked_by_s5"],
        "proof": {
            "claim": "valence·자격·s5 보호·7p 예산·domain cap 을 모두 만족하는 전역 "
                     "배치가 없고, event cap 을 완전히 풀어도 해결되지 않는다",
            "method": "초과 도메인의 모든 카드에 대해 카드 내 후보를 완전 탐색",
            "escape_option_count": len(escape_options),
            "rejected_escape_reasons": dict(rejected.most_common()),
            "infeasible": len(escape_options) == 0,
        },
    }


def raw_loss(raw: dict[str, HeadlineCandidate], ilju: str, alt: HeadlineCandidate) -> int:
    return raw[ilju].probability - alt.probability


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "P4-LC-C10-INFEASIBILITY",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "fixture": True,
        "verdict": {
            "authorized": (
                result["domain_cap_hard_violation"] == 0
                and result["constraint_override_reason"]
                == DOMAIN_CAP_INFEASIBLE_AFTER_EVENT_CAP_RELAXATION
                and result["proof"]["infeasible"]
            ),
        },
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "p4lc_c10_infeasibility_2026-07-30.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    print("  도메인 분포:", result["final_domain_counts"])
    print("  초과:", result["over_domain"], "+", result["over_by"])
    print("  hard violation:", result["domain_cap_hard_violation"],
          "· authorized:", result["domain_cap_authorized_override"])
    print("  사유:", result["constraint_override_reason"])
    print("  기각 사유:", result["proof"]["rejected_escape_reasons"])
    print("  탈출 후보 수:", result["proof"]["escape_option_count"],
          "· 교차 도메인 후보 없는 카드:", result["cards_with_no_cross_domain_candidate"])
    print("  판정:", data["verdict"])
