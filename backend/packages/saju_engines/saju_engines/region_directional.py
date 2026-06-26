"""읍면동 × 8방위 주변 지형 오행 집계(공유 코어, docs/12 §4-4·§6).

build_region_directional_summary.py(EPSG:5179 평면)와 P4-SearchSeed(lon/lat 등거리 투영)가 공유한다.
좌표계는 호출부가 평면 x/y로 통일해 넘기고(둘 다 미터 단위), 여기서는 거리·bearing·버킷·오행 집계만
한다. anchor·feature 모두 동일 평면으로 투영돼 있어야 거리/방위가 정합한다.
"""

from __future__ import annotations

import math
from collections import defaultdict

from saju_shared_types.region_element import (
    ExternalGeoFeature,
    RegionDirectionalElementSummary,
    RegionDirectionalTopFeature,
)

_DIR_CODES = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_MAX_RADIUS_M = 10000.0
_GRID_M = 10000.0  # prefilter 셀(=최대 반경). 인접 ±1셀만 검사.
_ELEMENT_COLS = (
    ("木", "wood"), ("火", "fire"), ("土", "earth"), ("金", "metal"), ("水", "water"),
)
# nearest_* 카테고리 판정(feature_type → 분류).
_NEAREST = {
    "mountain": lambda t: t.startswith("mountain") or t == "ridge_anchor",
    "river": lambda t: t in ("river_anchor", "stream_anchor"),
    "water": lambda t: t in (
        "river_anchor", "stream_anchor", "lake_centroid",
        "lake_boundary_anchor", "wetland_centroid", "coast_anchor",
    ),
    "coast": lambda t: t == "coast_anchor",
    "forest": lambda t: t in ("forest_patch", "park_green"),
}


def direction_code(dx: float, dy: float) -> str:
    """평면 변위 → 8방위 코드(N=0/E=90, atan2(dx,dy))."""
    bearing = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    return _DIR_CODES[int((bearing + 22.5) % 360.0 // 45.0)]


def influence(distance_m: float, buckets: list[tuple[float, float]]) -> float | None:
    """거리 → 버킷 influence(최대 반경 초과면 None). buckets는 (max_m, influence) 오름차순."""
    for max_m, inf in buckets:
        if distance_m <= max_m:
            return inf
    return None


def _round_opt(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def build_directional_summaries(
    anchors: list[tuple[str, float, float]],
    features: list[ExternalGeoFeature],
    buckets: list[tuple[float, float]],
    top_n: int = 5,
) -> list[RegionDirectionalElementSummary]:
    """anchor(code,x,y) × feature(평면 x_5179/y_5179) → 읍면동 × 방위 요약(그리드 prefilter).

    feature.x_5179/y_5179 는 anchor와 동일 평면(미터)으로 투영돼 있어야 한다(5179 또는 등거리).
    signal = feature 오행벡터 × influence × importance. 방위별 합산 + nearest_* + top_features.
    """
    grid: dict[tuple[int, int], list[ExternalGeoFeature]] = defaultdict(list)
    for f in features:
        grid[(int(f.x_5179 // _GRID_M), int(f.y_5179 // _GRID_M))].append(f)

    out: list[RegionDirectionalElementSummary] = []
    for region_code, ax, ay in anchors:
        gx, gy = int(ax // _GRID_M), int(ay // _GRID_M)
        acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        nearest: dict[str, dict[str, float]] = defaultdict(dict)
        ranked: dict[str, list[tuple[float, ExternalGeoFeature, float]]] = defaultdict(list)
        conf_num: dict[str, float] = defaultdict(float)
        conf_den: dict[str, float] = defaultdict(float)
        for cx in (gx - 1, gx, gx + 1):
            for cy in (gy - 1, gy, gy + 1):
                for f in grid.get((cx, cy), ()):
                    dx, dy = f.x_5179 - ax, f.y_5179 - ay
                    dist = math.hypot(dx, dy)
                    if dist > _MAX_RADIUS_M:
                        continue
                    inf = influence(dist, buckets)
                    if inf is None:
                        continue
                    code = direction_code(dx, dy)
                    score = inf * f.importance
                    for _hanja, key in _ELEMENT_COLS:
                        val = getattr(f, f"element_{key}")
                        if val:
                            acc[code][key] += val * score
                    for cat, pred in _NEAREST.items():
                        if pred(f.feature_type):
                            cur = nearest[code].get(cat)
                            if cur is None or dist < cur:
                                nearest[code][cat] = dist
                    ranked[code].append((score, f, dist))
                    conf_num[code] += f.confidence * score
                    conf_den[code] += score
        for code, sums in acc.items():
            top = sorted(ranked[code], key=lambda t: (-t[0], t[2]))[:top_n]
            out.append(RegionDirectionalElementSummary(
                region_code=region_code, direction_code=code,
                wood_score=round(sums.get("wood", 0.0), 4),
                fire_score=round(sums.get("fire", 0.0), 4),
                earth_score=round(sums.get("earth", 0.0), 4),
                metal_score=round(sums.get("metal", 0.0), 4),
                water_score=round(sums.get("water", 0.0), 4),
                nearest_mountain_m=_round_opt(nearest[code].get("mountain")),
                nearest_river_m=_round_opt(nearest[code].get("river")),
                nearest_water_m=_round_opt(nearest[code].get("water")),
                nearest_coast_m=_round_opt(nearest[code].get("coast")),
                nearest_forest_m=_round_opt(nearest[code].get("forest")),
                top_features=[
                    RegionDirectionalTopFeature(
                        feature_id=f.feature_id, name=f.feature_name, type=f.feature_type,
                        distance_m=round(dist, 1), influence=round(score, 3),
                    )
                    for score, f, dist in top
                ],
                confidence=round(conf_num[code] / conf_den[code], 4) if conf_den[code] else 0.0,
            ))
    out.sort(key=lambda s: (s.region_code, s.direction_code))
    return out
