"""위험 엔진 shadow 후보 밀도 리포트 (R0.5 — RISK_ENGINE.md §감수 절차 5, 2차 개정).

점수(R1) 없이 사전 과발동을 잡기 위한 계측. 후보를 단계별로 분리해 측정한다:

- observed  = 룰 하나 이상 매칭(INSUFFICIENT 포함 전체)
- eligible  = 증거 계약 충족(ELIGIBLE/MITIGATED/BLOCKED)
- active    = blocker·특이도 억제 통과(is_active)
- exposable = claimCeiling·등급 통과(R3 배선 후 — 현재 미산출)

밀도 목표(기준: raw가 아니라 active/unique family):
  active incident/period ≤ 1.5 · active family/period ≤ 3 · 단일 원인 활성 family ≤ 2(예외 3)
  incident 항목 발동률 >40% = 0건 · vulnerability/pressure >40% = 수동 검토 대상

기준 차트 1건은 진단용, 임계값 확정은 코퍼스(신강·신약·오행 과다 등 10차트)로 본다 —
평균만이 아니라 p50/p90/최댓값·kind별·차트별 상시 발동 항목을 본다.

실행: python scripts/risk_shadow_density.py [--levels year,month] [--baseline-only]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

from saju_api.services.manse_service import calculate  # noqa: E402
from saju_engines import EventEngineV2  # noqa: E402
from saju_engines.risk_engine import cause_atoms  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402
from saju_shared_types.risk_engine import (  # noqa: E402
    EligibilityStatus,
    EvidenceRole,
    RiskKind,
    is_active,
)

_DICTS = _BACKEND / "dictionaries"
_LEVELS = {"daewoon": GanjiLevel.DAEWOON, "year": GanjiLevel.YEAR,
           "month": GanjiLevel.MONTH, "day": GanjiLevel.DAY}
_REF = date(2026, 6, 11)

# 코퍼스 — 기준 차트 + 구조가 다른 합성 명식(신강·신약/오행 편중/관계 다·소 등을 넓게
# 커버하려는 생년 분산 샘플). 임계값 확정용이 아니라 분포 관찰용(R0.5).
# 출생지는 시드 지역(서울/부산)만 사용 — location_db seed 제약(구조 분포에는 무영향).
_CORPUS: list[tuple[str, BirthInput]] = [
    ("기준 1980 남", BirthInput(calendar_type="solar", birth_date=date(1980, 11, 22),
                              birth_time="09:08", birth_place_name="서울", gender="male",
                              reference_date=_REF)),
    ("1955 여", BirthInput(calendar_type="solar", birth_date=date(1955, 3, 5),
                           birth_time="04:30", birth_place_name="부산", gender="female",
                           reference_date=_REF)),
    ("1963 남", BirthInput(calendar_type="solar", birth_date=date(1963, 8, 17),
                           birth_time="22:10", birth_place_name="서울", gender="male",
                           reference_date=_REF)),
    ("1972 여", BirthInput(calendar_type="solar", birth_date=date(1972, 1, 29),
                           birth_time="13:40", birth_place_name="부산", gender="female",
                           reference_date=_REF)),
    ("1985 여", BirthInput(calendar_type="solar", birth_date=date(1985, 6, 10),
                           birth_time="07:15", birth_place_name="서울", gender="female",
                           reference_date=_REF)),
    ("1990 남", BirthInput(calendar_type="solar", birth_date=date(1990, 12, 3),
                           birth_time="18:55", birth_place_name="부산", gender="male",
                           reference_date=_REF)),
    ("1995 여", BirthInput(calendar_type="solar", birth_date=date(1995, 4, 21),
                           birth_time="11:05", birth_place_name="서울", gender="female",
                           reference_date=_REF)),
    ("1998 남", BirthInput(calendar_type="solar", birth_date=date(1998, 9, 9),
                           birth_time="02:20", birth_place_name="부산", gender="male",
                           reference_date=_REF)),
    ("2001 여", BirthInput(calendar_type="solar", birth_date=date(2001, 7, 7),
                           birth_time="16:45", birth_place_name="서울", gender="female",
                           reference_date=_REF)),
    ("2004 남", BirthInput(calendar_type="solar", birth_date=date(2004, 2, 14),
                           birth_time="09:50", birth_place_name="부산", gender="male",
                           reference_date=_REF)),
]


def _pct(n: float, d: float) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return float(s[idx])


def _chart_stats(engine: EventEngineV2, birth: BirthInput, levels: set[GanjiLevel]) -> dict:
    """차트 1건의 단계별 밀도 통계."""
    chart = calculate(birth)
    lc = chart.luck_cycles
    assert lc is not None
    total = 0
    if GanjiLevel.DAEWOON in levels:
        total += len(lc.daewoon_table)
    if GanjiLevel.YEAR in levels:
        total += len(lc.yearly_luck)
    if GanjiLevel.MONTH in levels:
        total += len(lc.monthly_luck)
    if GanjiLevel.DAY in levels:
        total += len(lc.daily_luck)
    engine.score(chart, levels=levels)
    cands = engine.risk_shadow
    eligible = [
        c for c in cands
        if c.eligibility_status is not EligibilityStatus.INSUFFICIENT_EVIDENCE
    ]
    active = [c for c in cands if is_active(c)]
    # 노출 단계 분리(감수 6차) — structural active를 노출 요구별로 나눈다:
    # exposure-required-unknown 후보는 R1에서 등급 상한·차단 대상이므로 일반 incident
    # 밀도와 합산하면 과발동 판단이 왜곡된다(structural vs exposure-qualified 병기).
    exp_unknown = [
        c for c in active
        if c.exposure_requirement in ("required_for_exposure", "confirmed_required")
    ]
    exp_qualified = [c for c in active if c not in exp_unknown]
    active_per_period: dict[str, int] = Counter(c.period_key for c in active)
    fam_per_period: dict[str, set[str]] = defaultdict(set)
    cause_fanout: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in active:
        fam_per_period[c.period_key].add(c.risk_family or c.risk_id)
        for e in c.evidence:
            if e.role is EvidenceRole.TRIGGER:
                for atom in cause_atoms(e.source):
                    if not atom.startswith("polarity:"):  # 극성은 원인이 아니라 방향
                        cause_fanout[(c.period_key, atom)].add(
                            c.risk_family or c.risk_id,
                        )
    fire_periods: dict[str, set[str]] = defaultdict(set)
    domain_family_periods: Counter = Counter()
    seen_dfp: set[tuple[str, str, str]] = set()
    for c in active:
        fire_periods[c.risk_id].add(c.period_key)
        key = (c.period_key, c.domain.value, c.risk_family or c.risk_id)
        if key not in seen_dfp:
            seen_dfp.add(key)
            domain_family_periods[c.domain.value] += 1
    # 최장 연속 발동(월운 기준) — 평균이 낮아도 특정 위험이 계속 켜져 있으면 범용 룰 신호.
    month_labels = sorted(p.label for p in lc.monthly_luck)
    longest_streak: dict[str, int] = {}
    for rid, ps in fire_periods.items():
        streak = best = 0
        for m in month_labels:
            streak = streak + 1 if m in ps else 0
            best = max(best, streak)
        longest_streak[rid] = best
    return {
        "n_months": len(month_labels),
        "longest_streak": longest_streak,
        "domain_family_periods": dict(domain_family_periods),
        "total": total,
        "observed": len(cands),
        "eligible": len(eligible),
        "active": len(active),
        "suppressed": sum(1 for c in cands if c.suppressed_by_specificity),
        "blocked": sum(
            1 for c in cands if c.eligibility_status is EligibilityStatus.BLOCKED
        ),
        "active_incident": sum(
            1 for c in active if c.kind is RiskKind.INCIDENT_RISK
        ),
        "exposure_required_unknown": len(exp_unknown),
        "exposure_qualified_incident": sum(
            1 for c in exp_qualified if c.kind is RiskKind.INCIDENT_RISK
        ),
        "active_kind": Counter(c.kind.value for c in active),
        "active_counts": [active_per_period.get(p, 0) for p in
                          {c.period_key for c in cands} | set(active_per_period)] or [0],
        "family_per_period": [len(v) for v in fam_per_period.values()] or [0],
        "max_cause_fanout": max((len(v) for v in cause_fanout.values()), default=0),
        "fire_rates": {rid: len(ps) / total for rid, ps in fire_periods.items() if total},
        "periods_with_active": len(active_per_period),
    }


def main() -> None:
    """코퍼스 단계별 밀도를 계산해 stdout으로 리포트한다."""
    parser = argparse.ArgumentParser(description="위험 shadow 후보 밀도 리포트(단계별)")
    parser.add_argument("--levels", default="year,month")
    parser.add_argument("--baseline-only", action="store_true",
                        help="기준 차트 1건만 실행(빠른 진단)")
    args = parser.parse_args()
    levels = {_LEVELS[x.strip()] for x in args.levels.split(",") if x.strip()}
    corpus = _CORPUS[:1] if args.baseline_only else _CORPUS

    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    all_stats: list[tuple[str, dict]] = []
    for name, birth in corpus:
        try:
            all_stats.append((name, _chart_stats(engine, birth, levels)))
        except Exception as exc:  # noqa: BLE001 -- 코퍼스 개별 실패는 건너뛰고 보고
            print(f"[skip] {name}: {exc}")

    print(f"# 위험 shadow 밀도 리포트(단계별) — 차트 {len(all_stats)}개, 층위={args.levels}")
    print(f"{'차트':<12} {'기간':>4} {'obs':>5} {'elig':>5} {'act':>5} {'흡수':>4} "
          f"{'차단':>4} {'act.inc':>7} {'act/기간':>8} {'fam/기간 p90':>12} {'원인확산max':>10}")
    agg_fire: dict[str, list[float]] = defaultdict(list)
    for name, s in all_stats:
        act_per = s["active"] / s["total"] if s["total"] else 0
        fam_p90 = _percentile(s["family_per_period"], 0.9)
        print(f"{name:<12} {s['total']:>4} {s['observed']:>5} {s['eligible']:>5} "
              f"{s['active']:>5} {s['suppressed']:>4} {s['blocked']:>4} "
              f"{s['active_incident']:>7} {act_per:>8.2f} {fam_p90:>12.1f} "
              f"{s['max_cause_fanout']:>10}")
        for rid, rate in s["fire_rates"].items():
            agg_fire[rid].append(rate)

    totals = [s for _, s in all_stats]
    n_periods = sum(s["total"] for s in totals)
    n_active = sum(s["active"] for s in totals)
    n_inc = sum(s["active_incident"] for s in totals)
    kind_sum: Counter = Counter()
    for s in totals:
        kind_sum.update(s["active_kind"])
    n_exp_unknown = sum(s.get("exposure_required_unknown", 0) for s in totals)
    n_exp_inc = sum(s.get("exposure_qualified_incident", 0) for s in totals)
    print("\n## 코퍼스 종합")
    print(f"활성/기간 평균: {n_active / max(1, n_periods):.2f} "
          f"(structural incident/기간: {n_inc / max(1, n_periods):.2f} · "
          f"exposure-qualified incident/기간: {n_exp_inc / max(1, n_periods):.2f} — "
          f"목표 ≤1.5는 exposure-qualified 기준 병기)")
    print(f"노출 확인 필요(UNKNOWN) 활성 후보: {n_exp_unknown} — R1 등급 상한·차단 대상"
          f"(일반 밀도와 분리, 룰 약화 판단에 합산 금지)")
    print("exposure_assumption: 전 후보 UNKNOWN 가정(프로필 미적용) · "
          "required_for_exposure/confirmed_required=분리 · "
          "not_required/required_for_warning=qualified 포함")
    print(f"활성 kind 분포: {dict(kind_sum)}")
    fam_all = [x for s in totals for x in s["family_per_period"]]
    print(f"활성 family/기간: p50 {_percentile(fam_all, 0.5):.0f} · "
          f"p90 {_percentile(fam_all, 0.9):.0f} · max {max(fam_all, default=0)} (목표 ≤3)")
    dom_fam: Counter = Counter()
    for s in totals:
        dom_fam.update(s.get("domain_family_periods", {}))
    total_fam_periods = sum(dom_fam.values()) or 1
    print("family 밀도 도메인 기여도(활성 family-기간 합): " + ", ".join(
        f"{d} {n}({100*n//total_fam_periods}%)" for d, n in dom_fam.most_common()))
    print("밀도 목표(감수 14차 분리): 구조 품질=structural incident 별도 추적(현재 상단) · "
          "사용자 노출 밀도=exposure-qualified incident ≤1.5")
    fanout_max = max((s["max_cause_fanout"] for s in totals), default=0)
    print(f"단일 원인 활성 family 확산 max: {fanout_max} (목표 ≤2, 예외 3)")

    # 발동률 분모 정의: 해당 위험이 1회 이상 활성인 '적용 차트'만 집계에 포함된다
    # (agg_fire에 없는 차트는 미적용). 코퍼스 평균은 적용 차트 평균이다.
    print("\n## 항목별 평균 발동률 top10 (활성 기준 · 분모=적용 차트 수)")
    warn: list[str] = []
    max_streaks: dict[str, int] = defaultdict(int)
    for _, s in all_stats:
        for rid, st in s.get("longest_streak", {}).items():
            max_streaks[rid] = max(max_streaks[rid], st)
    n_months = max((s.get("n_months", 0) for s in totals), default=0)
    for rid, rates in sorted(agg_fire.items(), key=lambda x: -sum(x[1]) / len(x[1]))[:10]:
        avg = sum(rates) / len(rates)
        n_high = sum(1 for r in rates if r > 0.4)
        streak = max_streaks.get(rid, 0)
        print(f"  - {rid}: 적용차트 평균 {_pct(avg, 1.0)} · >40% 차트 {n_high}/적용 "
              f"{len(rates)}/전체 {len(all_stats)} · 최장 연속(월) {streak}/{n_months}")
        if avg > 0.4:
            warn.append(f"{rid} 적용차트 평균 발동률 {_pct(avg, 1.0)} (>40%)")
        if n_months and streak / n_months > 0.5:
            warn.append(f"{rid} 최장 연속 발동 {streak}/{n_months}개월 (>50% — 범용 룰 의심)")
    if fanout_max > 3:
        warn.append(f"단일 원인 확산 {fanout_max} family (>3)")
    if n_periods and n_inc / n_periods > 1.5:
        warn.append("active incident/기간 > 1.5")
    print("\n경고 신호:" if warn else "\n경고 신호: 없음(목표 범위)")
    for w in warn:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
