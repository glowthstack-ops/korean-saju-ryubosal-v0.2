"""지형 feature 빌드(Tier B 최고정확, 무로그인 소스) — region_geo_features.jsonl 생성.

docs/12 P4-Data의 geo 레이어를 외부 로그인/API 없이 정식 연결한다. 지역 경계는 bbox 근사가 아니라
OSM 행정경계(centroid-containment 매칭)의 실폴리곤을 쓰고, 지형은 OSM 토지피복/수계 + Natural
Earth 해/육 + Copernicus DEM(고도·경사)로 산출한다. 모두 무로그인/무API.

입력(모두 무로그인):
  - OSM south-korea shp(Geofabrik): gis_osm_adminareas_a(행정경계 level4/6/7/8/10),
    gis_osm_landuse_a(forest/farmland/residential/industrial), gis_osm_water_a(내륙 수역).
  - Natural Earth 10m land(GitHub raw): 해/육 판정(바다 = 폴리곤 − 육지).
  - Copernicus DEM GLO-90(익명 AWS S3): 고도·경사 → mountain_score(土)/elevation(火).

산출(실폴리곤 기준 면적 비율·DEM 통계):
  - water_area_ratio = 바다 비율(1 − 육지∩poly/poly) + 내륙 수역 비율  → 水
  - forest_area_ratio → 木, agricultural/urban_built/industrial_ratio → 土/火/金
  - mean_elevation → 火, slope_mean, mountain_score(평균 경사 정규화) → 土
  forest(木)는 mountain_score(土, physical_geography 0.45)와 함께 들어와 산림 산악 지역이 土로
  균형 잡힌다(forest 단독 木 지배 방지). reviewed:false 1차 추정.

재생성:
  python scripts/build_geo_features.py
    [units.jsonl] [osm_dir] [ne_10m_land.geojson] [dem_dir] [out.jsonl]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.merge import merge as rio_merge
from shapely.geometry import box
from shapely.prepared import prep

_REPO = Path(__file__).resolve().parents[2]
_G = _REPO / "doc" / "gis"
_DEFAULT_UNITS = _G / "region_units_compact_20230729.jsonl"
_DEFAULT_OSM = _G / "_geo_src" / "osm"
_DEFAULT_LAND = _G / "_geo_src" / "ne_10m_land.geojson"
_DEFAULT_DEM = _G / "_geo_src" / "dem"
_DEFAULT_OUT = _G / "region_geo_features.jsonl"

_EPSG = 5179
_KR_BBOX_4326 = (124.0, 32.0, 132.5, 39.6)
_AGRI = {"farmland", "orchard", "farmyard", "meadow"}
_URBAN = {"residential", "commercial", "retail"}
# region_level → OSM 행정경계 fclass(작은=구체 우선).
_LEVEL_FCLASS = {
    "sido": ["admin_level4"],
    "sig": ["admin_level6", "admin_level7"],
    "emd": ["admin_level8", "admin_level9", "admin_level10", "admin_level11"],
}
_MOUNT_SLOPE_NORM = 15.0  # 평균 경사 15°+ → mountain_score 1.0.


def _load_5179(path: Path) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    g = g[g.geometry.notna()].copy()
    g["geometry"] = g.geometry.buffer(0)
    return g.to_crs(_EPSG)


def _resolve_polygons(units: list[dict], adm: gpd.GeoDataFrame) -> dict[str, object]:
    """region_code → 실폴리곤(5179). centroid를 포함하는 최소 행정경계 폴리곤(레벨셋별)."""
    groups = {
        lvl: (adm[adm["fclass"].isin(fcs)].reset_index(drop=True))
        for lvl, fcs in _LEVEL_FCLASS.items()
    }
    sidx = {lvl: g.sindex for lvl, g in groups.items()}
    out: dict[str, object] = {}
    from shapely.geometry import Point
    for u in units:
        lvl = str(u.get("region_level", "")).lower()
        g = groups.get(lvl)
        if g is None or len(g) == 0:
            continue
        pt = Point(u["centroid_x_5179"], u["centroid_y_5179"])
        cand = list(sidx[lvl].query(pt, predicate="within"))
        hits = [(g.geometry.iloc[i].area, g.geometry.iloc[i]) for i in cand]
        if hits:
            out[u["region_code"]] = min(hits, key=lambda a: a[0])[1]
    return out


def _ratio(geoms: gpd.GeoSeries, sindex, poly, poly_area: float) -> float:
    """레이어 폴리곤 ∩ 지역폴리곤 면적 비율(교차면적 합 근사, union 회피)."""
    if poly_area <= 0 or sindex is None:
        return 0.0
    cand = list(sindex.query(poly, predicate="intersects"))
    if not cand:
        return 0.0
    area = 0.0
    for i in cand:
        g = geoms.iloc[i]
        if not g.is_valid:
            g = g.buffer(0)
        area += g.intersection(poly).area
    return min(1.0, area / poly_area)


def _dem_rasters(dem_dir: Path):
    """DEM 타일 머지 → (elevation, slope_deg, transform). 없으면 None."""
    tiles = sorted(dem_dir.glob("*.tif"))
    if not tiles:
        return None
    srcs = [rasterio.open(t) for t in tiles]
    dem, transform = rio_merge(srcs)
    for s in srcs:
        s.close()
    elev = dem[0].astype("float32")
    elev[elev < -1000] = np.nan
    # 경사(도): 픽셀 간 고도차 → 미터 환산 후 arctan.
    px_lon, px_lat = abs(transform.a), abs(transform.e)
    mlat = 32.0 + 8.0 / 2  # 한반도 중위도 근사.
    dy_m = px_lat * 111_320.0
    dx_m = px_lon * 111_320.0 * math.cos(math.radians(mlat))
    gy, gx = np.gradient(np.nan_to_num(elev))
    slope = np.degrees(np.arctan(np.hypot(gx / dx_m, gy / dy_m)))
    return elev, slope.astype("float32"), transform


def _dem_stats(poly_4326, elev, slope, transform) -> tuple[float, float]:
    """지역 폴리곤(4326) 내 격자 표본 → (mean_elevation, mean_slope_deg)."""
    minx, miny, maxx, maxy = poly_4326.bounds
    inv = ~transform
    n = 16
    xs = np.linspace(minx, maxx, n)
    ys = np.linspace(miny, maxy, n)
    pe: list[float] = []
    ps: list[float] = []
    pgeom = prep(poly_4326)
    from shapely.geometry import Point
    h, w = elev.shape
    for x in xs:
        for y in ys:
            if not pgeom.contains(Point(x, y)):
                continue
            col, row = inv * (x, y)
            r, c = int(row), int(col)
            if 0 <= r < h and 0 <= c < w and not np.isnan(elev[r, c]):
                pe.append(float(elev[r, c]))
                ps.append(float(slope[r, c]))
    if not pe:
        return float("nan"), float("nan")
    return sum(pe) / len(pe), sum(ps) / len(ps)


def build(units_p: Path, osm: Path, land_p: Path, dem_dir: Path, out_p: Path) -> tuple[int, int]:
    units = [json.loads(ln) for ln in units_p.read_text("utf-8").splitlines() if ln.strip()]
    adm = _load_5179(osm / "gis_osm_adminareas_a_free_1.shp")
    polys = _resolve_polygons(units, adm)
    # 4326 폴리곤(DEM 샘플용) — adm 원본에서 매칭 결과를 4326로.
    adm_4326 = gpd.GeoSeries(list(polys.values()), crs=_EPSG).to_crs(4326)
    polys_4326 = dict(zip(polys.keys(), adm_4326, strict=True))

    landuse = _load_5179(osm / "gis_osm_landuse_a_free_1.shp")
    water = _load_5179(osm / "gis_osm_water_a_free_1.shp")
    kr = box(*_KR_BBOX_4326)
    land = gpd.read_file(land_p, bbox=_KR_BBOX_4326)
    land_5179 = gpd.GeoSeries(
        [g.intersection(kr) for g in land.geometry if g.intersects(kr)], crs=4326
    ).to_crs(_EPSG)
    land_gs = gpd.GeoSeries(
        [g.buffer(0) for g in land_5179 if not g.is_empty], crs=_EPSG
    ).reset_index(drop=True)

    def _idx(classes: set[str]):
        gs = landuse[landuse["fclass"].isin(classes)].geometry.reset_index(drop=True)
        return (gs, gs.sindex if len(gs) else None)

    layers = {
        "forest_area_ratio": _idx({"forest"}),
        "agricultural_ratio": _idx(_AGRI),
        "urban_built_ratio": _idx(_URBAN),
        "industrial_ratio": _idx({"industrial"}),
        "_water": (water.geometry.reset_index(drop=True), water.sindex),
    }
    land_idx = (land_gs, land_gs.sindex)
    dem = _dem_rasters(dem_dir)

    out_lines: list[str] = []
    have = 0
    for u in units:
        code = u["region_code"]
        poly = polys.get(code)
        if poly is None:  # 실폴리곤 미매칭 → bbox 폴백.
            poly = box(u["bbox_minx_5179"], u["bbox_miny_5179"],
                       u["bbox_maxx_5179"], u["bbox_maxy_5179"])
        parea = poly.area
        land_ratio = _ratio(land_idx[0], land_idx[1], poly, parea)
        sea = max(0.0, 1.0 - land_ratio)
        vals = {f: _ratio(gs, sx, poly, parea) for f, (gs, sx) in layers.items()}
        water_ratio = min(1.0, sea + vals.pop("_water", 0.0))
        feat: dict[str, object] = {"region_id": str(code),
                                   "legal_dong_code": str(u.get("emd_code") or "")}
        if water_ratio > 0.005:
            feat["water_area_ratio"] = round(water_ratio, 4)
        for f, v in vals.items():
            if v > 0.005:
                feat[f] = round(v, 4)
        if dem is not None and code in polys_4326:
            elev, slope_deg = _dem_stats(polys_4326[code], *dem)
            if not math.isnan(elev):
                feat["mean_elevation"] = round(elev, 1)
                feat["slope_mean"] = round(slope_deg, 2)
                feat["mountain_score"] = round(min(1.0, slope_deg / _MOUNT_SLOPE_NORM), 4)
        if len(feat) > 2:
            out_lines.append(json.dumps(feat, ensure_ascii=False))
            have += 1
    out_p.write_text("\n".join(out_lines) + "\n", "utf-8")
    return len(units), have


def main(argv: list[str]) -> int:
    units = Path(argv[1]) if len(argv) > 1 else _DEFAULT_UNITS
    osm = Path(argv[2]) if len(argv) > 2 else _DEFAULT_OSM
    land = Path(argv[3]) if len(argv) > 3 else _DEFAULT_LAND
    dem_dir = Path(argv[4]) if len(argv) > 4 else _DEFAULT_DEM
    out = Path(argv[5]) if len(argv) > 5 else _DEFAULT_OUT
    if not (osm / "gis_osm_adminareas_a_free_1.shp").exists():
        print(f"OSM shp 없음: {osm}")
        return 1
    total, have = build(units, osm, land, dem_dir, out)
    print(f"지형 신호 {have}/{total} 지역(실폴리곤+DEM) → {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
