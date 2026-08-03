"""실현 재생의 순서 독립성 (CAL-ROLE-BORDERLINE-01c1-b2, 2026-08-03).

강제 오행을 바꿔 가며 같은 세션에서 연달아 실행해도 결과가 흔들리지 않는지 본다.
흔들린다면 실현이 순수하지 않다는 뜻이고, 반사실 역할표를 보존할 근거가 사라진다.

    E1  fresh → 土            단독 기준선
    E2  fresh → 水            단독 기준선
    E3  fresh → 土 → 水        土 실행이 후속 水 를 오염시키는가
    E4  fresh → 水 → 土        水 실행이 후속 土 를 오염시키는가
    E5  fresh → 水 → 水        같은 입력 반복의 멱등성

**세션 사이에만 fresh capture 하고 세션 안에서는 재캡처하지 않는다.** 중간에 다시
포획하면 앞 실행의 영향이 지워져 순서 의존성을 검출할 수 없다.

값이 같다는 결과보다 **되먹임 경로가 없다는 구조적 확인**이 강하다. 그래서 두 번째
호출의 입력에 첫 실행 산출물이 섞이지 않았음을 identity 로도 확인한다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
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

_CASE_A = BirthInput(
    birth_date=date(1987, 8, 5), birth_time="21:00", birth_place_name="서울",
    gender="male", reference_date=date(2026, 7, 27),
)

_EARTH = "土"
_WATER = "水"

#: 세션별 강제 오행 순서.
_SESSIONS = {
    "E1": (_EARTH,),
    "E2": (_WATER,),
    "E3": (_EARTH, _WATER),
    "E4": (_WATER, _EARTH),
    "E5": (_WATER, _WATER),
}


def _fresh_capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """production 을 새로 돌려 실현 경계 입력을 포획한다(세션 시작점)."""
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    monkeypatch.setattr(cand_mod, "resolve_realized_roles", _spy)
    manse_service._cache.clear()
    calculate(_CASE_A)
    manse_service._cache.clear()
    assert captured, "실현 경계가 호출되지 않았다"
    return captured


def _input_fingerprint(kwargs: dict) -> str:
    """`selected_yongsin_element` 를 제외한 입력 지문."""
    ctx = kwargs["chart_context"]
    payload = {
        "models": [m.model_dump(mode="json") for m in kwargs["model_outputs"]],
        "candidates": [c.model_dump(mode="json") for c in kwargs["useful_candidates"]],
        "candidate_order": [c.element for c in kwargs["useful_candidates"]],
        "scores": {k: list(v) for k, v in sorted(kwargs["useful_scores"].items())},
        "group_elements": {k: str(v) for k, v in sorted(ctx.group_elements.items())},
        "group_strengths": dict(sorted(ctx.group_strengths.items())),
        "band": ctx.strength_band,
        "month_branch": str(ctx.month_branch),
        "bridge_detail": ctx.bridge_required_detail,
        "pillars": ctx.pillars.model_dump_json(),
        "force": ctx.force.model_dump_json(),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _semantic(result: RoleRealizationResult) -> tuple:
    """비교 대상 의미론. **원래 타입 그대로 비교한다** — 문자열로 정규화하면 Decimal
    정밀도와 역할표 구조가 뭉개진다. `selected_model_ref` identity 는 대상이 아니다.
    """
    return (
        result.selected_yongsin_element,
        result.top_model_type,
        result.selected_model_type,
        result.model_complete,
        result.special_role_kind,
        result.model_map_promoted,
        result.base_role_map,
        result.final_role_map,
        result.realization_origin,
        result.reason_codes,
        result.selected_model_confidence,
        result.warnings,
    )


def _run_sessions(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """E1~E5 를 실행한다. 세션 사이에만 재포획하고 안에서는 하지 않는다."""
    runs: dict[str, list] = {}
    for name, elements in _SESSIONS.items():
        captured = _fresh_capture(monkeypatch)
        session = []
        for element in elements:
            before = _input_fingerprint(captured)
            execution = resolve_realized_roles(
                **{**captured, "selected_yongsin_element": element}
            )
            session.append({
                "element": element,
                "result": execution.result,
                "fp_before": before,
                "fp_after": _input_fingerprint(captured),
            })
        runs[name] = session
    return runs


@pytest.fixture(scope="module")
def sessions(request) -> dict[str, list]:
    """5세션을 한 번만 실행해 모든 비교가 같은 관측을 보게 한다."""
    patcher = pytest.MonkeyPatch()
    request.addfinalizer(patcher.undo)
    return _run_sessions(patcher)


# ── 입력 불변식 ──────────────────────────────────────────────────────────


def test_every_session_starts_from_the_same_inputs(sessions) -> None:
    """세션마다 새로 포획해도 오행 외 입력 지문이 같다."""
    fingerprints = {r["fp_before"] for session in sessions.values() for r in session}
    assert len(fingerprints) == 1


def test_no_call_mutates_its_inputs(sessions) -> None:
    """어떤 호출도 입력을 바꾸지 않는다.

    출력 10필드가 우연히 같아도 입력이 변했다면 순서 독립성을 확정하면 안 된다.
    """
    for name, session in sessions.items():
        for run in session:
            assert run["fp_before"] == run["fp_after"], f"{name} {run['element']}"


# ── 水 결과 5종 ──────────────────────────────────────────────────────────


def test_all_water_replays_are_identical(sessions) -> None:
    """E2 · E3의 두 번째 · E4의 첫 번째 · E5의 두 실행이 모두 같다."""
    water = [
        ("E2", sessions["E2"][0]),
        ("E3.2", sessions["E3"][1]),
        ("E4.1", sessions["E4"][0]),
        ("E5.1", sessions["E5"][0]),
        ("E5.2", sessions["E5"][1]),
    ]
    assert all(run["element"] == _WATER for _, run in water)
    baseline = _semantic(water[0][1]["result"])
    for label, run in water[1:]:
        assert _semantic(run["result"]) == baseline, label


def test_water_baseline_matches_the_b1_finding(sessions) -> None:
    """b1 에서 고정한 실현 경로가 순서와 무관하게 유지된다."""
    r = sessions["E2"][0]["result"]
    assert r.top_model_type == "pattern_sangsin"
    assert r.selected_model_type == "pattern_sangsin"   # 조회 성공
    assert r.model_complete is False                    # 부분맵이라 승격 불가
    assert r.model_map_promoted is False
    assert r.realization_origin is RoleRealizationOrigin.STATIC_FALLBACK_ROLE_MAP
    assert r.reason_codes == ("static_fallback:model_incomplete",)
    assert r.final_role_map.as_dict() == {
        "yongsin": "水", "heesin": "金", "gisin": "土", "gusin": "火", "hansin": "木",
    }


# ── 土 결과 3종 — 역방향 오염 ────────────────────────────────────────────


def test_all_earth_replays_are_identical(sessions) -> None:
    """水 를 먼저 실행해도 뒤따르는 土 가 흔들리지 않는다."""
    earth = [
        ("E1", sessions["E1"][0]),
        ("E3.1", sessions["E3"][0]),
        ("E4.2", sessions["E4"][1]),
    ]
    assert all(run["element"] == _EARTH for _, run in earth)
    baseline = _semantic(earth[0][1]["result"])
    for label, run in earth[1:]:
        assert _semantic(run["result"]) == baseline, label


def test_earth_keeps_the_production_realization(sessions) -> None:
    """土 는 어느 순서에서도 production canonical 을 그대로 낸다."""
    for label, run in (("E1", sessions["E1"][0]), ("E4.2", sessions["E4"][1])):
        r = run["result"]
        assert r.top_model_type == "eokbu_normal", label
        assert r.selected_model_type == "eokbu_normal", label
        assert r.model_map_promoted is True, label
        assert r.realization_origin is (
            RoleRealizationOrigin.COMPLETE_MODEL_ROLE_MAP
        ), label
        assert r.final_role_map.as_dict() == {
            "yongsin": "土", "heesin": "金", "gisin": "木",
            "gusin": "火", "hansin": "水",
        }, label


def test_the_two_elements_really_take_different_paths(sessions) -> None:
    """두 결과가 같아서 순서 독립인 것이 아니다 — 실제로 다른 갈래를 탄다."""
    assert _semantic(sessions["E1"][0]["result"]) != _semantic(
        sessions["E2"][0]["result"]
    )


# ── 되먹임 경로 부재 (구조적) ────────────────────────────────────────────


def test_a_prior_execution_cannot_feed_the_next_call(monkeypatch) -> None:
    """두 번째 호출의 입력에 첫 실행 산출물이 identity 로도 섞이지 않는다.

    값이 같다는 결과보다 이쪽이 강하다. 되먹임 통로가 있으면 우연히 같은 값이 나온
    회귀는 통과하지만 계약은 이미 깨져 있다.
    """
    captured = _fresh_capture(monkeypatch)
    first = resolve_realized_roles(
        **{**captured, "selected_yongsin_element": _EARTH}
    )
    # `selected_model_ref` 는 새로 만든 객체가 아니라 **입력 모델 그대로**다. 그래서
    # 입력에서 그 id 가 보이는 것은 되먹임이 아니라 통과 참조다 — produced 에서 뺀다.
    assert any(m is first.selected_model_ref for m in captured["model_outputs"])
    produced = {
        id(first), id(first.result),
        id(first.result.final_role_map), id(first.result.base_role_map),
        id(first.result.reason_codes),
    }

    second_input = {**captured, "selected_yongsin_element": _WATER}
    seen: set[int] = set()
    for value in second_input.values():
        seen.add(id(value))
        if isinstance(value, (list, tuple)):
            seen.update(id(item) for item in value)
        elif isinstance(value, dict):
            seen.update(id(item) for item in value.values())
    assert produced & seen == set()

    # 강제 오행 외에는 첫 호출 입력과 **같은 객체**를 쓴다 — 재조립하지 않았다.
    for key, value in captured.items():
        if key != "selected_yongsin_element":
            assert second_input[key] is value
