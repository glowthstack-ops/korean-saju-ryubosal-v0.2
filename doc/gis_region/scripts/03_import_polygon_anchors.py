#!/usr/bin/env python3
"""Convert polygon geometries such as forest patches, lakes, wetlands to centroid/on-surface features."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from common_geo import element_vector_for, ensure_schema, insert_feature, normalize_source_id, xy_to_lonlat

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SCHEMA = ROOT / "schema" / "external_geo_feature_schema.sql"
RULES = ROOT / "config" / "feature_element_rules.json"


def main() -> int:
    try:
        import geopandas as gpd
    except Exception as e:  # pragma: no cover
        raise RuntimeError("geopandas is required: pip install geopandas pyogrio shapely") from e

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--feature-type", required=True, choices=["lake_centroid", "wetland_centroid", "forest_patch", "park_green"])
    parser.add_argument("--name-field", default=None)
    parser.add_argument("--source-name", default="polygon_source")
    parser.add_argument("--min-area-m2", type=float, default=0.0)
    parser.add_argument("--src-crs", default=None)
    args = parser.parse_args()

    gdf = gpd.read_file(args.input)
    if args.src_crs:
        gdf = gdf.set_crs(args.src_crs, allow_override=True)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:5179", allow_override=True)
    gdf = gdf.to_crs("EPSG:5179")

    with open(RULES, "r", encoding="utf-8") as f:
        rules = json.load(f)
    ev = element_vector_for(args.feature_type, rules)

    conn = sqlite3.connect(args.output)
    ensure_schema(conn, SCHEMA)
    count = 0
    for row_idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        area = float(geom.area)
        if area < args.min_area_m2:
            continue
        p = geom.representative_point()
        x, y = float(p.x), float(p.y)
        lon, lat = xy_to_lonlat(x, y, 5179)
        name = str(row[args.name_field]) if args.name_field and args.name_field in row else None
        fid = f"{args.source_name.upper()}_{args.feature_type.upper()}_{normalize_source_id(row_idx)}"
        insert_feature(conn, {
            "feature_id": fid,
            "feature_type": args.feature_type,
            "feature_name": name,
            "source_name": args.source_name,
            "source_feature_id": normalize_source_id(row_idx),
            "x_5179": x,
            "y_5179": y,
            "lon": lon,
            "lat": lat,
            "area_m2": area,
            "element_wood": ev["木"],
            "element_fire": ev["火"],
            "element_earth": ev["土"],
            "element_metal": ev["金"],
            "element_water": ev["水"],
            "importance": min(1.5, max(0.3, area / 1_000_000.0)),
            "confidence": 0.75,
            "anchor_role": "polygon_representative_point",
            "anchor_index": 0,
            "raw_props_json": json.dumps({str(k): str(v) for k, v in row.items() if k != "geometry"}, ensure_ascii=False),
        })
        count += 1
    conn.commit()
    conn.close()
    print(f"Created {count} {args.feature_type} polygon anchors into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
