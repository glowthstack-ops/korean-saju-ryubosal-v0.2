"""오늘의 운세 v2 funnel 감사 (docs/17 §22-4 — 상설).

사건별 `eligible → raw top3 → final → 전환율` 을 산출한다. 저노출(≤0.1%)은 결함이
아니라 감사 대상이며, 이 표가 5분류(트리거 희박/affinity/선발/클론/슬롯)의 1차 근거다.
카탈로그·가중을 고칠 때마다 같은 기간으로 재실행해 §22-5 기준선과 비교한다.

사용법:
    python scripts/audit_daily_v2_funnel.py [START_ISO] [DAYS]
기본: 2026-05-27 부터 90일(§22-5 검증 기준선과 동일 모집단).
"""

from __future__ import annotations

import collections
import datetime as dt
import sys

from saju_engines.daily_fortune_v2 import (
    build_pool_v2,
    day_channels,
    load_catalog_v2,
    select_slots_v2,
)
from saju_engines.daily_ilju_fortune import build_day_context
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

#: 저노출 감사 문턱 — 슬롯 점유율(§22-4).
LOW_EXPOSURE_RATIO = 0.001


def run(start: dt.date, days: int) -> int:
    """funnel 표를 출력한다. 항상 0(감사는 판정하지 않는다 — 판정은 사람이 한다)."""
    catalog = load_catalog_v2()
    iljus = [ganzi_from_index(i) for i in range(60)]

    eligible_days: collections.Counter[str] = collections.Counter()
    top3_raw: collections.Counter[str] = collections.Counter()
    final: collections.Counter[str] = collections.Counter()
    slot_final: dict[str, collections.Counter[str]] = {
        s: collections.Counter() for s in ("good", "caution", "support")
    }
    uniq_rows: list[int] = []
    fallback_n = 0

    for n in range(days):
        d = start + dt.timedelta(days=n)
        ctx = build_day_context(d)
        group_triples: dict[str, set[tuple[str, str, str]]] = collections.defaultdict(set)
        for stem, branch in iljus:
            ilju = f"{stem.value}{branch.value}"
            seed = f"{d.isoformat()}|{ilju}|funnel-audit"
            ch = day_channels(stem, branch, ctx)
            pool, eligible_keys, _fb = build_pool_v2(catalog, ch)
            eligible_days.update(eligible_keys)
            for slot in ("good", "caution", "support"):
                cand = sorted(
                    [
                        x for x in pool
                        if slot in x.slots
                        and (x.valence == "caution") == (slot == "caution")
                    ],
                    key=lambda x: -x.activation,
                )
                for x in cand[:3]:
                    top3_raw[x.event_key] += 1
            sel = select_slots_v2(catalog, ch, seed)
            fallback_n += 1 if sel.fallback_used else 0
            for slot_name, ev in (
                ("good", sel.good), ("caution", sel.caution), ("support", sel.support)
            ):
                final[ev.event_key] += 1
                slot_final[slot_name][ev.event_key] += 1
            group_triples[stem.value].add(
                (sel.good.event_key, sel.caution.event_key, sel.support.event_key)
            )
        uniq_rows.extend(len(v) for v in group_triples.values())

    total = days * 60 * 3
    cards = days * 60
    never = [k for k in catalog.events if final[k] == 0]
    low = [k for k in catalog.events if 0 < final[k] <= total * LOW_EXPOSURE_RATIO]
    top3_share = {
        s: sum(v for _, v in slot_final[s].most_common(3)) / cards
        for s in ("good", "caution", "support")
    }
    print(f"[v2 funnel] {start} ~ {start + dt.timedelta(days=days - 1)} ({days}일, "
          f"{len(catalog.events)}종) 슬롯 {total}건")
    print(f"미노출 {len(never)}종 {never} | ≤0.1% 저노출 {len(low)}종 {low}")
    print(f"top3 점유 good {top3_share['good']:.0%} caution {top3_share['caution']:.0%} "
          f"support {top3_share['support']:.0%} | "
          f"일간그룹 내 고유조합 {sum(uniq_rows) / len(uniq_rows):.2f}/6 | "
          f"폴백 {fallback_n}/{cards} ({100 * fallback_n / cards:.1f}%)")
    print(f"\n{'event_key':<32}{'elig':>6}{'elig%':>7}{'top3':>6}{'final':>6}"
          f"{'final%':>8}{'전환':>7}")
    for key in sorted(catalog.events, key=lambda k: final[k]):
        el, t3, f = eligible_days[key], top3_raw[key], final[key]
        conv = f"{100 * f / el:.1f}%" if el else "—"
        print(f"{key:<32}{el:>6}{100 * el / cards:>6.1f}%{t3:>6}{f:>6}"
              f"{100 * f / total:>7.2f}%{conv:>7}")
    return 0


def main() -> int:
    start = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2026, 5, 27)
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    return run(start, days)


if __name__ == "__main__":
    raise SystemExit(main())
