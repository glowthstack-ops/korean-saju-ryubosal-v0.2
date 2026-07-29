"""OA-7c-S — 사건 경쟁 구조 감사(측정 전용, 사전 변경 없음).

전체 평균 비교는 서로 다른 카드에서 계산된 값을 섞는다. **같은 카드에서 실제로
경쟁했을 때의 조건부 결과**를 봐야 M1/M2/M3 를 가릴 수 있다.

    M1 money_small_gain 자체가 과도하게 높다
    M2 경쟁 사건이 구조적으로 낮다
    M3 둘 다

실행 위치에 독립적이다.
"""

from __future__ import annotations

import collections
import copy
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_relation_shadow import _finalize, _signals  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
MONEY, NEWS = "money_small_gain", "good_news_arrives"
WORK = ("focus_flow", "praise_recognition", "teamwork_flow")
FAMILY = "family_talk"


def _eligible(ev: dict) -> bool:
    return ev["valence"] == "good" and "good" in (
        ev.get("headline_slots") or ev["slots"]
    )


def _score(ev: dict, key: str, stem, branch, ctx, **over):
    """반사실 채점 — 사전을 바꾸지 않고 복사본에만 적용한다."""
    if over:
        ev = {**copy.deepcopy(ev), **over}
    return _finalize(ev, _signals(ev, stem, branch, ctx), key)


def run() -> dict:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]

    h2h = collections.Counter()
    gaps: list[int] = []
    money_only = news_only = 0
    work_rank = collections.Counter()
    work_gap: list[int] = []
    cf_focus = collections.Counter()
    funnel = collections.Counter()
    rel_hits = collections.Counter()

    for i in range(DAYS):
        ctx = M.build_day_context(START + dt.timedelta(days=i))
        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            scored = {
                k: M._score_event(k, e, stem, branch, ctx) for k, e in events.items()
            }

            # ── ① money vs news 직접 대결 ──
            m_ok, n_ok = _eligible(events[MONEY]), _eligible(events[NEWS])
            if m_ok and n_ok:
                mp, np_ = scored[MONEY].probability, scored[NEWS].probability
                h2h["both"] += 1
                gap = abs(mp - np_)
                gaps.append(gap)
                if mp > np_:
                    h2h["money_wins"] += 1
                elif np_ > mp:
                    h2h["news_wins"] += 1
                else:
                    h2h["tie"] += 1
                h2h["gap_0_2" if gap <= 2 else ("gap_3_5" if gap <= 5 else "gap_6plus")] += 1
            elif m_ok:
                money_only += 1
            elif n_ok:
                news_only += 1

            # ── ② work 3종 내 순위 ──
            work_scores = sorted(
                ((scored[k].probability, k) for k in WORK), reverse=True
            )
            for rank, (_p, k) in enumerate(work_scores, 1):
                work_rank[f"{k}|{rank}"] += 1
            work_gap.append(work_scores[0][0] - scored["focus_flow"].probability)

            # focus_flow 반사실 — confidence·base 를 경쟁 사건 수준으로
            base_ff = scored["focus_flow"].probability
            top_work = work_scores[0][0]
            for label, over in (
                ("conf_1.0", {"expr_confidence": 1.0}),
                ("base_+0.02", {"base_weight": events["focus_flow"]["base_weight"] + 0.02}),
                ("both", {"expr_confidence": 1.0,
                          "base_weight": events["focus_flow"]["base_weight"] + 0.02}),
            ):
                p = _score(events["focus_flow"], "focus_flow", stem, branch, ctx, **over)
                cf_focus[f"{label}|delta"] += p.probability - base_ff
                if p.probability >= top_work:
                    cf_focus[f"{label}|would_top_work"] += 1

            # ── ③ family_talk 신호 깔때기 ──
            funnel["evaluated"] += 1
            fam = scored[FAMILY]
            no_rel = _score(events[FAMILY], FAMILY, stem, branch, ctx)
            rel_only = _finalize(
                events[FAMILY],
                _signals(events[FAMILY], stem, branch, ctx, relation_only=True), FAMILY,
            )
            if rel_only.probability > 5:
                funnel["positive_relation_contribution"] += 1
            if _eligible(events[FAMILY]):
                funnel["good_candidate"] += 1
            order = sorted(scored.values(), key=lambda s: -s.probability)
            pos = next(r for r, s in enumerate(order, 1) if s.event_key == FAMILY)
            if pos <= 10:
                funnel["top10"] += 1
            if pos <= 3:
                funnel["top3"] += 1
            if pos == 1:
                funnel["top1"] += 1
            # 실제 일지 관계가 얼마나 붙는가
            hits = M._branch_relations(
                M.Branch(ctx.day_branch), branch,
                (M.Branch(ctx.month_branch), M.Branch(ctx.year_branch)),
            )
            for h in hits:
                rel_hits[h] += 1
            if hits:
                funnel["any_day_branch_relation"] += 1
            _ = no_rel

    cards = DAYS * 60
    return {
        "cards": cards,
        "money_vs_news": {
            "both_eligible": h2h["both"],
            "money_only_eligible": money_only,
            "news_only_eligible": news_only,
            "money_wins": h2h["money_wins"], "news_wins": h2h["news_wins"],
            "ties": h2h["tie"],
            "money_win_rate_pct": round(h2h["money_wins"] / max(1, h2h["both"]) * 100, 1),
            "mean_abs_gap": round(statistics.mean(gaps), 2) if gaps else None,
            "gap_0_2": h2h["gap_0_2"], "gap_3_5": h2h["gap_3_5"],
            "gap_6plus": h2h["gap_6plus"],
        },
        "focus_flow": {
            "rank_in_work3": {
                k: {str(r): work_rank[f"{k}|{r}"] for r in (1, 2, 3)} for k in WORK
            },
            "mean_gap_to_work_top": round(statistics.mean(work_gap), 2),
            "counterfactual": {
                label: {
                    "mean_delta": round(cf_focus[f"{label}|delta"] / cards, 2),
                    "would_reach_work_top": cf_focus[f"{label}|would_top_work"],
                    "would_reach_pct": round(
                        cf_focus[f"{label}|would_top_work"] / cards * 100, 1
                    ),
                }
                for label in ("conf_1.0", "base_+0.02", "both")
            },
        },
        "family_talk": {
            "funnel": {
                "evaluated": funnel["evaluated"],
                "any_day_branch_relation": funnel["any_day_branch_relation"],
                "positive_relation_contribution": funnel["positive_relation_contribution"],
                "good_candidate": funnel["good_candidate"],
                "top10": funnel["top10"], "top3": funnel["top3"], "top1": funnel["top1"],
            },
            "day_branch_relation_hits": dict(rel_hits.most_common()),
            "relation_affinity": events[FAMILY].get("relation_affinity"),
            "ten_god_affinity": events[FAMILY].get("ten_god_affinity"),
            "base_weight": events[FAMILY]["base_weight"],
            "expr_confidence": events[FAMILY]["expr_confidence"],
        },
    }


if __name__ == "__main__":
    data = {"audit_id": "OA-7c-S2", "policy_status": "measurement_only",
            "live_behavior_changed": False, "days": DAYS, "result": run()}
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_event_competition_90d.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["result"], ensure_ascii=False, indent=1))
