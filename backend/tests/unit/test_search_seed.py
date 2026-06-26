"""P4-SearchSeed 파이프라인 검증(docs/12) — 네트워크 없이 오프라인 전수.

쿼리 생성·feature_type 분류(오탐 거름)·중복 병합·방위 요약·fetch(주입 provider)를 검증한다.
실제 API는 키 필요라 fake provider로 격리. 검색 기반은 confidence 낮음·review_status 강제.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from saju_engines.search_seed import (
    QUERY_KEYWORDS,
    SearchSeedFeature,
    classify_feature_type,
    dedupe,
    project_equirect,
)

_BACKEND = Path(__file__).resolve().parents[2]
_SCRIPTS = _BACKEND / "scripts"
# 청운동 anchor(실측 lon/lat) — 방위 정합 기준.
_ANCHOR_LON, _ANCHOR_LAT = 126.96977, 37.58904


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ── 분류 ─────────────────────────────────────────────────────────


def test_classify_geo_types() -> None:
    """대표 지형명·카테고리 → 올바른 feature_type."""
    assert classify_feature_type("북악산", "여행 > 관광,명소 > 산")[0] == "mountain_peak"
    assert classify_feature_type("청계천", "여행 > 하천")[0] == "river_anchor"
    assert classify_feature_type("팔당호", "여행 > 관광,명소 > 호수")[0] == "lake_centroid"
    assert classify_feature_type("인천항", "교통,수송 > 항구")[0] == "port"
    assert classify_feature_type("올림픽공원", "여행 > 공원")[0] == "park_green"


def test_classify_rejects_non_geo() -> None:
    """식당·카페 오탐(이름에 산/계곡 포함)은 reject."""
    assert classify_feature_type("계곡가든", "음식점 > 한식")[0] is None
    assert classify_feature_type("북한산카페", "음식점 > 카페")[0] is None


def test_classify_matched_by_strength() -> None:
    """카테고리 매칭=category(강), 이름만=name(중)."""
    assert classify_feature_type("도봉산", "여행 > 산")[1] == "category"
    assert classify_feature_type("어떤동산", "")[1] in ("name", "query", "rejected")


# ── 중복 병합 ────────────────────────────────────────────────────


def _feat(
    fid: str, name: str, lon: float, lat: float, ftype: str, region: str
) -> SearchSeedFeature:
    return SearchSeedFeature(
        feature_id=fid, feature_name=name, feature_type=ftype, lon=lon, lat=lat,
        region_name_ko=region, element_earth=0.75, element_wood=0.25, confidence=0.7,
    )


def test_dedupe_merges_same_place() -> None:
    """같은 이름 + 300m 이내 + 같은 type → 병합(source_count↑·confidence↑·지역 합산)."""
    feats = [
        _feat("A", "북악산", 126.9671, 37.5926, "mountain_peak", "종로구"),
        _feat("B", "북악산", 126.9673, 37.5927, "mountain_peak", "부암동"),  # ~25m
        _feat("C", "인왕산", 126.9590, 37.5860, "mountain_peak", "종로구"),
    ]
    merged = dedupe(feats)
    assert len(merged) == 2  # 북악산 병합 + 인왕산
    bukak = next(m for m in merged if m.feature_name == "북악산")
    assert bukak.source_count == 2
    assert bukak.confidence > 0.7  # 중복 보너스
    assert "종로구" in bukak.matched_regions and "부암동" in bukak.matched_regions


def test_dedupe_keeps_distant_same_name() -> None:
    """이름 같아도 300m 초과면 별개 feature."""
    feats = [
        _feat("A", "중앙공원", 127.0, 37.5, "park_green", "가"),
        _feat("B", "중앙공원", 127.1, 37.6, "park_green", "나"),  # 수 km
    ]
    assert len(dedupe(feats)) == 2


# ── 쿼리 생성 ────────────────────────────────────────────────────


def test_build_queries_sigungu_only(tmp_path: Path) -> None:
    """시군구만 × 키워드 쿼리 생성(읍면동 전수 금지)."""
    units = tmp_path / "u.jsonl"
    units.write_text(
        json.dumps({"region_code": "11", "region_level": "ctprvn", "full_name_ko": "서울"}) + "\n"
        + json.dumps({"region_code": "11110", "region_level": "sig",
                      "full_name_ko": "서울특별시 종로구"}) + "\n"
        + json.dumps({"region_code": "11110101", "region_level": "emd",
                      "full_name_ko": "서울특별시 종로구 청운동"}) + "\n",
        "utf-8",
    )
    mod = _load_script("build_search_seed_queries")
    rows = mod.build_queries(units)
    assert len(rows) == len(QUERY_KEYWORDS)  # sig 1개만
    assert all(r["region_level"] == "sig" for r in rows)
    assert any(r["query"] == "서울특별시 종로구 산" for r in rows)


# ── fetch(주입 provider) ─────────────────────────────────────────


def test_fetch_with_fake_provider(tmp_path: Path) -> None:
    """provider 주입으로 네트워크 없이 수집 — raw 행/ missing 처리."""
    mod = _load_script("fetch_search_seed_features")
    queries = [
        {"query": "서울특별시 종로구 산", "region_code": "11110", "region_level": "sig",
         "region_name_ko": "서울특별시 종로구"},
        {"query": "없는지역 항구", "region_code": "99999", "region_level": "sig",
         "region_name_ko": "없는지역"},
    ]

    def fake(q: str) -> list[dict]:
        if q.endswith("산"):
            return [{"place_name": "북악산", "category_name": "여행 > 산",
                     "x": "126.9671", "y": "37.5926"}]
        return []  # missing

    rows, missing = mod.fetch(queries, fake)
    assert len(rows) == 1 and rows[0]["feature_name"] == "북악산"
    assert rows[0]["source"] == "search_seed"
    assert missing == ["없는지역 항구"]


def test_fetch_no_key_graceful(tmp_path: Path, monkeypatch) -> None:
    """API 키 없으면 graceful 종료(0) — 오류 아님."""
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    queries = tmp_path / "q.csv"
    queries.write_text("region_code,region_level,region_name_ko,keyword,query\n"
                       "11110,sig,서울특별시 종로구,산,서울특별시 종로구 산\n", "utf-8")
    mod = _load_script("fetch_search_seed_features")
    assert mod.main(["x", str(queries), str(tmp_path / "out.csv")]) == 0


# ── 방위 요약(e2e) ───────────────────────────────────────────────


def test_direction_summary_from_search(tmp_path: Path) -> None:
    """deduped 검색 feature(lon/lat) → 읍면동 방위 요약(북쪽 산 → N 土 우세)."""
    # 청운동 북쪽 ~2.2km에 산(土) 배치.
    deduped = tmp_path / "deduped.csv"
    cols = list(SearchSeedFeature.model_fields)
    feat = SearchSeedFeature(
        feature_id="M1", feature_name="테스트산", feature_type="mountain_peak",
        lon=_ANCHOR_LON, lat=_ANCHOR_LAT + 0.02, element_earth=0.75, element_wood=0.25,
        confidence=0.7,
    )
    with deduped.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        row = feat.model_dump()
        row["matched_regions"] = json.dumps(row["matched_regions"], ensure_ascii=False)
        w.writerow(row)
    units = tmp_path / "u.jsonl"
    units.write_text(json.dumps({
        "region_code": "11110101", "region_level": "emd",
        "anchor_lon": _ANCHOR_LON, "anchor_lat": _ANCHOR_LAT,
    }) + "\n", "utf-8")

    mod = _load_script("build_search_seed_direction_summary")
    assert mod.main(["x", str(deduped), str(units), str(tmp_path)]) == 0
    snap = json.loads((tmp_path / "region_directional_summary_search_seed.json").read_text("utf-8"))
    rows = [s for s in snap["items"] if s["region_code"] == "11110101"]
    north = next(s for s in rows if s["direction_code"] == "N")
    assert north["earth_score"] > north["wood_score"]  # 산=土 우세
    assert north["nearest_mountain_m"] is not None


def test_projection_consistency() -> None:
    """등거리 투영은 같은 위도에서 동일 lat→동일 y(거리 정합)."""
    x1, y1 = project_equirect(127.0, 37.5)
    x2, y2 = project_equirect(127.1, 37.5)
    assert abs(y1 - y2) < 1e-6 and x2 > x1  # 동쪽으로 x 증가
