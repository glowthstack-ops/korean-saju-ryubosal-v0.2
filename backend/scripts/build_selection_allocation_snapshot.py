"""선발·배치 가중 사전 → 컴파일 스냅샷 (validate → compile, 절대 원칙 5).

검증: 단계 가중 8종 완전성·합 1.0(±0.001)·신호 키 유효성, 선발 방식 가드 7종
완전성·캡 0~100·enum, 강도/보정 상수 범위. 통과 시
compiled/selection_allocation_weights_v{version}.json 스냅샷을 쓴다(git 추적).

사용법:
    python scripts/build_selection_allocation_snapshot.py
종료 코드 0=성공, 1=검증 실패.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND / "packages" / "shared_types"))

_SRC = _BACKEND / "dictionaries" / "selection_allocation_weights.json"
_COMPILED = _BACKEND / "compiled"

_STAGES = (
    "opportunity", "application", "eligibility", "selection_support",
    "allocation", "preference_match", "execution", "adaptation",
)
_SIGNALS = {
    "institution_signal", "qualification_signal", "application_signal",
    "competition_signal", "benefit_signal", "matching_signal",
    "transition_signal", "stability_signal",
}
_MODES = (
    "lottery", "weighted_lottery", "score_ranked", "hybrid",
    "first_come", "queue", "administrative",
)
_LEVELS = {"low", "medium", "high"}


def _check_weight_map(name: str, weights: object, errors: list[str]) -> None:
    """신호 가중 맵 1개 검증 — 키 유효성 + 합 1.0."""
    if not isinstance(weights, dict) or not weights:
        errors.append(f"{name}: 누락/빈 객체")
        return
    bad = set(weights) - _SIGNALS
    if bad:
        errors.append(f"{name}: 무효 신호 키 {sorted(bad)}")
    total = sum(v for v in weights.values() if isinstance(v, (int, float)))
    if abs(total - 1.0) > 0.001:
        errors.append(f"{name}: 가중 합 {total:.3f} ≠ 1.0")


def validate(raw: dict) -> list[str]:
    """가중 사전 구조 검증 — 위반 메시지 목록(빈 목록=통과)."""
    errors: list[str] = []
    if not isinstance(raw.get("reviewed"), bool):
        errors.append("reviewed 플래그는 boolean")
    stage_weights = raw.get("stage_weights")
    if not isinstance(stage_weights, dict):
        errors.append("stage_weights 누락")
    else:
        for stage in _STAGES:
            _check_weight_map(f"stage_weights.{stage}", stage_weights.get(stage), errors)
        extra = set(stage_weights) - set(_STAGES)
        if extra:
            errors.append(f"stage_weights: 무효 단계 {sorted(extra)}")
    _check_weight_map("merit_selection_weights", raw.get("merit_selection_weights"), errors)
    guards = raw.get("mode_guards")
    if not isinstance(guards, dict):
        errors.append("mode_guards 누락")
    else:
        for mode in _MODES:
            g = guards.get(mode)
            if not isinstance(g, dict):
                errors.append(f"mode_guards.{mode}: 누락")
                continue
            if g.get("uncertainty") not in _LEVELS or g.get("confidence_cap") not in _LEVELS:
                errors.append(f"mode_guards.{mode}: uncertainty/confidence_cap enum 위반")
            for cap in ("selection_cap", "allocation_cap", "preference_cap"):
                v = g.get(cap)
                if not isinstance(v, int) or not 0 <= v <= 100:
                    errors.append(f"mode_guards.{mode}.{cap}: 0~100 정수 위반")
    for section, keys in (
        ("base_strengths", {"active", "present", "absent"}),
        ("transition", {"base", "clash", "inflow"}),
        ("stability", {"base", "friction_step", "qualification_coupling"}),
        ("competition_inversion", {"default", "peer_favorable"}),
    ):
        sec = raw.get(section)
        if not isinstance(sec, dict) or set(sec) != keys:
            errors.append(f"{section}: 키 집합 위반(기대 {sorted(keys)})")
    # pydantic 스키마 최종 검증(shared_types와의 구조 계약).
    try:
        from saju_shared_types.selection_allocation import SelectionWeightsConfig

        SelectionWeightsConfig.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 — 검증 도구는 위반 사유를 모아 보고
        errors.append(f"SelectionWeightsConfig 검증 실패: {exc}")
    return errors


def main() -> int:
    """엔트리포인트 — validate 통과 시 스냅샷 기록."""
    raw = json.loads(_SRC.read_text("utf-8"))
    errors = validate(raw)
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        return 1
    version = raw.get("version", "0.0.0")
    out = _COMPILED / f"selection_allocation_weights_v{version}.json"
    out.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"통과: {out.relative_to(_BACKEND)} 기록")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
