"""P4-SearchSeed 1단계 — 시군구 × 지형 키워드 검색 쿼리 생성(docs/12).

읍면동 5,065 전수 검색은 비용·정책상 금지(사용자 확정). 시군구 250개 × 키워드 9개 = 약 2,250건만
생성한다. 읍면동은 추천 후보/사용자 질의가 들어온 지역만 on-demand 확장(별도).

입력: doc/gis/region_units_compact_20230729.jsonl. 출력: doc/gis/search_seed/search_queries.csv.
사용법: python scripts/build_search_seed_queries.py [units] [out_csv]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from saju_engines.search_seed import QUERY_KEYWORDS

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_DEFAULT_UNITS = _REPO / "doc" / "gis" / "region_units_compact_20230729.jsonl"
_DEFAULT_OUT = _REPO / "doc" / "gis" / "search_seed" / "search_queries.csv"


def build_queries(units_path: Path, levels: tuple[str, ...] = ("sig",)) -> list[dict]:
    """행정구역 × 키워드 → 검색 쿼리 행 목록(기본 시군구만)."""
    rows: list[dict] = []
    for line in units_path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("region_level", "")).lower() not in levels:
            continue
        name = r.get("full_name_ko") or r.get("region_name_ko") or ""
        for kw in QUERY_KEYWORDS:
            rows.append({
                "region_code": str(r["region_code"]),
                "region_level": str(r["region_level"]).lower(),
                "region_name_ko": name,
                "keyword": kw,
                "query": f"{name} {kw}",
            })
    return rows


def main(argv: list[str]) -> int:
    """엔트리포인트."""
    units_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_UNITS
    out = Path(argv[2]) if len(argv) > 2 else _DEFAULT_OUT
    if not units_path.exists():
        print(f"입력 없음: {units_path}")
        return 1
    rows = build_queries(units_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["region_code", "region_level", "region_name_ko", "keyword", "query"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"검색 쿼리 {len(rows)}건 생성(시군구) → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
