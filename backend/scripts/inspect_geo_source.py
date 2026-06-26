"""외부 지형 원본 1개 수용 판정 출력(P4-Data Acceptance, docs/12).

사용법: python scripts/inspect_geo_source.py <파일경로> [--json]
csv/tsv/jsonl/geojson는 순수 파이썬 전수 검증, shp/gpkg는 geopandas 있으면 전수·없으면 메타 안내.
종료 0=pass/warning, 1=fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

from saju_engines.geo_acceptance import AcceptanceReport, inspect_source, report_markdown

_BACKEND = Path(__file__).resolve().parent.parent
_DICTS = _BACKEND / "dictionaries"


def main(argv: list[str]) -> int:
    """엔트리포인트."""
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print("사용법: inspect_geo_source.py <파일경로> [--json]")
        return 1
    acc = inspect_source(Path(args[0]), _DICTS)
    if "--json" in argv:
        print(acc.model_dump_json(indent=2))
    else:
        print(report_markdown(AcceptanceReport(sources=[acc], overall_status=acc.status)))
    return 1 if acc.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
