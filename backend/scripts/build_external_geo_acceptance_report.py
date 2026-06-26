"""외부 지형 수용 리포트 파일 생성(P4-Data Acceptance, docs/12).

여러 원본을 검증해 external_geo_acceptance_report.{json,md}를 출력한다(사람 검토·이력용).
validate_external_geo_sources.py가 게이트(종료코드)라면, 본 스크립트는 산출물(리포트 파일)이다.

사용법: python scripts/build_external_geo_acceptance_report.py [경로...] [--out DIR]
종료 0=pass/warning, 1=fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

from saju_engines.geo_acceptance import build_report, report_markdown

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_DICTS = _BACKEND / "dictionaries"
_DEFAULT_OUT = _BACKEND / "compiled"
_DEFAULT_DIR = _REPO / "doc" / "gis"
_SCAN_EXT = (".csv", ".tsv", ".jsonl", ".geojson", ".shp", ".gpkg")
_SKIP = ("region_units_compact", "region_lookup")


def _collect(paths: list[str]) -> list[Path]:
    """인자 경로(파일/디렉토리) → 검증 대상 파일 목록(validate 스크립트와 동일 규칙)."""
    targets = [Path(p) for p in paths] if paths else [_DEFAULT_DIR]
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
    out_dir = _DEFAULT_OUT
    paths: list[str] = []
    i = 1
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_dir = Path(argv[i + 1])
            i += 2
            continue
        paths.append(argv[i])
        i += 1
    files = _collect(paths)
    if not files:
        print("검증 대상 외부 지형 원본 없음(doc/gis에 다운로드 후 재실행).")
        return 1
    report = build_report(files, _DICTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "external_geo_acceptance_report.json").write_text(
        report.model_dump_json(indent=2) + "\n", "utf-8"
    )
    (out_dir / "external_geo_acceptance_report.md").write_text(
        report_markdown(report) + "\n", "utf-8"
    )
    print(
        f"수용 리포트 저장({report.overall_status}, 원본 {len(report.sources)}개) → "
        f"{out_dir}/external_geo_acceptance_report.{{json,md}}"
    )
    return 1 if report.overall_status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
