#!/usr/bin/env python3
"""Import point POI data into external_geo_feature.

This script is intentionally tolerant because public POI downloads often vary in
column names. Configure mappings in config/source_file_mapping_template.yaml.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from common_geo import element_vector_for, ensure_schema, insert_feature, lonlat_to_xy, normalize_source_id, xy_to_lonlat

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SCHEMA = ROOT / "schema" / "external_geo_feature_schema.sql"
RULES = ROOT / "config" / "feature_element_rules.json"

CATEGORY_MAP = {
    "산": "mountain_peak",
    "봉우리": "mountain_peak",
    "고개": "mountain_pass",
    "계곡": "valley_anchor",
    "항구": "port",
    "포구": "port",
    "공원": "park_green",
}


def find_col(cols, candidates):
    normalized = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        key = cand.strip().lower()
        if key in normalized:
            return normalized[key]
    return None


def infer_feature_type(category: str, name: str) -> str | None:
    text = f"{category or ''} {name or ''}"
    for keyword, ftype in CATEGORY_MAP.items():
        if keyword in text:
            return ftype
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-name", default="ngii_poi")
    parser.add_argument("--src-crs", default="auto", help="EPSG code, 4326, 5179, or auto")
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(input_path)
    else:
        df = pd.read_csv(input_path)

    x_col = find_col(df.columns, ["x", "X", "xpos", "pos_x", "경도", "lon", "longitude"])
    y_col = find_col(df.columns, ["y", "Y", "ypos", "pos_y", "위도", "lat", "latitude"])
    name_col = find_col(df.columns, ["name", "NAME", "명칭", "poi_nm", "POI_NM"])
    cat_col = find_col(df.columns, ["category", "CATEGORY", "분류", "대분류", "중분류", "소분류"])
    if x_col is None or y_col is None:
        raise ValueError(f"Could not find coordinate columns in {list(df.columns)}")

    with open(RULES, "r", encoding="utf-8") as f:
        rules = json.load(f)

    conn = sqlite3.connect(args.output)
    ensure_schema(conn, SCHEMA)
    count = 0
    for i, r in df.iterrows():
        name = str(r[name_col]) if name_col else ""
        category = str(r[cat_col]) if cat_col else ""
        feature_type = infer_feature_type(category, name)
        if not feature_type:
            continue
        a = float(r[x_col])
        b = float(r[y_col])
        if args.src_crs == "4326" or (args.src_crs == "auto" and -180 <= a <= 180 and -90 <= b <= 90):
            lon, lat = a, b
            x, y = lonlat_to_xy(lon, lat)
        else:
            x, y = a, b
            lon, lat = xy_to_lonlat(x, y, int(args.src_crs) if args.src_crs != "auto" else 5179)
        ev = element_vector_for(feature_type, rules)
        fid = f"{args.source_name.upper()}_{feature_type.upper()}_{i:08d}"
        insert_feature(conn, {
            "feature_id": fid,
            "feature_type": feature_type,
            "feature_name": name,
            "source_name": args.source_name,
            "source_feature_id": normalize_source_id(r.get("id", i)),
            "x_5179": x,
            "y_5179": y,
            "lon": lon,
            "lat": lat,
            "element_wood": ev["木"],
            "element_fire": ev["火"],
            "element_earth": ev["土"],
            "element_metal": ev["金"],
            "element_water": ev["水"],
            "importance": 1.0,
            "confidence": 0.65,
            "anchor_role": "point",
            "anchor_index": 0,
            "raw_props_json": json.dumps({str(k): str(v) for k, v in r.items()}, ensure_ascii=False),
        })
        count += 1
    conn.commit()
    conn.close()
    print(f"Imported {count} point features into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
