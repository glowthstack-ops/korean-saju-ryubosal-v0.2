"""방향성 지형 요약(P4-Data) 검증 — docs/12 §4-1·§4-4·§6.

합성 외부 지형 feature(실제 읍면동 anchor에 좌표 정합)로 build_region_directional_summary의 거리·
8방위·버킷·오행 집계를 검증한다. 사용자 §9 규칙: 산=土(무조건 木 아님), 하천=水 다중 anchor,
데이터 없으면 available=False(감점 금지). 좌표는 EPSG:5179 평면.
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

from saju_engines.region_geo_stubs import DirectionalFeatureAdapter
from saju_shared_types.region_element import RegionDirectionalSummarySnapshot

_BACKEND = Path(__file__).resolve().parents[2]
_BUILD = _BACKEND / "scripts" / "build_region_directional_summary.py"
# 청운동 anchor(실측, region_units_compact) — 합성 feature를 이 기준으로 배치한다.
_ANCHOR_X, _ANCHOR_Y = 953188.52, 1954537.22
_REGION = "11110101"


def _load_build_main():
    spec = importlib.util.spec_from_file_location("build_dirsum", _BUILD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.main


def _write_features(path: Path) -> None:
    """청운동 기준 북 2km 산(土)·동 2km 하천 anchor 2개(水)·남 2km 산림(木) 합성."""
    cols = [
        "feature_id", "feature_type", "feature_name", "source_name", "x_5179", "y_5179",
        "element_wood", "element_fire", "element_earth", "element_metal", "element_water",
        "importance", "confidence",
    ]
    rows = [
        # 북(N): y+2000 — 산 → 土 0.75 / 木 0.25
        ["M1", "mountain_peak", "테스트산", "syn", _ANCHOR_X, _ANCHOR_Y + 2000,
         0.25, 0, 0.75, 0, 0, 1, 0.8],
        # 동(E): x+2000 — 하천 anchor 2개(다중 anchor) → 水
        ["R1", "river_anchor", "테스트강", "syn", _ANCHOR_X + 2000, _ANCHOR_Y,
         0, 0, 0, 0, 1.0, 1, 0.85],
        ["R2", "river_anchor", "테스트강", "syn", _ANCHOR_X + 2200, _ANCHOR_Y + 200,
         0, 0, 0, 0, 1.0, 1, 0.85],
        # 남(S): y-2000 — 산림 → 木 0.9 / 土 0.1
        ["F1", "forest_patch", "테스트숲", "syn", _ANCHOR_X, _ANCHOR_Y - 2000,
         0.9, 0, 0.1, 0, 0, 1, 0.7],
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)


def _build(tmp_path: Path) -> RegionDirectionalSummarySnapshot:
    features = tmp_path / "feat.csv"
    _write_features(features)
    out_dir = tmp_path / "compiled"
    main = _load_build_main()
    rc = main(["x", str(features),
               str(_BACKEND.parent / "doc" / "gis" / "region_units_compact_20230729.jsonl"),
               str(out_dir)])
    assert rc == 0
    return RegionDirectionalSummarySnapshot.model_validate_json(
        (out_dir / "region_directional_summary_v1.json").read_text("utf-8")
    )


def test_directions_and_elements(tmp_path: Path) -> None:
    """북=산(土), 동=하천(水), 남=산림(木) — 방위·오행 정합."""
    snap = _build(tmp_path)
    rows = {s.direction_code: s for s in snap.items if s.region_code == _REGION}
    assert "N" in rows and "E" in rows and "S" in rows
    assert rows["N"].earth_score > rows["N"].wood_score  # 산=土 우세(木 아님)
    assert rows["E"].water_score > 0 and rows["E"].nearest_river_m is not None  # 하천=水
    assert rows["S"].wood_score > rows["S"].earth_score  # 산림=木 우세


def test_mountain_is_earth_not_wood(tmp_path: Path) -> None:
    """산은 土 중심 — 산림이 아닌 한 木으로 보지 않는다(§4-1·사용자 §9)."""
    snap = _build(tmp_path)
    north = next(s for s in snap.items if s.region_code == _REGION and s.direction_code == "N")
    assert north.earth_score > 0 and north.earth_score > north.wood_score
    assert any(t.type == "mountain_peak" for t in north.top_features)


def test_river_multiple_anchors_counted(tmp_path: Path) -> None:
    """하천은 대표점 1개로 축약하지 않는다 — 동쪽 anchor 2개가 모두 집계된다."""
    snap = _build(tmp_path)
    east = next(s for s in snap.items if s.region_code == _REGION and s.direction_code == "E")
    river_feats = [t for t in east.top_features if t.type == "river_anchor"]
    assert len(river_feats) == 2  # R1, R2 모두


def test_adapter_consumes_summary(tmp_path: Path) -> None:
    """DirectionalFeatureAdapter가 요약을 읽어 available=True + 방향성 벡터를 만든다."""
    _build(tmp_path)
    summary = tmp_path / "compiled" / "region_directional_summary_v1.json"
    adapter = DirectionalFeatureAdapter(summary)
    res = adapter.evaluate(_REGION)
    assert res.available is True and res.features
    vec = res.directional_element_vector.as_map()
    assert vec["水"] > 0 and vec["土"] > 0 and vec["木"] > 0  # 산·하천·산림 종합


def test_no_features_skips_build(tmp_path: Path) -> None:
    """외부 feature 없으면 요약을 만들지 않는다(스텁 상태 유지, graceful)."""
    empty = tmp_path / "empty.csv"
    empty.write_text("feature_id,feature_type,x_5179,y_5179\n", "utf-8")
    out_dir = tmp_path / "compiled"
    main = _load_build_main()
    rc = main(["x", str(empty),
               str(_BACKEND.parent / "doc" / "gis" / "region_units_compact_20230729.jsonl"),
               str(out_dir)])
    assert rc == 0
    assert not (out_dir / "region_directional_summary_v1.json").exists()
