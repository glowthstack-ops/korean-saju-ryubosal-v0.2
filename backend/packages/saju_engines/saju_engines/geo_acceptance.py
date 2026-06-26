"""외부 지형 데이터 수용 계층(P4-Data Acceptance Layer, docs/12).

사람이 다운로드한 GIS 원본(POI csv/xlsx/jsonl, line/polygon shp/geojson/gpkg, 또는 이미 변환된
external_geo_feature.csv)이 **엔진에 먹일 수 있는 상태인지 사전 판정**하고, 문제를 사람이 이해할
리포트로 출력한다. 실제 변환·엔진 결과는 바꾸지 않는다(입구 검증 전용).

검증 실패 시 변환하지 않는다. CRS가 없으면 좌표 범위로 추정하되 warning. feature_type을 확정할
수 없으면 unknown(fail 아님, warning). geometry 없이 lon/lat만 있으면 point source로 처리 가능.

geopandas/pyproj가 없는 환경에서는 csv/jsonl/geojson은 순수 파이썬으로 전수 검증하고, 이진 GIS
(shp/gpkg)는 메타(.prj 등)만 보고 'geopandas 필요'를 warning/next_action으로 안내한다(감점 아님).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# 한반도 좌표 범위(WGS84 / EPSG:5179 평면) — 좌표 정합 sanity.
_KR_LON = (124.0, 132.0)
_KR_LAT = (33.0, 39.6)
_KR_X5179 = (700_000.0, 1_460_000.0)
_KR_Y5179 = (1_400_000.0, 2_100_000.0)

# 컬럼 매핑 후보(canonical → 원본 후보들).
_COORD_X = ("x_5179", "x", "tm_x", "utmk_x", "easting")
_COORD_Y = ("y_5179", "y", "tm_y", "utmk_y", "northing")
_COORD_LON = ("lon", "lng", "longitude", "x_wgs84", "경도")
_COORD_LAT = ("lat", "latitude", "y_wgs84", "위도")
_NAME_COLS = ("feature_name", "name", "poi_name", "fac_nm", "kor_nm", "명칭", "지명", "fclty_nm")
_TYPE_COLS = ("feature_type", "type", "gubun", "구분", "fclty_ty", "category", "ctgry")

# 파일명 키워드 → feature_type 추론(타입 컬럼 부재 시 보조).
_FILENAME_TYPE_HINTS = {
    "river": "river_anchor", "하천": "river_anchor", "stream": "stream_anchor",
    "coast": "coast_anchor", "해안": "coast_anchor", "shore": "coast_anchor",
    "mountain": "mountain_peak", "peak": "mountain_peak", "산": "mountain_peak",
    "pass": "mountain_pass", "고개": "mountain_pass", "valley": "valley_anchor",
    "계곡": "valley_anchor", "lake": "lake_centroid", "호수": "lake_centroid",
    "wetland": "wetland_centroid", "습지": "wetland_centroid", "port": "port",
    "항": "port", "포구": "port", "forest": "forest_patch", "임상": "forest_patch",
    "산림": "forest_patch", "park": "park_green", "공원": "park_green",
}
_TABULAR_EXT = {".csv", ".tsv", ".jsonl"}
_GEOJSON_EXT = {".geojson", ".json"}
_BINARY_GIS_EXT = {".shp", ".gpkg"}


class SourceAcceptance(BaseModel):
    """원본 1개의 수용 판정 결과(docs/12 P4-Data Acceptance)."""

    source_name: str
    path: str
    status: Literal["pass", "warning", "fail"] = "pass"
    file_format: str = ""
    detected_crs: str = ""  # epsg:5179 / epsg:4326 / unknown
    row_count: int = 0
    geometry_type: str = ""  # point/line/polygon/mixed/tabular_point
    mapped_columns: dict[str, str] = Field(default_factory=dict)  # canonical → 원본 컬럼
    unmapped_columns: list[str] = Field(default_factory=list)
    feature_type_candidates: list[str] = Field(default_factory=list)
    blocking_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str = ""


class AcceptanceReport(BaseModel):
    """여러 원본 수용 판정 종합."""

    sources: list[SourceAcceptance] = Field(default_factory=list)
    overall_status: Literal["pass", "warning", "fail"] = "pass"


def _valid_feature_types(dictionaries_dir: Path | None) -> set[str]:
    """region_geo_feature_elements.json의 feature_type 집합(element rule 매핑 가능 판정용)."""
    if dictionaries_dir is None:
        return set(_FILENAME_TYPE_HINTS.values())
    path = dictionaries_dir / "region" / "region_geo_feature_elements.json"
    try:
        rules = json.loads(path.read_text("utf-8"))
        return set(rules.get("feature_type_rules", {}))
    except (OSError, json.JSONDecodeError):
        return set(_FILENAME_TYPE_HINTS.values())


def _decode(path: Path) -> tuple[str, str | None]:
    """파일을 텍스트로 디코드(utf-8→utf-8-sig→cp949). (text, 경고) — 실패 시 (\"\", 에러)."""
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            text = raw.decode(enc)
            warn = None if enc.startswith("utf-8") else f"인코딩 {enc}(UTF-8 권장)"
            return text, warn
        except UnicodeDecodeError:
            continue
    return "", "디코딩 실패(utf-8/cp949 불가)"


def _filename_type_hint(name: str) -> list[str]:
    low = name.lower()
    return sorted({ft for kw, ft in _FILENAME_TYPE_HINTS.items() if kw in low})


def _match_col(header: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {h.lower(): h for h in header}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _coerce(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_coord_ranges(
    rows: list[dict[str, str]], cols: dict[str, str], acc: SourceAcceptance
) -> None:
    """좌표 범위가 한반도 안인지 검사(샘플 200행). 벗어나면 warning."""
    sample = rows[:200]
    out_of_range = 0
    checked = 0
    for r in sample:
        if "x_5179" in cols and "y_5179" in cols:
            x, y = _coerce(r.get(cols["x_5179"], "")), _coerce(r.get(cols["y_5179"], ""))
            if x is None or y is None:
                continue
            checked += 1
            if not (_KR_X5179[0] <= x <= _KR_X5179[1] and _KR_Y5179[0] <= y <= _KR_Y5179[1]):
                out_of_range += 1
        elif "lon" in cols and "lat" in cols:
            lon, lat = _coerce(r.get(cols["lon"], "")), _coerce(r.get(cols["lat"], ""))
            if lon is None or lat is None:
                continue
            checked += 1
            if not (_KR_LON[0] <= lon <= _KR_LON[1] and _KR_LAT[0] <= lat <= _KR_LAT[1]):
                out_of_range += 1
    if checked and out_of_range > checked * 0.2:
        acc.warnings.append(
            f"좌표가 한반도 범위를 벗어남({out_of_range}/{checked}) — CRS 확인 필요"
        )


def _finalize(acc: SourceAcceptance) -> SourceAcceptance:
    """blocking_errors/warnings로 최종 status·next_action 확정."""
    if acc.blocking_errors:
        acc.status = "fail"
        if not acc.next_action:
            acc.next_action = "blocking_errors 해소 후 재검증(변환 금지)"
    elif acc.warnings:
        acc.status = "warning"
        if not acc.next_action:
            acc.next_action = "warning 확인 후 변환 진행 가능"
    else:
        acc.status = "pass"
        if not acc.next_action:
            acc.next_action = "변환 진행 가능"
    return acc


def _inspect_tabular(
    path: Path, valid_types: set[str], acc: SourceAcceptance
) -> SourceAcceptance:
    """csv/tsv/jsonl point source 검증(순수 파이썬)."""
    acc.geometry_type = "tabular_point"
    text, enc_warn = _decode(path)
    if not text:
        acc.blocking_errors.append(enc_warn or "디코딩 실패")
        return _finalize(acc)
    if enc_warn:
        acc.warnings.append(enc_warn)
    if path.suffix.lower() == ".jsonl":
        records = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        header = list(records[0].keys()) if records else []
        rows = [{k: str(v) for k, v in rec.items()} for rec in records]
    else:
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        reader = csv.DictReader(text.splitlines(), delimiter=delim)
        header = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in r.items()} for r in reader]
    acc.row_count = len(rows)
    if acc.row_count == 0:
        acc.blocking_errors.append("행이 0개")
        return _finalize(acc)

    cols: dict[str, str] = {}
    x, y = _match_col(header, _COORD_X), _match_col(header, _COORD_Y)
    lon, lat = _match_col(header, _COORD_LON), _match_col(header, _COORD_LAT)
    if x and y:
        cols["x_5179"], cols["y_5179"] = x, y
        acc.detected_crs = "epsg:5179"
    if lon and lat:
        cols["lon"], cols["lat"] = lon, lat
        if not acc.detected_crs:
            acc.detected_crs = "epsg:4326"
    if not cols:
        acc.blocking_errors.append("좌표 컬럼 없음(x_5179/y_5179 또는 lon/lat 필요)")
        acc.next_action = "좌표 컬럼명을 x_5179/y_5179 또는 lon/lat로 매핑"
        return _finalize(acc)

    name_col = _match_col(header, _NAME_COLS)
    type_col = _match_col(header, _TYPE_COLS)
    if name_col:
        cols["feature_name"] = name_col
    else:
        acc.warnings.append("이름 컬럼 미검출 — feature_name 매핑 권장")
    feature_types: list[str] = []
    if type_col:
        cols["feature_type"] = type_col
        raw_vals = sorted({r.get(type_col, "") for r in rows if r.get(type_col)})
        feature_types = [v for v in raw_vals if v in valid_types]
        unknown = [v for v in raw_vals if v not in valid_types]
        if unknown:
            acc.warnings.append(
                f"미정의 feature_type {unknown[:5]} — element rule 매핑 불가(unknown 처리)"
            )
    else:
        feature_types = _filename_type_hint(path.name)
        if feature_types:
            acc.warnings.append(
                f"type 컬럼 없음 — 파일명 기반 추론 {feature_types}(확인 필요)"
            )
        else:
            acc.warnings.append("feature_type 추론 불가(unknown) — 변환 시 명시 필요")
    acc.feature_type_candidates = feature_types
    acc.mapped_columns = cols
    acc.unmapped_columns = [h for h in header if h not in cols.values()]
    _check_coord_ranges(rows, cols, acc)
    return _finalize(acc)


def _inspect_geojson(
    path: Path, valid_types: set[str], acc: SourceAcceptance
) -> SourceAcceptance:
    """geojson 검증(순수 파이썬 — geometry type·CRS·범위·count)."""
    text, enc_warn = _decode(path)
    if not text:
        acc.blocking_errors.append(enc_warn or "디코딩 실패")
        return _finalize(acc)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        acc.blocking_errors.append(f"JSON 파싱 실패: {exc}")
        return _finalize(acc)
    features = data.get("features", []) if isinstance(data, dict) else []
    acc.row_count = len(features)
    if acc.row_count == 0:
        acc.blocking_errors.append("features 0개")
        return _finalize(acc)
    # CRS(geojson crs member; 없으면 WGS84 가정이 표준이나 국내 SHP→geojson은 5179 흔함).
    crs_name = ""
    crs = data.get("crs") if isinstance(data, dict) else None
    if isinstance(crs, dict):
        crs_name = str(crs.get("properties", {}).get("name", ""))
    if "5179" in crs_name:
        acc.detected_crs = "epsg:5179"
    elif "4326" in crs_name or "CRS84" in crs_name:
        acc.detected_crs = "epsg:4326"
    else:
        acc.detected_crs = "unknown"
        acc.warnings.append("CRS 미명시 — 좌표 범위로 추정(EPSG 확인 권장)")
    geom_types = {
        (f.get("geometry") or {}).get("type", "") for f in features if isinstance(f, dict)
    }
    geom_types.discard("")
    empties = sum(1 for f in features if not (f.get("geometry") or {}).get("coordinates"))
    if empties:
        acc.warnings.append(f"빈 geometry {empties}개 — 변환 시 제외 필요")
    line = {"LineString", "MultiLineString"}
    poly = {"Polygon", "MultiPolygon"}
    point = {"Point", "MultiPoint"}
    if geom_types & line:
        acc.geometry_type = "line"
        acc.warnings.append("line geometry — 500m~1km anchor 생성 필요(상류 변환)")
    elif geom_types & poly:
        acc.geometry_type = "polygon"
        acc.warnings.append("polygon geometry — representative point/centroid 변환 필요")
    elif geom_types & point:
        acc.geometry_type = "point"
    else:
        acc.geometry_type = "mixed"
        acc.warnings.append(f"geometry 타입 혼재/불명 {sorted(geom_types)}")
    hints = _filename_type_hint(path.name)
    acc.feature_type_candidates = [h for h in hints if h in valid_types] or hints
    if not acc.feature_type_candidates:
        acc.warnings.append("feature_type 추론 불가(unknown) — 변환 시 명시 필요")
    return _finalize(acc)


def _inspect_binary_gis(path: Path, acc: SourceAcceptance) -> SourceAcceptance:
    """shp/gpkg — geopandas 있으면 전수, 없으면 메타(.prj)만 보고 graceful 안내."""
    try:
        import geopandas  # noqa: F401  (선택 의존)
    except ImportError:
        acc.warnings.append("geopandas 미설치 — 이진 GIS는 geometry 전수 검증 불가")
        if path.suffix.lower() == ".shp":
            prj = path.with_suffix(".prj")
            if prj.exists():
                prj_text = prj.read_text("utf-8", errors="ignore")
                if "5179" in prj_text:
                    acc.detected_crs = "epsg:5179"
                elif "4326" in prj_text or "WGS_1984" in prj_text:
                    acc.detected_crs = "epsg:4326"
                else:
                    acc.detected_crs = "unknown"
            else:
                acc.detected_crs = "unknown"
                acc.warnings.append(".prj 없음 — CRS 미상(좌표 범위로 추정 필요)")
        acc.next_action = "geopandas 설치 또는 geojson 변환 후 재검증"
        return _finalize(acc)
    import geopandas as gpd

    try:
        gdf = gpd.read_file(path)
    except Exception as exc:  # noqa: BLE001 — 읽기 실패도 리포트로 surface
        acc.blocking_errors.append(f"GIS 읽기 실패: {exc}")
        return _finalize(acc)
    acc.row_count = len(gdf)
    if acc.row_count == 0:
        acc.blocking_errors.append("feature 0개")
        return _finalize(acc)
    acc.detected_crs = str(gdf.crs).lower() if gdf.crs else "unknown"
    if gdf.crs is None:
        acc.warnings.append("CRS 미설정 — 좌표 범위로 추정 필요")
    geom_types = {str(t) for t in gdf.geom_type.unique()}
    if geom_types & {"LineString", "MultiLineString"}:
        acc.geometry_type = "line"
    elif geom_types & {"Polygon", "MultiPolygon"}:
        acc.geometry_type = "polygon"
    elif geom_types & {"Point", "MultiPoint"}:
        acc.geometry_type = "point"
    else:
        acc.geometry_type = "mixed"
    invalid = int((~gdf.geometry.is_valid).sum())
    empty = int(gdf.geometry.is_empty.sum())
    if invalid or empty:
        acc.warnings.append(f"invalid {invalid}·empty {empty} geometry — 변환 시 정리 필요")
    acc.feature_type_candidates = _filename_type_hint(path.name)
    return _finalize(acc)


def inspect_source(
    path: Path, dictionaries_dir: Path | None = None
) -> SourceAcceptance:
    """원본 파일 1개 수용 판정(포맷 자동 분기)."""
    acc = SourceAcceptance(source_name=path.name, path=str(path))
    if not path.exists():
        acc.blocking_errors.append("파일 없음")
        acc.next_action = "경로 확인 후 재시도"
        return _finalize(acc)
    ext = path.suffix.lower()
    acc.file_format = ext.lstrip(".")
    valid_types = _valid_feature_types(dictionaries_dir)
    if ext in _TABULAR_EXT:
        return _inspect_tabular(path, valid_types, acc)
    if ext in _GEOJSON_EXT:
        return _inspect_geojson(path, valid_types, acc)
    if ext in _BINARY_GIS_EXT:
        return _inspect_binary_gis(path, acc)
    if ext == ".xlsx":
        acc.warnings.append("xlsx — csv로 변환 후 검증 권장(openpyxl 필요)")
        acc.next_action = "csv 변환 후 재검증"
        return _finalize(acc)
    acc.blocking_errors.append(f"미지원 포맷 {ext}")
    return _finalize(acc)


def build_report(
    paths: list[Path], dictionaries_dir: Path | None = None
) -> AcceptanceReport:
    """여러 원본 종합 판정. overall = 최악 status."""
    sources = [inspect_source(p, dictionaries_dir) for p in paths]
    order = {"pass": 0, "warning": 1, "fail": 2}
    overall: Literal["pass", "warning", "fail"] = "pass"
    for s in sources:
        if order[s.status] > order[overall]:
            overall = s.status
    return AcceptanceReport(sources=sources, overall_status=overall)


def report_markdown(report: AcceptanceReport) -> str:
    """사람이 읽는 수용 리포트(md)."""
    icon = {"pass": "✅", "warning": "⚠️", "fail": "⛔"}
    lines = [
        "# 외부 지형 데이터 수용 리포트",
        "",
        f"**종합: {icon[report.overall_status]} {report.overall_status}** "
        f"(원본 {len(report.sources)}개)",
        "",
    ]
    for s in report.sources:
        lines.append(f"## {icon[s.status]} {s.source_name} ({s.status})")
        lines.append(
            f"- 포맷 {s.file_format} / CRS {s.detected_crs or '미상'} / "
            f"geometry {s.geometry_type or '미상'} / 행 {s.row_count}"
        )
        if s.mapped_columns:
            lines.append(f"- 매핑: {s.mapped_columns}")
        if s.feature_type_candidates:
            lines.append(f"- feature_type 후보: {s.feature_type_candidates}")
        for e in s.blocking_errors:
            lines.append(f"- ⛔ {e}")
        for w in s.warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append(f"- ▶ {s.next_action}")
        lines.append("")
    return "\n".join(lines)
