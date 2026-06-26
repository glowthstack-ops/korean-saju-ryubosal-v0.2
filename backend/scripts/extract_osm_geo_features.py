"""OSM 이산 지형 feature 추출(P5-2, docs/12 §14-10) → external_geo_features.csv.

방향성 지형(산봉우리·하천·호수·해안·산림 + 도로·철도)을 OSM/NE에서 추출해 ExternalGeoFeature
계약(대표 좌표 index)으로 직렬화한다. 면적 비율(P4-Data·Tier B)과 별개의 점·선 feature·방위
경로다. 산출 CSV는 기존 build_region_directional_summary.py가 소비한다.

오행(element_*)은 region_geo_feature_elements.json의 feature_type_rules에서 가져온다(reviewed:
false). **도로·철도(major_road_anchor·railway_anchor)는 매핑이 감수 대기(§14-5)라 element_*=0으로
'운반만' 한다** — feature는 추출하되 오행 미개입(활성은 P5-3 감수 후).

입력(무로그인): OSM south-korea shp(gis_osm_natural/waterways/water_a/landuse/railways/roads),
Natural Earth 해안선. 출력: doc/gis/external_geo_features.csv(gitignore, 재생성 가능).

재생성: python scripts/extract_osm_geo_features.py [osm_dir] [ne_coastline.geojson] [out.csv]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import geopandas as gpd

_REPO = Path(__file__).resolve().parents[2]
_G = _REPO / "doc" / "gis"
_DEFAULT_OSM = _G / "_geo_src" / "osm"
_DEFAULT_COAST = _G / "_geo_src" / "ne_10m_coastline.geojson"
_DEFAULT_OUT = _G / "external_geo_features.csv"
_RULES = (
    _REPO / "backend" / "dictionaries" / "region" / "region_geo_feature_elements.json"
)
_EPSG = 5179
_KR_BBOX = (124.0, 32.0, 132.5, 39.6)
_ELEM_COL = {"木": "element_wood", "火": "element_fire", "土": "element_earth",
             "金": "element_metal", "水": "element_water"}
_COLS = [
    "feature_id", "feature_type", "feature_subtype", "feature_name", "source_name",
    "source_feature_id", "x_5179", "y_5179", "lon", "lat", "elevation_m", "area_m2",
    "length_m", "element_wood", "element_fire", "element_earth", "element_metal",
    "element_water", "importance", "confidence", "anchor_role", "anchor_index",
    "parent_feature_id",
]
_LINE_INTERVAL_M = 2000.0  # 선형(하천·해안·도로·철도) anchor 간격.


def _rules() -> dict[str, dict[str, float]]:
    return json.loads(_RULES.read_text("utf-8"))["feature_type_rules"]


def _row(fid: str, ftype: str, x: float, y: float, *, name: str = "",
         elem: dict[str, float] | None = None, subtype: str = "",
         elevation: float | None = None, conf: float = 0.5,
         anchor_idx: int | None = None) -> dict:
    r = {c: "" for c in _COLS}
    r.update(feature_id=fid, feature_type=ftype, feature_subtype=subtype,
             feature_name=name, source_name="osm", x_5179=round(x, 1), y_5179=round(y, 1),
             importance=1.0, confidence=conf)
    if elevation is not None:
        r["elevation_m"] = round(elevation, 1)
    if anchor_idx is not None:
        r["anchor_index"] = anchor_idx
    for el, col in _ELEM_COL.items():
        r[col] = (elem or {}).get(el, 0.0)
    return r


def _read(osm: Path, layer: str, fclasses: set[str] | None = None) -> gpd.GeoDataFrame:
    g = gpd.read_file(osm / layer)
    if fclasses is not None:
        g = g[g["fclass"].isin(fclasses)]
    g = g[g.geometry.notna()]
    return g.to_crs(_EPSG)


def _line_anchors(geom, interval: float = _LINE_INTERVAL_M):
    """선형 geometry → interval 간격 anchor 점(5179)."""
    lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
    for ln in lines:
        n = max(1, int(ln.length / interval))
        for i in range(n + 1):
            p = ln.interpolate(i * interval)
            yield p.x, p.y, i


def build(
    osm: Path, coast_path: Path, out: Path, *, include_transport: bool = False
) -> dict[str, int]:
    rules = _rules()
    rows: list[dict] = []
    counts: dict[str, int] = {}

    def add(ftype: str, items: list[dict]) -> None:
        rows.extend(items)
        counts[ftype] = counts.get(ftype, 0) + len(items)

    # 산봉우리(점) — natural=peak.
    peaks = _read(osm, "gis_osm_natural_free_1.shp", {"peak"})
    add("mountain_peak", [
        _row(f"PK_{i}", "mountain_peak", g.geometry.x, g.geometry.y,
             name=g.get("name") or "", elem=rules["mountain_peak"], conf=0.6)
        for i, (_, g) in enumerate(peaks.iterrows())
    ])
    # 하천(선) — river/canal anchor.
    rivers = _read(osm, "gis_osm_waterways_free_1.shp", {"river", "canal"})
    riv: list[dict] = []
    for fi, (_, g) in enumerate(rivers.iterrows()):
        for x, y, ai in _line_anchors(g.geometry):
            riv.append(_row(f"RV_{fi}_{ai}", "river_anchor", x, y,
                            name=g.get("name") or "", elem=rules["river_anchor"],
                            anchor_idx=ai))
    add("river_anchor", riv)
    # 호수(폴리곤) — 큰 수역 centroid.
    water = _read(osm, "gis_osm_water_a_free_1.shp")
    water = water[water.geometry.area > 1e5]  # >0.1km²
    add("lake_centroid", [
        _row(f"LK_{i}", "lake_centroid", g.geometry.centroid.x, g.geometry.centroid.y,
             name=g.get("name") or "", elem=rules["lake_centroid"])
        for i, (_, g) in enumerate(water.iterrows())
    ])
    # 산림(폴리곤) — 큰 패치 centroid.
    forest = _read(osm, "gis_osm_landuse_a_free_1.shp", {"forest"})
    forest = forest[forest.geometry.area > 1e6]  # >1km²
    add("forest_patch", [
        _row(f"FR_{i}", "forest_patch", g.geometry.centroid.x, g.geometry.centroid.y,
             name=g.get("name") or "", elem=rules.get("forest_patch", {"木": 0.8, "土": 0.2}))
        for i, (_, g) in enumerate(forest.iterrows())
    ])
    # 해안(선) — NE 해안선 anchor(한국 bbox).
    coast = gpd.read_file(coast_path, bbox=_KR_BBOX).to_crs(_EPSG)
    cst: list[dict] = []
    for fi, (_, g) in enumerate(coast.iterrows()):
        for x, y, ai in _line_anchors(g.geometry):
            cst.append(_row(f"CST_{fi}_{ai}", "coast_anchor", x, y,
                            elem=rules["coast_anchor"], anchor_idx=ai))
    add("coast_anchor", cst)
    # 도로·철도(선) — 기본 제외. 오행 매핑이 감수 대기(§14-5)인데다, 실제 쓰임은 8방위 element
    # 집계가 아니라 road_rush 直충 penalty(P5-3 형국 레이어, 최근접 도로 bearing) — 다른 소비자다.
    # element-directional CSV에 inert 점 수십만개를 넣지 않는다. --with-transport로만 운반 추출.
    if include_transport:
        rail = _read(osm, "gis_osm_railways_free_1.shp", {"rail"})
        rl: list[dict] = []
        for fi, (_, g) in enumerate(rail.iterrows()):
            for x, y, ai in _line_anchors(g.geometry, 3000.0):
                rl.append(_row(f"RL_{fi}_{ai}", "railway_anchor", x, y,
                               subtype="rail", anchor_idx=ai, conf=0.4))
        add("railway_anchor", rl)
        roads = _read(osm, "gis_osm_roads_free_1.shp", {"motorway", "trunk", "primary"})
        rd: list[dict] = []
        for fi, (_, g) in enumerate(roads.iterrows()):
            for x, y, ai in _line_anchors(g.geometry, 3000.0):
                rd.append(_row(f"RD_{fi}_{ai}", "major_road_anchor", x, y,
                               subtype=str(g.get("fclass") or ""), anchor_idx=ai, conf=0.4))
        add("major_road_anchor", rd)

    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLS)
        w.writeheader()
        w.writerows(rows)
    counts["_total"] = len(rows)
    return counts


def main(argv: list[str]) -> int:
    transport = "--with-transport" in argv
    args = [a for a in argv if not a.startswith("--")]
    osm = Path(args[1]) if len(args) > 1 else _DEFAULT_OSM
    coast = Path(args[2]) if len(args) > 2 else _DEFAULT_COAST
    out = Path(args[3]) if len(args) > 3 else _DEFAULT_OUT
    if not (osm / "gis_osm_natural_free_1.shp").exists():
        print(f"OSM shp 없음: {osm}")
        return 1
    counts = build(osm, coast, out, include_transport=transport)
    print(f"이산 feature 추출 → {out.name}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
