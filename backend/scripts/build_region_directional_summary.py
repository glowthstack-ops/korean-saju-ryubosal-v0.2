"""읍면동 방위별 주변 지형 오행 요약 빌드 (v2.2 P4-Data, docs/12 §4-4·§4-5·§6).

외부 지형 feature 대표 좌표(external_geo_feature — doc/gis_region 툴킷이 원본 SHP에서 추출)와
region_units_compact의 읍면동 anchor를 결합해 **읍면동 × 8방위 주변 지형 오행**을 사전계산한다.
'주변 어느 방향에 산/물'은 사용자 무관 고정 사실이므로 사전계산 가능(§4-4가 금지하는 '사용자 기준
이동 방위 적합 저장'과 다름 — 별도 summary).

산식(doc/gis_region 규약과 정렬): bearing=atan2(dx,dy) N=0/E=90, 8방위, 거리 버킷
(1/3/5/10km)별 influence 감쇠, signal=feature 오행벡터×influence×importance, 방위별 합산 +
nearest_* + top_features. 좌표는 EPSG:5179 평면(거리·방위 평면 근사로 충분).

입력(대용량·gitignore): doc/gis/external_geo_features.csv(미공급 시 graceful 종료 — 스텁) +
region anchor doc/gis/region_units_compact_20230729.jsonl.
출력(git 추적): compiled/region_directional_summary_v1.json.

사용법: python scripts/build_region_directional_summary.py [features_csv] [units] [compiled_dir]
종료 0=성공/입력 없음(스텁), 1=치명 오류.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from saju_engines.region_directional import build_directional_summaries
from saju_shared_types.region_element import (
    ExternalGeoFeature,
    RegionDirectionalSummarySnapshot,
)

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_DEFAULT_FEATURES = _REPO / "doc" / "gis" / "external_geo_features.csv"
_DEFAULT_UNITS = _REPO / "doc" / "gis" / "region_units_compact_20230729.jsonl"
_DEFAULT_COMPILED = _BACKEND / "compiled"
_MODEL_VERSION = "region-directional-p4.0"

def _load_buckets() -> list[tuple[float, float]]:
    """거리 버킷 (max_m, influence) 오름차순 로드."""
    rules = json.loads(
        (_BACKEND / "dictionaries" / "region" / "region_geo_feature_elements.json")
        .read_text("utf-8")
    )
    return [(float(b["max_m"]), float(b["influence"])) for b in rules["distance_buckets"]]


def _load_features(path: Path) -> list[ExternalGeoFeature]:
    """external_geo_feature.csv 로드(부재 시 빈 리스트)."""
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.read_text("utf-8-sig").splitlines()))
    out: list[ExternalGeoFeature] = []
    for r in rows:
        clean = {k: v for k, v in r.items() if v not in (None, "")}
        out.append(ExternalGeoFeature.model_validate(clean))
    return out


def _emd_anchors(units_path: Path) -> list[tuple[str, float, float]]:
    """읍면동 (region_code, anchor_x_5179, anchor_y_5179) — anchor 없으면 centroid 폴백."""
    out: list[tuple[str, float, float]] = []
    for line in units_path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("region_level", "")).lower() != "emd":
            continue
        x = r.get("anchor_x_5179") or r.get("centroid_x_5179")
        y = r.get("anchor_y_5179") or r.get("centroid_y_5179")
        if x in (None, "") or y in (None, ""):
            continue
        out.append((str(r["region_code"]), float(x), float(y)))
    return out


def main(argv: list[str]) -> int:
    """엔트리포인트. external_geo_feature 없으면 스텁(요약 미생성)으로 정상 종료."""
    features_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_FEATURES
    units_path = Path(argv[2]) if len(argv) > 2 else _DEFAULT_UNITS
    compiled_dir = Path(argv[3]) if len(argv) > 3 else _DEFAULT_COMPILED

    features = _load_features(features_path)
    if not features:
        print(f"외부 지형 feature 없음: {features_path} — 방향성 요약 미생성(스텁 상태 유지)")
        return 0
    if not units_path.exists():
        print(f"입력 없음: {units_path}")
        return 1

    anchors = _emd_anchors(units_path)
    summaries = build_directional_summaries(anchors, features, _load_buckets())
    snapshot = RegionDirectionalSummarySnapshot(
        model_version=_MODEL_VERSION,
        source_version=features_path.stem,
        reviewed=False,
        region_count=len({s.region_code for s in summaries}),
        items=summaries,
    )
    compiled_dir.mkdir(parents=True, exist_ok=True)
    out = compiled_dir / "region_directional_summary_v1.json"
    out.write_text(
        json.dumps(snapshot.model_dump(), ensure_ascii=False, separators=(",", ":")) + "\n",
        "utf-8",
    )
    print(
        f"방향성 요약 {len(summaries)}행({snapshot.region_count}개 읍면동) 저장 → {out.name} "
        f"(feature {len(features)}개)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
