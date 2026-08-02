"""역할 실현 경계 추출 + primary 재현 (CAL-ROLE-BORDERLINE-01c1-a, 2026-08-03).

01c0 은 canonical 역할표의 출처를 **소스 읽기로만** 추적하다 두 번 뒤집혔다. 경로가
함수 안에 잠겨 있으면 반사실을 실행할 방법이 없고, 그래서 runner-up 을 같은 경로로
재생할 수 있는지조차 확인하지 못했다.

이 슬라이스는 경계를 뽑고 **primary 土 재현까지만** 한다. runner-up 水 실행은 포함하지
않는다 — primary 가 재현되지 않으면 반사실 실험은 의미가 없다.

재현 방식은 내부값 재구성이 아니라 **production 입력 포획**이다. 실제 호출이 받은
인자를 그대로 다시 넣어 같은 결과가 나오는지 본다. 재구성하면 재구성이 맞는지를
다시 증명해야 한다.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from saju_manse_analysis.yongsin import candidates as cand_mod
from saju_manse_analysis.yongsin.role_realization import (
    RoleRealizationOrigin,
    RoleRealizationResult,
    resolve_realized_roles,
)

from saju_api.services import manse_service
from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")

_CASE_A = BirthInput(
    birth_date=date(1987, 8, 5), birth_time="21:00", birth_place_name="서울",
    gender="male", reference_date=date(2026, 7, 27),
)

#: 실현 갈래가 한 종류만 나오면 origin 구분이 검증되지 않는다.
_COHORT = (
    (date(1987, 8, 5), "21:00", "male"),
    (date(1990, 3, 12), "07:30", "female"),
    (date(1975, 11, 2), "14:00", "male"),
    (date(2001, 6, 21), "03:10", "female"),
    (date(1968, 1, 9), "19:45", "male"),
    (date(1995, 9, 30), "11:20", "female"),
    (date(1983, 4, 17), "23:40", "male"),
    (date(1979, 12, 25), "05:05", "female"),
)


def _capture(birth: BirthInput, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict]:
    """`calculate` 를 한 번 돌리고 실현 경계가 받은 인자를 포획한다.

    캐시를 비우지 않으면 앞선 테스트의 결과가 반환돼 경계가 호출되지 않는다.
    """
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)  # 스파이를 겹치지 않게 원본을 직접 부른다

    monkeypatch.setattr(cand_mod, "resolve_realized_roles", _spy)
    manse_service._cache.clear()
    result = calculate(birth).yongsin_analysis
    manse_service._cache.clear()
    assert captured, "실현 경계가 호출되지 않았다"
    return result, captured


# ── 경계가 production 경로 위에 있다 ─────────────────────────────────────


def test_boundary_is_on_the_production_path(monkeypatch) -> None:
    """포획된 인자가 실제 산출과 이어진다 — 죽은 코드가 아니다."""
    y, kwargs = _capture(_CASE_A, monkeypatch)
    assert kwargs["selected_yongsin_element"] == y.final["yongsin"]
    assert set(kwargs) == {
        "chart_context", "selected_yongsin_element", "useful_candidates",
        "useful_scores", "model_outputs", "static_classifier", "bridge_classifier",
    }


def test_resolver_does_not_accept_derived_decisions_as_input() -> None:
    """강제할 수 있는 것은 용신 오행 하나뿐이다.

    `top_model`·`selected_model`·`model_complete`·`model_map_promoted` 를 입력으로
    받으면 강제 용신 재생이 primary 의 판정을 그대로 물려받아 반사실이 성립하지 않는다.
    """
    params = set(inspect.signature(resolve_realized_roles).parameters)
    forbidden = {
        "top_model_type", "top_model", "selected_model", "selected_model_ref",
        "selected_model_type", "model_complete", "model_map_promoted",
        "special_role_kind", "final_role_map",
    }
    assert params & forbidden == set()


def test_derived_top_model_matches_the_production_rule(monkeypatch) -> None:
    """오행 기준 도출이 production 의 index-0 규칙과 코호트 전건에서 같다.

    정렬 키가 `(role == "yongsin", score)` 내림차순이라 yongsin 역할 후보가 있으면
    index 0 이 곧 확정 용신의 후보다. 그런데도 오행 기준으로 뽑는 이유는 강제 재생
    때문이며, 두 규칙이 실제로 같은지를 여기서 고정한다.
    """
    for birth_date, birth_time, gender in _COHORT:
        birth = BirthInput(
            birth_date=birth_date, birth_time=birth_time, birth_place_name="서울",
            gender=gender, reference_date=date(2026, 7, 27),
        )
        y, kwargs = _capture(birth, monkeypatch)
        candidates = kwargs["useful_candidates"]
        production_rule = candidates[0].model if candidates else None
        derived = resolve_realized_roles(**kwargs).result.top_model_type
        assert derived == production_rule == y.final["selected_model"]


# ── primary 土 재현 ──────────────────────────────────────────────────────


def test_primary_case_a_replay_matches_the_contract(monkeypatch) -> None:
    """사례 A 의 실제 선택(土)을 그대로 넣어 재생한다."""
    y, kwargs = _capture(_CASE_A, monkeypatch)
    replay = resolve_realized_roles(**kwargs).result

    assert replay.selected_yongsin_element == "土"
    assert replay.selected_model_type == "eokbu_normal"
    assert replay.selected_model_confidence == Decimal("0.6033")
    assert replay.special_role_kind is None
    assert replay.model_complete is True
    assert replay.model_map_promoted is True
    assert replay.realization_origin is RoleRealizationOrigin.COMPLETE_MODEL_ROLE_MAP
    assert replay.final_role_map.as_dict() == {
        "yongsin": "土", "heesin": "金", "gisin": "木", "gusin": "火", "hansin": "水",
    }
    assert "model_map_promoted" in replay.reason_codes
    assert replay.warnings == ()
    # 정적 폴백은 채택되지 않았다 — base 와 final 이 다르다.
    assert replay.base_role_map != replay.final_role_map


def test_primary_replay_equals_production_canonical(monkeypatch) -> None:
    """재생 결과가 production canonical 5역할과 전부 같다."""
    y, kwargs = _capture(_CASE_A, monkeypatch)
    execution = resolve_realized_roles(**kwargs)
    assert execution.result.final_role_map.as_dict() == y.canonical_roles


def test_replay_is_deterministic_and_leaves_inputs_untouched(monkeypatch) -> None:
    """반복 실행이 같은 결과를 내고 입력을 변형하지 않는다.

    runner-up 재생(01c1-b)의 전제다 — primary 실행이 입력을 바꿔 놓으면 두 번째
    실행은 다른 입력을 받는다.
    """
    _, kwargs = _capture(_CASE_A, monkeypatch)
    before_models = [m.model_dump() for m in kwargs["model_outputs"]]
    before_scores = dict(kwargs["useful_scores"])

    first = resolve_realized_roles(**kwargs)
    second = resolve_realized_roles(**kwargs)

    assert first == second
    assert [m.model_dump() for m in kwargs["model_outputs"]] == before_models
    assert dict(kwargs["useful_scores"]) == before_scores


def test_role_map_hands_out_fresh_dicts(monkeypatch) -> None:
    """`as_dict()` 를 바꿔도 결과가 흔들리지 않는다 — mutable 내부 상태를 넘기지 않는다."""
    _, kwargs = _capture(_CASE_A, monkeypatch)
    replay = resolve_realized_roles(**kwargs).result
    borrowed = replay.final_role_map.as_dict()
    borrowed["yongsin"] = "破壞"
    assert replay.final_role_map.as_dict()["yongsin"] == "土"


# ── 폴백 갈래 — 경계를 뽑은 덕에 행동으로 볼 수 있다 ─────────────────────
#
# 아래 둘은 **용신 오행을 바꾸지 않는다**(계속 土). 모델 구성만 달리해 승격 조건을
# 검증하는 순수 함수 단위 테스트이며, runner-up 재생(01c1-b)이 아니다.


def test_missing_selected_model_falls_back_to_static_map(monkeypatch) -> None:
    """선택 모델을 못 찾으면 승격하지 않고 정적 생극 폴백을 쓴다."""
    _, kwargs = _capture(_CASE_A, monkeypatch)
    replay = resolve_realized_roles(**{**kwargs, "model_outputs": ()}).result

    assert replay.selected_model_type is None
    assert replay.model_complete is False
    assert replay.model_map_promoted is False
    assert replay.realization_origin is RoleRealizationOrigin.STATIC_FALLBACK_ROLE_MAP
    assert replay.final_role_map == replay.base_role_map
    assert "static_fallback:no_selected_model" in replay.reason_codes


def test_partial_model_falls_back_to_static_map(monkeypatch) -> None:
    """부분맵 모델만 남으면 승격 불가 — canonical 이 정적 폴백이 된다."""
    _, kwargs = _capture(_CASE_A, monkeypatch)
    partial = [m for m in kwargs["model_outputs"] if m.is_auxiliary]
    assert partial, "부분맵 모델이 없으면 이 갈래를 검증할 수 없다"
    forced_models = [m.model_copy(update={"yongsin": "土"}) for m in partial]
    # 모델 종류는 후보표에서 도출되므로 후보표도 함께 부분맵 모델을 가리켜야 한다.
    forced_candidates = [
        c.model_copy(update={"model": forced_models[0].model_type})
        if c.element == "土" else c
        for c in kwargs["useful_candidates"]
    ]

    replay = resolve_realized_roles(**{
        **kwargs, "model_outputs": forced_models,
        "useful_candidates": forced_candidates,
    }).result
    assert replay.selected_model_type == forced_models[0].model_type
    assert replay.model_complete is False
    assert replay.model_map_promoted is False
    assert replay.realization_origin is RoleRealizationOrigin.STATIC_FALLBACK_ROLE_MAP
    assert "static_fallback:model_incomplete" in replay.reason_codes


# ── production 비회귀 ────────────────────────────────────────────────────


def test_selection_stage_outputs_are_unchanged() -> None:
    """선택 단계 값이 추출 전과 같다.

    실현 resolver 는 선택 산출물을 되돌려 쓰지 않는다 — 값이 바뀌면 선택·실현 결합
    문제를 다시 열어야 한다.
    """
    y = calculate(_CASE_A).yongsin_analysis
    assert y.final == {
        "yongsin": "土", "heesin": "金", "gisin": "木", "gusin": "火", "hansin": "水",
        "confidence": 0.6033, "selected_model": "eokbu_normal",
    }
    assert y.status == "candidate"
    useful = y.useful_candidates
    assert [(c.element, c.score, c.model, c.reason) for c in useful] == [
        ("土", 0.1508, "eokbu_normal", "yongsin"),
        ("水", 0.14, "pattern_sangsin", "yongsin"),
    ]
    # competing 은 선택 단계에서 계산되고 실현이 건드리지 않는다.
    assert (useful[0].score - useful[1].score) < 0.12


def test_realization_origin_is_recorded_per_case(monkeypatch) -> None:
    """코호트 전건에서 경계 산출이 production canonical 과 같고 갈래가 기록된다."""
    seen: set[RoleRealizationOrigin] = set()
    for birth_date, birth_time, gender in _COHORT:
        birth = BirthInput(
            birth_date=birth_date, birth_time=birth_time, birth_place_name="서울",
            gender=gender, reference_date=date(2026, 7, 27),
        )
        y, kwargs = _capture(birth, monkeypatch)
        replay = resolve_realized_roles(**kwargs).result
        assert replay.final_role_map.as_dict() == y.canonical_roles
        assert replay.selected_yongsin_element == y.final["yongsin"]
        seen.add(replay.realization_origin)

    # 갈래가 하나뿐이면 구분 자체가 검증되지 않는다.
    assert RoleRealizationOrigin.COMPLETE_MODEL_ROLE_MAP in seen
    assert RoleRealizationOrigin.BRIDGE_SPECIAL_ROLE_MAP in seen


def test_special_branch_precedes_model_map_promotion(monkeypatch) -> None:
    """특수분기 사례는 완비 모델이 있어도 승격되지 않는다."""
    bridge = BirthInput(
        birth_date=date(1968, 1, 9), birth_time="19:45", birth_place_name="서울",
        gender="male", reference_date=date(2026, 7, 27),
    )
    y, kwargs = _capture(bridge, monkeypatch)
    replay = resolve_realized_roles(**kwargs).result
    assert replay.special_role_kind == "bridge_tonggwan"
    assert replay.model_map_promoted is False
    assert replay.realization_origin is RoleRealizationOrigin.BRIDGE_SPECIAL_ROLE_MAP
    assert replay.final_role_map.as_dict() == y.canonical_roles


# ── selected_model_ref 오염 방지 (01c1-b0) ──────────────────────────────


def test_semantic_result_holds_no_model_object() -> None:
    """의미론 결과에 mutable 모델 객체가 없다 — identity 가 비교·지문에 새지 않는다."""
    fields = {f.name for f in dataclasses.fields(RoleRealizationResult)}
    assert "selected_model" not in fields
    assert "selected_model_ref" not in fields
    assert {"selected_model_type", "selected_model_confidence"} <= fields


def test_model_ref_is_excluded_from_equality(monkeypatch) -> None:
    """참조가 달라도 의미론이 같으면 같은 실행이다."""
    _, kwargs = _capture(_CASE_A, monkeypatch)
    execution = resolve_realized_roles(**kwargs)
    assert execution.selected_model_ref is not None

    stripped = dataclasses.replace(execution, selected_model_ref=None)
    assert stripped == execution
    assert stripped.result == execution.result
    # 모델 **객체** 는 repr 에 실려 나가지 않는다(의미론 필드인 모델 종류는 남는다).
    assert type(execution.selected_model_ref).__name__ not in repr(execution)
    assert execution.result.selected_model_type == "eokbu_normal"


def test_model_ref_is_not_reusable_as_replay_input() -> None:
    """참조를 입력으로 되먹일 통로가 없다 — 시그니처에 자리가 없다."""
    params = inspect.signature(resolve_realized_roles).parameters
    assert not any("model_ref" in name for name in params)


# ── eeaed83 비배선 유지 ──────────────────────────────────────────────────


def test_boundary_does_not_wire_the_superseded_role_candidates() -> None:
    """`CanonicalRoleMap` 과 모양이 같아도 SUPERSEDED 타입을 끌어오지 않는다."""
    from pathlib import Path

    from saju_manse_analysis.yongsin import role_realization

    text = Path(role_realization.__file__).read_text(encoding="utf-8")
    imports = [ln for ln in text.splitlines() if ln.startswith(("import ", "from "))]
    assert imports
    assert not any("role_candidates" in ln or "saju_engines" in ln for ln in imports)
