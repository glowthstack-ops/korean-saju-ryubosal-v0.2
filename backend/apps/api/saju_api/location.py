"""Minimal seed location lookup (MVP).

Resolves a birth place to coordinates + IANA timezone. Explicit lat/lon/tz on the
request always take precedence over the seed DB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_SEED_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "location_db" / "seed_locations.json"
)


@dataclass
class ResolvedLocation:
    name: str
    latitude: float
    longitude: float
    iana_timezone: str
    source: str  # "request" | "seed"


@lru_cache(maxsize=1)
def _seed() -> list[dict]:
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))["locations"]


def resolve(
    place_name: str,
    latitude: float | None,
    longitude: float | None,
    timezone: str | None,
) -> ResolvedLocation:
    if latitude is not None and longitude is not None and timezone:
        return ResolvedLocation(place_name, latitude, longitude, timezone, "request")

    key = place_name.strip().lower()
    for loc in _seed():
        names = [loc["name"].lower(), *(a.lower() for a in loc.get("aliases", []))]
        if key in names:
            return ResolvedLocation(
                name=loc["name"],
                latitude=latitude if latitude is not None else loc["latitude"],
                longitude=longitude if longitude is not None else loc["longitude"],
                iana_timezone=timezone or loc["iana_timezone"],
                source="seed",
            )

    raise ValueError(
        f"cannot resolve birth place '{place_name}': provide latitude, longitude and "
        f"timezone, or use a known seed location"
    )
