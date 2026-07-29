#!/usr/bin/env python3
"""OA-11d — S0/S1/S2 인과적 배분 비교 + 차단 사유 깔때기 (측정 전용, 라이브 불변).

질문은 더 이상 "낮은 순위 헤드라인을 골라야 하는가"가 아니다(OA-11c 에서 기각).
**C10 이 그날 이미 존재하는 합법적인 top-1 신규 family 후보를 왜 선택하지 않는가**다.

    S0  현재 C10 — 실제 날짜순 history, 현재 `_longterm_key`, coverage floor,
        band·loss 보호, 실제 card pipeline, 실제 board rebalance.
    S1  인과적 family-deficit 우선 — 미래를 보지 않는다. 당일 합법 good 후보를
        **실제 card pipeline 에 넣어** top-1 헤드라인 family 를 구하고, 최근 90일
        final family 에 없는 것을 우선한다.
    S2  S1 + board 이후 결과 확인 — 신규 family 가 board rebalance 를 넘어 실제로
        살아남는지까지 본다.

세 정책이 같은 날짜에 **같은 카드 선택지 열거를 공유**한다(1 패스). 정책마다 자기
history 만 따로 들고 간다.

안전 가드(s5 하락 금지 · 7p 예산 · valence 불변 · headline eligibility · slot 계약)는
S1/S2 에서도 그대로 지킨다. 완화 counterfactual 은 이 감사에서 하지 않는다.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
for _p in (_BACKEND / "packages" / "saju_engines", _BACKEND / "packages" / "shared_types"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    SEVERITY_CLEAN,
    HeadlineCandidate,
    SelectionPolicy,
    repeat_severity,
    select_board,
    select_good_representative,
    strength_band,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

LOOKBACK, BUDGET, TARGET, FLOOR = 90, 7, 15, 16
QUALIFY_MIN = 55
WARMUP = 90
_DOMAIN_CAP, _EVENT_CAP = 0.30, 0.25
#: 라이브 board 정책과 동일(OA-10b 와 같은 값).
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True,
                         recency_rotation=True)
_ILJUS = [f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)]

# ── 차단 사유 ─────────────────────────────────────────────────────────────
RECOVERY_NOT_ACTIVE = "RECOVERY_NOT_ACTIVE"
RAW_TOP_CLEAN_SHORT_CIRCUIT = "RAW_TOP_CLEAN_SHORT_CIRCUIT"
NO_REALIZED_NEW_FAMILY_CANDIDATE = "NO_REALIZED_NEW_FAMILY_CANDIDATE"
NEW_FAMILY_AVAILABLE_BUT_NOT_SELECTED = "NEW_FAMILY_AVAILABLE_BUT_NOT_SELECTED"
LOSS_BUDGET_BLOCKED = "LOSS_BUDGET_BLOCKED"
EXCEPTIONAL_BAND_BLOCKED = "EXCEPTIONAL_BAND_BLOCKED"
INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE = "INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE"
CARD_TOP1_DID_NOT_ADD_FAMILY = "CARD_TOP1_DID_NOT_ADD_FAMILY"
BOARD_REBALANCE_REMOVED_GAIN = "BOARD_REBALANCE_REMOVED_GAIN"
GAIN_REALIZED = "GAIN_REALIZED"


@dataclass
class PolicyState:
    """한 정책의 날짜순 상태 — 정책끼리 history 를 공유하지 않는다."""

    name: str
    headline_history: dict[str, list[str]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    good_history: dict[str, list[str]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    losses: list[int] = field(default_factory=list)
    rep_changed: int = 0
    rep_total: int = 0
    band_downgrades: int = 0
    s5_drops: int = 0
    reasons: collections.Counter = field(default_factory=collections.Counter)
    gains_realized: int = 0
    gains_lost_at_board: int = 0


def _coverage(state: PolicyState, ilju: str, family_of: dict[str, str]) -> int:
    recent = state.headline_history[ilju][-LOOKBACK:]
    return len({family_of.get(k, k) for k in recent})


def _recent_families(state: PolicyState, ilju: str, family_of: dict[str, str]) -> set[str]:
    return {family_of.get(k, k) for k in state.headline_history[ilju][-LOOKBACK:]}


def _legal_options(
    scored: list, seed: str, events: dict, top_key: str, top_p: int
) -> list[dict[str, Any]]:
    """당일 합법 good 대표 선택지 — 안전 가드를 모두 지킨 것만.

    good 슬롯 자격은 `slots` 로 본다(`_select_slots` 가 그렇게 한다). 의도한 대표가
    슬롯에서 무효화되면 그 후보는 애초에 존재하지 않는 것으로 센다.
    """
    out: list[dict[str, Any]] = []
    top_band = strength_band(top_p)
    for s in scored:
        if s.valence != "good" or "good" not in events[s.event_key]["slots"]:
            continue
        loss = top_p - s.probability
        if loss < 0 or loss > BUDGET:
            continue
        band = strength_band(s.probability)
        if top_band == 4 and band < top_band:
            continue          # s5 하락 금지
        if top_band - band >= 2:
            continue          # 2밴드 하락 금지
        g, c, sup = M._select_slots(scored, seed, good_override=s.event_key)
        if g.event_key != s.event_key:
            continue          # slot 에서 무효화 — 선택지가 아니다
        cands = M._headline_candidates(g, sup, c, M._band(g, c))
        out.append({
            "key": s.event_key, "probability": s.probability, "loss": loss,
            "band": band, "supporting_groups": s.supporting_groups,
            "candidates": cands, "card_top1": cands[0].event_key,
        })
    return out


def _s1_choose(
    options: list[dict[str, Any]], recent_fams: set[str], family_of: dict[str, str],
    in_deficit: bool, top_key: str,
) -> tuple[dict[str, Any] | None, str]:
    """S1 — 실현 기준 신규 family 를 추가하는 후보를 우선한다(미래 미참조)."""
    if not options:
        return None, NO_REALIZED_NEW_FAMILY_CANDIDATE
    if not in_deficit:
        return None, RECOVERY_NOT_ACTIVE
    gaining = [
        o for o in options
        if family_of.get(o["card_top1"], o["card_top1"]) not in recent_fams
    ]
    if not gaining:
        return None, NO_REALIZED_NEW_FAMILY_CANDIDATE
    # 실현 이득 → 손실 최소 → band 유지 → supporting groups → 안정 정렬.
    chosen = min(
        gaining,
        key=lambda o: (o["loss"], -o["band"], -o["supporting_groups"], o["key"]),
    )
    if chosen["key"] == top_key:
        return chosen, CARD_TOP1_DID_NOT_ADD_FAMILY   # 원시 1위가 이미 이득을 낸다
    return chosen, GAIN_REALIZED


def run(anchors: list[dt.date]) -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in tax.items()}

    start = min(anchors) - dt.timedelta(days=WARMUP)
    end = max(anchors) + dt.timedelta(days=89)
    states = {n: PolicyState(n) for n in ("S0", "S1", "S2")}
    snaps: dict[str, dict[str, dict[str, int]]] = collections.defaultdict(dict)
    anchor_set = {a.isoformat() for a in anchors}

    day = start
    while day <= end:
        ctx = M.build_day_context(day)
        # 정책별 이번 날의 board 입력
        raw = {n: {} for n in states}
        cmap = {n: {} for n in states}
        pending_gain: dict[str, dict[str, str]] = {n: {} for n in states}

        for idx in range(60):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
            scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
            head_goods = [
                (s.event_key, s.probability) for s in scored
                if s.valence == "good"
                and "good" in (events[s.event_key].get("headline_slots")
                               or events[s.event_key]["slots"])
            ]
            if not head_goods:
                continue
            ranked = sorted(head_goods, key=lambda x: (-x[1], x[0]))
            top_key, top_p = ranked[0]
            options = _legal_options(scored, seed, events, top_key, top_p)

            for name, st in states.items():
                if name == "S0":
                    rep = select_good_representative(
                        head_goods, st.good_history[ilju], BUDGET, policy=C10_POLICY,
                        family_of=family_of, headline_history=st.headline_history[ilju],
                    )
                    pick = rep.display_good_representative
                    loss = rep.display_displacement_loss
                    # 차단 사유 — 원시 1위가 clean 이면 C10 은 즉시 반환한다.
                    cov = _coverage(st, ilju, family_of)
                    if cov < FLOOR:
                        fams = _recent_families(st, ilju, family_of)
                        gaining = [
                            o for o in options
                            if family_of.get(o["card_top1"], o["card_top1"]) not in fams
                        ]
                        if not gaining:
                            st.reasons[NO_REALIZED_NEW_FAMILY_CANDIDATE] += 1
                        elif pick in {o["key"] for o in gaining}:
                            st.reasons[GAIN_REALIZED] += 1
                        elif repeat_severity(
                            st.good_history[ilju], top_key
                        ) == SEVERITY_CLEAN:
                            st.reasons[RAW_TOP_CLEAN_SHORT_CIRCUIT] += 1
                        else:
                            st.reasons[NEW_FAMILY_AVAILABLE_BUT_NOT_SELECTED] += 1
                    else:
                        st.reasons[RECOVERY_NOT_ACTIVE] += 1
                else:
                    cov = _coverage(st, ilju, family_of)
                    fams = _recent_families(st, ilju, family_of)
                    chosen, why = _s1_choose(
                        options, fams, family_of, cov < FLOOR, top_key
                    )
                    st.reasons[why] += 1
                    if chosen is None:
                        rep = select_good_representative(
                            head_goods, st.good_history[ilju], BUDGET,
                            policy=C10_POLICY, family_of=family_of,
                            headline_history=st.headline_history[ilju],
                        )
                        pick, loss = (
                            rep.display_good_representative, rep.display_displacement_loss
                        )
                    else:
                        pick, loss = chosen["key"], chosen["loss"]
                        if why == GAIN_REALIZED:
                            pending_gain[name][ilju] = family_of.get(
                                chosen["card_top1"], chosen["card_top1"]
                            )

                g, c, sup = M._select_slots(scored, seed, good_override=pick)
                if g.event_key != pick:
                    st.reasons[INTENDED_REPRESENTATIVE_NOT_SLOT_FEASIBLE] += 1
                cands = M._headline_candidates(g, sup, c, M._band(g, c))
                cmap[name][ilju] = [
                    HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
                ]
                raw[name][ilju] = cmap[name][ilju][0]
                st.good_history[ilju].append(g.event_key)
                st.losses.append(loss)
                st.rep_total += 1
                if g.event_key != top_key:
                    st.rep_changed += 1
                nb, tb = strength_band(g.probability), strength_band(top_p)
                if nb < tb:
                    st.band_downgrades += 1
                    if tb == 4:
                        st.s5_drops += 1

        for name, st in states.items():
            if not raw[name]:
                continue
            r = select_board(
                raw[name], cmap[name], st.headline_history, domain_cap=_DOMAIN_CAP,
                event_cap=_EVENT_CAP, max_displacement_cost=BUDGET, policy=_BOARD,
                today=day.toordinal(),
            )
            for ilju, sel in r.selections.items():
                fam = family_of.get(sel.event_key, sel.event_key)
                want = pending_gain[name].get(ilju)
                if want is not None:
                    if fam == want:
                        st.gains_realized += 1
                    else:
                        st.gains_lost_at_board += 1
                        st.reasons[BOARD_REBALANCE_REMOVED_GAIN] += 1
                st.headline_history[ilju].append(sel.event_key)

        iso = day.isoformat()
        if iso in anchor_set:
            for name, st in states.items():
                snaps[iso][name] = {
                    ilju: len({
                        family_of.get(k, k)
                        for k in st.headline_history[ilju][-LOOKBACK:]
                    })
                    for ilju in _ILJUS
                }
        day += dt.timedelta(days=1)

    # anchor 별 결과 — snapshot 은 anchor 시점의 직전 90일 coverage 다.
    out: dict[str, Any] = {}
    for iso in sorted(snaps):
        out[iso] = {}
        for name in states:
            vals = sorted(snaps[iso][name].values())
            out[iso][name] = {
                "qualifying_iljus": sum(1 for v in vals if v >= TARGET),
                "family_p10": vals[5], "family_min": vals[0],
            }
    summary = {}
    for name, st in states.items():
        summary[name] = {
            "representative_change_rate_pct": round(
                100 * st.rep_changed / max(1, st.rep_total), 2
            ),
            "realized_loss_mean": round(statistics.mean(st.losses), 3),
            "realized_loss_p90": sorted(st.losses)[int(len(st.losses) * 0.9)],
            "band_downgrades": st.band_downgrades,
            "s5_drops": st.s5_drops,
            "gains_realized": st.gains_realized,
            "gains_lost_at_board": st.gains_lost_at_board,
            "block_reasons": dict(st.reasons.most_common()),
        }
    return {"anchors": out, "policy_summary": summary}


if __name__ == "__main__":
    anchors = [dt.date.fromisoformat(a) for a in sys.argv[1:]] or [
        dt.date(2026, 4, 2), dt.date(2027, 3, 3), dt.date(2027, 6, 1),
        dt.date(2027, 8, 5), dt.date(2027, 10, 9),
    ]
    result = run(anchors)
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11d_causal_family_deficit.json"
    out.write_text(
        json.dumps({
            "audit_id": "OA-11d",
            "policy_status": "measurement_only",
            "live_behavior_changed": False,
            "measurement_stage": "final_headline",
            "result": result,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for iso, row in result["anchors"].items():
        print(f"  {iso}")
        for name in ("S0", "S1", "S2"):
            r = row[name]
            print(f"    {name} 자격 {r['qualifying_iljus']}/60 · p10 {r['family_p10']} "
                  f"· min {r['family_min']}")
    for name, s in result["policy_summary"].items():
        print(f"  {name} 대표 변경률 {s['representative_change_rate_pct']}% · "
              f"손실 평균 {s['realized_loss_mean']} p90 {s['realized_loss_p90']} · "
              f"s5 하락 {s['s5_drops']}")
        for k, v in list(s["block_reasons"].items())[:8]:
            print(f"      {k:46} {v}")
