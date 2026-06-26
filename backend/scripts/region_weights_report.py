"""지역 오행 엔진 가중치 튜닝 준비 리포트(P4 #5, docs/12).

reviewed:false인 지역 엔진의 **튜닝 가능한 모든 파라미터를 한곳에 모으고**(사전 + 코드 상수),
현재 스냅샷의 행동 베이스라인(dominance 분포·신뢰도 히스토그램·레이어 사용·우세 오행 분포)을
함께 출력한다. 전문가 감수·가중 튜닝의 출발점(절대원칙 5: 검수 전 초안).

실제 튜닝(값 변경)은 전문가/코호트 데이터가 필요하므로 본 스크립트는 변경하지 않고 surface만 한다.

사용법: python scripts/region_weights_report.py [out_dir]
출력: <out_dir>/region_weights_review.{json,md} (기본 compiled/).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from saju_engines import region_element_engine as ree
from saju_shared_types.region_element import RegionProfilesSnapshot

_BACKEND = Path(__file__).resolve().parent.parent
_DICTS = _BACKEND / "dictionaries" / "region"
_PROFILES = _BACKEND / "compiled" / "region_element_profiles_v1.json"
_DEFAULT_OUT = _BACKEND / "compiled"

# 외부 사전화 후보(현재 region_element_engine.py 모듈 상수 — 튜닝 시 사전 이관 검토).
_ENGINE_CONSTANTS = (
    "_PHONETIC_CONFIDENCE", "_PHONETIC_ONLY_CONFIDENCE", "_HANJA_FALLBACK_CONFIDENCE",
    "_HANJA_TOKEN_BASE_CONF", "_HANJA_TOKEN_PER_MATCH", "_HANJA_TOKEN_MAX_CONF",
    "_INHERIT_DECAY",
)
_DICT_FILES = (
    "region_layer_weights.json", "region_dominance_rules.json", "region_intent_weights.json",
    "region_geo_signal_rules.json", "region_geo_feature_elements.json",
)


def collect_params() -> dict:
    """튜닝 파라미터 수집: 사전 5종 + 엔진 코드 상수."""
    dicts: dict[str, object] = {}
    for fname in _DICT_FILES:
        path = _DICTS / fname
        if path.exists():
            dicts[fname] = json.loads(path.read_text("utf-8"))
    constants = {name: getattr(ree, name) for name in _ENGINE_CONSTANTS}
    return {
        "dictionaries": dicts,
        "engine_constants": constants,
        "note": "전 항목 reviewed:false 초안 — 전문가 감수/코호트 캘리브레이션 대상. "
                "engine_constants는 코드 상수(튜닝 시 사전 이관 검토).",
    }


def profile_stats(profiles_path: Path) -> dict:
    """현재 스냅샷 행동 베이스라인(분포·히스토그램)."""
    if not profiles_path.exists():
        return {"available": False, "reason": "프로필 스냅샷 미빌드"}
    snap = RegionProfilesSnapshot.model_validate_json(profiles_path.read_text("utf-8"))
    by_level = Counter(p.region_level.value for p in snap.items)
    by_dom = Counter(p.dominant_type.value for p in snap.items)
    dom_el = Counter(p.dominant_elements[0] for p in snap.items if p.dominant_elements)
    layers = Counter(lbl for p in snap.items for lbl in p.source_layers)
    conf_bins: Counter[str] = Counter()
    for p in snap.items:
        conf_bins[f"{int(p.confidence * 10) / 10:.1f}"] += 1
    return {
        "available": True,
        "model_version": snap.model_version,
        "total": len(snap.items),
        "by_level": dict(by_level),
        "by_dominance": dict(by_dom),
        "dominant_element": dict(dom_el.most_common()),
        "source_layer_usage": dict(layers.most_common()),
        "confidence_histogram": dict(sorted(conf_bins.items())),
    }


def build_markdown(params: dict, stats: dict) -> str:
    """전문가 검토용 md 리뷰 시트."""
    lines = ["# 지역 오행 엔진 가중치 튜닝 리뷰 시트", "", "> 전 항목 reviewed:false 초안.", ""]
    lines.append("## 1. 행동 베이스라인(현재 스냅샷)")
    if not stats.get("available"):
        lines.append(f"- (미빌드: {stats.get('reason')})")
    else:
        lines.append(f"- model_version {stats['model_version']} / 총 {stats['total']}")
        lines.append(f"- 레벨: {stats['by_level']}")
        lines.append(f"- dominance: {stats['by_dominance']}")
        lines.append(f"- 우세 오행: {stats['dominant_element']}")
        lines.append(f"- 레이어 사용: {stats['source_layer_usage']}")
        lines.append(f"- 신뢰도 분포: {stats['confidence_histogram']}")
    lines.append("")
    lines.append("## 2. 튜닝 파라미터(사전)")
    for fname, data in params["dictionaries"].items():
        lines.append(f"### {fname}")
        keys = [k for k in data if k not in ("note", "version", "reviewed")]
        lines.append(f"- 키: {keys}")
    lines.append("")
    lines.append("## 3. 엔진 코드 상수(사전 이관 검토 대상)")
    for name, val in params["engine_constants"].items():
        lines.append(f"- {name} = {val}")
    lines.append("")
    lines.append("## 4. 튜닝 가이드")
    lines.append("- 절대값보다 **상대 순위**를 신뢰(golden case 회귀로 고정).")
    lines.append("- 외부 지형 데이터 연결 전까지 confidence 상한(score_caps)으로 과추천 억제.")
    lines.append("- 코호트/전문가 라벨 확보 후 role_scores·layer 가중·geo scale 순으로 보정.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """엔트리포인트."""
    out_dir = Path(argv[1]) if len(argv) > 1 else _DEFAULT_OUT
    params = collect_params()
    stats = profile_stats(_PROFILES)
    out_dir.mkdir(parents=True, exist_ok=True)
    review = {"params": params, "baseline": stats}
    (out_dir / "region_weights_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    (out_dir / "region_weights_review.md").write_text(
        build_markdown(params, stats) + "\n", "utf-8"
    )
    print(
        f"튜닝 리뷰 시트 저장(파라미터 사전 {len(params['dictionaries'])}종 + 상수 "
        f"{len(params['engine_constants'])}개, baseline {'O' if stats.get('available') else 'X'}) "
        f"→ {out_dir}/region_weights_review.{{json,md}}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
