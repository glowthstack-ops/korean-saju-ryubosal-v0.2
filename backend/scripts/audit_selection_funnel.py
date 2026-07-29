"""OA-7c-S2 — 단계별 선택 깔때기 추적(측정 전용).

pairwise 비교만으로는 "왜 헤드라인이 아닌가"를 설명할 수 없다. news 가 money 를 61대
60으로 이겨도 제3 사건이 75점이면 둘 다 헤드라인이 아니다. **전체 순위와 단계별 탈락
경로를 함께** 본다.

    S0 점수 산출 → 전체 49종 순위
    S1 _select_slots → good / support / caution
    S2 headline 후보 → band 에 따라 raw headline
    S3 보드 재배정 → domain cap 적용 후 final

탈락 사유는 추론하지 않고 각 단계의 실제 조건에서 기록한다.
"""

from __future__ import annotations

import collections
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
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

START, DAYS = dt.date(2026, 7, 1), 90
TRACKED = ("money_small_gain", "good_news_arrives", "focus_flow")
MONEY, NEWS, FOCUS = TRACKED


def _reason(key, scored_map, good, caution, support, band, cands, raw, final):
    """이 사건이 최종 헤드라인이 되지 못한 첫 번째 사유."""
    if final and final.event_key == key:
        return "FINAL_SELECTED"
    s = scored_map[key]
    if raw and raw.event_key == key:
        return "BOARD_DOMAIN_CAP_DISPLACED"
    if band == "s1":
        return "S1_BAND_USES_CAUTION" if caution.event_key != key else "FINAL_SELECTED"
    if any(c.event_key == key for c in cands):
        return "LOWER_CANDIDATE_SCORE"
    if good.event_key == key:
        return "HEADLINE_SLOT_INELIGIBLE"
    if support.event_key == key:
        return "SUPPORT_SLOT_SELECTED"
    if caution.event_key == key:
        return "CAUTION_SLOT_SELECTED"
    if "good" not in s.slots or s.valence != "good":
        return "NOT_GOOD_SLOT_EVENT"
    # good 자격은 있는데 슬롯에 못 든 경우 — 왜인지 가른다.
    if s.synonym_group and s.synonym_group == good.synonym_group:
        return "SYNONYM_GROUP_CONFLICT"
    if s.domain == good.domain:
        return "DOMAIN_DEDUP"
    return "GOOD_SLOT_ALREADY_FILLED"


def run() -> dict:
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    stage = {k: collections.Counter() for k in TRACKED}
    reasons = {k: collections.Counter() for k in TRACKED}
    blockers = collections.Counter()
    blocker_gap = collections.defaultdict(list)
    cond = {"money_wins": collections.Counter(), "news_wins": collections.Counter()}
    focus_top_work = collections.Counter()

    for i in range(DAYS):
        d = START + dt.timedelta(days=i)
        ctx = M.build_day_context(d)
        board = M.compute_board(ctx, M.load_daily_dicts_for(d))
        finals = {f.ilju: f for f in board.fortunes}
        audits = {a.ilju: a for a in board._headline_audit}

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{d.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            smap = {s.event_key: s for s in scored}
            order = sorted(scored, key=lambda s: -s.probability)
            rank = {s.event_key: r for r, s in enumerate(order, 1)}

            good, caution, support = M._select_slots(scored, seed)
            band = M._band(good, caution)
            cands = M._headline_candidates(good, support, caution, band)
            raw = cands[0] if cands else None
            a = audits[ilju]
            fin = smap.get(a.selected_event_key)

            for k in TRACKED:
                st = stage[k]
                r = rank[k]
                st["rank1"] += r == 1
                st["top3"] += r <= 3
                st["top5"] += r <= 5
                st["good_slot"] += good.event_key == k
                st["support_slot"] += support.event_key == k
                st["caution_slot"] += caution.event_key == k
                st["raw_headline"] += bool(raw and raw.event_key == k)
                st["final_headline"] += a.selected_event_key == k
                if raw and raw.event_key == k and a.selected_event_key != k:
                    st["cap_displaced"] += 1
                if a.selection_reason == "board_domain_cap" and a.selected_event_key == k:
                    st["cap_promoted"] += 1
                reasons[k][_reason(k, smap, good, caution, support, band, cands, raw, fin)] += 1

            # money vs news 조건부
            mp, np_ = smap[MONEY].probability, smap[NEWS].probability
            side = "money_wins" if mp > np_ else ("news_wins" if np_ > mp else None)
            if side:
                w, loser = (MONEY, NEWS) if side == "money_wins" else (NEWS, MONEY)
                c = cond[side]
                c["cards"] += 1
                wr = rank[w]
                c["winner_rank1"] += wr == 1
                c["winner_top3"] += wr <= 3
                c["winner_rank4plus"] += wr >= 4
                c["winner_final_headline"] += a.selected_event_key == w
                _ = loser
                # news 가 money 를 이겼는데 헤드라인이 아닌 카드의 blocker
                if side == "news_wins" and a.selected_event_key != NEWS:
                    top = order[0]
                    if top.event_key != NEWS:
                        blockers[top.event_key] += 1
                        blocker_gap[top.event_key].append(top.probability - np_)

            # focus_flow 가 work 3종 1위인 카드의 전체 위치
            work = sorted(((smap[k].probability, k) for k in
                           ("focus_flow", "praise_recognition", "teamwork_flow")), reverse=True)
            if work[0][1] == FOCUS:
                focus_top_work["cards"] += 1
                focus_top_work["global_rank1"] += rank[FOCUS] == 1
                focus_top_work["global_top3"] += rank[FOCUS] <= 3
                focus_top_work["good_slot"] += good.event_key == FOCUS
                focus_top_work["raw_headline"] += bool(raw and raw.event_key == FOCUS)

    return {
        "cards": DAYS * 60,
        "stages": {k: dict(v) for k, v in stage.items()},
        "exit_reasons": {k: dict(v.most_common()) for k, v in reasons.items()},
        "money_vs_news_conditional": {k: dict(v) for k, v in cond.items()},
        "news_blockers": [
            {"event_key": k, "count": n,
             "mean_gap": round(statistics.mean(blocker_gap[k]), 2)}
            for k, n in blockers.most_common(8)
        ],
        "focus_flow_when_work_top": dict(focus_top_work),
    }


if __name__ == "__main__":
    data = {"audit_id": "OA-7c-S2", "policy_status": "measurement_only",
            "live_behavior_changed": False, "days": DAYS, "result": run()}
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa7c_selection_funnel_90d.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data["result"], ensure_ascii=False, indent=1))
