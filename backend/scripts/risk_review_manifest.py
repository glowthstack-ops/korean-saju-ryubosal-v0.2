"""위험 사전 감수 manifest 자동 생성 (감수 16차 — 데굴님 요구).

reviewed 수량을 수동 집계("대표 7 + FIN 6 + …")로 설명하면 중복 집계·누락이 생긴다 —
사전 JSON을 유일한 원천으로 삼아 결정적 manifest를 생성하고 git으로 추적한다.
회귀 테스트(tests/regression/test_risk_review_manifest.py)가 파일과 재생성 결과의
일치를 강제한다(사전 변경 시 manifest 재생성 누락 검출).

실행: python scripts/risk_review_manifest.py [--check]
  --check: 재생성 결과가 기존 파일과 다르면 종료 코드 1(CI·훅용).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "packages" / "shared_types"))
sys.path.insert(0, str(_BACKEND / "packages" / "saju_engines"))

from saju_engines.dictionaries import (  # noqa: E402
    _RISK_HASH_SCHEMA_VERSION,
    RISK_REVIEW_ENVIRONMENT_VERSION,
)
from saju_engines.risk_scoring import (  # noqa: E402
    RISK_SCORING_VERSION,
    cause_semantics_hash,
    scoring_config_hash,
    transition_policy_hash,
)
from saju_engines.risk_selection import (  # noqa: E402
    RISK_SELECTION_VERSION,
    selection_policy_hash,
)

_RISKS_DIR = _BACKEND / "dictionaries" / "risks"
_MANIFEST_PATH = _BACKEND.parent / "doc" / "v2_2" / "RISK_REVIEW_MANIFEST.json"


def build_manifest() -> dict:
    """risks/*.json 전수에서 감수 현황 manifest를 결정적으로 산출한다.

    Returns:
        reviewed_total / reviewed_by_scope / reviewed_by_domain / reviewed_risk_ids /
        unreviewed_risk_ids / review_environment_version / hash_schema_version.
    """
    reviewed_ids: list[str] = []
    unreviewed_ids: list[str] = []
    by_scope: dict[str, int] = {}
    by_domain: dict[str, dict[str, int]] = {}
    for path in sorted(_RISKS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        domain = data["domain"]
        stats = by_domain.setdefault(domain, {"reviewed": 0, "unreviewed": 0})
        for item in data["items"]:
            if item.get("reviewed"):
                reviewed_ids.append(item["riskId"])
                stats["reviewed"] += 1
                for scope in item.get("reviewScopes", []):
                    by_scope[scope] = by_scope.get(scope, 0) + 1
            else:
                unreviewed_ids.append(item["riskId"])
                stats["unreviewed"] += 1
    return {
        "review_environment_version": RISK_REVIEW_ENVIRONMENT_VERSION,
        "hash_schema_version": _RISK_HASH_SCHEMA_VERSION,
        # 점수 감수 표면(감수 33차) — 공식·가중·cause registry 변경 시 manifest
        # diff로 감지(회귀 테스트가 재생성 일치를 강제 → 재감수 신호).
        "risk_scoring_version": RISK_SCORING_VERSION,
        "scoring_config_hash": scoring_config_hash(),
        "cause_semantics_hash": cause_semantics_hash(),
        # 선별 감수 표면(감수 34차) — 병합·대표·budget·portfolio·recovery 정책
        # 변경 시 manifest diff로 감지(재감수 신호). scope shadow_selection은
        # R2 측정·감수 후 스탬프.
        "risk_selection_version": RISK_SELECTION_VERSION,
        "selection_policy_hash": selection_policy_hash(),
        # temporal 감수 표면(감수 37차 — scope 분리): 계수·MAX_BONUS·커널 참조
        # 변경 시 manifest diff로 감지. shadow_temporal 0/49 → 감수 후 스탬프.
        "transition_policy_hash": transition_policy_hash(),
        "reviewed_total": len(reviewed_ids),
        "unreviewed_total": len(unreviewed_ids),
        "reviewed_by_scope": dict(sorted(by_scope.items())),
        "reviewed_by_domain": dict(sorted(by_domain.items())),
        "reviewed_risk_ids": sorted(reviewed_ids),
        "unreviewed_risk_ids": sorted(unreviewed_ids),
    }


def render(manifest: dict) -> str:
    """결정적 직렬화(키 정렬 없이 저작 순서 유지 — dict 구성이 이미 결정적)."""
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="파일 일치 검사만 수행")
    args = parser.parse_args()
    text = render(build_manifest())
    if args.check:
        current = _MANIFEST_PATH.read_text(encoding="utf-8") if _MANIFEST_PATH.exists() else ""
        if current != text:
            print("manifest 불일치 — scripts/risk_review_manifest.py 재실행 필요")
            return 1
        print("manifest 일치")
        return 0
    _MANIFEST_PATH.write_text(text, encoding="utf-8")
    print(f"작성: {_MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
