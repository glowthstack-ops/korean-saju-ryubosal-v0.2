"""board cap 인자는 **비율이 아니라 개수**다.

비율(0.30)을 그대로 넘겨도 파이썬은 받아들이고 cap=0 으로 해석돼 조용히 전혀 다른
제약이 된다. OA-11d shadow harness 가 실제로 그렇게 어긋났다 — 같은 의미 오류가
후속 oracle 에서 반복되지 않도록 호출 시점에 막는다.
"""

from __future__ import annotations

import pytest

from saju_engines.daily_board_constraints import cap_count
from saju_engines.daily_selection_contracts import (
    DAILY_CANONICAL_SCHEDULE_ORIGIN,
    DAILY_SCHEDULE_CONTRACT_VERSION,
    DAILY_SCHEDULE_WARMUP_DAYS,
)
from saju_engines.daily_selection_policy_shadow import (
    HeadlineCandidate,
    select_board,
)


def _board(n: int = 4) -> dict[str, HeadlineCandidate]:
    return {
        f"i{k}": HeadlineCandidate(f"e{k}", "money" if k % 2 else "work", 70 - k)
        for k in range(n)
    }


def _call(**over):
    raw = _board()
    cmap = {k: [v] for k, v in raw.items()}
    kwargs = {"domain_cap": 2, "event_cap": 2}
    kwargs.update(over)
    return select_board(raw, cmap, {}, **kwargs)


def test_valid_counts_are_accepted() -> None:
    assert _call().selections


@pytest.mark.parametrize("ratio", [0.30, 0.25, 0.35])
def test_ratio_for_domain_cap_fails_immediately(ratio: float) -> None:
    """`domain_cap=0.30` 은 조용히 통과하면 안 된다."""
    with pytest.raises(TypeError) as e:
        _call(domain_cap=ratio)
    assert "cap_count" in str(e.value)


def test_ratio_for_event_cap_fails_immediately() -> None:
    with pytest.raises(TypeError):
        _call(event_cap=0.25)


def test_bool_is_rejected() -> None:
    """`True` 는 int 의 부분형이라 1 로 통과해버린다."""
    with pytest.raises(TypeError):
        _call(domain_cap=True)


def test_non_positive_is_rejected() -> None:
    with pytest.raises(ValueError):
        _call(domain_cap=0)


def test_cap_above_the_ceiling_is_rejected() -> None:
    with pytest.raises(ValueError):
        _call(domain_cap=99)


def test_full_board_cap_is_allowed() -> None:
    """`domain_cap=60` 은 "사실상 무제한" 관용구다 — 작은 보드에서도 유효하다."""
    assert _call(domain_cap=60, event_cap=60).selections


def test_event_cap_none_is_allowed() -> None:
    """event cap 미적용은 유효한 계약이다(완화 경로)."""
    assert _call(event_cap=None).selections


def test_cap_count_converts_ratio_at_one_place() -> None:
    """비율→개수 환산은 이 함수 한 곳에서만 한다."""
    assert cap_count(60, 0.35) == 21
    assert cap_count(60, 0.30) == 18


def test_schedule_origin_is_a_declared_contract() -> None:
    """원점은 테스트 편의값이 아니라 순차 상태를 결정하는 계약이다."""
    assert DAILY_CANONICAL_SCHEDULE_ORIGIN.isoformat() == "2025-04-06"
    assert DAILY_SCHEDULE_CONTRACT_VERSION == "daily-schedule.v1"
    assert DAILY_SCHEDULE_WARMUP_DAYS == 180
