"""설정된 LLM 모델의 가격표 커버리지 게이트 (2026-07-31).

`estimate_cost_usd()` 는 미등록 모델을 **경고 없이 0.0** 으로 집계한다. 원가 누락이
대시보드 값을 낮추기만 하고 틀린 티를 내지 않아, `gpt-5.4-mini` 가 등록된 적 없는
채로 계속 지나갔다. 배포 전에 잡는 지점이 여기다.

두 계약을 함께 고정한다.

    구성된 역할 전체를 검사   런타임 활성 여부가 검사 대상을 결정하지 않는다
    0.0 fallback 은 불변      가격 누락으로 운영 중 응답을 막지 않는다
"""

from __future__ import annotations

from typing import Any

import pytest

from saju_api.services import llm_client
from saju_engines.report_builder import estimate_cost_usd


def test_all_configured_models_have_prices() -> None:
    """배포 전 게이트 — 설정된 모델은 모두 가격표에 있어야 한다."""
    missing = llm_client.missing_price_models()
    assert not missing, (
        f"가격표에 없는 모델: {missing}. "
        "backend/config/model_prices.json 에 입력/출력 단가($/1M tokens)를 등록하십시오."
    )


def test_configured_models_are_sorted_and_deduplicated() -> None:
    """결정론적 반환 — parser 와 primary 가 같은 모델이면 한 번만 나온다."""
    models = llm_client.configured_models()
    assert models == sorted(set(models))


def test_roles_cover_primary_fallback_parser() -> None:
    """역할이 늘거나 줄면 커버리지 범위가 조용히 달라진다."""
    assert llm_client.MODEL_ROLES == ("primary", "fallback", "parser")


# ── 계약 경계 ────────────────────────────────────────────────────────────


def _patch_config(monkeypatch: pytest.MonkeyPatch, cfg: dict[str, Any]) -> None:
    monkeypatch.setattr(llm_client, "load_config", lambda *a, **k: cfg)


def test_inactive_parser_with_unregistered_model_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**런타임 비활성 역할도 검사한다.**

    parser 는 현재 비활성이고(절대원칙 9) 마침 primary 와 같은 모델이라 지금은
    누락이 드러나지 않는다. 둘이 갈라진 뒤 parser 만 재활성화되는 순간을 위해,
    활성 여부가 아니라 **설정 여부**를 기준으로 삼는다.
    """
    _patch_config(monkeypatch, {
        "primary": {"model": "gemini-3-flash-preview"},
        "fallback": {"model": "gpt-5.6-luna"},
        "parser": {"model": "some-unregistered-parser-model"},
    })
    assert llm_client.missing_price_models() == ["some-unregistered-parser-model"]


def test_blank_and_absent_models_are_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 모델명·역할 부재는 누락이 아니다 — 지정된 적이 없으면 가격도 필요 없다."""
    _patch_config(monkeypatch, {
        "primary": {"model": "gemini-3-flash-preview"},
        "fallback": {"model": "   "},
        # parser 키 자체가 없음
        "note": "프로필이 아니다",
        "options": {"timeout": 30},
    })
    assert llm_client.configured_models() == ["gemini-3-flash-preview"]
    assert llm_client.missing_price_models() == []


def test_missing_models_are_sorted_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """같은 미등록 모델이 두 역할에 있어도 한 번만 보고한다."""
    _patch_config(monkeypatch, {
        "primary": {"model": "zzz-unregistered"},
        "fallback": {"model": "aaa-unregistered"},
        "parser": {"model": "zzz-unregistered"},
    })
    assert llm_client.missing_price_models() == [
        "aaa-unregistered", "zzz-unregistered",
    ]


def test_malformed_profile_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """설정이 망가져도 예외를 던지지 않는다 — 게이트가 임포트 시점에 터지면 안 된다."""
    _patch_config(monkeypatch, {
        "primary": "문자열이지 프로필이 아니다",
        "fallback": {"model": None},
        "parser": {},
    })
    assert llm_client.configured_models() == []
    assert llm_client.missing_price_models() == []


def test_unregistered_model_still_costs_zero_at_runtime() -> None:
    """운영 계약 불변 — 가격 누락이 런타임 호출을 막지 않는다.

    이 게이트는 배포 전에만 실패한다. `estimate_cost_usd()` 를 예외로 바꾸면
    가격표 누락이 서비스 장애가 된다.
    """
    assert estimate_cost_usd("no-such-model-anywhere", 1_000_000, 1_000_000) == 0.0
