"""P4-SearchSeed 5단계 — 검색 feature → 읍면동 방위 요약(docs/12).

deduped 검색 feature(lon/lat)와 region_unit anchor(lon/lat)를 동일 등거리 평면으로 투영해
거리·방위·버킷을 계산한다(pyproj 불필요). 산출은 DirectionalFeatureAdapter가 소비하는 표준
스냅샷(json) + 사람 검토용 CSV. 검색 기반이라 provisional — compiled 운영본 자동 덮어쓰기 금지
(기본 search_seed 디렉토리에 출력, 검수 후 수동 승격).

입력: external_geo_features_search_seed_deduped.csv + region_units_compact.jsonl.
사용법: python scripts/build_search_seed_direction_summary.py [deduped_csv] [units] [out_dir]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from saju_engines.region_directional import build_directional_summaries
from saju_engines.search_seed import project_equirect
from saju_shared_types.region_element import (
    ExternalGeoFeature,
    RegionDirectionalSummarySnapshot,
)

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_SEED_DIR = _REPO / "doc" / "gis" / "search_seed"
_DEFAULT_IN = _SEED_DIR / "external_geo_features_search_seed_deduped.csv"
_DEFAULT_UNITS = _REPO / "doc" / "gis" / "region_units_compact_20230729.jsonl"
_DEFAULT_OUT = _SEED_DIR
_MODEL_VERSION = "region-directional-searchseed-p4.0"
_ELEMENT_KEYS = (("木", "wood"), ("火", "fire"), ("土", "earth"), ("金", "metal"), ("水", "water"))


def _load_buckets() -> list[tuple[float, float]]:
    rules = json.loads(
        (_BACKEND / "dictionaries" / "region" / "region_geo_feature_elements.json")
        .read_text("utf-8")
    )
    return [(float(b["max_m"]), float(b["influence"])) for b in rules["distance_buckets"]]


def _load_features(path: Path) -> list[ExternalGeoFeature]:
    """deduped 검색 CSV → ExternalGeoFeature(lon/lat 등거리 투영 → x/y)."""
    out: list[ExternalGeoFeature] = []
    for r in csv.DictReader(path.read_text("utf-8-sig").splitlines()):
        if not r.get("feature_type"):
            continue
        x, y = project_equirect(float(r["lon"]), float(r["lat"]))
        out.append(ExternalGeoFeature(
            feature_id=r["feature_id"], feature_type=r["feature_type"],
            feature_name=r.get("feature_name", ""), source_name="search_seed",
            x_5179=x, y_5179=y, lon=float(r["lon"]), lat=float(r["lat"]),
            element_wood=float(r.get("element_wood") or 0),
            element_fire=float(r.get("element_fire") or 0),
            element_earth=float(r.get("element_earth") or 0),
            element_metal=float(r.get("element_metal") or 0),
            element_water=float(r.get("element_water") or 0),
            confidence=float(r.get("confidence") or 0.45),
        ))
    return out


def _emd_anchors(units_path: Path) -> list[tuple[str, float, float]]:
    """읍면동 anchor를 동일 등거리 평면으로 투영(검색 feature와 정합)."""
    out: list[tuple[str, float, float]] = []
    for line in units_path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("region_level", "")).lower() != "emd":
            continue
        lon = r.get("anchor_lon") or r.get("centroid_lon")
        lat = r.get("anchor_lat") or r.get("centroid_lat")
        if lon in (None, "") or lat in (None, ""):
            continue
        x, y = project_equirect(float(lon), float(lat))
        out.append((str(r["region_code"]), x, y))
    return out


def main(argv: list[str]) -> int:
    """엔트리포인트. 검색 feature 없으면 graceful(요약 미생성)."""
    in_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_IN
    units_path = Path(argv[2]) if len(argv) > 2 else _DEFAULT_UNITS
    out_dir = Path(argv[3]) if len(argv) > 3 else _DEFAULT_OUT
    if not in_path.exists():
        print(f"deduped 검색 feature 없음: {in_path} — 이전 단계 먼저 실행(스텁 유지)")
        return 0
    if not units_path.exists():
        print(f"입력 없음: {units_path}")
        return 1
    features = _load_features(in_path)
    if not features:
        print("검색 지형 feature 0건 — 요약 미생성")
        return 0
    anchors = _emd_anchors(units_path)
    summaries = build_directional_summaries(anchors, features, _load_buckets())
    snapshot = RegionDirectionalSummarySnapshot(
        model_version=_MODEL_VERSION, source_version="search_seed", reviewed=False,
        region_count=len({s.region_code for s in summaries}), items=summaries,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    json_out = out_dir / "region_directional_summary_search_seed.json"
    json_out.write_text(
        json.dumps(snapshot.model_dump(), ensure_ascii=False, separators=(",", ":")) + "\n",
        "utf-8",
    )
    csv_out = out_dir / "region_directional_summary_search_seed.csv"
    with csv_out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "region_code", "direction_code", "wood_score", "fire_score", "earth_score",
            "metal_score", "water_score", "nearest_mountain_m", "nearest_river_m",
            "nearest_water_m", "nearest_coast_m", "nearest_forest_m", "confidence",
        ])
        for s in summaries:
            writer.writerow([
                s.region_code, s.direction_code, s.wood_score, s.fire_score, s.earth_score,
                s.metal_score, s.water_score, s.nearest_mountain_m, s.nearest_river_m,
                s.nearest_water_m, s.nearest_coast_m, s.nearest_forest_m, s.confidence,
            ])
    print(
        f"검색 기반 방위 요약 {len(summaries)}행({snapshot.region_count}개 읍면동, "
        f"feature {len(features)}개) → {json_out.name}/.csv (provisional — 검수 후 승격)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
