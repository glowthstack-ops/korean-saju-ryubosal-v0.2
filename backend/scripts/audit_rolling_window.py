"""OA-10b — 일별 rolling 90일 창 검증 (측정 전용, 라이브 불변).

단일 anchor 판정은 폐기한다. 같은 정책이 anchor 에 따라 key/family p10 14↔15 로
갈린다면, C10 은 **시간축 전체에서 안정적인 정책으로 아직 증명되지 않은 상태**다.

    정책        C10 90일 계약
    warm-up     최초 anchor 이전 180일
    측정        매일 anchor · 각 anchor D 의 창 = D-90 ~ D-1

anchor 마다 상태를 초기화하지 않는다 — **하나의 날짜순 canonical schedule 을 연속
재생**하고 각 날짜에서 직전 90일 창을 평가한다. 정책의 기억 길이가 90일이므로,
충분한 warm-up 이후에는 독립 bootstrap 과 같은 결과가 나와야 한다(회귀로 확인).

가장 유력한 가설은 **사건 만료**다. 오늘 coverage 16 이라 회복 모드가 꺼져 있는데
내일 유일하게 한 번 등장한 family 가 창 밖으로 빠지면 15 로 내려가고, 그날 새 family
를 고를 기회가 없으면 이후 14 까지 떨어진다. 그래서 만료 예정까지 함께 센다.
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
from saju_engines.daily_canonical_bootstrap import C10_POLICY  # noqa: E402
from saju_engines.daily_selection_policy_shadow import (  # noqa: E402
    LONGITUDINAL_HISTORY_LOOKBACK_DAYS,
    SelectionPolicy,
    select_board,
    select_good_representative,
)
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index  # noqa: E402

WARMUP_DAYS = 180
WINDOW = LONGITUDINAL_HISTORY_LOOKBACK_DAYS          # 90
FIRST_ANCHOR = dt.date(2026, 1, 1)
ANCHOR_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 730
_BOARD = SelectionPolicy(global_swap=True, severity_tiers=True, recency_rotation=True)
_DOMAIN_CAP, _EVENT_CAP, _BUDGET = cap_count(60, 0.35), 10, 7
_P10 = 5                                              # 60개 중 6번째로 작은 값
_TARGET = 15
#: coverage 회복 모드가 켜지는 문턱(C10). 만료 분석의 기준선.
_RECOVERY_TARGET = 16


def _schedule_start() -> dt.date:
    """생성 시작일 — 첫 anchor 의 창(D-90)보다 warm-up 만큼 더 앞."""
    return FIRST_ANCHOR - dt.timedelta(days=WARMUP_DAYS + WINDOW)


def build_schedule(family_of: dict[str, str]) -> dict[str, list[str]]:
    """연속 canonical schedule 을 날짜순으로 생성한다.

    Returns:
        일주 → 날짜순 final headline 목록(생성 시작일부터).
    """
    dicts = M.load_daily_dicts()
    events = dicts.catalog["events"]
    headline_history: dict[str, list[str]] = collections.defaultdict(list)
    good_history: dict[str, list[str]] = collections.defaultdict(list)

    total = WARMUP_DAYS + WINDOW + ANCHOR_DAYS
    day = _schedule_start()
    for _ in range(total):
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
            good_history[ilju].append(rep.display_good_representative)
        r = select_board(
            raw, cmap, headline_history, domain_cap=_DOMAIN_CAP, event_cap=_EVENT_CAP,
            max_displacement_cost=_BUDGET, policy=_BOARD, today=day.toordinal(),
        )
        for ilju, sel in r.selections.items():
            headline_history[ilju].append(sel.event_key)
        day += dt.timedelta(days=1)
    return dict(headline_history)


def _expiry_profile(window: list[str], family_of: dict[str, str]) -> dict[str, int]:
    """창 안 family 의 만료 예정. index 0 = 가장 오래된 날(D-90)."""
    last_seen: dict[str, int] = {}
    for i, key in enumerate(window):
        last_seen[family_of.get(key, key)] = i
    return last_seen


def run() -> dict[str, Any]:
    taxonomy = json.loads(
        (_BACKEND / "dictionaries" / "daily_fortune" / "daily_event_taxonomy.json")
        .read_text(encoding="utf-8")
    )["events"]
    family_of = {k: t["semantic_family"] for k, t in taxonomy.items()}
    events = M.load_daily_dicts().catalog["events"]

    schedule = build_schedule(family_of)
    offset = WARMUP_DAYS          # 첫 anchor 창(D-90)의 시작 인덱스
    daily: list[dict[str, Any]] = []
    below_counter = collections.Counter()
    expiry_at_risk = 0
    expired_without_replacement = 0

    for a in range(ANCHOR_DAYS):
        anchor = FIRST_ANCHOR + dt.timedelta(days=a)
        lo, hi = offset + a, offset + a + WINDOW
        keys, fams, doms = [], [], []
        below: list[str] = []
        risk = 0
        for ilju, series in schedule.items():
            w = series[lo:hi]
            uk = len(set(w))
            uf = len({family_of.get(e, e) for e in set(w)})
            keys.append(uk)
            fams.append(uf)
            doms.append(len({events[e]["domain"] for e in set(w)}))
            if uk < _TARGET:
                below.append(ilju)
                below_counter[ilju] += 1
            # 만료 위험: 오늘 coverage 는 문턱 이상이나 7일 내 만료로 목표 아래가 된다
            last_seen = _expiry_profile(w, family_of)
            projected = sum(1 for v in last_seen.values() if v >= 7)
            if uf >= _RECOVERY_TARGET and projected < _TARGET:
                risk += 1
        expiry_at_risk += risk
        kp, fp, dp = sorted(keys)[_P10], sorted(fams)[_P10], sorted(doms)[_P10]
        daily.append({
            "anchor_date": anchor.isoformat(),
            "key_p10": kp, "family_p10": fp, "domain_p10": dp,
            "count_below_15": len(below),
            "count_equal_14": sum(1 for k in keys if k == 14),
            "bottom_6_iljus": sorted(below)[:6],
            "expiry_at_risk_iljus": risk,
            "passes": kp >= _TARGET and fp >= _TARGET,
        })

    passing = [d for d in daily if d["passes"]]
    # 연속 실패 episode
    episodes: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    for d in daily:
        if d["passes"]:
            if cur:
                episodes.append(cur)
                cur = []
        else:
            cur.append(d)
    if cur:
        episodes.append(cur)

    episode_rows = [
        {
            "episode_start": e[0]["anchor_date"],
            "episode_end": e[-1]["anchor_date"],
            "duration_days": len(e),
            "minimum_key_p10": min(x["key_p10"] for x in e),
            "affected_iljus": sorted({i for x in e for i in x["bottom_6_iljus"]}),
        }
        for e in episodes
    ]
    # 14 → 15 → 14 진동
    seq = [d["key_p10"] for d in daily]
    oscillation = sum(
        1 for i in range(len(seq) - 2)
        if seq[i] < _TARGET <= seq[i + 1] and seq[i + 2] < _TARGET
    )
    by_month = collections.Counter(
        d["anchor_date"][:7] for d in daily if not d["passes"]
    )
    return {
        "measurement_stage": "display_pipeline",
        "protocol": {
            "warmup_days": WARMUP_DAYS, "window_days": WINDOW,
            "first_anchor": FIRST_ANCHOR.isoformat(),
            "anchor_days": ANCHOR_DAYS,
            "schedule_start": _schedule_start().isoformat(),
            "note": "anchor 마다 초기화하지 않고 하나의 연속 schedule 을 재생한다.",
        },
        "summary": {
            "total_anchors": len(daily),
            "passing_anchors": len(passing),
            "pass_rate_pct": round(len(passing) / max(1, len(daily)) * 100, 1),
            "worst_key_p10": min(seq),
            "worst_family_p10": min(d["family_p10"] for d in daily),
            "worst_domain_p10": min(d["domain_p10"] for d in daily),
            "failure_episodes": len(episode_rows),
            "longest_failure_days": max((e["duration_days"] for e in episode_rows),
                                        default=0),
            "oscillation_14_15_14": oscillation,
            "expiry_at_risk_ilju_days": expiry_at_risk,
            "expired_without_replacement": expired_without_replacement,
            "note": "통과율은 진단 지표다 — 아직 출시 판정 기준으로 쓰지 않는다.",
        },
        "repeatedly_below_iljus": dict(below_counter.most_common(12)),
        "failures_by_month": dict(sorted(by_month.items())),
        "episodes": episode_rows[:20],
        "daily": daily,
    }


if __name__ == "__main__":
    result = run()
    data = {
        "audit_id": "OA-10b",
        "policy_status": "measurement_only",
        "live_behavior_changed": False,
        "measurement_stage": "display_pipeline",
        "result": result,
    }
    out = _ROOT / "doc" / "v2_2" / "audits" / "oa10b_rolling_window.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok]", out.name)
    s = result["summary"]
    print(f"  anchor {s['total_anchors']} · 통과 {s['passing_anchors']} "
          f"({s['pass_rate_pct']}%) · 최악 key p10 {s['worst_key_p10']}")
    print(f"  실패 episode {s['failure_episodes']}개 · 최장 {s['longest_failure_days']}일 "
          f"· 14→15→14 진동 {s['oscillation_14_15_14']}회")
    print(f"  만료 위험 일주-일 {s['expiry_at_risk_ilju_days']}")
    print("  반복 미달 일주:", result["repeatedly_below_iljus"])
    print("  월별 실패:", dict(list(result["failures_by_month"].items())[:12]))
