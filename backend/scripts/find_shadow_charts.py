#!/usr/bin/env python3
"""Shadow 차트 탐색 — 합성 birth 그리드를 calculate predicate 로 검증해 구조 coverage 확보.

손으로 생일을 찍지 않는다. deterministic stratified 그리드(1950–2009 × 월 × 일{3,13,23} × 12시지
× 성별)를 calculate 로 돌려, shadow_chart_specs 의 required/critical predicate 를 만족하는
BirthInput 만 채택한다. FOUND/BEST_MATCH 만 charts.jsonl 에 추가하고, 전 chart 상태를
coverage_report.json(manifest)에 남긴다. NOT_FOUND 는 억지 주입하지 않는다.

사용:
    python scripts/find_shadow_charts.py --max-candidates 60000
    python scripts/find_shadow_charts.py --dry-run     # charts.jsonl 미기록, 리포트만

규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §13-5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from saju_engines.shadow_chart_predicates import Pred
from saju_engines.shadow_chart_specs import SCHEMA_VERSION, SPECS, ChartSpec
from saju_shared_types.birth_input import BirthInput

_BACKEND = Path(__file__).resolve().parents[1]
_CHARTS = _BACKEND / "data" / "shadow_charts" / "charts.jsonl"
_REPORT = _BACKEND / "data" / "shadow_charts" / "coverage_report.json"

# deterministic stratified 그리드 — 연도를 가장 빠르게 순회(앞 연도 편향 방지).
_YEARS = list(range(1950, 2010))
_MONTHS = list(range(1, 13))
_DAYS = [3, 13, 23]
_HOURS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
_GENDERS = ["male", "female"]


def _calculate(birth: BirthInput):
    from saju_api.services.manse_service import calculate
    return calculate(birth)


def _candidates(days: list[int], years: list[int]):
    """결정적 stratified 순서 — (일, 월, 시, 성별) 고정 후 연도 innermost."""
    for day in days:
        for month in _MONTHS:
            for hour in _HOURS:
                for gender in _GENDERS:
                    for year in years:
                        yield BirthInput(
                            calendar_type="solar",
                            birth_date=f"{year}-{month:02d}-{day:02d}",
                            birth_time=f"{hour:02d}:30",
                            birth_place_name="Seoul",
                            gender=gender,
                        )


def _eval(preds: list[Pred], result) -> tuple[list[str], list[str]]:
    """(satisfied 이름, missing 이름)."""
    sat: list[str] = []
    mis: list[str] = []
    for p in preds:
        try:
            ok = p.fn(result)
        except (AttributeError, KeyError, TypeError):
            ok = False
        (sat if ok else mis).append(p.name)
    return sat, mis


def _best_match_ok(spec: ChartSpec, result) -> tuple[bool, list[str], list[str]]:
    """best_match 기준: critical 전부 + required 2/3 이상."""
    crit_sat, _ = _eval(spec.critical, result)
    if len(crit_sat) != len(spec.critical):
        return False, [], []
    sat, mis = _eval(spec.required, result)
    enough = len(sat) >= (2 * len(spec.required) + 2) // 3  # ceil(2/3)
    return enough, sat, mis


def _birth_dict(b: BirthInput) -> dict:
    # pydantic 이 birth_date/birth_time 를 date/time 으로 강제 — JSON 직렬화 위해 문자열화.
    return {"calendar_type": str(b.calendar_type), "birth_date": str(b.birth_date),
            "birth_time": str(b.birth_time)[:5], "birth_place_name": b.birth_place_name,
            "gender": str(b.gender)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Shadow 차트 구조 탐색")
    ap.add_argument("--max-candidates", type=int, default=60000)
    ap.add_argument("--days", default="3,13,23",
                    help="탐색 일자 세트(2차 확장: 1,6,11,16,21,26).")
    ap.add_argument("--year-start", type=int, default=1950)
    ap.add_argument("--year-end", type=int, default=2009)
    ap.add_argument("--only", default="",
                    help="특정 chart_id 만 탐색(쉼표구분) — 2차 확장 focused sweep.")
    ap.add_argument("--dry-run", action="store_true",
                    help="charts.jsonl 미기록 — coverage_report 만 출력.")
    args = ap.parse_args()

    days = [int(d) for d in args.days.split(",") if d.strip()]
    years = list(range(args.year_start, args.year_end + 1))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    active_specs = [s for s in SPECS if s.chart_id in only] if only else SPECS

    found: dict[str, dict] = {}          # chart_id → 채택(distinct birth 우선)
    fallback: dict[str, dict] = {}       # required 전부 만족 첫 후보(birth 재사용 허용·폴백)
    best: dict[str, dict] = {}           # best_match 후보(아직 FOUND 아님)
    used_births: set[tuple] = set()      # 이미 채택된 birth — 구조 다양성 위해 distinct 우선
    scanned = 0

    def _record(spec, birth, sat, result) -> dict:
        es_sat, _ = _eval([spec.expected_shadow] if spec.expected_shadow else [], result)
        _, inv_mis = _eval(spec.invariants, result)
        return {
            "status": "FOUND", "match_quality": "FOUND", "birth": _birth_dict(birth),
            "satisfied_predicates": sat, "missing_predicates": [],
            "expected_shadow_ok": (bool(es_sat) if spec.expected_shadow else None),
            "invariants_ok": not inv_mis, "notes": spec.notes,
        }

    for birth in _candidates(days, years):
        if scanned >= args.max_candidates or len(found) == len(active_specs):
            break
        scanned += 1
        result = _calculate(birth)
        bkey = (birth.birth_date, str(birth.birth_time), birth.gender)
        for spec in active_specs:
            if spec.chart_id in found:
                continue
            sat, mis = _eval(spec.required, result)
            if not mis:  # required 전부 — distinct birth 우선, 아니면 폴백 기억.
                if spec.chart_id not in fallback:
                    fallback[spec.chart_id] = _record(spec, birth, sat, result)
                if bkey not in used_births:
                    found[spec.chart_id] = _record(spec, birth, sat, result)
                    used_births.add(bkey)
                continue
            if spec.best_match_allowed and spec.chart_id not in best:
                ok, bsat, bmis = _best_match_ok(spec, result)
                if ok:
                    best[spec.chart_id] = {
                        "status": "BEST_MATCH", "match_quality": "best_match",
                        "birth": _birth_dict(birth), "satisfied_predicates": bsat,
                        "missing_predicates": bmis, "expected_shadow_ok": None,
                        "invariants_ok": None, "notes": spec.notes,
                    }

    # distinct birth 로 못 채운 spec 은 폴백(birth 재사용)으로 채운다 — 커버리지 보장.
    for cid, rec in fallback.items():
        found.setdefault(cid, rec)

    # --only 2차 확장 시: 비대상 spec 은 기존 coverage_report 레코드 보존(병합).
    prior: dict[str, dict] = {}
    if only and _REPORT.exists():
        for c in json.loads(_REPORT.read_text(encoding="utf-8")).get("charts", []):
            prior[c["chart_id"]] = c

    # 리포트: FOUND > BEST_MATCH > NOT_FOUND (대상 spec 만 재탐색, 나머지는 prior)
    report = []
    active_ids = {s.chart_id for s in active_specs}
    for spec in SPECS:
        if only and spec.chart_id not in active_ids and spec.chart_id in prior:
            report.append({"chart_id": spec.chart_id, "target": spec.target,
                           **{k: v for k, v in prior[spec.chart_id].items()
                              if k != "chart_id"}})
            continue
        if spec.chart_id in found:
            rec = found[spec.chart_id]
        elif spec.chart_id in best:
            rec = best[spec.chart_id]
        else:
            rec = {"status": "NOT_FOUND", "match_quality": None, "birth": None,
                   "satisfied_predicates": [],
                   "missing_predicates": [p.name for p in spec.required],
                   "expected_shadow_ok": None, "invariants_ok": None, "notes": spec.notes}
        report.append({"chart_id": spec.chart_id, "target": spec.target, **rec})

    n_found = sum(1 for r in report if r["status"] == "FOUND")
    n_best = sum(1 for r in report if r["status"] == "BEST_MATCH")
    n_not = sum(1 for r in report if r["status"] == "NOT_FOUND")
    print(f"scanned={scanned} | FOUND={n_found} BEST_MATCH={n_best} NOT_FOUND={n_not}")
    for r in report:
        mark = {"FOUND": "✓", "BEST_MATCH": "~", "NOT_FOUND": "✗"}[r["status"]]
        bd = r.get("birth")  # prior(병합) 레코드는 birth 없음(manifest 미저장)
        bs = f"{bd['birth_date']} {bd['birth_time']} {bd['gender'][0]}" if bd else "-"
        print(f"  {mark} {r['chart_id']:<28} {bs:<22} miss={r.get('missing_predicates', [])}")

    if args.dry_run:
        print("\n--dry-run: charts.jsonl·coverage_report 미기록.")
        return

    # charts.jsonl — 기존 유지 + 신규 FOUND/BEST_MATCH 추가(chart_id 중복 방지).
    existing = []
    seen = set()
    if _CHARTS.exists():
        for line in _CHARTS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                existing.append(rec)
                seen.add(rec["chart_id"])
    for r in report:
        if (r["status"] in ("FOUND", "BEST_MATCH") and r["chart_id"] not in seen
                and r.get("birth")):  # prior(병합) 레코드는 birth 없음 → 이미 charts.jsonl 존재
            existing.append({"chart_id": r["chart_id"], "input": r["birth"],
                             "match_quality": r["match_quality"]})
            seen.add(r["chart_id"])
    with _CHARTS.open("w", encoding="utf-8") as f:
        for rec in existing:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # coverage_report.json — manifest(timestamp·경로·로그 제외).
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "summary": {"found": n_found, "best_match": n_best, "not_found": n_not},
        "charts": [{k: r[k] for k in ("chart_id", "status", "match_quality",
                                      "satisfied_predicates", "missing_predicates",
                                      "expected_shadow_ok", "notes")} for r in report],
    }
    _REPORT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록: {_CHARTS.name}(+{n_found + n_best}) · {_REPORT.name}")


if __name__ == "__main__":
    main()
