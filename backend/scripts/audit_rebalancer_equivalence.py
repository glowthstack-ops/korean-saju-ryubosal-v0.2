#!/usr/bin/env python3
"""OA-11a — 선형 cap 모델이 라이브 재배정기와 **동등한가** (측정 전용, 라이브 불변).

exact global oracle 을 세우기 전에 반드시 먼저 답해야 하는 질문이다. 다음만 넣은
MILP 는 exact oracle 이 아니라 relaxed oracle 이다.

    일별 domain count <= cap

`_rebalance_headlines` 가 그 제약과 같은 feasible set 을 표현하는지 확인하지 않고
"exact" 라고 부르면 OA-6f7 의 relaxed oracle 오류를 반복하게 된다.

두 방향을 모두 본다.

    A. MILP 가 feasible 로 본 board → 라이브 재생 → 같은 final board 인가
    B. 라이브가 만든 final board → MILP 제약을 만족하는가

`_rebalance_headlines` 는 **domain cap 만** 다룬다. event cap 완화와 authorized
domain override 는 C10 선택 정책(`daily_selection_policy_shadow`) 계층의 개념이므로
이 감사에서는 측정 대상이 아니다 — 0 이 아니라 `NOT_APPLICABLE` 로 보고한다.
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

import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402
from scipy.sparse import lil_matrix  # noqa: E402

import saju_engines.daily_ilju_fortune as M  # noqa: E402
from saju_engines.daily_selection_policy_shadow import strength_band  # noqa: E402
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

BUDGET = 7
#: 라이브 상수를 그대로 쓴다 — 감사가 자체 값을 들고 있으면 조용히 어긋난다.
_DOMAIN_CAP = M._DOMAIN_HEADLINE_CAP
_ILJUS = [f"{ganzi_from_index(i)[0].value}{ganzi_from_index(i)[1].value}" for i in range(60)]


def _band_ok(top_p: int, alt_p: int) -> bool:
    tb, ab = strength_band(top_p), strength_band(alt_p)
    return ab >= tb or (tb != 4 and tb - ab < 2)


def card_options(
    scored: list, seed: str, events: dict
) -> list[dict[str, Any]]:
    """이 카드에서 도달 가능한 good 대표 선택지 전수.

    자유도는 good 대표 하나뿐이다 — `_select_slots` 가 support·caution 을 good 의
    함수로 정한다. good 슬롯 자격은 `headline_slots` 가 아니라 `slots` 로 판정한다.
    """
    goods = sorted(
        (s for s in scored if s.valence == "good" and "good" in events[s.event_key]["slots"]),
        key=lambda x: -x.probability,
    )
    if not goods:
        return []
    top = goods[0]
    rows: list[dict[str, Any]] = []
    for g in goods:
        loss = top.probability - g.probability
        if loss > BUDGET or not _band_ok(top.probability, g.probability):
            continue
        good, caution, support = M._select_slots(scored, seed, good_override=g.event_key)
        if good.event_key != g.event_key:
            continue   # 의도한 대표가 슬롯 자격이 없어 무효화됨
        cands = M._headline_candidates(good, support, caution, M._band(good, caution))
        rows.append({
            "good": good.event_key,
            "candidates": cands,                 # 라이브 재생에 그대로 넘긴다
            "raw_headline": cands[0].event_key,
            "raw_headline_domain": cands[0].domain,
            "realized_loss": loss,
        })
    return rows


def day_options(day: dt.date, events: dict) -> dict[str, list[dict[str, Any]]]:
    """하루치 60일주의 선택지."""
    ctx = M.build_day_context(day)
    out: dict[str, list[dict[str, Any]]] = {}
    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        ilju = f"{stem.value}{branch.value}"
        seed = f"{day.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"
        scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
        out[ilju] = card_options(scored, seed, events)
    return out


def solve_cap_model(
    options: dict[str, list[dict[str, Any]]], limit: int, *, top_only: bool
) -> dict[str, tuple[int, int]] | None:
    """선형 cap 모델.

    Args:
        options: 일주 → good 대표 선택지.
        limit: 도메인 점유 상한.
        top_only: True 면 헤드라인을 각 행의 **raw 1위**로 고정한다(초판 모델).
            False 면 카드 안의 헤드라인 후보까지 자유 변수로 둔다.

    `top_only=True` 는 오라클로 쓸 수 없다 — 라이브 재배정기는 상한을 지키려고
    카드 안에서 하위 후보로 **강등**하는데, 그 자유도가 모델에 없어서 라이브가
    멀쩡히 만들어내는 board 를 infeasible 로 판정한다(상계가 아니다).

    Returns:
        일주 → (행 인덱스, 후보 인덱스). 불가능하면 None.
    """
    iljus = [i for i in _ILJUS if options.get(i)]
    flat = [
        (i, r, k)
        for i in iljus
        for r in range(len(options[i]))
        for k in range(1 if top_only else len(options[i][r]["candidates"]))
    ]
    pos = {key: n for n, key in enumerate(flat)}
    n = len(flat)
    domains = sorted(
        options[i][r]["candidates"][k].domain for i, r, k in flat
    )
    domains = sorted(set(domains))

    # 카드마다 정확히 하나.
    a_card = lil_matrix((len(iljus), n))
    row_of = {i: m for m, i in enumerate(iljus)}
    for i, r, k in flat:
        a_card[row_of[i], pos[(i, r, k)]] = 1
    # 도메인 상한 — **선택된 헤드라인 후보**의 도메인 기준.
    a_dom = lil_matrix((len(domains), n))
    dom_row = {d: m for m, d in enumerate(domains)}
    for i, r, k in flat:
        a_dom[dom_row[options[i][r]["candidates"][k].domain], pos[(i, r, k)]] = 1

    cons = [
        LinearConstraint(a_card.tocsr(), 1, 1),
        LinearConstraint(a_dom.tocsr(), 0, limit),
    ]
    # 목적: 실현 손실 최소화.
    c = np.array([options[i][r]["realized_loss"] for i, r, _k in flat], dtype=float)
    res = milp(c=c, constraints=cons, integrality=np.ones(n), bounds=Bounds(0, 1))
    if not res.success:
        return None
    x = np.round(res.x).astype(int)
    return {i: (r, k) for (i, r, k), v in zip(flat, x, strict=True) if v == 1}


def live_replay(
    options: dict[str, list[dict[str, Any]]], pick: dict[str, tuple[int, int]], limit: int
) -> tuple[dict[str, str], int]:
    """선택된 good 대표로 라이브 재배정기를 그대로 돌린다."""
    decisions = {i: options[i][r]["candidates"] for i, (r, _k) in pick.items()}
    order = [i for i in _ILJUS if i in decisions]
    selected, _reasons, unresolved = M._rebalance_headlines(decisions, order, _DOMAIN_CAP)
    assert limit == max(1, int(len(order) * _DOMAIN_CAP))
    return {i: e.event_key for i, e in selected.items()}, unresolved


def audit_day(day: dt.date, events: dict) -> dict[str, Any]:
    """한 날짜의 양방향 동등성."""
    options = day_options(day, events)
    live_iljus = [i for i in _ILJUS if options.get(i)]
    limit = max(1, int(len(live_iljus) * _DOMAIN_CAP))

    # ── B. 라이브 → MILP: 라이브 기본 선택(각 카드 raw 1위)의 결과가 cap 을 만족하는가
    base_pick = {i: (0, 0) for i in live_iljus}
    live_final, live_unresolved = live_replay(options, base_pick, limit)
    dom_of = {
        o["candidates"][k].event_key: o["candidates"][k].domain
        for i in live_iljus for o in options[i] for k in range(len(o["candidates"]))
    }
    final_counts = collections.Counter(dom_of[e] for e in live_final.values())
    live_violates_cap = sum(max(0, n - limit) for n in final_counts.values())

    # ── A. MILP → 라이브: cap 모델이 고른 board 를 재생하면 같은 board 인가
    top_pick = solve_cap_model(options, limit, top_only=True)
    milp_pick = solve_cap_model(options, limit, top_only=False)
    a_row: dict[str, Any] = {
        "top_only_model_feasible": top_pick is not None,
        "milp_feasible": milp_pick is not None,
    }
    if milp_pick is not None:
        assumed = {
            i: options[i][r]["candidates"][k].event_key
            for i, (r, k) in milp_pick.items()
        }
        replayed, replay_unresolved = live_replay(options, milp_pick, limit)
        mismatch = [i for i in assumed if assumed[i] != replayed[i]]
        a_row.update({
            "final_headline_mismatch": len(mismatch),
            "mismatch_iljus": mismatch[:5],
            "replay_unresolved": replay_unresolved,
            "milp_loss_sum": sum(
                options[i][r]["realized_loss"] for i, (r, _k) in milp_pick.items()
            ),
        })

    top_pick_infeasible = top_pick is None
    return {
        "date": day.isoformat(),
        "domain_limit": limit,
        "options_per_card_mean": round(
            sum(len(options[i]) for i in live_iljus) / max(1, len(live_iljus)), 2
        ),
        "options_per_card_max": max(len(options[i]) for i in live_iljus),
        "cards_with_single_option": sum(1 for i in live_iljus if len(options[i]) == 1),
        # B 방향
        "live_unresolved_overflow": live_unresolved,
        # 라이브 결과가 모델의 feasible 점인가 — 상계 자격의 최소 조건이다.
        "live_board_is_milp_feasible": live_violates_cap == 0,
        "live_feasible_top_only_model_infeasible": int(
            live_violates_cap == 0 and top_pick_infeasible
        ),
        "live_cap_excess": live_violates_cap,
        # A 방향
        **a_row,
        # 이 계층에 존재하지 않는 개념 — 0 으로 보고하면 "확인했다"로 읽힌다.
        "event_cap_relaxation_mismatch": "NOT_APPLICABLE_AT_THIS_LAYER",
        "authorized_override_mismatch": "NOT_APPLICABLE_AT_THIS_LAYER",
    }


def run(days: list[dt.date]) -> dict[str, Any]:
    events = M.load_daily_dicts().catalog["events"]
    rows = [audit_day(d, events) for d in days]
    equivalent = all(
        r.get("final_headline_mismatch") == 0
        and r["live_feasible_top_only_model_infeasible"] == 0
        and r["milp_feasible"]
        for r in rows
    )
    return {
        "days": rows,
        "verdict": (
            "LINEAR_CAP_MODEL_EQUIVALENT_TO_LIVE_REBALANCER"
            if equivalent
            else "CAP_CONSTRAINED_RELAXED_ORACLE"
        ),
        "note": (
            "`_rebalance_headlines` 는 domain cap 만 다루며, 유효 대안이 없으면 초과를 "
            "허용한다(조건부 제약). event cap 완화·authorized domain override 는 C10 "
            "선택 정책 계층의 개념이라 이 감사에서 측정 대상이 아니다."
        ),
    }


if __name__ == "__main__":
    targets = [
        dt.date(2026, 7, 30),    # authorized domain override 가 기록된 날
        dt.date(2026, 8, 3),
        dt.date(2026, 8, 12),
        dt.date(2026, 8, 28),
        dt.date(2027, 3, 3),     # 실패창 시작
        dt.date(2026, 4, 2),     # 통과창 시작
    ]
    result = run(targets)
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa11a_rebalancer_equivalence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({
            "audit_id": "OA-11a",
            "policy_status": "measurement_only",
            "live_behavior_changed": False,
            "measurement_stage": "final_headline",
            "result": result,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[ok]", out.name)
    for r in result["days"]:
        print(f"  {r['date']} limit={r['domain_limit']} "
              f"선택지/카드 평균 {r['options_per_card_mean']} 최대 {r['options_per_card_max']} "
              f"단일 {r['cards_with_single_option']}/60")
        print(f"    live 미해소 초과 {r['live_unresolved_overflow']} · "
              f"라이브 board 가 모델 feasible {r['live_board_is_milp_feasible']}")
        print(f"    top-only 모델 feasible {r['top_only_model_feasible']} → "
              f"라이브는 되는데 모델은 불가 {r['live_feasible_top_only_model_infeasible']}")
        print(f"    후보자유 모델 feasible {r['milp_feasible']} · "
              f"MILP→live 헤드라인 불일치 {r.get('final_headline_mismatch')} "
              f"{r.get('mismatch_iljus', '')}")
    print("  판정:", result["verdict"])
