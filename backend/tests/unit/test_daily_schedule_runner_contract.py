"""공용 runner 의 계약 검사는 `python -O` 에서도 살아 있어야 한다.

`assert` 로 쓰면 최적화 모드에서 통째로 사라진다. 이 검사들은 디버깅 가정이 아니라
정확성을 지키는 런타임 계약이다.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from saju_engines.daily_schedule_runner import (
    DAILY_BOARD_CONTRACT_V1,
    DAILY_HISTORY_CONTRACT_V1,
    DAILY_ROLLING_AUDIT_CONTRACT_V1,
    DailyHistoryContract,
    DailyScheduleContractError,
    DailyScheduleState,
    RepeatHistorySource,
    empty_state,
    validate_history_contract,
)


def test_official_contract_passes() -> None:
    validate_history_contract(DAILY_HISTORY_CONTRACT_V1)
    assert DAILY_BOARD_CONTRACT_V1.domain_cap_count == 21
    assert DAILY_BOARD_CONTRACT_V1.event_cap_count == 10
    assert DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.isoformat() == "2025-04-06"


def test_lookback_shorter_than_cooldown_is_rejected() -> None:
    with pytest.raises(DailyScheduleContractError, match="쿨다운"):
        validate_history_contract(
            DailyHistoryContract("x", 3, RepeatHistorySource.INTENDED_GOOD)
        )


def test_lookback_diverging_from_coverage_window_is_rejected() -> None:
    """coverage 창이 120일로 바뀌는데 이력이 90일로 남는 표류를 막는다."""
    with pytest.raises(DailyScheduleContractError, match="coverage"):
        validate_history_contract(
            DailyHistoryContract("x", 120, RepeatHistorySource.INTENDED_GOOD)
        )


def test_contract_checks_survive_optimized_mode() -> None:
    """`python -O` 에서도 동일하게 실패해야 한다."""
    code = (
        "from saju_engines.daily_schedule_runner import ("
        " DailyHistoryContract, RepeatHistorySource, validate_history_contract,"
        " DailyScheduleContractError)\n"
        "try:\n"
        "    validate_history_contract(DailyHistoryContract("
        "'x', 3, RepeatHistorySource.INTENDED_GOOD))\n"
        "except DailyScheduleContractError:\n"
        "    print('BLOCKED')\n"
    )
    out = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "BLOCKED"


def test_history_source_is_read_through_one_accessor() -> None:
    """정책이 필드를 직접 읽으면 H0/H1/H2 감사에서 분기가 흩어진다."""
    state = DailyScheduleState(
        {"甲子": ("a",)}, {"甲子": ("b",)}, {"甲子": ("c",)}, {"甲子": ("d",)}
    )
    assert state.repeat_history_for(
        "甲子", source=RepeatHistorySource.INTENDED_GOOD
    ) == ("a",)
    assert state.repeat_history_for(
        "甲子", source=RepeatHistorySource.REALIZED_GOOD
    ) == ("b",)
    assert state.repeat_history_for(
        "甲子", source=RepeatHistorySource.FINAL_HEADLINE_FAMILY
    ) == ("c",)


def test_empty_state_is_fresh_each_call() -> None:
    """mutable 초기 state 를 공유하면 재실행 간 상태가 섞인다."""
    a, b = empty_state(), empty_state()
    assert a is not b
    assert a.intended_good_history is not b.intended_good_history
    assert a.fingerprint() == b.fingerprint()
