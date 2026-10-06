"""이동 시기 가설(계절 묶임·삼합 왕지 트리거) 실사례 대조 — MOVEMENT_TIMING_SHADOW.md §5.

현실 신호 원장(`subject_life_events`, 사용자가 확인/부정한 사건)과 골든 사례(2025-08 이사)를
정답으로 삼아, 사건 시점의 세운·월운 지지가 그 명식의 **묶인 계절 앵커의 삼합 왕지**였는지를
센다. 감사는 판정하지 않는다 — 수치만 내고 판정은 사람이 한다(승격은 데굴님 승인).

지표
- 적용률: 계절 묶임이 성립하는 명식 비율(묶임 없으면 규칙 자체가 적용되지 않는다).
- confirmed(실제 발생) 중 왕지 연/월 비율 vs not_happened(엔진 후보였으나 미발생) 중 비율.
  우연 기준선: 왕지 연 1/12, 월까지 보면 1-(11/12)^2.
- 고지(戌丑辰未) 비율: 영상은 고지가 끌어당기지 못한다고 본다 — 왕지와 같은 수준이면 규칙 반증.
- 묶임 없는 명식(대조군)에서도 같은 비율을 낸다 — 왕지 자체의 효과인지 묶임의 효과인지 분리.

사용법:
    python scripts/backtest_movement_timing.py [--json 출력경로]
DSN 은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 실사용자 데이터는 생년월일시·장소·사건
연월만 읽고 식별자는 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

from saju_api.services.manse_service import calculate
from saju_engines.movement_timing_shadow import SeasonBound, detect_season_bound
from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput

_BACKEND = Path(__file__).resolve().parent.parent
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]
_EVENT_KEYS = ("relocation", "career_change", "job_gain")

#: 골든 사례 — tests/fixtures/cases.jsonl `regression_2025_08_move_not_job`(실측 2025-08 이사).
#: 출생정보는 tests/fixtures/life_event_cases.jsonl 템플릿 행의 기준 명식과 동일.
_EXTRA_CASES: list[dict[str, Any]] = [
    {
        # 출생지 좌표 명시 — '서울 구로구'는 seed 지명이 아니라 좌표 없이는 계산이 ValueError 로
        # 실패한다(2026-10-06 1차 대조에서 이 행이 조용히 건너뛰어졌던 원인).
        "birth": {
            "calendar_type": "solar", "birth_date": "1980-11-22", "birth_time": "09:40",
            "birth_place_name": "서울 구로구", "gender": "male",
            "latitude": 37.4944, "longitude": 126.8563, "timezone": "Asia/Seoul",
        },
        "event_key": "relocation", "period": "2025-08", "outcome": "confirmed",
        "source": "cases.jsonl regression_2025_08_move_not_job",
    },
]


def _load_env() -> None:
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _rows_from_db(dsn: str) -> list[dict[str, Any]]:
    sql = (
        "SELECT e.subject_id, e.event_key, e.period, e.outcome, s.birth "
        "FROM subject_life_events e JOIN subjects s ON s.subject_id = e.subject_id "
        "WHERE e.event_key = ANY(%s) AND e.outcome IN ('confirmed', 'not_happened')"
    )
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(sql, (list(_EVENT_KEYS),)).fetchall()
    return [
        {"subject_id": r[0], "event_key": r[1], "period": r[2], "outcome": r[3], "birth": r[4],
         "source": "subject_life_events"}
        for r in rows
    ]


def _month_branch_map(years: set[int]) -> dict[str, str]:
    """'YYYY-MM'(절입 월 라벨) → 지지 — luck_cycles._monthly 와 같은 라벨 규칙."""
    from zoneinfo import ZoneInfo

    table = get_table()
    tz = ZoneInfo("Asia/Seoul")
    out: dict[str, str] = {}
    for y in sorted({yy for y0 in years for yy in (y0 - 1, y0)}):
        for inst, _name, branch in table.month_terms_in_solar_year(y):
            local = inst.astimezone(tz)
            out[f"{local.year}-{local.month:02d}"] = str(branch)
    return out


@dataclass
class RowResult:
    event_key: str
    period: str
    outcome: str
    tier: str
    season: str | None
    anchor: str | None
    royal: str | None
    storage: str | None
    year_branch: str
    month_branch: str | None
    royal_year: bool
    royal_month: bool
    storage_year: bool
    storage_month: bool
    natal_royal_present: bool
    source: str

    @property
    def royal_any(self) -> bool:
        return self.royal_year or self.royal_month

    @property
    def storage_any(self) -> bool:
        return self.storage_year or self.storage_month


@dataclass
class Bucket:
    n: int = 0
    royal_year: int = 0
    royal_any: int = 0
    storage_year: int = 0
    storage_any: int = 0
    with_month: int = 0
    rows: list[str] = field(default_factory=list)

    def add(self, r: RowResult) -> None:
        self.n += 1
        self.royal_year += int(r.royal_year)
        self.royal_any += int(r.royal_any)
        self.storage_year += int(r.storage_year)
        self.storage_any += int(r.storage_any)
        self.with_month += int(r.month_branch is not None)
        tag = "R" if r.royal_any else ("S" if r.storage_any else "-")
        self.rows.append(f"{r.event_key}@{r.period}:{tag}")

    def rates(self) -> dict[str, float | None]:
        if self.n == 0:
            return {"royal_year": None, "royal_any": None, "storage_year": None,
                    "storage_any": None, "chance_any": None}
        # 월 정보가 있는 행은 연·월 두 번 기회 — 우연 기준선을 행 구성에 맞춰 계산.
        chance = (
            self.with_month * (1 - (11 / 12) ** 2) + (self.n - self.with_month) * (1 / 12)
        ) / self.n
        return {
            "royal_year": round(self.royal_year / self.n, 3),
            "royal_any": round(self.royal_any / self.n, 3),
            "storage_year": round(self.storage_year / self.n, 3),
            "storage_any": round(self.storage_any / self.n, 3),
            "chance_any": round(chance, 3),
        }


def _evaluate(rows: list[dict[str, Any]]) -> tuple[list[RowResult], dict[str, Any]]:
    bounds: dict[str, SeasonBound] = {}
    results: list[RowResult] = []
    years = {int(str(r["period"])[:4]) for r in rows}
    month_map = _month_branch_map(years)
    skipped: Counter[str] = Counter()
    for r in rows:
        key = json.dumps(r["birth"], sort_keys=True, ensure_ascii=False)
        if key not in bounds:
            try:
                birth = BirthInput.model_validate(r["birth"])
                chart = calculate(birth.model_copy(update={"reference_date": date(2026, 1, 1)}))
            except Exception as exc:  # noqa: BLE001 — 한 명식 실패가 전체를 막지 않도록
                skipped[f"calc_fail:{type(exc).__name__}"] += 1
                continue
            if chart.pillars is None:
                skipped["no_pillars"] += 1
                continue
            bounds[key] = detect_season_bound(chart.pillars)
        b = bounds[key]
        period = str(r["period"])
        year = int(period[:4])
        year_branch = str(year_ganzi(year)[1])
        month_branch = month_map.get(period) if len(period) == 7 else None
        if len(period) == 7 and month_branch is None:
            skipped["month_label_unmapped"] += 1
        results.append(RowResult(
            event_key=r["event_key"], period=period, outcome=r["outcome"],
            tier=b.tier, season=b.season, anchor=b.anchor,
            royal=b.royal_branch, storage=b.storage_branch,
            year_branch=year_branch, month_branch=month_branch,
            royal_year=b.royal_branch == year_branch,
            royal_month=month_branch is not None and b.royal_branch == month_branch,
            storage_year=b.storage_branch == year_branch,
            storage_month=month_branch is not None and b.storage_branch == month_branch,
            natal_royal_present="natal_royal_present" in b.flags,
            source=r["source"],
        ))
    summary: dict[str, Any] = {
        "subjects": len(bounds),
        "subjects_bound": sum(1 for b in bounds.values() if b.tier != "none"),
        "subjects_by_tier": dict(Counter(b.tier for b in bounds.values())),
        "rows": len(results),
        "skipped": dict(skipped),
        "buckets": {},
    }
    buckets: dict[str, Bucket] = {}
    for res in results:
        group = "bound" if res.tier != "none" else "unbound"
        for name in (f"{group}/{res.outcome}", f"{group}/{res.outcome}/{res.event_key}"):
            buckets.setdefault(name, Bucket()).add(res)
    summary["buckets"] = {
        k: {"n": v.n, **v.rates(), "with_month": v.with_month, "rows": v.rows}
        for k, v in sorted(buckets.items())
    }
    return results, summary


def _print(summary: dict[str, Any]) -> None:
    print(f"명식 {summary['subjects']}건 중 계절 묶임 성립 {summary['subjects_bound']}건 "
          f"(등급 {summary['subjects_by_tier']}) · 사건 행 {summary['rows']}건 · "
          f"건너뜀 {summary['skipped']}")
    print()
    print(f"{'bucket':<40}{'n':>4}{'왕지연':>8}{'왕지연/월':>10}{'고지연':>8}{'고지연/월':>10}{'우연':>8}")
    for name, b in summary["buckets"].items():
        if "/" in name and name.count("/") == 1 or name.count("/") == 2:
            fmt = lambda v: "   -" if v is None else f"{v:.3f}"  # noqa: E731
            print(f"{name:<40}{b['n']:>4}{fmt(b['royal_year']):>8}{fmt(b['royal_any']):>10}"
                  f"{fmt(b['storage_year']):>8}{fmt(b['storage_any']):>10}{fmt(b['chance_any']):>8}")
    print()
    print("판독: bound/confirmed 의 왕지연/월 비율이 bound/not_happened 와 우연 기준선을 모두 "
          "뚜렷이 넘고, 고지 비율은 올라가지 않아야 가설이 지지된다. n 이 작으면 참고치다.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=None, help="요약 JSON 출력 경로")
    parser.add_argument("--no-db", action="store_true", help="원장 없이 골든 사례만")
    args = parser.parse_args(argv)
    _load_env()
    rows: list[dict[str, Any]] = []
    if not args.no_db:
        dsn = os.environ.get("SAJU_V2_DATABASE_URL")
        if not dsn:
            print("SAJU_V2_DATABASE_URL 미설정 — --no-db 로 골든 사례만 돌리거나 DSN 을 주세요",
                  file=sys.stderr)
            return 2
        rows.extend(_rows_from_db(dsn))
    rows.extend(_EXTRA_CASES)
    results, summary = _evaluate(rows)
    _print(summary)
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"summary": summary, "rows": [asdict(r) for r in results]},
            ensure_ascii=False, indent=2,
        ), encoding="utf-8")
        print(f"\nJSON → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
