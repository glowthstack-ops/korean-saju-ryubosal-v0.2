"""계열 인지 감쇠(2차-2단계) — 같은 현상 중복 가산 제거.

재성 활성(재성국·충개고·식상생재)은 한 '재성 작동' 계열이라 대표만 full, 추가는 감쇠한다.
식상생재처럼 base 십성 조합에 이미 잡힌 발동은 교차 중복으로 추가 가산을 최소화한다.
"""

from __future__ import annotations

from saju_engines.wealth_activation_modifier import _ACT_WEIGHT, _family_boost


def test_single_activation_full() -> None:
    """발동 1개면 감쇠 없이 가중 × mult."""
    assert _family_boost(["재성국 완성"], [], 1.0) == _ACT_WEIGHT["재성국 완성"]


def test_same_family_extra_diminished() -> None:
    """같은 계열 2개 — 대표(full) + 추가(0.45배)로, 단순 합보다 작다."""
    full_sum = _ACT_WEIGHT["재성국 완성"] + _ACT_WEIGHT["묘고 충개고"]
    got = _family_boost(["재성국 완성", "묘고 충개고"], [], 1.0)
    # 대표 0.18 + 추가 0.12×0.45 = 0.234 < 0.30(단순 합)
    assert got < full_sum
    assert abs(got - (0.18 + 0.12 * 0.45)) < 1e-6


def test_cross_phase_duplicate_minimized() -> None:
    """식상생재가 base 조합(COMBO_OUTPUT_WEALTH)에 이미 잡혔으면 추가 가산 최소화(×0.35)."""
    plain = _family_boost(["식상생재"], [], 1.0)
    deduped = _family_boost(["식상생재"], ["COMBO_OUTPUT_WEALTH"], 1.0)
    assert deduped < plain
    assert abs(deduped - _ACT_WEIGHT["식상생재"] * 0.35) < 1e-6


def test_capacity_mult_applies() -> None:
    """그릇 배율은 감쇠 후 곱한다(weak 0.5)."""
    assert _family_boost(["재성국 완성"], [], 0.5) == _ACT_WEIGHT["재성국 완성"] * 0.5


def test_order_independent_representative() -> None:
    """입력 순서와 무관하게 가중 큰 발동이 대표(full)로 잡힌다."""
    a = _family_boost(["식상생재", "재성국 완성"], [], 1.0)
    b = _family_boost(["재성국 완성", "식상생재"], [], 1.0)
    assert a == b
    # 대표는 재성국(0.18) full, 식상생재(0.10) 0.45배.
    assert abs(a - (0.18 + 0.10 * 0.45)) < 1e-6
