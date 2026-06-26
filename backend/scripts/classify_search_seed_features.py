"""P4-SearchSeed 3단계 — 검색 raw → feature_type 분류 + 오행·신뢰도 부여(docs/12).

장소명·카테고리·검색어로 feature_type을 분류하고(비지형은 rejected), feature_type 오행 벡터와
검수 전 신뢰도(카테고리>이름>검색어)를 매긴다. 검색 기반이라 confidence는 공식 GIS보다 낮다.

입력: external_geo_features_search_seed_raw.csv. 출력: external_geo_features_search_seed.csv.
사용법: python scripts/classify_search_seed_features.py [raw_csv] [out_csv]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from saju_engines.search_seed import (
    SearchSeedFeature,
    base_confidence,
    classify_feature_type,
    element_vector_for,
)

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_SEED_DIR = _REPO / "doc" / "gis" / "search_seed"
_DEFAULT_RAW = _SEED_DIR / "external_geo_features_search_seed_raw.csv"
_DEFAULT_OUT = _SEED_DIR / "external_geo_features_search_seed.csv"
_ELEMENT_KEYS = (("木", "wood"), ("火", "fire"), ("土", "earth"), ("金", "metal"), ("水", "water"))
_OUT_COLS = list(SearchSeedFeature.model_fields)


def _rules() -> dict:
    return json.loads(
        (_BACKEND / "dictionaries" / "region" / "region_geo_feature_elements.json")
        .read_text("utf-8")
    )


def classify_rows(raw_rows: list[dict], rules: dict) -> list[SearchSeedFeature]:
    """raw 검색행 → 분류된 SearchSeedFeature(비지형은 rejected로 표기·보존)."""
    out: list[SearchSeedFeature] = []
    for r in raw_rows:
        name = r.get("feature_name", "")
        ftype, matched_by = classify_feature_type(
            name, r.get("category", ""), r.get("search_query", "").split()[-1]
            if r.get("search_query") else "",
        )
        try:
            lon, lat = float(r["lon"]), float(r["lat"])
        except (KeyError, TypeError, ValueError):
            continue
        feat = SearchSeedFeature(
            feature_id=r.get("feature_id", ""),
            search_query=r.get("search_query", ""),
            region_code=r.get("region_code", ""),
            region_level=r.get("region_level", ""),
            region_name_ko=r.get("region_name_ko", ""),
            feature_name=name, lon=lon, lat=lat,
            raw_json=r.get("raw_json", ""),
        )
        if ftype is None:
            feat.review_status = "rejected"
            feat.confidence = 0.0
            out.append(feat)
            continue
        feat.feature_type = ftype
        vec = element_vector_for(ftype, rules)
        for hanja, key in _ELEMENT_KEYS:
            setattr(feat, f"element_{key}", vec.get(hanja, 0.0))
        feat.confidence = round(base_confidence(matched_by), 2)
        feat.review_status = (
            "auto_high_confidence" if matched_by == "category" else "needs_review"
        )
        out.append(feat)
    return out


def main(argv: list[str]) -> int:
    """엔트리포인트."""
    raw_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_RAW
    out = Path(argv[2]) if len(argv) > 2 else _DEFAULT_OUT
    if not raw_path.exists():
        print(f"raw 없음: {raw_path} — fetch_search_seed_features.py 먼저 실행")
        return 1
    raw_rows = list(csv.DictReader(raw_path.read_text("utf-8-sig").splitlines()))
    feats = classify_rows(raw_rows, _rules())
    kept = [f for f in feats if f.review_status != "rejected"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_OUT_COLS)
        writer.writeheader()
        for f in feats:
            row = f.model_dump()
            row["matched_regions"] = json.dumps(row["matched_regions"], ensure_ascii=False)
            writer.writerow(row)
    rejected = len(feats) - len(kept)
    print(f"분류 {len(feats)}건(지형 {len(kept)} / 오탐 rejected {rejected}) → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
