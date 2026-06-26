"""외부 지형 원본 묶음 수용 검증(P4-Data Acceptance, docs/12).

여러 원본(또는 디렉토리)을 검증하고 종합 status를 반환한다 — 변환 전 게이트. 검증 실패(fail)면
변환하지 않는다(종료 코드 1). 인자 없으면 기본 doc/gis 디렉토리의 후보 파일을 스캔한다.

사용법: python scripts/validate_external_geo_sources.py [경로...]
종료 0=pass/warning, 1=fail(또는 대상 없음).
"""

from __future__ import annotations

import sys
from pathlib import Path

from saju_engines.geo_acceptance import build_report, report_markdown

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_DICTS = _BACKEND / "dictionaries"
_DEFAULT_DIR = _REPO / "doc" / "gis"
_SCAN_EXT = (".csv", ".tsv", ".jsonl", ".geojson", ".shp", ".gpkg")
# 검증 대상에서 제외할 파일(엔진 산출·행정 단위 — 외부 지형 원본 아님).
_SKIP = ("region_units_compact", "region_lookup")


def _collect(paths: list[str]) -> list[Path]:
    """인자 경로(파일/디렉토리) → 검증 대상 파일 목록."""
    if not paths:
        targets = [_DEFAULT_DIR]
    else:
        targets = [Path(p) for p in paths]
    out: list[Path] = []
    for t in targets:
        if t.is_dir():
            out.extend(
                f for f in sorted(t.iterdir())
                if f.suffix.lower() in _SCAN_EXT and not any(s in f.name for s in _SKIP)
            )
        elif t.exists():
            out.append(t)
    return out


def main(argv: list[str]) -> int:
    """엔트리포인트."""
    files = _collect(argv[1:])
    if not files:
        print("검증 대상 외부 지형 원본 없음(doc/gis에 다운로드 후 재실행).")
        return 1
    report = build_report(files, _DICTS)
    print(report_markdown(report))
    return 1 if report.overall_status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
