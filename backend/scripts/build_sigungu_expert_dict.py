"""전문가 감수 시군구 오행 CSV → region_sigungu_expert_ohaeng.json(권위 사전, reviewed:true).

전문가가 감수한 시군구별 오행(dictionaries/_src/sigungu_ohaeng_expert.csv, UTF-8)을 region_code로
매핑해 엔진이 한자 토큰화 위에 override하는 권위 레이어 사전을 생성한다(docs/12 §14). 통합시(수원·
창원 등)는 시 단위라 자치구 코드로 해소되지 않으므로 제외 — 자치구는 자체 한자를 유지한다. 시군구
아닌 지명(여의도·묵호)도 제외. 검수필요 상태는 entry별 reviewed:false.

재생성: python scripts/build_sigungu_expert_dict.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from saju_engines.region_element_engine import RegionElementEngine

_BACKEND = Path(__file__).resolve().parents[1]
_SRC = _BACKEND / "dictionaries" / "_src" / "sigungu_ohaeng_expert.csv"
_OUT = _BACKEND / "dictionaries" / "region" / "region_sigungu_expert_ohaeng.json"
_COMPILED = _BACKEND / "compiled"
# CSV 시도 표기 → resolver 시도 단축명.
_SIDO = {
    "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주",
    "대전": "대전", "울산": "울산", "세종": "세종", "경기도": "경기", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주": "제주",
}


def main() -> int:
    if not _SRC.exists():
        print(f"소스 CSV 없음: {_SRC}")
        return 1
    eng = RegionElementEngine(
        _BACKEND / "dictionaries",
        _COMPILED / "region_element_profiles_v1.json",
        _COMPILED / "region_admin_units_v1.json",
    )
    rows = list(csv.DictReader(_SRC.read_text("utf-8").splitlines()))
    entries: dict[str, dict] = {}
    skipped: list[str] = []
    for r in rows:
        name, status, note = r["자치구/시군명"], r["상태"], r["비고"]
        if "지명으로 보여" in note:  # 시군구 아닌 지명(여의도·묵호)
            skipped.append(name)
            continue
        full = f"{_SIDO.get(r['시도'], r['시도'])} {name}"
        code, _ = eng.resolve_region(full)
        if not code:
            code, _ = eng.resolve_region(name)
        if not code:  # 통합시(시 단위) 등 미해소 → 제외(자치구 한자 유지)
            skipped.append(name)
            continue
        profile = eng.get_profile(code)
        entries[code] = {
            "name": profile.full_name if profile else full,
            "elements": list(r["오행한자"]),
            "status": status,
            "reviewed": status != "검수필요",
            "note": note,
        }
    out = {
        "version": "1.0.0",
        "reviewed": True,
        "note": "전문가 감수 시군구 오행(권위 레이어). 한자 토큰화를 override한다. 검수필요는 "
                "entry별 reviewed:false. 통합시 자치구(마산합포구 등)는 미수록 — 자체 한자 유지.",
        "entries": entries,
    }
    _OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"전문가 사전 {len(entries)} entry → {_OUT.name} (제외 {len(skipped)}: {skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
