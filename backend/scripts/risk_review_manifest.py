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

import sys as _sys  # noqa: E402

from saju_engines.dictionaries import (  # noqa: E402
    _RISK_HASH_SCHEMA_VERSION,
    RISK_REVIEW_ENVIRONMENT_VERSION,
)

_sys.path.insert(0, str(_BACKEND / "apps" / "api"))
from saju_api.services.token_counter_registry import (  # noqa: E402
    adapter_validation_policy_hash as _adapter_validation_policy_hash,
)
from saju_engines.risk_exposure import (  # noqa: E402
    RISK_EXPOSURE_VERSION,
    critical_validation_state,
    expose_policy_hash,
)
from saju_engines.risk_presentation import (  # noqa: E402
    RISK_PRESENTATION_VERSION,
    presentation_policy_hash,
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


# adapter 감수 승격 allowlist(감수 56차 §9 — manifest=SSOT): shadow 검증
# artifact의 corpus canonical hash를 감수자가 승인하면 여기에 추가한다 —
# 그때만 해당 entry가 reviewed=true로 생성된다(30표본 통과 자체는 승격이
# 아니다). corpus hash가 다르면(재검증) 새 identity로 재감수.
_REVIEWED_COUNTER_CORPUS_HASHES: frozenset[str] = frozenset({
    # gemini-3-flash-preview · countTokens-v1beta-r1 · schema 1 ·
    # PROVIDER_EXACT — 감수 58차 §11 조건부 승인 조건 충족 확인 후 승격:
    # native 30표본만의 hash(rerouting 부록 분리)·full SHA-256·artifact
    # 재해시 일치·policy full hash 일치·transport digest 병기·fallback
    # (gemini-2.5-flash) 미감수 BYPASS 유지. adapter 감수≠expose 개방
    # (expose_pipeline.reviewed=false·RUNTIME_ENABLED=false·MODE=off 유지).
    "65db8eb9e5c04ddb7e73e982ed1332ddca767b72bde1785089170633437ee59b",
})

_ADAPTER_VALIDATION_DIR = (
    Path(__file__).resolve().parents[1] / "compiled"
    / "risk_adapter_validation")


def _token_counter_candidates() -> list[dict]:
    """shadow 검증 artifact → validatedTokenCounters 항목(결정적).

    artifact의 identity+corpus hash를 그대로 옮기고 reviewed는
    _REVIEWED_COUNTER_CORPUS_HASHES 포함 여부로만 결정한다(감수 56차 §9 —
    artifact 해시와 manifest entry의 기계 대조).
    """
    entries: list[dict] = []
    if not _ADAPTER_VALIDATION_DIR.exists():
        return entries
    for path in sorted(_ADAPTER_VALIDATION_DIR.glob("*.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        corpus_hash = str(artifact["validationCorpusHash"])
        # artifact 무결성(감수 58차 §2): validationCorpusHash는 **native
        # corpus(해당 모델 30표본)만의** 재해시와 일치해야 후보 자격 —
        # 다른 모델의 rerouting 부록은 supplementaryReroutingHash로 분리
        # (파일 수정=후보 탈락이 아니라 생성 실패로 조기 노출).
        import hashlib
        # 정본=전체 digest(감수 57차 §5) — 축약(16자)은 파일명·표시 전용.
        recomputed = hashlib.sha256(json.dumps(
            artifact["nativeValidationCorpus"], ensure_ascii=False,
            sort_keys=True).encode()).hexdigest()
        if recomputed != corpus_hash:
            raise ValueError(
                f"adapter validation artifact 무결성 실패: {path.name}")
        identity = dict(artifact["nativeValidationCorpus"]["identity"])
        entries.append({**identity, "validationCorpusHash": corpus_hash,
                        "reviewed": corpus_hash
                        in _REVIEWED_COUNTER_CORPUS_HASHES})
    return entries


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
    sensitivity_dist: dict[str, int] = {}
    sensitivity_high: dict[str, dict[str, str]] = {}
    for path in sorted(_RISKS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        domain = data["domain"]
        stats = by_domain.setdefault(domain, {"reviewed": 0, "unreviewed": 0})
        for item in data["items"]:
            sens = item.get("transitionSensitivity", "none")
            sensitivity_dist[sens] = sensitivity_dist.get(sens, 0) + 1
            if sens == "high":
                # high 판정 근거표(감수 39차) — 항목별 상태 전환성 근거를
                # manifest에 보존(스탬프 추적 가능성 요구).
                sensitivity_high[item["riskId"]] = {
                    "domain": domain,
                    "note": item.get("transitionSensitivityNote", ""),
                }
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
        # 노출 감수 표면(감수 41차 — R3): 밴드·상한 매트릭스·critical gate·
        # claim 정책·token guard 변경 시 manifest diff로 감지.
        # scope shadow_presentation 0/49 — R3 측정·감수 후 스탬프.
        "risk_presentation_version": RISK_PRESENTATION_VERSION,
        "presentation_policy_hash": presentation_policy_hash(),
        # EXPOSE 게이트(감수 44차 — R4): 전역 pipeline 계약(항목 scope 아님).
        # critical 실증 상태는 presentation policy와 분리 — 상태 변화가
        # 49항목 감수를 강등하지 않는다(EXPOSE 게이트 감수만 갱신).
        "risk_exposure_version": RISK_EXPOSURE_VERSION,
        # adapter 승격 기준(감수 51차 — 실측 전 선행 고정): 변경=재감수 신호.
        "adapter_validation_policy_hash": _adapter_validation_policy_hash(),
        "expose_pipeline": {
            "reviewed": False,
            "expose_policy_hash": expose_policy_hash(),
            "critical_validation_state": critical_validation_state(),
            "validatedTokenCounters": _token_counter_candidates(),
        },
        # transitionSensitivity 저작 현황(감수 39차 확정 — MAX_BONUS 0.20):
        # 분포 + high 항목별 판정 근거(상태 전환성 기준) 보존.
        "transition_sensitivity_distribution": dict(
            sorted(sensitivity_dist.items())),
        "transition_sensitivity_high": dict(
            sorted(sensitivity_high.items())),
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
