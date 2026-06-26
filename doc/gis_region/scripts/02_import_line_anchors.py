#!/usr/bin/env python3
"""Convert line geometries such as rivers or coastline to anchor point features."""
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
    parser.add_argument("--feature-type", required=True, choices=["river_anchor", "stream_anchor", "coast_anchor", "ridge_anchor", "valley_anchor"])
    parser.add_argument("--name-field", default=None)
    parser.add_argument("--source-name", default="line_source")
    parser.add_argument("--interval-m", type=float, default=1000.0)
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
        parts = list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
        name = str(row[args.name_field]) if args.name_field and args.name_field in row else None
        parent_id = f"{args.source_name.upper()}_{normalize_source_id(row_idx)}"
        for part_idx, line in enumerate(parts):
            length = float(line.length)
            if length <= 0:
                continue
            n = max(1, int(length // args.interval_m))
            distances = [min(length, i * args.interval_m) for i in range(n + 1)]
            if distances[-1] < length:
                distances.append(length)
            for anchor_idx, d in enumerate(distances):
                p = line.interpolate(d)
                x, y = float(p.x), float(p.y)
                lon, lat = xy_to_lonlat(x, y, 5179)
                fid = f"{parent_id}_{part_idx:03d}_{anchor_idx:05d}"
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
                    "length_m": length,
                    "element_wood": ev["木"],
                    "element_fire": ev["火"],
                    "element_earth": ev["土"],
                    "element_metal": ev["金"],
                    "element_water": ev["水"],
                    "importance": 1.0,
                    "confidence": 0.80,
                    "anchor_role": "line_anchor",
                    "anchor_index": anchor_idx,
                    "parent_feature_id": parent_id,
                    "raw_props_json": json.dumps({str(k): str(v) for k, v in row.items() if k != "geometry"}, ensure_ascii=False),
                })
                count += 1
    conn.commit()
    conn.close()
    print(f"Created {count} {args.feature_type} anchors into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
