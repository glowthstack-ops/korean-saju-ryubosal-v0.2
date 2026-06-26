"""지역 오행 프로필 스냅샷 빌드 (v2.2 P1, docs/12 §8·§10).

doc/gis 의 계산용 행정구역 데이터(region_units_compact, 시도17/시군구250/읍면동5,065 = 5,332)와
dictionaries/region_elements.json(시군구 한자, 흡수 §12)을 결합해 **읍면동까지** 5차원 오행
프로필을 사전계산하고 compiled 스냅샷에 저장한다(절대원칙 9 — 요청 시점 재계산 금지).

레이어(P1): 한자 토큰화(시군구) + 미매칭 폴백(region_elements) + 한글 음운(cap 0.03) +
부모 상속(한자 없는 읍면동·일부 시군구). 지형·수계·풍수 GIS 레이어는 미공급 → P3에서 활성.
방위는 프로필에 저장하지 않는다(§4-4) — 추천 시점 계산.

입력(대용량, gitignore): doc/gis/region_units_compact_20230729.{jsonl,csv}. 미존재 시 graceful
종료(원본 패키지 재배치 안내). 출력은 git 추적:
  compiled/region_element_profiles_v1.json       (프로필 본체)
  compiled/region_element_profiles_v1.meta.json  (단위·레이어·조인 커버리지 요약)

사용법:
    python scripts/build_region_profiles.py [units_path] [compiled_dir]
종료 코드 0=성공, 1=입력 없음/검증 실패.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from saju_engines.region_element_engine import RegionElementEngine
from saju_shared_types.region_element import (
    RegionGeoFeature,
    RegionLevel,
    RegionProfilesMeta,
    RegionProfilesSnapshot,
    RegionUnitInput,
)

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_DEFAULT_UNITS = _REPO / "doc" / "gis" / "region_units_compact_20230729.jsonl"
# 지형 feature(P3) — GIS 공급 시 배치. 부재 시 지형 레이어 미활성(P1 동작 유지).
_DEFAULT_GEO = _REPO / "doc" / "gis" / "region_geo_features.jsonl"
_DEFAULT_COMPILED = _BACKEND / "compiled"
_MODEL_VERSION = "region-element-p1.0"
_SOURCE_VERSION = "20230729"

# region_elements.json 약식 시도명 → doc/gis 정식 시도명(한자 조인 키 정규화).
_SIDO_FULL: dict[str, str] = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기도": "경기도", "강원도": "강원특별자치도", "충청북도": "충청북도", "충청남도": "충청남도",
    "전라북도": "전라북도", "전라남도": "전라남도", "경상북도": "경상북도", "경상남도": "경상남도",
    "제주": "제주특별자치도",
}


def _load_units(path: Path) -> list[dict]:
    """compact 단위 데이터 로드(jsonl 우선, 없으면 동일 stem csv)."""
    if path.exists():
        return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        import csv

        text = csv_path.read_text("utf-8-sig")
        return list(csv.DictReader(text.splitlines()))
    raise FileNotFoundError(path)


def _load_geo(path: Path) -> dict[str, RegionGeoFeature]:
    """지형 feature 로드(region_code → RegionGeoFeature). 부재 시 빈 dict(graceful, P3 스텁)."""
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    return {str(r["region_id"]): RegionGeoFeature.model_validate(r) for r in rows}


def _build_hanja_index(region_elements_path: Path) -> dict[tuple[str, str], dict]:
    """region_elements.json → (정식시도, 시군구명) 인덱스(한자 레이어 조인용, §12)."""
    items = json.loads(region_elements_path.read_text("utf-8"))["items"]
    idx: dict[tuple[str, str], dict] = {}
    for it in items:
        full = _SIDO_FULL.get(it["sido"], it["sido"])
        idx[(full, it["district"])] = it
    return idx


def _join_hanja(
    row: dict, idx: dict[tuple[str, str], dict]
) -> tuple[str | None, list[str]]:
    """시군구 행 → (한자명, 폴백 오행). 완전일치 → 도시명 접두(○○시 ○○구→○○시) 폴백."""
    sido = row.get("sido_name_ko") or ""
    sgg = row.get("sigungu_name_ko") or ""
    hit = idx.get((sido, sgg))
    if hit is None and " " in sgg:
        hit = idx.get((sido, sgg.split()[0]))  # '수원시 장안구' → '수원시'
    if hit is None:
        return None, []
    return hit.get("hanja"), list(hit.get("elements", []))


def _to_unit(row: dict, idx: dict[tuple[str, str], dict]) -> RegionUnitInput:
    """compact 행 → RegionUnitInput(시군구만 한자 조인)."""
    level = RegionLevel(str(row["region_level"]).lower())
    hanja: str | None = None
    fallback: list[str] = []
    if level is RegionLevel.SIG:
        hanja, fallback = _join_hanja(row, idx)

    def _f(key: str) -> float | None:
        val = row.get(key)
        if val is None or val == "":
            return None
        return float(val)

    return RegionUnitInput(
        region_code=str(row["region_code"]),
        region_level=level,
        parent_code=str(row["parent_code"]) if row.get("parent_code") else None,
        full_name_ko=row.get("full_name_ko") or "",
        region_name_ko=row.get("region_name_ko") or "",
        hanja=hanja,
        fallback_elements=fallback,
        centroid_lat=_f("centroid_lat"),
        centroid_lon=_f("centroid_lon"),
        anchor_lat=_f("anchor_lat"),
        anchor_lon=_f("anchor_lon"),
    )


def main(argv: list[str]) -> int:
    """엔트리포인트. 입력 없으면 안내 후 1, 성공 시 0."""
    units_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_UNITS
    compiled_dir = Path(argv[2]) if len(argv) > 2 else _DEFAULT_COMPILED
    dicts_dir = _BACKEND / "dictionaries"
    try:
        rows = _load_units(units_path)
    except FileNotFoundError:
        print(f"입력 없음: {units_path}")
        print("doc/gis 패키지(region_units_compact_20230729.jsonl/csv)를 재배치한 뒤 재실행하세요.")
        return 1

    hanja_idx = _build_hanja_index(dicts_dir / "region_elements.json")
    units = [_to_unit(r, hanja_idx) for r in rows]
    sig_total = sum(1 for u in units if u.region_level is RegionLevel.SIG)
    sig_joined = sum(
        1 for u in units if u.region_level is RegionLevel.SIG and u.hanja is not None
    )
    geo_by_code = _load_geo(Path(argv[3]) if len(argv) > 3 else _DEFAULT_GEO)

    engine = RegionElementEngine(dicts_dir)
    profiles = engine.build_profiles(units, _MODEL_VERSION, geo_by_code)

    counts = {lvl.value: sum(1 for p in profiles if p.region_level is lvl) for lvl in RegionLevel}
    layers = ["hanja_token", "hanja_fallback_legacy", "phonetic_layer", "parent_inheritance"]
    if geo_by_code:
        layers = ["physical_geography", "landcover_hydro_forest", *layers]
    meta = RegionProfilesMeta(
        model_version=_MODEL_VERSION,
        source_gis_version=_SOURCE_VERSION,
        direction_included=False,
        layers=layers,
        profile_counts=counts,
        hanja_join={"matched": sig_joined, "total": sig_total, "geo_features": len(geo_by_code)},
        calculated_at=datetime.now(UTC).isoformat(),
    )
    snapshot = RegionProfilesSnapshot(
        model_version=_MODEL_VERSION,
        source_gis_version=_SOURCE_VERSION,
        reviewed=False,
        meta=meta,
        items=profiles,
    )

    compiled_dir.mkdir(parents=True, exist_ok=True)
    out = compiled_dir / "region_element_profiles_v1.json"
    meta_out = compiled_dir / "region_element_profiles_v1.meta.json"
    # 5,332행 운영 스냅샷 — 크기 최소화: 벡터/좌표 라운딩, 런타임 미사용·빈 필드 제거,
    # 컴팩트 직렬화. centroid는 추천 시점 방위에 쓰지 않으므로(anchor 사용) 생략한다.
    _DROP_EMPTY = ("legal_dong_code", "parent_code", "evidence", "calculated_at")
    payload = snapshot.model_dump()
    for item in payload["items"]:
        item["confidence"] = round(item["confidence"], 4)
        item["element_vector"] = {k: round(v, 4) for k, v in item["element_vector"].items()}
        item.pop("centroid_lat", None)
        item.pop("centroid_lon", None)
        for key in ("anchor_lat", "anchor_lon"):
            if item.get(key) is not None:
                item[key] = round(item[key], 5)
        for key in _DROP_EMPTY:
            if not item.get(key):
                item.pop(key, None)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8"
    )
    meta_out.write_text(
        json.dumps(meta.model_dump(), ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(
        f"프로필 {len(profiles)}개 저장 → {out.name} "
        f"(시도 {counts['ctprvn']}/시군구 {counts['sig']}/읍면동 {counts['emd']}, "
        f"한자조인 {sig_joined}/{sig_total})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
