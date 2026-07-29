"""공용 runner 의 계약 검사는 `python -O` 에서도 살아 있어야 한다.

`assert` 로 쓰면 최적화 모드에서 통째로 사라진다. 이 검사들은 디버깅 가정이 아니라
정확성을 지키는 런타임 계약이다.
"""

from __future__ import annotations

import datetime as _dt
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


# ── rolling window 날짜 범위 (지문 일치와 별개로 직접 검사) ────────────────
#
# fingerprint 직렬화가 우연히 같은 오류를 공유하는 경우까지 막는다.


def _window_lengths(days: int) -> tuple[list[int], list[int]]:
    """(선택 전 창 길이, commit 후 창 길이) — 한 일주 기준."""
    from saju_engines.daily_schedule_runner import _append_window

    keep = DAILY_HISTORY_CONTRACT_V1.lookback_days
    hist: dict[str, tuple[str, ...]] = {}
    before, after = [], []
    for d in range(days):
        before.append(len(hist.get("甲子", ())))
        hist, _ev = _append_window(hist, {"甲子": f"e{d}"}, keep)
        after.append(len(hist["甲子"]))
    return before, after


def test_window_ranges_at_the_boundaries() -> None:
    """D일 선택은 D-90~D-1 을 읽고, commit 후에는 D-89~D 다."""
    before, after = _window_lengths(181)
    keep = DAILY_HISTORY_CONTRACT_V1.lookback_days
    assert (before[0], after[0]) == (0, 1)          # 1일째
    assert (before[89], after[89]) == (89, 90)      # 90일째
    assert (before[90], after[90]) == (90, 90)      # 91일째 — 최초 eviction
    assert (before[180], after[180]) == (90, 90)    # 181일째
    assert max(after) == keep


def test_eviction_starts_exactly_at_day_91() -> None:
    """90일째까지는 밀려나는 값이 없어야 한다."""
    from saju_engines.daily_schedule_runner import _append_window

    keep = DAILY_HISTORY_CONTRACT_V1.lookback_days
    hist: dict[str, tuple[str, ...]] = {}
    first_evicted_day = None
    for d in range(120):
        hist, ev = _append_window(hist, {"甲子": f"e{d}"}, keep)
        if ev["甲子"] is not None and first_evicted_day is None:
            first_evicted_day = d + 1
            assert ev["甲子"] == "e0"
    assert first_evicted_day == keep + 1


def test_no_eviction_is_recorded_as_explicit_none() -> None:
    """필드 누락·빈 문자열로 표현하면 fingerprint 가 불안정해진다."""
    from saju_engines.daily_schedule_runner import _append_window

    _hist, ev = _append_window({}, {"甲子": "a"}, 90)
    assert ev == {"甲子": None}


# ── 공식 anchor 날짜 범위 (분모 계약) ─────────────────────────────────────
#
# `1000 - 180 = 820` 으로 연결하면 틀린다. warm-up 뒤에 **첫 anchor 의 측정 창
# 90일**이 한 번 더 들어간다. 산술이 아니라 날짜를 직접 고정한다.

OFFICIAL_FIRST_ANCHOR = _dt.date(2026, 1, 1)
OFFICIAL_LAST_ANCHOR = _dt.date(2027, 12, 31)
OFFICIAL_ANCHOR_COUNT = 730
GENERATED_DAYS = 1000


def test_official_anchor_range_is_pinned_by_date_not_arithmetic() -> None:
    origin = DAILY_ROLLING_AUDIT_CONTRACT_V1.origin
    warmup = DAILY_ROLLING_AUDIT_CONTRACT_V1.warmup_days
    window = DAILY_HISTORY_CONTRACT_V1.lookback_days

    assert (OFFICIAL_FIRST_ANCHOR - origin).days == warmup + window == 270
    assert (OFFICIAL_LAST_ANCHOR - OFFICIAL_FIRST_ANCHOR).days + 1 == (
        OFFICIAL_ANCHOR_COUNT
    )
    assert warmup + window + OFFICIAL_ANCHOR_COUNT == GENERATED_DAYS
    # 흔한 오해를 명시적으로 부정한다.
    assert GENERATED_DAYS - warmup != OFFICIAL_ANCHOR_COUNT


def test_2025_dates_are_outside_the_official_denominator() -> None:
    """2025년 날짜는 history 안정화에만 쓰이고 anchor 통계에는 안 들어간다."""
    assert DAILY_ROLLING_AUDIT_CONTRACT_V1.origin.year == 2025
    assert OFFICIAL_FIRST_ANCHOR.year == 2026
    assert DAILY_ROLLING_AUDIT_CONTRACT_V1.origin < OFFICIAL_FIRST_ANCHOR
