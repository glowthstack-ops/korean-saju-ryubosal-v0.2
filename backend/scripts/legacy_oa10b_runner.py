#!/usr/bin/env python3
"""OA-10b characterization baseline — **동결본**. 리팩터링 대상이 아니다.

`audit_rolling_window.build_schedule` 을 그대로 옮겨 온 뒤, **관측만** 덧붙였다.
공용 runner 를 추출하는 동안 이 파일이 "현재 C10 이 실제로 무엇을 만드는가"의
기준선이 된다.

parity 가 끝날 때까지 이 파일에 하면 안 되는 것:

    · `build_daily_schedule()` 호출로 교체
    · 새 공용 state reducer / contract resolver 사용
    · S1/S2 용 helper 공유
    · reason code·후보 순서 정규화

관측 훅은 선택 거동을 바꾸지 않는다. `verify_observation_is_non_perturbing()` 이
원본 스크립트의 `build_schedule` 과 최종 headline_history 가 완전히 같은지 확인해
그 사실을 증명한다 — 계측이 결과를 움직이면 기준선 자체가 무의미해진다.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
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
from saju_engines.daily_board_constraints import HeadlineCandidate, cap_count  # noqa: E402
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

# ── 동결된 계약값 (audit_rolling_window.py 와 동일) ───────────────────────
WARMUP_DAYS = 180
WINDOW = LONGITUDINAL_HISTORY_LOOKBACK_DAYS          # 90
FIRST_ANCHOR = dt.date(2026, 1, 1)
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP, _BUDGET = cap_count(60, 0.35), 10, 7


def schedule_start() -> dt.date:
    """생성 시작일 — 첫 anchor 의 창(D-90)보다 warm-up 만큼 더 앞."""
    return FIRST_ANCHOR - dt.timedelta(days=WARMUP_DAYS + WINDOW)


@dataclass
class LegacyObservation:
    """관측 결과 — 선택 거동에 영향을 주지 않는다."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    daily_state: list[dict[str, str]] = field(default_factory=list)
    headline_history: dict[str, list[str]] = field(default_factory=dict)


def _fp(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_schedule_observed(
    family_of: dict[str, str], *, days: int, observe: bool = True
) -> LegacyObservation:
    """동결된 legacy 루프 + 관측.

    Args:
        family_of: event_key → semantic family.
        days: 생성 일수(schedule_start 부터).
        observe: False 면 행·state 를 수집하지 않는다(비계측 대조용).

    Returns:
        관측 결과. `headline_history` 는 계측 여부와 무관하게 같아야 한다.
    """
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)
    obs = LegacyObservation()

    day = schedule_start()
    for _ in range(days):
        ctx = M.build_day_context(day)
        raw: dict[str, HeadlineCandidate] = {}
        cmap: dict[str, list[HeadlineCandidate]] = {}
        pending: dict[str, dict[str, Any]] = {}
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
                goods, good_history[ilju], _BUDGET, policy=C10_POLICY,
                family_of=family_of, headline_history=headline_history[ilju],
            )
            g, c, s = M._select_slots(
                scored, seed, good_override=rep.display_good_representative
            )
            cands = M._headline_candidates(g, s, c, M._band(g, c))
            cmap[ilju] = [
                HeadlineCandidate(x.event_key, x.domain, x.probability) for x in cands
            ]
            raw[ilju] = cmap[ilju][0]
            # 현재 C10 계약: 반복 판정 이력에 **의도한** 대표를 기록한다.
            good_history[ilju].append(rep.display_good_representative)
            if observe:
                pending[ilju] = {
                    "fortune_date": day.isoformat(),
                    "ilju": ilju,
                    "raw_good_winner": rep.raw_good_winner,
                    "intended_good_representative": rep.display_good_representative,
                    "realized_good_event": g.event_key,
                    "support_event": s.event_key,
                    "caution_event": c.event_key,
                    "raw_headline": cands[0].event_key,
                    "selection_reason_codes": [rep.good_selection_reason],
                    "display_displacement_loss": rep.display_displacement_loss,
                }
        r = select_board(
            raw, cmap, headline_history, domain_cap=_DOMAIN_CAP, event_cap=_EVENT_CAP,
            max_displacement_cost=_BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        for ilju, sel in r.selections.items():
            headline_history[ilju].append(sel.event_key)
            if observe:
                row = pending[ilju]
                row["final_headline"] = sel.event_key
                row["final_headline_family"] = family_of.get(
                    sel.event_key, sel.event_key
                )
                obs.rows.append(row)
        if observe:
            obs.daily_state.append({
                "fortune_date": day.isoformat(),
                "intended_history_fp": _fp(
                    {k: good_history[k] for k in sorted(good_history)}
                ),
                "final_headline_history_fp": _fp(
                    {k: headline_history[k] for k in sorted(headline_history)}
                ),
                "board_fp": _fp(
                    [[i, r.selections[i].event_key] for i in sorted(r.selections)]
                ),
            })
        day += dt.timedelta(days=1)
    obs.headline_history = dict(headline_history)
    return obs


def verify_observation_is_non_perturbing(
    family_of: dict[str, str], *, days: int
) -> bool:
    """계측이 선택 거동을 바꾸지 않았는지 증명한다."""
    a = build_schedule_observed(family_of, days=days, observe=True)
    b = build_schedule_observed(family_of, days=days, observe=False)
    return a.headline_history == b.headline_history


def load_family_map() -> dict[str, str]:
    tax = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    return {k: t["semantic_family"] for k, t in tax.items()}


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else WARMUP_DAYS + WINDOW + 90
    family_of = load_family_map()
    obs = build_schedule_observed(family_of, days=days)
    payload = {
        "audit_id": "OA-10b-characterization",
        "status": "FROZEN_BASELINE",
        "note": (
            "공용 runner parity 의 기준선. 이 파일은 리팩터링 대상이 아니며 공용 "
            "코드를 공유하지 않는다."
        ),
        "contract": {
            "origin": schedule_start().isoformat(),
            "warmup_days": WARMUP_DAYS,
            "window": WINDOW,
            "domain_cap_count": _DOMAIN_CAP,
            "event_cap_count": _EVENT_CAP,
            "budget": _BUDGET,
            "repeat_history_source": "INTENDED_GOOD",
            "days_generated": days,
        },
        "row_count": len(obs.rows),
        "rows_fingerprint": _fp(obs.rows),
        "daily_state_fingerprint": _fp(obs.daily_state),
        "final_state_fingerprint": _fp(
            {k: obs.headline_history[k] for k in sorted(obs.headline_history)}
        ),
        "daily_state": obs.daily_state,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa10b_characterization.json"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows_out = _BACKEND / "compiled" / "oa10b_characterization_rows.jsonl"
    with rows_out.open("w", encoding="utf-8") as fh:
        for row in obs.rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("[ok]", out.name, "·", rows_out.name)
    print(f"  행 {len(obs.rows)} · 날짜 {len(obs.daily_state)}")
    print(f"  rows_fp        {payload['rows_fingerprint'][:16]}")
    print(f"  daily_state_fp {payload['daily_state_fingerprint'][:16]}")
    print(f"  final_state_fp {payload['final_state_fingerprint'][:16]}")
