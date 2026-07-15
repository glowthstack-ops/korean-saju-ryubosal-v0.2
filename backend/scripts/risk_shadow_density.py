"""위험 엔진 shadow 후보 밀도 리포트 (R0.5 — RISK_ENGINE.md §감수 절차 5).

점수(R1) 없이도 사전 과발동을 조기에 잡기 위한 계측이다. 기준 차트(1980-11-22 09:08
서울 남)의 세운+월운을 shadow 모드로 스코어링해 원자 후보 밀도를 출력한다.

경고 신호(사전 매핑 문제 — R1 전에 수정):
- 거의 모든 기간에 위험 후보 존재 / incident가 pressure보다 많음 /
  특정 risk_id가 대부분 기간에서 발동 / 하나의 원인(충 등)이 5개 이상의 위험 생성 /
  blocker가 있는데 활성 집계가 줄지 않음.

실행: python scripts/risk_shadow_density.py [--levels year,month]
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
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402
from saju_shared_types.risk_engine import (  # noqa: E402
    EligibilityStatus,
    EvidenceRole,
    RiskKind,
)

_DICTS = _BACKEND / "dictionaries"
_LEVELS = {"daewoon": GanjiLevel.DAEWOON, "year": GanjiLevel.YEAR,
           "month": GanjiLevel.MONTH, "day": GanjiLevel.DAY}


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def main() -> None:
    """기준 차트 shadow 후보 밀도를 계산해 stdout으로 리포트한다."""
    parser = argparse.ArgumentParser(description="위험 shadow 후보 밀도 리포트")
    parser.add_argument("--levels", default="year,month",
                        help="쉼표 구분 운 층위 (daewoon,year,month,day)")
    args = parser.parse_args()
    levels = {_LEVELS[x.strip()] for x in args.levels.split(",") if x.strip()}

    chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))
    lc = chart.luck_cycles
    assert lc is not None
    total_periods = 0
    if GanjiLevel.DAEWOON in levels:
        total_periods += len(lc.daewoon_table)
    if GanjiLevel.YEAR in levels:
        total_periods += len(lc.yearly_luck)
    if GanjiLevel.MONTH in levels:
        total_periods += len(lc.monthly_luck)
    if GanjiLevel.DAY in levels:
        total_periods += len(lc.daily_luck)

    engine = EventEngineV2(_DICTS, risk_mode="shadow")
    engine.score(chart, levels=levels)
    cands = engine.risk_shadow

    active = [c for c in cands if c.eligibility_status is not EligibilityStatus.BLOCKED]
    by_kind = Counter(c.kind for c in cands)
    by_domain = Counter(c.domain.value for c in cands)
    by_status = Counter(c.eligibility_status.value for c in cands)
    periods_with = len({c.period_key for c in cands})
    periods_with_active = len({c.period_key for c in active})
    periods_with_incident = len({
        c.period_key for c in active if c.kind is RiskKind.INCIDENT_RISK
    })

    # risk_id별 발동률(활성 기준).
    fire_periods: dict[str, set[str]] = defaultdict(set)
    for c in active:
        fire_periods[c.risk_id].add(c.period_key)

    # 독립 출처 수 분포(trigger source distinct).
    src_dist = Counter(
        len({e.source for e in c.evidence if e.role is EvidenceRole.TRIGGER})
        for c in cands
    )

    # 동일 원인 → 다중 risk_id: (기간, trigger source)당 서로 다른 risk_id 수.
    cause_fanout: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in active:
        for e in c.evidence:
            if e.role is EvidenceRole.TRIGGER:
                cause_fanout[(c.period_key, e.source)].add(c.risk_id)
    fanout_dist = Counter(len(v) for v in cause_fanout.values())
    worst_causes = sorted(
        ((k, len(v)) for k, v in cause_fanout.items()), key=lambda x: -x[1],
    )[:5]

    print(f"# 위험 shadow 후보 밀도 리포트 — 기준 차트 1980-11-22, 층위={args.levels}")
    print(f"평가 기간 수: {total_periods}")
    print(f"전체 원자 후보: {len(cands)} (기간당 평균 {len(cands) / max(1, total_periods):.2f})")
    print(f"활성(비 blocked) 후보: {len(active)}")
    print(f"상태 분포: {dict(by_status)}")
    print(f"kind 분포: {dict((k.value, v) for k, v in by_kind.items())}"
          f" — incident:pressure = {by_kind.get(RiskKind.INCIDENT_RISK, 0)}"
          f":{by_kind.get(RiskKind.PRESSURE, 0)}")
    print(f"도메인 분포: {dict(by_domain)}")
    print(f"후보 존재 기간: {periods_with}/{total_periods} ({_pct(periods_with, total_periods)})"
          f" · 활성 {_pct(periods_with_active, total_periods)}"
          f" · incident {_pct(periods_with_incident, total_periods)}")
    print(f"후보 0건 기간: {_pct(total_periods - periods_with, total_periods)}")
    print(f"독립 출처 수 분포(후보당): {dict(sorted(src_dist.items()))}")
    print(f"원인→risk_id 확산 분포: {dict(sorted(fanout_dist.items()))}")
    print("최다 확산 원인 top5:")
    for (period, source), n in worst_causes:
        print(f"  - {period} {source} → {n}개 risk_id")
    print("risk_id 발동률 top10(활성 기간/전체 기간):")
    for rid, ps in sorted(fire_periods.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  - {rid}: {len(ps)}/{total_periods} ({_pct(len(ps), total_periods)})")

    # 경고 신호 요약.
    warnings: list[str] = []
    if total_periods and periods_with_active / total_periods > 0.9:
        warnings.append("거의 모든 기간에 활성 위험 후보 존재(>90%)")
    if by_kind.get(RiskKind.INCIDENT_RISK, 0) > by_kind.get(RiskKind.PRESSURE, 0):
        warnings.append("incident 후보가 pressure보다 많음")
    for rid, ps in fire_periods.items():
        if total_periods and len(ps) / total_periods > 0.5:
            warnings.append(f"{rid} 발동률 {len(ps)}/{total_periods} (>50%)")
    if any(n >= 5 for _, n in worst_causes):
        warnings.append("하나의 원인이 5개 이상 위험 생성")
    print("\n경고 신호:" if warnings else "\n경고 신호: 없음")
    for w in warnings:
        print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
