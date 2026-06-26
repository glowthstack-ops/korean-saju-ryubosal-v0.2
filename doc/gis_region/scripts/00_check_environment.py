#!/usr/bin/env python3
"""Check optional GIS dependencies for the procurement pipeline."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys

REQUIRED = ["pandas", "pyproj"]
OPTIONAL_GIS = ["geopandas", "shapely", "fiona", "pyogrio"]


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    print("Python:", sys.version)
    print("sqlite3:", sqlite3.sqlite_version)
    missing_required = []
    for name in REQUIRED:
        ok = has_module(name)
        print(f"{name}: {'OK' if ok else 'MISSING'}")
        if not ok:
            missing_required.append(name)
    for name in OPTIONAL_GIS:
        print(f"{name}: {'OK' if has_module(name) else 'optional missing'}")
    if missing_required:
        print("\nInstall required dependencies, for example:")
        print("pip install pandas pyproj")
        return 1
    if not has_module("geopandas"):
        print("\nFor SHP/GPKG conversion install optional GIS stack:")
        print("pip install geopandas shapely pyproj pyogrio openpyxl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
