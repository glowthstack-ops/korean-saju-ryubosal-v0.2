"""direction_suggestions 사전·스키마·lint 검증 (능동 제안 계층 Phase A, docs/15)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from saju_engines.dictionaries import SCHEMA_BY_PATH, _lint_direction_suggestions
from saju_shared_types.direction_suggestions import (
    DirectionSuggestion,
    DirectionSuggestionDict,
    SuggestionCondition,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_SRC = _DICTS / "direction_suggestions.json"


def _load() -> DirectionSuggestionDict:
    """시드 사전 원본을 파싱한다."""
    return DirectionSuggestionDict.model_validate(json.loads(_SRC.read_text("utf-8")))


def _minimal_rule(**overrides: Any) -> dict[str, Any]:
    """lint 음성 테스트용 최소 유효 룰(2축: group_state + ten_god_status)."""
    rule: dict[str, Any] = {
        "suggestion_id": "T1",
        "name_ko": "테스트",
        "group": "wealth",
        "reality_note": "n",
        "trigger": [{"kind": "group_state", "group": "wealth", "states": ["natal_excess"]}],
        "channels": [
            {
                "channel_id": "c1",
                "name_ko": "c",
                "conditions": [
                    {"kind": "ten_god_status", "ten_gods": ["SHANGGUAN"], "status": "active"}
                ],
                "direction": {"headline": "h", "actions": ["a"]},
            }
        ],
        "llm_tag": "t",
    }
    rule.update(overrides)
    return rule


def _dict_with(rules: list[dict[str, Any]]) -> DirectionSuggestionDict:
    """테스트용 사전을 구성한다."""
    return DirectionSuggestionDict.model_validate(
        {"schema": "direction_suggestions.v1", "reviewed": False, "rules": rules}
    )


def test_registered_in_schema_by_path() -> None:
    """새 사전이 validate 파이프라인에 등록되어 있어야 한다(원칙 5)."""
    assert SCHEMA_BY_PATH["direction_suggestions.json"] is DirectionSuggestionDict


def test_seed_parses_and_covers_all_groups() -> None:
    """시드는 5개 십성군 x 과다/부족 = 10 base rule 전체 규격(절대원칙 10)."""
    file = _load()
    ids = {r.suggestion_id for r in file.rules}
    assert ids == {
        "WEALTH_EXCESS",
        "WEALTH_DEFICIT",
        "AUTHORITY_EXCESS",
        "AUTHORITY_DEFICIT",
        "RESOURCE_EXCESS",
        "RESOURCE_DEFICIT",
        "PEER_EXCESS",
        "PEER_DEFICIT",
        "OUTPUT_EXCESS",
        "OUTPUT_DEFICIT",
    }
    assert {r.group for r in file.rules} == {"peer", "output", "wealth", "authority", "resource"}


def test_seed_lint_clean() -> None:
    """시드 사전은 lint 위반이 없어야 한다."""
    assert _lint_direction_suggestions(_DICTS, _load()) == []


def test_seed_prototype_rule_shape() -> None:
    """원형 룰(재성 과다 x 상관 작동)이 승인된 구조를 유지해야 한다."""
    rule = next(r for r in _load().rules if r.suggestion_id == "WEALTH_EXCESS")
    channel = next(c for c in rule.channels if c.channel_id == "sanggwan_side_income")
    kinds = {c.kind for c in channel.conditions}
    assert kinds == {"ten_god_status"}  # 상관 작동 + 식신 비작동
    assert rule.guards, "guard(신약·기신·충파 등) 없이는 반전 정책이 성립하지 않는다"
    assert rule.caution_headline
    assert any("퇴사" in f for f in rule.forbidden_framings)


def test_lint_rejects_single_axis_channel() -> None:
    """trigger+channel 조건 축이 1종이면 다요소 원칙 위반."""
    rule = _minimal_rule(
        channels=[
            {
                "channel_id": "c1",
                "name_ko": "c",
                "conditions": [{"kind": "group_state", "group": "peer", "states": ["luck_inflow"]}],
                "direction": {"headline": "h", "actions": ["a"]},
            }
        ]
    )
    errors = _lint_direction_suggestions(_DICTS, _dict_with([rule]))
    assert any("다요소" in e for e in errors)


def test_lint_rejects_unknown_pattern_id() -> None:
    """structure_patterns 에 없는 pattern_id 참조는 위반."""
    rule = _minimal_rule(
        guards=[
            {
                "guard_id": "g1",
                "conditions": [{"kind": "pattern", "pattern_ids": ["NO_SUCH_PATTERN"]}],
                "note": "n",
            }
        ],
        caution_headline="c",
    )
    errors = _lint_direction_suggestions(_DICTS, _dict_with([rule]))
    assert any("미등록 구조패턴" in e for e in errors)


def test_lint_requires_caution_headline_with_guards() -> None:
    """guard가 있으면 반전용 caution_headline이 반드시 있어야 한다."""
    rule = _minimal_rule(
        guards=[
            {
                "guard_id": "g1",
                "conditions": [{"kind": "strength_band", "bands": ["신약"]}],
                "note": "n",
            }
        ]
    )
    errors = _lint_direction_suggestions(_DICTS, _dict_with([rule]))
    assert any("caution_headline" in e for e in errors)


def test_lint_rejects_duplicate_suggestion_id() -> None:
    """suggestion_id 중복은 위반."""
    errors = _lint_direction_suggestions(_DICTS, _dict_with([_minimal_rule(), _minimal_rule()]))
    assert any("중복 suggestion_id" in e for e in errors)


def test_lint_rejects_invalid_enums() -> None:
    """미지원 십성/십성군/역할 값은 위반."""
    rule = _minimal_rule(
        trigger=[{"kind": "group_state", "group": "wealth", "states": ["natal_excess"]}],
        supports=[
            {
                "condition": {"kind": "yongsin_role", "target": "NOPE", "roles": ["용신"]},
                "note": "n",
            }
        ],
    )
    errors = _lint_direction_suggestions(_DICTS, _dict_with([rule]))
    assert any("yongsin_role target 미지원" in e for e in errors)


def test_condition_kind_requires_fields() -> None:
    """kind별 필수 필드 누락은 스키마 단계에서 거부."""
    with pytest.raises(ValidationError):
        SuggestionCondition(kind="group_state")
    with pytest.raises(ValidationError):
        SuggestionCondition(kind="ten_god_status", ten_gods=["SHANGGUAN"])  # status 누락


def test_output_model_strength_bounds() -> None:
    """엔진 출력 strength는 0~1 범위를 강제한다."""
    base: dict[str, Any] = {
        "suggestion_id": "WEALTH_EXCESS",
        "name_ko": "n",
        "group": "wealth",
        "group_state": "natal_excess",
        "mode": "recommend",
        "channel_id": "c1",
        "headline": "h",
    }
    assert DirectionSuggestion(**base, strength=0.5).strength == 0.5
    with pytest.raises(ValidationError):
        DirectionSuggestion(**base, strength=1.5)


def test_snapshot_build(tmp_path: Path) -> None:
    """validate → compile 스냅샷 빌드가 성공하고 룰 수가 보존돼야 한다."""
    script = _BACKEND / "scripts" / "build_direction_suggestions_snapshot.py"
    spec = importlib.util.spec_from_file_location("build_direction_suggestions_snapshot", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_direction_suggestions_snapshot"] = module
    spec.loader.exec_module(module)

    assert module.build(_DICTS, tmp_path) == 0
    out = tmp_path / f"direction_suggestions_v{module.DIRECTION_SUGGESTIONS_VERSION}.json"
    snapshot = json.loads(out.read_text("utf-8"))
    assert len(snapshot["rules"]) == len(_load().rules)
    assert snapshot["snapshot_version"] == module.DIRECTION_SUGGESTIONS_VERSION
