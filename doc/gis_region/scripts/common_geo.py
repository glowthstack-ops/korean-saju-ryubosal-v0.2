from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

try:
    from pyproj import Transformer
except Exception:  # pragma: no cover
    Transformer = None

ELEMENT_KEYS = ["木", "火", "土", "金", "水"]
ELEMENT_TO_COL = {
    "木": "element_wood",
    "火": "element_fire",
    "土": "element_earth",
    "金": "element_metal",
    "水": "element_water",
}
SIGNAL_TO_COL = {
    "木": "signal_wood",
    "火": "signal_fire",
    "土": "signal_earth",
    "金": "signal_metal",
    "水": "signal_water",
}


def load_rules(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_schema(conn: sqlite3.Connection, schema_path: str | Path) -> None:
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def transformer(src_crs: str | int, dst_crs: str | int):
    if Transformer is None:
        raise RuntimeError("pyproj is required for CRS transformation")
    return Transformer.from_crs(src_crs, dst_crs, always_xy=True)


def xy_to_lonlat(x: float, y: float, src_crs: str | int = 5179) -> Tuple[float, float]:
    tr = transformer(f"EPSG:{src_crs}" if isinstance(src_crs, int) else src_crs, "EPSG:4326")
    lon, lat = tr.transform(x, y)
    return lon, lat


def lonlat_to_xy(lon: float, lat: float, dst_crs: str | int = 5179) -> Tuple[float, float]:
    tr = transformer("EPSG:4326", f"EPSG:{dst_crs}" if isinstance(dst_crs, int) else dst_crs)
    x, y = tr.transform(lon, lat)
    return x, y


def element_vector_for(feature_type: str, rules: Dict[str, Any]) -> Dict[str, float]:
    values = rules.get("feature_type_rules", {}).get(feature_type, {})
    return {e: float(values.get(e, 0.0)) for e in ELEMENT_KEYS}


def bearing_deg(dx: float, dy: float) -> float:
    # North=0, East=90
    deg = math.degrees(math.atan2(dx, dy))
    return (deg + 360.0) % 360.0


def direction_code(bearing: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int(((bearing + 22.5) % 360) // 45)
    return dirs[idx]


def distance_bucket(distance_m: float, rules: Dict[str, Any]) -> tuple[str | None, float]:
    for b in rules.get("distance_buckets", []):
        if distance_m <= float(b["max_m"]):
            return str(b["bucket"]), float(b["influence"])
    return None, 0.0


def insert_feature(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    cols = [
        "feature_id", "feature_type", "feature_subtype", "feature_name", "source_name", "source_feature_id",
        "x_5179", "y_5179", "lon", "lat", "elevation_m", "area_m2", "length_m",
        "element_wood", "element_fire", "element_earth", "element_metal", "element_water",
        "importance", "confidence", "anchor_role", "anchor_index", "parent_feature_id", "raw_props_json",
    ]
    payload = {c: row.get(c) for c in cols}
    conn.execute(
        f"INSERT OR REPLACE INTO external_geo_feature ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        [payload[c] for c in cols],
    )


def normalize_source_id(text: Any) -> str:
    s = str(text or "unknown").strip().replace(" ", "_")
    return "".join(ch for ch in s if ch.isalnum() or ch in "_-.")[:80] or "unknown"
