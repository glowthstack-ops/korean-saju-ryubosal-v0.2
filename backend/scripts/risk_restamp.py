"""reviewed 항목 재스탬프 도구 — 감수 절차 가드 (감수 19·20차 조건 자동화).

원칙(데굴님 확정): 불변 판정의 기준은 git HEAD가 아니라 **각 항목에 저장된 감수
해시(reviewHashes)**다 — 변경이 먼저 커밋되어도 저장 해시와 다르면 반드시 강등된다
(작업 순서 비의존). git HEAD 비교는 변경 사유를 보여주는 보조 진단으로만 쓴다.

판정:
  전 scope 해시 일치 + 엔진 환경(env 버전)만 변경 → env 재스탬프 허용
  하나라도 scope 해시 불일치 → reviewed=false + scope·해시 제거 + reviewPending

예외 — 해시 스키마 이행(--schema-migration): 해시 대상 구성(v5→v6 등)이 바뀌면 저장
해시가 전부 불일치한다. 이때만 git HEAD 구조 본문 비교를 보조 진단으로 사용해 '본문
불변 + 스키마만 변경' 항목의 재스탬프를 허용한다(본문까지 다르면 여전히 강등).

실행:
  python scripts/risk_restamp.py                          # 분류 보고만
  python scripts/risk_restamp.py --restamp                # 불변 항목 env·해시 재스탬프
  python scripts/risk_restamp.py --restamp --schema-migration
  python scripts/risk_restamp.py --restamp --demote-changed C7
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "packages" / "shared_types"))
sys.path.insert(0, str(_BACKEND / "packages" / "saju_engines"))

from saju_engines.dictionaries import (  # noqa: E402
    RISK_REVIEW_ENVIRONMENT_VERSION,
    RiskItem,
    risk_scope_hash,
)

_RISKS_DIR = _BACKEND / "dictionaries" / "risks"


def _stamped_hashes_match(raw: dict) -> bool:
    """저장된 감수 해시 vs 현재 재계산 — 전 scope 일치 여부(불변 판정의 1차 기준)."""
    item = RiskItem.model_validate(raw)
    stamped = raw.get("reviewHashes", {})
    scopes = raw.get("reviewScopes", [])
    if not scopes or set(stamped) != set(scopes):
        return False
    return all(stamped[s] == risk_scope_hash(item, s) for s in scopes)


def _head_structure_hashes(rel_path: str) -> dict[str, str]:
    """git HEAD 사전의 risk_id→shadow_structure 해시(보조 진단 — 스키마 이행 전용)."""
    try:
        raw = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            capture_output=True, text=True, check=True, cwd=_BACKEND.parent,
        ).stdout
    except subprocess.CalledProcessError:
        return {}
    out: dict[str, str] = {}
    for item_raw in json.loads(raw)["items"]:
        try:
            item = RiskItem.model_validate(item_raw)
        except Exception:  # noqa: BLE001 -- 구 스키마 항목은 content change로 취급
            continue
        out[item.risk_id] = risk_scope_hash(item, "shadow_structure")
    return out


def classify(risks_dir: Path, schema_migration: bool = False) -> tuple[list, list]:
    """reviewed 항목을 (불변, 변경) 목록으로 분류한다 — 회귀 테스트가 직접 소비.

    1차 기준=저장된 reviewHashes(작업 순서 비의존). schema_migration일 때만 HEAD
    구조 본문 일치를 보조 기준으로 허용한다.
    """
    unchanged: list[str] = []
    changed: list[str] = []
    for path in sorted(risks_dir.glob("*.json")):
        head_hashes: dict[str, str] = {}
        if schema_migration:
            head_hashes = _head_structure_hashes(
                f"backend/dictionaries/risks/{path.name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for raw in data["items"]:
            if not raw.get("reviewed"):
                continue
            if _stamped_hashes_match(raw):
                unchanged.append(raw["riskId"])
            elif schema_migration and head_hashes.get(raw["riskId"]) == (
                risk_scope_hash(RiskItem.model_validate(raw), "shadow_structure")
            ):
                unchanged.append(raw["riskId"])  # 본문 불변 — 해시 스키마 이행만
            else:
                changed.append(raw["riskId"])
    return unchanged, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restamp", action="store_true",
                        help="불변 reviewed 항목의 env·해시 재스탬프 수행")
    parser.add_argument("--schema-migration", action="store_true",
                        help="해시 스키마 이행 — HEAD 본문 비교를 보조 기준으로 허용")
    parser.add_argument("--demote-changed", metavar="차수",
                        help="변경 reviewed 항목을 reviewPending=<차수>로 강등")
    args = parser.parse_args()
    unchanged_ids, changed_ids = classify(_RISKS_DIR, args.schema_migration)
    if args.restamp or args.demote_changed:
        unchanged_set, changed_set = set(unchanged_ids), set(changed_ids)
        for path in sorted(_RISKS_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            dirty = False
            for raw in data["items"]:
                if not raw.get("reviewed"):
                    continue
                if raw["riskId"] in unchanged_set and args.restamp:
                    item = RiskItem.model_validate(raw)
                    raw["reviewEnvironmentVersion"] = RISK_REVIEW_ENVIRONMENT_VERSION
                    raw["reviewHashes"] = {
                        scope: risk_scope_hash(item, scope)
                        for scope in raw.get("reviewScopes", [])
                    }
                    dirty = True
                elif raw["riskId"] in changed_set and args.demote_changed:
                    raw["reviewed"] = False
                    raw["reviewPending"] = args.demote_changed
                    for k in ("reviewScopes", "reviewVersions", "reviewHashes",
                              "reviewEnvironmentVersion"):
                        raw.pop(k, None)
                    dirty = True
            if dirty:
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"불변(저장 감수 해시 일치{'/스키마 이행' if args.schema_migration else ''}"
          f" — 재스탬프 {'수행' if args.restamp else '가능'}): {len(unchanged_ids)}건")
    print(f"변경(강등 {'수행' if args.demote_changed else '대상 — 사람 감수 필요'}): "
          f"{len(changed_ids)}건")
    for rid in changed_ids:
        print(f"  - {rid}")
    return 0 if not changed_ids or args.demote_changed else 3


if __name__ == "__main__":
    raise SystemExit(main())
