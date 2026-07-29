"""OA-6f4 — 고유 p10 미달 일주의 15번째 후보 추적 (측정 전용, 라이브 불변).

지시의 "OA-6f3 하위 일주 trace". 파일명 `oa6f3` 는 잔여 재집계가 선점해 f4 로 둔다.

닫아야 할 질문: 고유 event_key p10 이 14 인 원인이 **점수 부족**인가, 아니면
**P4 가 7일 반복 완화에만 최적화돼 90일 미사용 유효 후보를 계속 놓치는 것**인가.

    eligible_unique_p10       17
    within_budget_unique_p10  16
    selected_unique_p10       14

15번째 사건이 이미 7p 안에 있었다면 점수 보강(G2)은 잘못된 처방이다.

또한 `event_key` 고유 수만으로는 체감 다양성을 과대평가할 수 있어
`semantic_family`·`domain` 고유 수를 보조 지표로 함께 낸다 —
`money_small_gain → money_good_deal` 같은 형제 교체로 기준을 통과하는 것을 막는다.
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
from saju_engines.daily_cooldown_shadow import LOSS_BUDGET_EXCEEDED  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    GOOD_LOSS_BUDGET_EXCEEDED,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
DOMAIN_CAP = cap_count(60, 0.35)
EVENT_CAP = 10
BUDGET = 7
_POLICY = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
#: p10 = 60개 중 6번째로 작은 값. 통과하려면 15 미만 일주가 5개 이하여야 한다.
_P10_INDEX = 5
_TARGET_UNIQUE = 15


def _p10(values: list[int]) -> int:
    return sorted(values)[_P10_INDEX]


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]

    history: dict[str, list[str]] = collections.defaultdict(list)
    #: 일주 → 사건 → 그 사건이 good 후보였던 날의 (top 점수 - 자기 점수) 목록
    gap_days: dict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    #: 잔여 카드의 단계 집합(중복 계산 방지)
    residual_stages: dict[tuple[str, int], set[str]] = collections.defaultdict(set)
    residual_uplift: dict[tuple[str, int], int] = {}
    residual_alt: dict[tuple[str, int], str] = {}

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
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
            top = max(p for _k, p in goods)
            for key, p in goods:
                gap_days[ilju][key].append(top - p)

            rep = select_good_representative(goods, history[ilju], BUDGET)
            if rep.good_selection_reason == GOOD_LOSS_BUDGET_EXCEEDED:
                residual_stages[(ilju, i)].add("good_representative")
                residual_uplift[(ilju, i)] = rep.required_uplift_to_fit or 0
                residual_alt[(ilju, i)] = rep.best_blocked_alternative or ""

            g, c, s = M._select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]

        r = select_board(
            raw, cmap, history, domain_cap=DOMAIN_CAP, event_cap=EVENT_CAP,
            max_displacement_cost=BUDGET, policy=_POLICY, today=day.toordinal(),
        )
        for u in r.unresolved_cards:
            if u.reason != LOSS_BUDGET_EXCEEDED:
                continue
            residual_stages[(u.ilju, i)].add("headline")
            residual_uplift.setdefault((u.ilju, i), u.required_uplift_to_fit or 0)
            residual_alt.setdefault((u.ilju, i), u.best_alternative_event_key or "")
        for ilju, sel in r.selections.items():
            history[ilju].append(sel.event_key)

    # ── 일주 분류 ──
    unique_keys = {k: len(set(v)) for k, v in history.items()}
    unique_family = {
        k: len({taxonomy.get(e, {}).get("semantic_family", e) for e in set(v)})
        for k, v in history.items()
    }
    unique_domain = {
        k: len({events[e]["domain"] for e in set(v)}) for k, v in history.items()
    }
    below = sorted(k for k, n in unique_keys.items() if n < _TARGET_UNIQUE)
    buckets = collections.Counter(
        "<15" if n < 15 else "=15" if n == 15 else ">15" for n in unique_keys.values()
    )

    # ── 하위 일주의 미선택 후보 추적 ──
    traces: list[dict[str, Any]] = []
    branch_counts = collections.Counter()
    lift_sources = collections.Counter()
    for ilju in below:
        used = set(history[ilju])
        rows = []
        for key, gaps in gap_days[ilju].items():
            if key in used or not gaps:
                continue
            within = sum(1 for g in gaps if g <= BUDGET)
            t = taxonomy.get(key, {})
            rows.append({
                "event_key": key,
                "eligible_days": len(gaps),
                "within_7p_days": within,
                "min_required_uplift": max(0, min(gaps) - BUDGET),
                "min_gap": min(gaps),
                "blocking_stage": (
                    "HIGHER_CLEAN_CANDIDATE_PREFERRED" if within
                    else "SCORE_OUTSIDE_BUDGET"
                ),
                "previous_selection_count": 0,
                "semantic_family": t.get("semantic_family"),
                "domain": events[key]["domain"],
                "routing_evidence": t.get("subject_evidence"),
            })
        rows.sort(key=lambda x: (x["min_required_uplift"], -x["within_7p_days"]))
        best = rows[0] if rows else None
        if best is None:
            branch_counts["E_no_unused_candidate"] += 1
        elif best["within_7p_days"] > 0:
            branch_counts["A_already_within_7p"] += 1
            lift_sources[best["event_key"]] += 1
        elif best["min_required_uplift"] <= 3:
            branch_counts["B_needs_1_to_3p"] += 1
            lift_sources[best["event_key"]] += 1
        else:
            branch_counts["E_needs_4p_or_more"] += 1
        traces.append({
            "ilju": ilju,
            "selected_unique": unique_keys[ilju],
            "unique_semantic_family": unique_family[ilju],
            "unique_domain": unique_domain[ilju],
            "unused_candidates": rows[:5],
        })

    # ── document_progress 커버리지 ──
    doc = "document_progress"
    doc_iljus = {
        k for k in below
        if doc not in set(history[k]) and gap_days[k].get(doc)
    }
    doc_within = {k for k in doc_iljus if any(g <= BUDGET for g in gap_days[k][doc])}
    doc_uplift = collections.Counter()
    for k in doc_iljus:
        up = max(0, min(gap_days[k][doc]) - BUDGET)
        doc_uplift["+1p 이내" if up <= 1 else "+2p 이내" if up <= 2
                   else "+3p 이내" if up <= 3 else "+4p 이상"] += 1

    # ── 잔여 카드 단계 중복 ──
    stage_counts = collections.Counter()
    for stages in residual_stages.values():
        stage_counts[
            "both_stages" if len(stages) == 2 else f"{next(iter(stages))}_only"
        ] += 1
    unique_residual = len(residual_stages)
    unique_within3 = sum(1 for k in residual_stages if residual_uplift.get(k, 99) <= 3)

    return {
        "cards": DAYS * 60,
        "measurement_stage": "display_pipeline",
        "baseline": "P4_good_slot_cooldown",
        "p10_definition": "60개 일주 중 6번째로 작은 값 — 15 미만 일주가 5개 이하면 통과",
        "diversity_metrics": {
            "unique_event_key_p10": _p10(list(unique_keys.values())),
            "unique_semantic_family_p10": _p10(list(unique_family.values())),
            "unique_domain_count_p10": _p10(list(unique_domain.values())),
            "unique_event_key_median": statistics.median(unique_keys.values()),
        },
        "ilju_buckets": dict(buckets),
        "count_below_15": len(below),
        "count_equal_14": sum(1 for n in unique_keys.values() if n == 14),
        "required_ilju_lifts_to_pass": max(0, len(below) - _P10_INDEX),
        "branch_verdict": dict(branch_counts.most_common()),
        "lift_source_events": dict(lift_sources.most_common(10)),
        "document_progress_coverage": {
            "below_15_iljus_with_candidate": len(doc_iljus),
            "below_15_iljus_already_within_7p": len(doc_within),
            "required_uplift_distribution": dict(doc_uplift.most_common()),
            "iljus_lifted_14_to_15_if_selected_once": len(doc_iljus),
        },
        "residual_stage_overlap": {
            "unique_residual_cards": unique_residual,
            "by_stage": dict(stage_counts.most_common()),
            "unique_recoverable_within_3p": unique_within3,
            "note": "앞서 보고한 292·178 은 **단계 행 수**였다. 고유 카드 기준은 이 값이다.",
        },
        "traces": traces,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f4",
        "aka": "지시의 'OA-6f3 하위 일주 trace' (oa6f3 파일명은 잔여 재집계가 선점)",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "days": DAYS,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f4_low_ilju_trace_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    print("  다양성:", result["diversity_metrics"])
    print("  일주 분포:", result["ilju_buckets"],
          "· 15 미만", result["count_below_15"],
          "· 통과에 필요한 상승", result["required_ilju_lifts_to_pass"])
    print("  분기 판정:", result["branch_verdict"])
    print("  상승 후보:", result["lift_source_events"])
    print("  document_progress:", result["document_progress_coverage"])
    print("  잔여 고유 카드:", result["residual_stage_overlap"])
