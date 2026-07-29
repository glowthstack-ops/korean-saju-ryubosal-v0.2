"""board cap 인자는 **비율이 아니라 개수**다.

비율(0.30)을 그대로 넘겨도 파이썬은 받아들이고 cap=0 으로 해석돼 조용히 전혀 다른
제약이 된다. OA-11d shadow harness 가 실제로 그렇게 어긋났다 — 같은 의미 오류가
후속 oracle 에서 반복되지 않도록 호출 시점에 막는다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines.daily_board_constraints import cap_count
from saju_engines.daily_selection_contracts import (
    DAILY_ROLLING_AUDIT_CONTRACT_VERSION,
    DAILY_ROLLING_AUDIT_ORIGIN,
    DAILY_ROLLING_AUDIT_WARMUP_DAYS,
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


def test_rolling_audit_origin_is_a_declared_contract() -> None:
    """원점은 테스트 편의값이 아니라 순차 상태를 결정하는 계약이다."""
    assert DAILY_ROLLING_AUDIT_ORIGIN.isoformat() == "2025-04-06"
    assert DAILY_ROLLING_AUDIT_CONTRACT_VERSION == "daily-rolling-audit.v1"
    assert DAILY_ROLLING_AUDIT_WARMUP_DAYS == 180


def test_rolling_audit_contract_is_separate_from_beta_bootstrap() -> None:
    """감사 원점과 베타 풀 bootstrap 은 **다른 계약**이다.

    이름을 겸용하면 누군가 v2 풀을 2025-04-06 부터 재생성해야 한다고 오해한다.
    """
    from saju_engines.daily_beta_pool import pool_metadata

    meta = pool_metadata("beta-daily-pool.c10.v2")
    # 베타 bootstrap 은 anchor 기준이고 감사 원점과 무관하다.
    assert meta["bootstrap_start"] == "2026-01-31"
    assert meta["bootstrap_warmup_days"] == 90
    assert meta["history_lookback_days"] == 90
    assert dt.date.fromisoformat(meta["bootstrap_start"]) != DAILY_ROLLING_AUDIT_ORIGIN
    assert meta["bootstrap_contract_version"] == "daily-selection-bootstrap.v1"
    assert meta["bootstrap_contract_version"] != DAILY_ROLLING_AUDIT_CONTRACT_VERSION


def test_v2_pool_fingerprints_do_not_depend_on_the_audit_contract() -> None:
    """감사 계약을 바꿔도 이미 동결한 v2 지문은 움직이지 않아야 한다."""
    from saju_engines.daily_beta_pool import pool_metadata

    meta = pool_metadata("beta-daily-pool.c10.v2")
    assert meta["pool_result_fingerprint"] == (
        "f0ce1e0c20c80d892d6a28ac1a286bc2c2cf61fcac0d2209424b6c35f3414f68"
    )
    assert meta["bootstrap_fingerprint"] == (
        "a499f3424dea1ead18c1f6cbe40f05012e53d9b8d314c025dd6b0951408e53e7"
    )


# ── 정수 스칼라 계약 (SciPy·NumPy oracle 경로) ────────────────────────────


def test_numpy_integer_is_accepted_and_normalized() -> None:
    """MILP·oracle 경로에서 numpy 정수 스칼라가 들어올 수 있다."""
    np = pytest.importorskip("numpy")
    assert _call(domain_cap=np.int64(2), event_cap=np.int64(2)).selections


def test_numpy_float_is_rejected() -> None:
    """`np.float64(21.0)` 은 정수처럼 보여도 비율 오입력 경로다."""
    np = pytest.importorskip("numpy")
    with pytest.raises(TypeError):
        _call(domain_cap=np.float64(21.0))


def test_python_float_with_integral_value_is_rejected() -> None:
    with pytest.raises(TypeError):
        _call(domain_cap=2.0)
