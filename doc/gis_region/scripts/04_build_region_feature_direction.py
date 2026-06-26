#!/usr/bin/env python3
"""Build region_feature_direction from region_unit and external_geo_feature."""
from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path

from common_geo import bearing_deg, direction_code, distance_bucket, ensure_schema, load_rules

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SCHEMA = ROOT / "schema" / "external_geo_feature_schema.sql"
RULES = ROOT / "config" / "feature_element_rules.json"

FEATURE_COLS = ["element_wood", "element_fire", "element_earth", "element_metal", "element_water"]
SIGNAL_COLS = ["signal_wood", "signal_fire", "signal_earth", "signal_metal", "signal_water"]


def attach_features(conn: sqlite3.Connection, features_db: Path) -> None:
    conn.execute("ATTACH DATABASE ? AS feat", (str(features_db),))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region-db", required=True, help="region_spatial_engine_p0 sqlite path")
    parser.add_argument("--features-db", required=True, help="sqlite path containing external_geo_feature")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-distance-m", type=float, default=10000.0)
    args = parser.parse_args()

    rules = load_rules(RULES)
    out = sqlite3.connect(args.output)
    ensure_schema(out, SCHEMA)
    out.execute("ATTACH DATABASE ? AS reg", (args.region_db,))
    out.execute("ATTACH DATABASE ? AS feat", (args.features_db,))

    regions = out.execute(
        """
        SELECT region_code, anchor_x_5179, anchor_y_5179
        FROM reg.region_unit
        WHERE region_level = 'emd'
        """
    ).fetchall()
    features = out.execute(
        """
        SELECT feature_id, feature_type, feature_name, x_5179, y_5179,
               element_wood, element_fire, element_earth, element_metal, element_water,
               importance, confidence
        FROM feat.external_geo_feature
        """
    ).fetchall()

    inserted = 0
    for region_code, rx, ry in regions:
        if rx is None or ry is None:
            continue
        for f in features:
            fid, ftype, fname, fx, fy, ew, ef, ee, em, ewater, importance, conf = f
            dx = float(fx) - float(rx)
            dy = float(fy) - float(ry)
            dist = math.hypot(dx, dy)
            if dist > args.max_distance_m:
                continue
            bucket, influence = distance_bucket(dist, rules)
            if not bucket:
                continue
            brg = bearing_deg(dx, dy)
            dcode = direction_code(brg)
            weight = float(influence) * float(importance or 1.0)
            out.execute(
                """
                INSERT OR REPLACE INTO region_feature_direction
                (region_code, feature_id, feature_type, feature_name, distance_m, bearing_deg,
                 direction_code, radius_bucket, signal_wood, signal_fire, signal_earth,
                 signal_metal, signal_water, influence_score, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    region_code, fid, ftype, fname, dist, brg, dcode, bucket,
                    float(ew or 0) * weight, float(ef or 0) * weight, float(ee or 0) * weight,
                    float(em or 0) * weight, float(ewater or 0) * weight, weight, float(conf or 0.5),
                ),
            )
            inserted += 1
    out.commit()
    out.close()
    print(f"Inserted {inserted} region-feature direction rows into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
