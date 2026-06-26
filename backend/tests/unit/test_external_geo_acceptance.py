"""외부 지형 데이터 수용 계층(P4-Data Acceptance) 검증 — docs/12.

다운로드 원본이 엔진 변환 가능 상태인지 입구에서 판정한다. 정상→pass, 치명 문제→fail(변환 금지),
보정 필요→warning. 실제 변환·엔진 결과는 바꾸지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from saju_engines.geo_acceptance import build_report, inspect_source, report_markdown

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _csv(tmp: Path, name: str, header: str, *rows: str) -> Path:
    p = tmp / name
    p.write_text(header + "\n" + "\n".join(rows) + "\n", "utf-8")
    return p


def test_pass_point_csv(tmp_path: Path) -> None:
    """좌표·이름·타입 갖춘 point csv → pass + 컬럼 매핑·feature_type 검출."""
    p = _csv(
        tmp_path, "poi.csv",
        "feature_id,feature_type,feature_name,x_5179,y_5179",
        "M1,mountain_peak,북악산,953210,1954210",
        "R1,river_anchor,한강,946120,1943210",
    )
    acc = inspect_source(p, _DICTS)
    assert acc.status == "pass"
    assert acc.detected_crs == "epsg:5179" and acc.row_count == 2
    assert "x_5179" in acc.mapped_columns and "feature_name" in acc.mapped_columns
    assert set(acc.feature_type_candidates) == {"mountain_peak", "river_anchor"}


def test_fail_no_coordinates(tmp_path: Path) -> None:
    """좌표 컬럼 없으면 fail(변환 금지)."""
    p = _csv(tmp_path, "bad.csv", "name,memo", "foo,bar")
    acc = inspect_source(p, _DICTS)
    assert acc.status == "fail"
    assert any("좌표" in e for e in acc.blocking_errors)


def test_fail_missing_file(tmp_path: Path) -> None:
    """파일 없으면 fail."""
    acc = inspect_source(tmp_path / "nope.csv", _DICTS)
    assert acc.status == "fail" and any("없" in e for e in acc.blocking_errors)


def test_fail_empty_rows(tmp_path: Path) -> None:
    """행 0개면 fail."""
    p = _csv(tmp_path, "empty.csv", "feature_type,x_5179,y_5179")
    acc = inspect_source(p, _DICTS)
    assert acc.status == "fail" and any("0" in e for e in acc.blocking_errors)


def test_warning_out_of_range_and_unknown_type(tmp_path: Path) -> None:
    """좌표 한반도 이탈 + 미정의 feature_type → warning(fail 아님)."""
    p = _csv(
        tmp_path, "x.csv",
        "feature_id,feature_type,feature_name,lon,lat",
        "P1,unknown_kind,foo,200.0,99.0",
    )
    acc = inspect_source(p, _DICTS)
    assert acc.status == "warning"
    assert any("범위" in w for w in acc.warnings)
    assert any("feature_type" in w for w in acc.warnings)


def test_warning_no_type_column_filename_hint(tmp_path: Path) -> None:
    """type 컬럼 없으면 파일명으로 추론 + warning."""
    p = _csv(tmp_path, "river_centerline.csv", "lon,lat", "127.0,37.5")
    acc = inspect_source(p, _DICTS)
    assert acc.status == "warning"
    assert "river_anchor" in acc.feature_type_candidates


def test_geojson_line_warns_anchor_needed(tmp_path: Path) -> None:
    """line geojson → anchor 생성 필요 warning(좌표는 한반도 범위)."""
    gj = {
        "type": "FeatureCollection",
        "crs": {"properties": {"name": "EPSG:4326"}},
        "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "LineString", "coordinates": [[127.0, 37.5], [127.1, 37.6]]}},
        ],
    }
    p = tmp_path / "river.geojson"
    p.write_text(json.dumps(gj), "utf-8")
    acc = inspect_source(p, _DICTS)
    assert acc.geometry_type == "line"
    assert any("anchor" in w for w in acc.warnings)
    assert acc.detected_crs == "epsg:4326"


def test_binary_gis_graceful_without_geopandas(tmp_path: Path) -> None:
    """shp는 geopandas 없으면 메타만 보고 graceful 안내(fail 아님 — 파일 존재 시 warning)."""
    shp = tmp_path / "coast.shp"
    shp.write_bytes(b"\x00\x00")  # 더미(실제 검증은 geopandas 필요)
    acc = inspect_source(shp, _DICTS)
    # geopandas 미설치 → warning + 안내. 설치 환경이면 읽기 실패로 fail일 수 있음(둘 다 허용).
    assert acc.status in ("warning", "fail")
    if acc.status == "warning":
        assert "geopandas" in acc.next_action


def test_report_aggregates_and_markdown(tmp_path: Path) -> None:
    """여러 원본 종합 — 최악 status가 overall, markdown 생성."""
    good = _csv(tmp_path, "ok.csv", "feature_type,x_5179,y_5179", "river_anchor,946120,1943210")
    bad = _csv(tmp_path, "bad.csv", "memo", "x")
    report = build_report([good, bad], _DICTS)
    assert report.overall_status == "fail"  # bad 때문에
    md = report_markdown(report)
    assert "수용 리포트" in md and "ok.csv" in md and "bad.csv" in md
