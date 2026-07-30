#!/usr/bin/env python3
"""OA-11f — 후보별 한계 도달성 감사 (측정 전용, 정책 미구현).

S1 은 "신규 family" 를 봤기 때문에 실현은 했으나 순효과를 얻지 못했다(실현 34건,
family qualifying 순증가 0). 같은 commit 에서 오래된 family 가 창 밖으로 빠지거나
key 를 잃으면 상쇄된다.

그래서 이번 지표는 신규 여부가 아니라 **기준 선택 대비 한계효과**다.

    S0 원시 선택을 commit 했을 때의 다음 history
    vs
    후보 선택을 commit 했을 때의 다음 history

양쪽에 같은 D-90 eviction 을 적용해 비교하므로, 당일 이전 정보와 이미 예정된
eviction 만 쓴다 — 온라인 계약에 어긋나지 않는다.

정책은 구현하지 않는다. **기존 후보열**만 검사하며 새 사건을 만들거나 별도 점수순
풀을 구성하지 않는다.
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
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types",
           _BACKEND / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_schedule_runner import (  # noqa: E402
    DAILY_BOARD_CONTRACT_V1,
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    CardCandidateBundle,
    ProjectionStatus,
    advance_daily_schedule,
    derive_top1_family_projection,
    empty_state,
)
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    SelectionPolicy,
    repeat_severity,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_ILJUS = [
    f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)
]
ANCHORS = ("2026-04-02", "2027-03-03", "2027-06-01", "2027-08-05", "2027-10-09")
_LOOKBACK = DAILY_HISTORY_CONTRACT_V1.lookback_days
_BUDGET = DAILY_BOARD_CONTRACT_V1.displacement_loss_budget

# ── 후보 분류 (상호 배타) ─────────────────────────────────────────────────
#
# 1차 지표는 coverage delta 가 아니라 **qualifying delta** 다. S1 은 신규 family 를
# 34건 실현했는데 family qualifying 순증가가 0 이었다 — 13→14 는 coverage 가 늘어도
# 문턱(15)을 넘지 않아 anchor 를 닫지 못한다. 13→14 도 장기적으로는 쓸모가 있어
# 버리지 않지만, 즉시 anchor 를 닫는 후보와 분리한다.
IMMEDIATE_FAMILY_THRESHOLD_GAIN_KEY_SAFE = (
    "IMMEDIATE_FAMILY_THRESHOLD_GAIN_KEY_SAFE"
)
POSITIVE_FAMILY_COVERAGE_KEY_SAFE = "POSITIVE_FAMILY_COVERAGE_KEY_SAFE"
FAMILY_GAIN_WITH_KEY_LOSS = "FAMILY_GAIN_WITH_KEY_LOSS"
NEW_FAMILY_BUT_ZERO_NET_GAIN = "NEW_FAMILY_BUT_ZERO_NET_GAIN"
NO_POSITIVE_FAMILY_CANDIDATE = "NO_POSITIVE_FAMILY_CANDIDATE"
SLOT_INFEASIBLE = "SLOT_INFEASIBLE"
AMBIGUOUS_PROJECTION = "AMBIGUOUS_PROJECTION"
SAFETY_BLOCKED = "SAFETY_BLOCKED"
#: 문턱 판정값 — anchor qualifying 과 같은 값을 쓴다.
_QUALIFY_THRESHOLD = 15


def _committed_counts(
    history: tuple[str, ...], addition: str, family_of: dict[str, str]
) -> tuple[int, int]:
    """그 후보를 commit 했을 때의 **다음** 창 (key, family) coverage.

    양쪽에 같은 eviction 을 적용한다 — 창을 넘기면 가장 오래된 하나가 빠진다.
    """
    merged = (*history, addition)
    if len(merged) > _LOOKBACK:
        merged = merged[-_LOOKBACK:]
    return len(set(merged)), len({family_of.get(k, k) for k in merged})


def _rank_bucket(rank: int) -> str:
    for n in (1, 2, 3, 5):
        if rank <= n:
            return f"rank_le_{n}"
    return "rank_gt_5"


def audit_day(
    day: dt.date, state, family_of: dict[str, str], events: dict
) -> list[dict[str, Any]]:
    """그날의 deficit·CLEAN 행에서 기존 후보열 전수 한계효과."""
    ctx = M.build_day_context(day)
    out: list[dict[str, Any]] = []
    for idx, ilju in enumerate(_ILJUS):
        stem, branch = ganzi_from_index(idx)
        seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
        scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
        goods = [
            (s.event_key, s.probability) for s in scored
            if s.valence == "good"
            and "good" in (events[s.event_key].get("headline_slots")
                           or events[s.event_key]["slots"])
        ]
        if not goods:
            continue
        ranked = sorted(goods, key=lambda x: (-x[1], x[0]))
        raw_key, raw_p = ranked[0]
        headline_hist = tuple(state.final_headline_history.get(ilju, ()))
        window = headline_hist[-_LOOKBACK:]
        families = {family_of.get(k, k) for k in window}
        deficit = (
            C10_POLICY.coverage_floor is not None
            and len(families) < C10_POLICY.coverage_floor
        )
        good_hist = list(state.repeat_history_for(
            ilju, source=DAILY_HISTORY_CONTRACT_V1.repeat_history_source
        ))
        if not deficit or repeat_severity(good_hist, raw_key) != SEVERITY_CLEAN:
            continue

        # 기준선: 원시 1위를 commit 했을 때
        rg, rc, rs = M._select_slots(scored, seed, good_override=raw_key)
        if rg.event_key != raw_key:
            out.append({
                "fortune_date": day.isoformat(), "ilju": ilju,
                "baseline_available": False,
                "classification": SLOT_INFEASIBLE, "candidate_rank": 1,
            })
            continue
        rcands = M._headline_candidates(rg, rs, rc, M._band(rg, rc))
        base_key, base_fam = _committed_counts(
            window, rcands[0].event_key, family_of
        )
        top_band = strength_band(raw_p)

        rows: list[dict[str, Any]] = []
        for rank, (key, prob) in enumerate(ranked, start=1):
            if key == raw_key:
                continue
            loss = raw_p - prob
            safety = None
            if loss > _BUDGET:
                safety = "LOSS_BUDGET"
            elif top_band == 4 and strength_band(prob) < top_band:
                safety = "S5_PROTECTION"
            elif top_band - strength_band(prob) >= 2:
                safety = "TWO_BAND_DROP"
            if safety is not None:
                rows.append({
                    "candidate_rank": rank, "event_key": key,
                    "classification": SAFETY_BLOCKED, "safety_block": safety,
                })
                continue
            g, c, s = M._select_slots(scored, seed, good_override=key)
            if g.event_key != key:
                rows.append({
                    "candidate_rank": rank, "event_key": key,
                    "classification": SLOT_INFEASIBLE,
                })
                continue
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            projection = derive_top1_family_projection(
                raw_top_event_key=key,
                card_candidates=CardCandidateBundle(
                    good_event_key=g.event_key, slots=(g, c, s),
                    headline_candidates=tuple(cands),
                ),
                family_of=family_of,
            )
            if projection.status is not ProjectionStatus.PROJECTED:
                rows.append({
                    "candidate_rank": rank, "event_key": key,
                    "classification": AMBIGUOUS_PROJECTION,
                    "projection_status": projection.status.value,
                })
                continue
            cand_key, cand_fam = _committed_counts(
                window, cands[0].event_key, family_of
            )
            fam_cov_delta = cand_fam - base_fam
            key_cov_delta = cand_key - base_key
            fam_qual_delta = (
                int(cand_fam >= _QUALIFY_THRESHOLD)
                - int(base_fam >= _QUALIFY_THRESHOLD)
            )
            key_qual_delta = (
                int(cand_key >= _QUALIFY_THRESHOLD)
                - int(base_key >= _QUALIFY_THRESHOLD)
            )
            is_new = projection.family not in families
            key_safe = key_cov_delta >= 0 and key_qual_delta >= 0
            if fam_qual_delta > 0 and key_safe:
                cls = IMMEDIATE_FAMILY_THRESHOLD_GAIN_KEY_SAFE
            elif fam_cov_delta > 0 and not key_safe:
                cls = FAMILY_GAIN_WITH_KEY_LOSS
            elif fam_cov_delta > 0 and fam_qual_delta == 0:
                cls = POSITIVE_FAMILY_COVERAGE_KEY_SAFE
            elif is_new:
                cls = NEW_FAMILY_BUT_ZERO_NET_GAIN
            else:
                cls = NO_POSITIVE_FAMILY_CANDIDATE
            rows.append({
                "candidate_rank": rank, "event_key": key,
                "classification": cls,
                "projected_preboard_family": projection.family,
                "projected_family_is_new": is_new,
                "raw_next_family_coverage": base_fam,
                "candidate_next_family_coverage": cand_fam,
                "family_coverage_delta_vs_raw": fam_cov_delta,
                "family_qualifying_delta_vs_raw": fam_qual_delta,
                "raw_next_key_coverage": base_key,
                "candidate_next_key_coverage": cand_key,
                "key_coverage_delta_vs_raw": key_cov_delta,
                "key_qualifying_delta_vs_raw": key_qual_delta,
                "display_loss_delta": loss,
            })
        out.append({
            "fortune_date": day.isoformat(), "ilju": ilju,
            "baseline_available": True,
            "baseline_key_coverage": base_key,
            "baseline_family_coverage": base_fam,
            "preday_family_coverage": len(families),
            "candidates": rows,
        })
    return out


def run() -> dict[str, Any]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}
    events = M.load_daily_dicts().catalog["events"]

    # 각 anchor 의 측정 창(D-90 ~ D-1)만 감사한다 — family_p10 이 그 창으로 계산된다.
    targets: dict[str, set[str]] = {}
    for iso in ANCHORS:
        anchor = dt.date.fromisoformat(iso)
        targets[iso] = {
            (anchor - dt.timedelta(days=n)).isoformat()
            for n in range(1, _LOOKBACK + 1)
        }
    all_days = set().union(*targets.values())

    state = empty_state()
    day = DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    last = max(dt.date.fromisoformat(d) for d in all_days)
    collected: dict[str, list[dict[str, Any]]] = {}
    while day <= last:
        iso = day.isoformat()
        if iso in all_days:
            collected[iso] = audit_day(day, state, family_of, events)
        step, state = advance_daily_schedule(
            fortune_date=day, state=state, policy=C10_POLICY, board_policy=_BOARD,
            board_contract=DAILY_BOARD_CONTRACT_V1,
            history_contract=DAILY_HISTORY_CONTRACT_V1, family_of=family_of,
            iljus=_ILJUS, compute_projection_trace=False,
        )
        day += dt.timedelta(days=1)

    per_anchor: dict[str, Any] = {}
    for iso, days in targets.items():
        rows = [r for d in days for r in collected.get(d, [])]
        cls = collections.Counter()
        best_rank = collections.Counter()
        reachable_rows = 0
        for row in rows:
            if not row.get("baseline_available"):
                cls[SLOT_INFEASIBLE] += 1
                continue
            threshold = [
                c for c in row["candidates"]
                if c["classification"] == IMMEDIATE_FAMILY_THRESHOLD_GAIN_KEY_SAFE
            ]
            for c in row["candidates"]:
                cls[c["classification"]] += 1
            if threshold:
                reachable_rows += 1
                ranks = [c["candidate_rank"] for c in threshold]
                best_rank[_rank_bucket(min(ranks))] += 1
            elif any(
                c["classification"] == FAMILY_GAIN_WITH_KEY_LOSS
                for c in row["candidates"]
            ):
                cls["ROW_ONLY_KEY_LOSS_GAIN"] += 1
            elif any(
                c["classification"] == POSITIVE_FAMILY_COVERAGE_KEY_SAFE
                for c in row["candidates"]
            ):
                cls["ROW_ONLY_SUBTHRESHOLD_GAIN"] += 1
            else:
                cls["ROW_NO_POSITIVE_CANDIDATE"] += 1
        per_anchor[iso] = {
            # 단위를 섞지 않는다 — rows 는 행 수, candidates 는 후보 개수 합계다.
            "deficit_clean_rows": len(rows),
            "threshold_gain_rows": reachable_rows,
            "threshold_gain_candidates": cls.get(
                IMMEDIATE_FAMILY_THRESHOLD_GAIN_KEY_SAFE, 0
            ),
            "best_rank_distribution_rows": dict(best_rank),
            "candidate_classification_candidates": dict(cls),
        }
    return {
        "audit_id": "OA-11f",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "note": (
            "지표는 신규 여부가 아니라 기준 선택 대비 한계효과다. 정책은 구현하지 "
            "않았고 기존 후보열만 검사했다."
        ),
        "coverage_source": {
            "family": "FINAL_HEADLINE_FAMILY (OA-10b family_p10 과 동일 축)",
            "key": "FINAL_HEADLINE event_key (OA-10b key_p10 과 동일 축)",
            "note": "history source 를 새로 정의하지 않고 기존 aggregate 축을 쓴다.",
        },
        "primary_metric": "family_qualifying_delta_vs_raw",
        "static_vs_online": {
            "STATIC_CAPACITY": "TOP1_ONLY_STATIC_UPPER_BOUND 56~59/60",
            "ONLINE_CAUSAL_REACHABILITY": "이 감사가 측정한다 — 상한과 다른 값이다",
        },
        "per_anchor": per_anchor,
    }


if __name__ == "__main__":
    r = run()
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11f_candidate_reachability.json"
    out.write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for iso, a in r["per_anchor"].items():
        print(f"  {iso}  deficit·CLEAN 행 {a['deficit_clean_rows']} · "
              f"문턱 이득 행 {a['threshold_gain_rows']} "
              f"(후보 {a['threshold_gain_candidates']}개)")
        print(f"      최소 rank 분포(행) {a['best_rank_distribution_rows']}")
        c = a["candidate_classification_candidates"]
        print(f"      후보 {dict(list(c.items())[:6])}")
