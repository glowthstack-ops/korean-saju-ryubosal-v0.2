"""P4-SearchSeed 2단계 — 검색 쿼리 → 좌표 API로 지형 후보 수집(docs/12).

Kakao Local 키워드 장소 검색으로 쿼리별 장소 후보(이름·카테고리·좌표)를 수집한다. API 키는
환경변수 KAKAO_REST_API_KEY로만 받는다. 키가 없으면 graceful 종료(미수집 — 오류 아님).
검색 실패는 missing으로 기록하고 raw_json을 보존한다. provider는 주입 가능(테스트는 fake provider).

API 정책: 요청 간 간격·재시도·캐시로 부하를 낮춘다(OSM/Kakao 정책 준수). 검색 기반은 오탐이 있어
분류·검수(다음 단계)를 반드시 거친다.

입력: doc/gis/search_seed/search_queries.csv. 출력: external_geo_features_search_seed_raw.csv.
사용법: python scripts/fetch_search_seed_features.py [queries_csv] [out_csv] [--limit N]
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_SEED_DIR = _REPO / "doc" / "gis" / "search_seed"
_DEFAULT_QUERIES = _SEED_DIR / "search_queries.csv"
_DEFAULT_OUT = _SEED_DIR / "external_geo_features_search_seed_raw.csv"
_KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_RATE_SLEEP_S = 0.12  # 요청 간격(정책 준수)
_RETRY = 2
_RAW_COLS = [
    "feature_id", "source", "search_query", "region_code", "region_level",
    "region_name_ko", "feature_name", "category", "lon", "lat", "raw_json",
]

# 검색 provider 타입: query → [{place_name, category_name, x(lon), y(lat)}, ...]
Provider = Callable[[str], list[dict]]


def kakao_provider(api_key: str, size: int = 5) -> Provider:
    """Kakao Local 키워드 검색 provider(재시도 포함). place 상위 size건."""

    def _search(query: str) -> list[dict]:
        params = urllib.parse.urlencode({"query": query, "size": size})
        req = urllib.request.Request(
            f"{_KAKAO_URL}?{params}", headers={"Authorization": f"KakaoAK {api_key}"}
        )
        for attempt in range(_RETRY + 1):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return list(data.get("documents", []))
            except Exception:  # noqa: BLE001 — 실패는 missing 처리(다음 시도/스킵)
                if attempt == _RETRY:
                    return []
                time.sleep(_RATE_SLEEP_S * (attempt + 1))
        return []

    return _search


def fetch(
    queries: list[dict], provider: Provider, limit: int | None = None, sleep_s: float = 0.0
) -> tuple[list[dict], list[str]]:
    """쿼리 목록 → (raw feature 행, missing 쿼리). provider 호출은 주입(테스트 격리)."""
    rows: list[dict] = []
    missing: list[str] = []
    seq = 0
    for i, q in enumerate(queries):
        if limit is not None and i >= limit:
            break
        docs = provider(q["query"])
        if sleep_s:
            time.sleep(sleep_s)
        if not docs:
            missing.append(q["query"])
            continue
        for doc in docs:
            lon, lat = _coords(doc)
            if lon is None or lat is None:
                continue
            seq += 1
            rows.append({
                "feature_id": f"SEARCH_{seq:06d}",
                "source": "search_seed",
                "search_query": q["query"],
                "region_code": q.get("region_code", ""),
                "region_level": q.get("region_level", ""),
                "region_name_ko": q.get("region_name_ko", ""),
                "feature_name": doc.get("place_name", ""),
                "category": doc.get("category_name", ""),
                "lon": lon,
                "lat": lat,
                "raw_json": json.dumps(doc, ensure_ascii=False),
            })
    return rows, missing


def _coords(doc: dict) -> tuple[float | None, float | None]:
    """Kakao doc → (lon, lat). x=경도, y=위도(문자열)."""
    try:
        return float(doc["x"]), float(doc["y"])
    except (KeyError, TypeError, ValueError):
        return None, None


def main(argv: list[str], provider: Provider | None = None) -> int:
    """엔트리포인트. provider 미지정 시 KAKAO_REST_API_KEY로 Kakao provider 구성."""
    args = [a for a in argv[1:] if not a.startswith("--")]
    queries_path = Path(args[0]) if args else _DEFAULT_QUERIES
    out = Path(args[1]) if len(args) > 1 else _DEFAULT_OUT
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    if not queries_path.exists():
        print(f"쿼리 없음: {queries_path} — build_search_seed_queries.py 먼저 실행")
        return 1
    if provider is None:
        api_key = os.environ.get("KAKAO_REST_API_KEY", "")
        if not api_key:
            print("KAKAO_REST_API_KEY 미설정 — 검색 수집 생략(키 설정 후 재실행).")
            return 0
        provider = kakao_provider(api_key)

    queries = list(csv.DictReader(queries_path.read_text("utf-8-sig").splitlines()))
    rows, missing = fetch(queries, provider, limit=limit, sleep_s=_RATE_SLEEP_S)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RAW_COLS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"검색 수집 {len(rows)}건 / missing 쿼리 {len(missing)}건 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
