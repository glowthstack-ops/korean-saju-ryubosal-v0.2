"""시군구 오행 소스 CSV → region_elements.json 컴파일(재현 가능 빌드).

소스: dictionaries/_src/sigungu_ohaeng.csv (UTF-8, 사용자 제공 230 시군구). 출력:
dictionaries/region_elements.json. region 키는 '{시도} {시군구}'(동명 시군구 disambiguation).
복합 오행(예: 광진구 土水)은 elements[전체] + element[대표=첫 글자, region_fit용]로 보존한다.
reviewed는 전부 false 유지 — 명리 표준 규격 없는 자체 기준 초안(절대원칙 5: 검수 전 출시 금지).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SRC = _BACKEND / "dictionaries" / "_src" / "sigungu_ohaeng.csv"
_OUT = _BACKEND / "dictionaries" / "region_elements.json"
_VALID = {"木", "火", "土", "金", "水"}


def main() -> None:
    """소스 CSV를 읽어 region_elements.json을 생성·검증한다."""
    rows = list(csv.DictReader(_SRC.read_text("utf-8").splitlines()))
    items: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        sido = r["시도"].strip()
        district = r["자치구/시군명"].strip()
        elements = list(r["오행한자"].strip())
        assert all(e in _VALID for e in elements), f"오행 오류: {r}"
        assert elements, f"오행 없음: {r}"
        region = f"{sido} {district}"
        assert region not in seen, f"중복 키: {region}"
        seen.add(region)
        item = {
            "region": region,
            "sido": sido,
            "district": district,
            "hanja": r["한자명"].strip(),
            "element": elements[0],  # 대표(첫 글자) — region_fit 단일 오행 입력
            "elements": elements,  # 복합 보존(향후 다중 오행 적합용)
            "status": r["상태"].strip(),
            "reviewed": False,
        }
        if r.get("비고", "").strip():
            item["note"] = r["비고"].strip()
        items.append(item)

    out = {
        "version": "2.0.0",
        "note": (
            "지역오행 — 명리학 표준 규격 없음. 지명 한자 오행 기반 자체 기준 초안으로 전 항목 "
            "사용자/전문가 검수 전 출시 금지(reviewed:false, 절대원칙 5). 시군구 단위 230개, "
            "키='{시도} {시군구}'(동명 disambiguation). 복합 오행은 elements 전체 보존, "
            "element는 대표(첫 글자)로 region_fit 단일 입력용. 출처: _src/sigungu_ohaeng.csv "
            "(scripts/build_region_elements.py로 재생성). 미등재 지역은 보정 없음(중립 0.5)."
        ),
        "items": items,
    }
    _OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    comp = sum(1 for i in items if len(i["elements"]) > 1)
    print(f"생성: {_OUT.relative_to(_BACKEND)}  ({len(items)}개, 복합오행 {comp}개)")


if __name__ == "__main__":
    main()
