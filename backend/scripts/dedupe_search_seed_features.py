"""P4-SearchSeed 4단계 — 검색 중복 병합(docs/12).

같은 이름 + 300m 이내 + 같은 feature_type을 한 feature로 병합하고, 출처 수(source_count)·
매칭 지역을 합쳐 confidence를 보정한다(중복 출처 2+ → +0.10). 오탐(rejected)은 제외.

입력: external_geo_features_search_seed.csv. 출력: external_geo_features_search_seed_deduped.csv.
사용법: python scripts/dedupe_search_seed_features.py [classified_csv] [out_csv]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from saju_engines.search_seed import SearchSeedFeature, dedupe

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_SEED_DIR = _REPO / "doc" / "gis" / "search_seed"
_DEFAULT_IN = _SEED_DIR / "external_geo_features_search_seed.csv"
_DEFAULT_OUT = _SEED_DIR / "external_geo_features_search_seed_deduped.csv"
_OUT_COLS = list(SearchSeedFeature.model_fields)


def load_features(path: Path, include_rejected: bool = False) -> list[SearchSeedFeature]:
    """분류 CSV → SearchSeedFeature 목록(기본 rejected 제외)."""
    rows = list(csv.DictReader(path.read_text("utf-8-sig").splitlines()))
    out: list[SearchSeedFeature] = []
    for r in rows:
        if not include_rejected and r.get("review_status") == "rejected":
            continue
        if not r.get("feature_type"):
            continue
        data = dict(r)
        mr = data.get("matched_regions", "")
        data["matched_regions"] = json.loads(mr) if mr else []
        out.append(SearchSeedFeature.model_validate(data))
    return out


def main(argv: list[str]) -> int:
    """엔트리포인트."""
    in_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_IN
    out = Path(argv[2]) if len(argv) > 2 else _DEFAULT_OUT
    if not in_path.exists():
        print(f"입력 없음: {in_path} — classify_search_seed_features.py 먼저 실행")
        return 1
    feats = load_features(in_path)
    merged = dedupe(feats)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_OUT_COLS)
        writer.writeheader()
        for f in merged:
            row = f.model_dump()
            row["matched_regions"] = json.dumps(row["matched_regions"], ensure_ascii=False)
            writer.writerow(row)
    print(f"중복 병합 {len(feats)}→{len(merged)}건 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
