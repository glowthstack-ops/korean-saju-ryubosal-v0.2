"""runner-up 水 단독 fresh replay (CAL-ROLE-BORDERLINE-01c1-b1, 2026-08-03).

**용신 오행 하나만 강제하고 나머지는 전부 resolver 가 다시 정한다.** `top_model`·
`selected_model`·`model_complete`·`special_role_kind`·`model_map_promoted`·
`final_role_map`·폴백 사유를 이전 실행에서 가져오면 반사실이 아니라 primary 의 그림자다.

기대값을 먼저 고정하지 않았다. production resolver 산출을 사실대로 기록한 뒤 사후 비교만
붙인다 — 01c0 에서 감사 가설을 기대값으로 넣었다가 두 번 뒤집혔다.

    직접 원인을 반드시 함께 고정한다

    STATIC_FALLBACK_FROM_INCOMPLETE_MODEL_MAP   조회 성공 + 부분맵          ← 실측
    STATIC_FALLBACK_FROM_MODEL_LOOKUP_MISS      조회 실패                   ← 아님

    결과는 둘 다 정적 폴백이지만 계약이 전혀 다르다. 01c1-b0 이전에는 `top_model` 이
    index 로 고정돼 강제 水 가 primary 의 eokbu_normal 을 물려받았고, 그러면 조회
    실패로 폴백해 **맞는 결론을 틀린 근거로** 얻었다.

`order_independence` 는 아직 시작하지 않았다(01c1-b2).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from saju_manse_analysis.yongsin import candidates as cand_mod
from saju_manse_analysis.yongsin.candidates import _classify_roles
from saju_manse_analysis.yongsin.role_realization import (
    RoleRealizationOrigin,
    resolve_realized_roles,
)

from saju_api.services import manse_service
from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_CASE_A = BirthInput(
    birth_date=date(1987, 8, 5), birth_time="21:00", birth_place_name="서울",
    gender="male", reference_date=date(2026, 7, 27),
)

_RUNNER_UP = "水"
_PRIMARY = "土"


def _fresh_capture(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict]:
    """production 을 새로 돌려 실현 경계 입력을 포획한다.

    **매 실험이 여기서 시작한다.** 같은 dict 를 돌려 쓰면 앞 실행의 흔적이 남았는지
    검사할 수 없다. 캐시를 비우지 않으면 경계가 아예 호출되지 않는다.
    """
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return resolve_realized_roles(**kwargs)

    monkeypatch.setattr(cand_mod, "resolve_realized_roles", _spy)
    manse_service._cache.clear()
    result = calculate(_CASE_A).yongsin_analysis
    manse_service._cache.clear()
    assert captured, "실현 경계가 호출되지 않았다"
    return result, captured


def _input_fingerprint(kwargs: dict) -> str:
    """`selected_yongsin_element` 를 **제외한** 입력 지문.

    이게 같아야 "水 만 바꾼 replay" 라고 말할 수 있다. 실행 전후만 비교하면 애초에
    다른 입력으로 시작했는지를 놓친다.
    """
    ctx = kwargs["chart_context"]
    payload = {
        "models": [m.model_dump(mode="json") for m in kwargs["model_outputs"]],
        "candidates": [c.model_dump(mode="json") for c in kwargs["useful_candidates"]],
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


# ── 강제 입력은 오행 하나뿐 ──────────────────────────────────────────────


def test_only_the_element_differs_between_captures(monkeypatch) -> None:
    """서로 다른 fresh capture 의 입력 지문이 같다 — 실험 기반이 흔들리지 않는다."""
    _, first = _fresh_capture(monkeypatch)
    _, second = _fresh_capture(monkeypatch)
    assert _input_fingerprint(first) == _input_fingerprint(second)
    assert first["selected_yongsin_element"] == second["selected_yongsin_element"]


def test_forced_water_input_differs_only_in_the_element(monkeypatch) -> None:
    """강제 입력이 production 포획과 오행 외에는 동일하다."""
    _, captured = _fresh_capture(monkeypatch)
    forced = {**captured, "selected_yongsin_element": _RUNNER_UP}

    assert captured["selected_yongsin_element"] == _PRIMARY
    assert forced["selected_yongsin_element"] == _RUNNER_UP
    assert _input_fingerprint(forced) == _input_fingerprint(captured)


def test_replay_does_not_mutate_its_inputs(monkeypatch) -> None:
    """실행 전후 입력 지문이 같다."""
    _, captured = _fresh_capture(monkeypatch)
    forced = {**captured, "selected_yongsin_element": _RUNNER_UP}

    before = _input_fingerprint(forced)
    resolve_realized_roles(**forced)
    assert _input_fingerprint(forced) == before


# ── 실제 산출 — 가설이 아니라 사실 ───────────────────────────────────────


def test_water_standalone_replay_records_the_actual_path(monkeypatch) -> None:
    """水 단독 재생의 실현 경로 전체를 사실대로 고정한다."""
    _, captured = _fresh_capture(monkeypatch)
    execution = resolve_realized_roles(
        **{**captured, "selected_yongsin_element": _RUNNER_UP}
    )
    r = execution.result

    assert r.selected_yongsin_element == "水"                 # 1 강제 오행
    assert r.top_model_type == "pattern_sangsin"              # 2 재도출된 모델 종류
    assert r.selected_model_type == "pattern_sangsin"         # 3·4 조회 키와 결과
    assert r.model_complete is False                          # 5
    assert r.special_role_kind is None                        # 6
    assert r.model_map_promoted is False                      # 7
    assert r.realization_origin is (                          # 8
        RoleRealizationOrigin.STATIC_FALLBACK_ROLE_MAP
    )
    assert r.reason_codes == ("static_fallback:model_incomplete",)  # 9
    assert r.selected_model_confidence == Decimal("0.7")      # 10
    assert r.warnings == ()
    assert r.final_role_map.as_dict() == {
        "yongsin": "水", "heesin": "金", "gisin": "土", "gusin": "火", "hansin": "木",
    }


def test_fallback_cause_is_an_incomplete_map_not_a_lookup_miss(monkeypatch) -> None:
    """직접 원인을 고정한다 — 결과가 같아도 계약이 다르다.

    조회는 **성공**했다(pattern_sangsin·yongsin=水). 승격이 막힌 이유는 그 모델의
    역할표가 부분맵이기 때문이다. 01c1-b0 이전이라면 primary 의 eokbu_normal 을
    물려받아 조회 실패로 떨어졌을 것이고, 같은 `STATIC_FALLBACK` 을 틀린 근거로
    기록했을 것이다.
    """
    _, captured = _fresh_capture(monkeypatch)
    r = resolve_realized_roles(
        **{**captured, "selected_yongsin_element": _RUNNER_UP}
    ).result

    assert r.selected_model_type is not None, "조회 실패가 아니다"
    assert "static_fallback:no_selected_model" not in r.reason_codes
    assert "static_fallback:model_incomplete" in r.reason_codes

    water_model = next(
        m for m in captured["model_outputs"]
        if m.model_type == "pattern_sangsin" and m.yongsin == "水"
    )
    missing = [
        k for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")
        if getattr(water_model, k) is None
    ]
    assert missing, "부분맵이 아니면 이 원인 기록이 틀렸다"


def test_primary_and_runner_up_take_different_realization_paths(monkeypatch) -> None:
    """같은 입력에서 오행만 바꾸면 실현 갈래 자체가 달라진다."""
    _, captured = _fresh_capture(monkeypatch)
    primary = resolve_realized_roles(**captured).result
    runner_up = resolve_realized_roles(
        **{**captured, "selected_yongsin_element": _RUNNER_UP}
    ).result

    assert primary.realization_origin is RoleRealizationOrigin.COMPLETE_MODEL_ROLE_MAP
    assert runner_up.realization_origin is (
        RoleRealizationOrigin.STATIC_FALLBACK_ROLE_MAP
    )
    assert primary.top_model_type != runner_up.top_model_type
    assert primary.final_role_map != runner_up.final_role_map


# ── 선택 단계 feedback 없음 ──────────────────────────────────────────────


def test_forced_replay_does_not_change_the_production_decision(monkeypatch) -> None:
    """반사실 실행은 원본 결정 묶음을 바꾸지 않는다."""
    production, captured = _fresh_capture(monkeypatch)
    resolve_realized_roles(**{**captured, "selected_yongsin_element": _RUNNER_UP})

    after = calculate(_CASE_A).yongsin_analysis
    assert after.final["yongsin"] == _PRIMARY
    assert after.final["selected_model"] == "eokbu_normal"
    assert after.canonical_roles == production.canonical_roles
    assert [(c.element, c.score, c.model) for c in after.useful_candidates] == [
        ("土", 0.1508, "eokbu_normal"), ("水", 0.14, "pattern_sangsin"),
    ]
    margin = after.useful_candidates[0].score - after.useful_candidates[1].score
    assert round(margin, 4) == 0.0108


# ── 사후 비교 — 근거가 아니라 관측 ───────────────────────────────────────


def test_observed_map_coincides_with_the_static_classifier(monkeypatch) -> None:
    """관측된 역할표가 `_classify_roles(水)` 와 같다.

    **이것이 근거는 아니다.** 실현 경로가 정적 폴백이었으므로 같은 것이 당연하고,
    반대로 이 일치를 보고 경로를 추정하면 01c0 의 오류를 반복한다. origin 은
    `STATIC_FALLBACK_ROLE_MAP` 이라는 산출로만 정한다.
    """
    _, captured = _fresh_capture(monkeypatch)
    r = resolve_realized_roles(
        **{**captured, "selected_yongsin_element": _RUNNER_UP}
    ).result
    assert r.final_role_map.as_dict() == _classify_roles(_RUNNER_UP)
    assert r.final_role_map == r.base_role_map
