"""P2-0 캘리브레이션 명세 ↔ 코드 drift lint (RELATIONSHIP_VECTOR_CALIBRATION).

spec_only 레지스트리(`relationship_vector_calibration_spec.v1.json`)의 current 값이
실제 코드 상수(`relationship_effect_vector` + `relation_palace_modifier.json`)와
일치하는지 강제한다. 계수가 코드에서 바뀌면 명세도 갱신해야 하며(그렇지 않으면 이
테스트가 실패), 명세를 "자동 충족"으로 처리하지 않는다(리뷰 §2-4).

추가로 레지스트리 구조 검증: spec_only 상태·중복 parameter_id·band 오름차순.
"""

from __future__ import annotations

import json
from pathlib import Path

import saju_engines.relationship_effect_vector as V

_SPEC = (Path(__file__).resolve().parents[2].parent / "doc" / "v2_2"
         / "relationship_vector_calibration_spec.v1.json")
_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _spec() -> dict:
    return json.loads(_SPEC.read_text(encoding="utf-8"))


def test_spec_is_spec_only_not_runtime_loadable():
    s = _spec()
    assert s["status"] == "spec_only"
    assert s["runtime_loadable"] is False


def test_current_values_match_code_constants():
    """레지스트리 current_values가 코드 상수와 정확히 일치(drift 차단)."""
    cur = _spec()["current_values"]
    assert cur["same_root.secondary_factor"] == V._SECONDARY_FACTOR
    assert cur["modifier.jaenghap_support_weaken"] == V._SUPPORT_WEAKEN
    assert cur["activation.thresholds"] == {
        "weak": V._ACT_BAND["weak"], "moderate": V._ACT_BAND["moderate"],
        "strong": V._ACT_BAND["strong"]}
    assert cur["stability.support"] == V._STAB_SUPPORT
    assert cur["stability.pressure"] == V._STAB_PRESSURE
    assert cur["separation.pressure"] == V._SEP_WEIGHT


def test_activation_kind_bonus_matches_dictionary():
    """activation.kind_base_bonus가 relation_palace_modifier.json과 일치(S1 소스)."""
    raw = json.loads(
        (_DICTS / "event_engine" / "relation_palace_modifier.json")
        .read_text(encoding="utf-8"))
    dict_bonus = {k: v["base_event_score_bonus"]
                  for k, v in raw["relation_types"].items()}
    spec_bonus = _spec()["current_values"]["activation.kind_base_bonus"]
    for k, v in spec_bonus.items():
        assert dict_bonus[k] == v, f"{k}: spec {v} != dict {dict_bonus[k]}"


def test_stability_band_matches_code():
    """stability signed band 경계가 코드(synthesize)와 일치."""
    # 코드: weak if net <= -0.8 else moderate if net < 0.3 else strong
    cur = _spec()["current_values"]["stability.band"]
    assert cur["weak_max_inclusive"] == -0.8
    assert cur["moderate_max_exclusive"] == 0.3


def test_no_duplicate_parameter_ids():
    ids = [p["parameter_id"] for p in _spec()["parameters"]]
    assert len(ids) == len(set(ids)), "중복 parameter_id"


def test_activation_band_profiles_ascending():
    """모든 band profile은 weak <= moderate <= strong(오름차순)."""
    for prof in _spec()["activation_band_profiles"]:
        assert prof["weak"] <= prof["moderate"] <= prof["strong"], prof["id"]


def test_scope_axes_are_three_evaluated():
    s = _spec()
    assert set(s["scope_axes"]) == {
        "activation", "stability", "separation_pressure"}
    assert set(s["out_of_scope_axes"]) == {
        "exposure", "realization", "experience_valence", "formalization"}


def test_every_parameter_has_required_fields():
    """리뷰 §2-2 — 각 파라미터에 stage·affected_axes·hard_constraints·experiment_only."""
    for p in _spec()["parameters"]:
        for field in ("parameter_id", "current_value", "calculation_stage",
                      "affected_axes", "candidate_values", "hard_constraints",
                      "experiment_only"):
            assert field in p, f"{p.get('parameter_id')}: {field} 누락"


def test_calibration_version_matches_code():
    s = _spec()
    assert s["calibration_version_current"] == V.RELATIONSHIP_CALIBRATION_VERSION
    assert s["schema_version_current"] == V.RELATIONSHIP_VECTOR_SCHEMA_VERSION
