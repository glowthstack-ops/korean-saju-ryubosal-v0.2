"""LLM 사용량 비용 계산(compute_cost_usd) 단위 테스트 — 관리자 콘솔 Phase A."""

from __future__ import annotations

from saju_engines.usage_store import compute_cost_usd


def test_cost_splits_cached_input() -> None:
    """캐시된 입력은 cached 단가로 분리 과금(나머지 입력은 full 단가)."""
    # 입력 8000(캐시 5000) → full 3000@0.3 + cached 5000@0.075 + 출력 700@2.5 (/1M)
    cost = compute_cost_usd(8000, 700, 5000, 0.3, 2.5, 0.075)
    assert cost == round((3000 * 0.3 + 5000 * 0.075 + 700 * 2.5) / 1e6, 6)


def test_cost_zero_when_no_pricing() -> None:
    assert compute_cost_usd(10000, 5000, 0, 0, 0, 0) == 0.0


def test_cost_no_cache() -> None:
    cost = compute_cost_usd(1000, 500, 0, 0.3, 2.5, 0.075)
    assert cost == round((1000 * 0.3 + 500 * 2.5) / 1e6, 6)
