#!/usr/bin/env python3
"""Aggregate region_feature_direction to region_directional_element_summary."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from common_geo import ensure_schema

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SCHEMA = ROOT / "schema" / "external_geo_feature_schema.sql"

DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction-db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()

    src = sqlite3.connect(args.direction_db)
    out = sqlite3.connect(args.output)
    ensure_schema(out, SCHEMA)
    src.row_factory = sqlite3.Row

    region_codes = [r[0] for r in src.execute("SELECT DISTINCT region_code FROM region_feature_direction")]
    count = 0
    for region_code in region_codes:
        for d in DIRECTIONS:
            rows = src.execute(
                """
                SELECT * FROM region_feature_direction
                WHERE region_code = ? AND direction_code = ?
                ORDER BY influence_score DESC, distance_m ASC
                """,
                (region_code, d),
            ).fetchall()
            if not rows:
                continue
            sums = {
                "wood": sum(float(r["signal_wood"] or 0) for r in rows),
                "fire": sum(float(r["signal_fire"] or 0) for r in rows),
                "earth": sum(float(r["signal_earth"] or 0) for r in rows),
                "metal": sum(float(r["signal_metal"] or 0) for r in rows),
                "water": sum(float(r["signal_water"] or 0) for r in rows),
            }
            nearest_mountain = min([r["distance_m"] for r in rows if str(r["feature_type"]).startswith("mountain") or r["feature_type"] == "ridge_anchor"], default=None)
            nearest_river = min([r["distance_m"] for r in rows if r["feature_type"] in ("river_anchor", "stream_anchor")], default=None)
            nearest_water = min([r["distance_m"] for r in rows if r["feature_type"] in ("river_anchor", "stream_anchor", "lake_centroid", "lake_boundary_anchor", "wetland_centroid", "coast_anchor")], default=None)
            nearest_coast = min([r["distance_m"] for r in rows if r["feature_type"] == "coast_anchor"], default=None)
            nearest_forest = min([r["distance_m"] for r in rows if r["feature_type"] in ("forest_patch", "park_green")], default=None)
            top_features = [
                {
                    "feature_id": r["feature_id"],
                    "name": r["feature_name"],
                    "type": r["feature_type"],
                    "distance_m": round(float(r["distance_m"]), 1),
                    "influence": round(float(r["influence_score"]), 3),
                }
                for r in rows[: args.top_n]
            ]
            confidence = sum(float(r["confidence"] or 0.5) * float(r["influence_score"] or 0) for r in rows) / max(1e-9, sum(float(r["influence_score"] or 0) for r in rows))
            out.execute(
                """
                INSERT OR REPLACE INTO region_directional_element_summary
                (region_code, direction_code, wood_score, fire_score, earth_score, metal_score, water_score,
                 nearest_mountain_m, nearest_river_m, nearest_water_m, nearest_coast_m, nearest_forest_m,
                 top_features_json, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    region_code, d, sums["wood"], sums["fire"], sums["earth"], sums["metal"], sums["water"],
                    nearest_mountain, nearest_river, nearest_water, nearest_coast, nearest_forest,
                    json.dumps(top_features, ensure_ascii=False), confidence,
                ),
            )
            count += 1
    out.commit()
    out.close()
    src.close()
    print(f"Created {count} directional summary rows into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
