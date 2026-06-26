#!/usr/bin/env python3
"""Merge multiple SQLite files containing external_geo_feature into one DB."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from common_geo import ensure_schema

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SCHEMA = ROOT / "schema" / "external_geo_feature_schema.sql"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = sqlite3.connect(args.output)
    ensure_schema(out, SCHEMA)
    total = 0
    for i, input_path in enumerate(args.inputs):
        alias = f"src{i}"
        out.execute(f"ATTACH DATABASE ? AS {alias}", (input_path,))
        cols = [r[1] for r in out.execute("PRAGMA table_info(external_geo_feature)").fetchall()]
        out.execute(
            f"INSERT OR REPLACE INTO external_geo_feature ({', '.join(cols)}) SELECT {', '.join(cols)} FROM {alias}.external_geo_feature"
        )
        total += out.execute(f"SELECT COUNT(*) FROM {alias}.external_geo_feature").fetchone()[0]
        out.execute(f"DETACH DATABASE {alias}")
    out.commit()
    print(f"Merged up to {total} feature rows into {args.output}")
    out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
