"""OA-6f3 — P4 잔여 `LOSS_BUDGET_EXCEEDED` 재집계 (측정 전용, 라이브 불변).

P4 가 good 슬롯 단계까지 바꿨으므로 F4 기준의 G2 후보 목록은 더 이상 유효하지 않다.
G2 대상은 **P4 잔여 미해소군**에서만 고른다.

두 층을 분리해 센다:

    good 대표 선택 단계   반복을 피할 good 후보가 예산 밖이라 원시 1위를 유지한 카드
    헤드라인 단계         good/support 2개 중 반복을 피할 후보가 예산 밖인 카드

앞의 층이 G2 의 1차 표적이다 — good 후보 풀은 평균 4.39개로 넓고, 여기서 예산 안에
들어오면 헤드라인 단계까지 갈 필요 없이 반복이 풀린다.
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
    LONGITUDINAL_ALTERNATIVE_SELECTED,
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


def _bucket(uplift: int) -> str:
    if uplift <= 1:
        return "+1p 이내"
    if uplift <= 2:
        return "+2p 이내"
    if uplift <= 3:
        return "+3p 이내"
    if uplift <= 5:
        return "+4~5p"
    return "+6p 이상"


def run() -> dict[str, Any]:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    history: dict[str, list[str]] = collections.defaultdict(list)

    good_reasons = collections.Counter()
    good_blocked: list[dict[str, Any]] = []
    headline_blocked: list[dict[str, Any]] = []
    good_display_loss: list[int] = []

    for i in range(DAYS):
        day = START + dt.timedelta(days=i)
        ctx = M.build_day_context(day)

        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        reps: dict[str, Any] = {}
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
            rep = select_good_representative(goods, history[ilju], BUDGET)
            reps[ilju] = rep
            good_reasons[rep.good_selection_reason] += 1
            if rep.good_selection_reason == LONGITUDINAL_ALTERNATIVE_SELECTED:
                good_display_loss.append(rep.display_displacement_loss)
            if rep.good_selection_reason == GOOD_LOSS_BUDGET_EXCEEDED:
                alt = rep.best_blocked_alternative or ""
                t = taxonomy.get(alt, {})
                good_blocked.append({
                    "stage": "good_representative",
                    "ilju": ilju,
                    "raw_good_winner": rep.raw_good_winner,
                    "blocked_alternative": alt,
                    "alternative_domain": events[alt]["domain"] if alt else None,
                    "alternative_semantic_family": t.get("semantic_family"),
                    "routing_evidence": t.get("subject_evidence"),
                    "probability_gap": rep.raw_good_probability - (
                        rep.raw_good_probability - (rep.required_uplift_to_fit or 0) - BUDGET
                    ),
                    "required_uplift_to_fit": rep.required_uplift_to_fit,
                    "recent7": collections.Counter(history[ilju][-7:]).most_common(3),
                    "recent30_alt_count": collections.Counter(
                        history[ilju][-30:]).get(alt, 0),
                })

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
            alt = u.best_alternative_event_key or ""
            t = taxonomy.get(alt, {})
            headline_blocked.append({
                "stage": "headline",
                "ilju": u.ilju,
                "raw_good_winner": reps[u.ilju].raw_good_winner,
                "original_event_key": u.original_event_key,
                "blocked_alternative": alt,
                "alternative_domain": u.best_alternative_domain,
                "alternative_semantic_family": t.get("semantic_family"),
                "routing_evidence": t.get("subject_evidence"),
                "probability_gap": u.probability_gap,
                "required_uplift_to_fit": u.required_uplift_to_fit,
                "recent30_alt_count": collections.Counter(
                    history[u.ilju][-30:]).get(alt, 0),
            })
        for ilju, sel in r.selections.items():
            history[ilju].append(sel.event_key)

    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        uplifts = [r["required_uplift_to_fit"] for r in rows
                   if r["required_uplift_to_fit"] is not None]
        near = [r for r in rows if (r["required_uplift_to_fit"] or 99) <= 3]
        return {
            "cards": len(rows),
            "required_uplift_distribution": dict(
                collections.Counter(_bucket(u) for u in uplifts).most_common()),
            "recoverable_within_3p": len(near),
            "recoverable_alternatives": dict(
                collections.Counter(r["blocked_alternative"] for r in near).most_common(10)),
            "recoverable_domains": dict(
                collections.Counter(r["alternative_domain"] for r in near).most_common()),
            "recoverable_semantic_families": dict(
                collections.Counter(
                    r["alternative_semantic_family"] for r in near).most_common(8)),
            "mean_required_uplift": round(statistics.mean(uplifts), 2) if uplifts else None,
        }

    combined = good_blocked + headline_blocked
    return {
        "cards": DAYS * 60,
        "measurement_stage": "display_pipeline",
        "baseline": "P4_good_slot_cooldown",
        "good_representative_reasons": dict(good_reasons.most_common()),
        "good_representative_mean_display_loss": round(
            statistics.mean(good_display_loss), 2) if good_display_loss else 0.0,
        "stage_good_representative": _summary(good_blocked),
        "stage_headline": _summary(headline_blocked),
        "combined": _summary(combined),
        "sample_rows": combined[:8],
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-6f3",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "days": DAYS,
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa6f3_p4_residual_90d.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    print("  good 대표 선택 사유:", result["good_representative_reasons"])
    for stage in ("stage_good_representative", "stage_headline", "combined"):
        d = result[stage]
        print(f"  {stage:28} {d['cards']:5}건 · +3p 이내 회복 {d['recoverable_within_3p']:4}건")
        print(f"     {d['required_uplift_distribution']}")
        print(f"     {d['recoverable_alternatives']}")
