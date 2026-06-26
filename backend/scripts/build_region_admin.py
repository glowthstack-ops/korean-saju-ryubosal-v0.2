"""행정구역 registry 스냅샷 빌드 (v2.2 P2, docs/12 §2·§3-A).

doc/gis 의 region_units_compact(시도17/시군구250/읍면동5,065 = 5,332)를 **경량 행정 registry**로
적재한다. 지명 → region_code 해소(RegionNameResolver)와 scope(시도/수도권) 후보 열거의 원천이다.

좌표는 프로필 스냅샷이 이미 보유하므로(중복·용량 방지) 수록하지 않는다 — 본 registry는 구조화
이름(시도/시군구/읍면동)·면적(area_m2)·상하위 트리(parent_code)만 담는다. ri 레벨은 원천에 없다.

입력(대용량·gitignore): doc/gis/region_units_compact_20230729.{jsonl,csv}. 미존재 시 graceful.
출력(git 추적): compiled/region_admin_units_v1.json.

사용법:
    python scripts/build_region_admin.py [units_path] [compiled_dir]
종료 코드 0=성공, 1=입력 없음.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from saju_shared_types.region_element import (
    RegionAdminSnapshot,
    RegionAdminUnit,
    RegionLevel,
)

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
_DEFAULT_UNITS = _REPO / "doc" / "gis" / "region_units_compact_20230729.jsonl"
_DEFAULT_COMPILED = _BACKEND / "compiled"
_MODEL_VERSION = "region-admin-p2.0"
_SOURCE_VERSION = "20230729"


def _load_units(path: Path) -> list[dict]:
    """compact 단위 데이터 로드(jsonl 우선, 없으면 동일 stem csv)."""
    if path.exists():
        return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        import csv

        return list(csv.DictReader(csv_path.read_text("utf-8-sig").splitlines()))
    raise FileNotFoundError(path)


def _to_admin(row: dict) -> RegionAdminUnit:
    """compact 행 → 경량 RegionAdminUnit(좌표 생략, 면적·구조명·트리만)."""
    level = RegionLevel(str(row["region_level"]).lower())
    code = str(row["region_code"])
    area_raw = row.get("area_m2")
    area = float(area_raw) if area_raw is not None and area_raw != "" else None
    return RegionAdminUnit(
        region_id=code,
        legal_dong_code=code if level is RegionLevel.EMD else "",
        region_level=level,
        sido_name=row.get("sido_name_ko") or "",
        sigungu_name=row.get("sigungu_name_ko") or "",
        eup_myeon_dong_name=row.get("emd_name_ko") or "",
        full_name=row.get("full_name_ko") or "",
        parent_code=str(row["parent_code"]) if row.get("parent_code") else None,
        area_m2=area,
    )


def main(argv: list[str]) -> int:
    """엔트리포인트. 입력 없으면 안내 후 1, 성공 시 0."""
    units_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_UNITS
    compiled_dir = Path(argv[2]) if len(argv) > 2 else _DEFAULT_COMPILED
    try:
        rows = _load_units(units_path)
    except FileNotFoundError:
        print(f"입력 없음: {units_path}")
        print("doc/gis 패키지(region_units_compact_20230729.jsonl/csv)를 재배치한 뒤 재실행하세요.")
        return 1

    items = [_to_admin(r) for r in rows]
    counts = {lvl.value: sum(1 for u in items if u.region_level is lvl) for lvl in RegionLevel}
    snapshot = RegionAdminSnapshot(
        model_version=_MODEL_VERSION,
        source_gis_version=_SOURCE_VERSION,
        reviewed=False,
        profile_counts=counts,
        items=items,
    )

    compiled_dir.mkdir(parents=True, exist_ok=True)
    out = compiled_dir / "region_admin_units_v1.json"
    # 좌표 없는 경량 registry — area는 1m² 단위로 라운딩(diff 안정).
    payload = snapshot.model_dump()
    for item in payload["items"]:
        for key in ("centroid_lat", "centroid_lon", "anchor_lat", "anchor_lon"):
            item.pop(key, None)
        if item.get("area_m2") is not None:
            item["area_m2"] = round(item["area_m2"])
        # 빈 선택 필드만 제거(필수 legal_dong_code/sido_name/full_name/region_level은 유지).
        for key in ("sigungu_name", "eup_myeon_dong_name", "ri_name", "parent_code"):
            if not item.get(key):
                item.pop(key, None)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8"
    )
    print(
        f"행정구역 {len(items)}개 저장 → {out.name} "
        f"(시도 {counts['ctprvn']}/시군구 {counts['sig']}/읍면동 {counts['emd']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
