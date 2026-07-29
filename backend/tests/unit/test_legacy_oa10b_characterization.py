"""동결본이 원본 OA-10b 와 같은 schedule 을 만든다는 것을 고정한다.

공용 runner 를 추출하는 동안 이 파일이 "현재 C10 이 실제로 무엇을 만드는가"의
기준선이다. 기준선 자체가 움직이면 parity 비교가 무의미해지므로, 두 가지를 건다.

  · 동결본 == 원본 `audit_rolling_window.build_schedule`
  · 계측 on/off 가 선택 거동을 바꾸지 않음
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import legacy_oa10b_runner as L  # noqa: E402

#: 300일이면 warm-up(180) + 창(90) + anchor 30 을 모두 지난다.
_DAYS = 300


@pytest.fixture(scope="module")
def family_of() -> dict[str, str]:
    return L.load_family_map()


def test_frozen_runner_matches_the_original(family_of, monkeypatch) -> None:
    """동결본은 원본을 그대로 옮긴 것이다 — 결과가 갈리면 기준선이 아니다."""
    monkeypatch.setattr(sys, "argv", ["x", "30"])
    import audit_rolling_window as original

    assert original.build_schedule(family_of) == (
        L.build_schedule_observed(family_of, days=_DAYS).headline_history
    )


def test_observation_hooks_do_not_perturb_selection(family_of) -> None:
    """계측이 결과를 움직이면 관측값을 기준선으로 쓸 수 없다."""
    assert L.verify_observation_is_non_perturbing(family_of, days=60)


def test_frozen_contract_values_are_pinned(family_of) -> None:
    """동결본이 계약값을 조립하지 않는다 — 상수 표류를 막는다."""
    assert L.schedule_start().isoformat() == "2025-04-06"
    assert (L.WARMUP_DAYS, L.WINDOW) == (180, 90)
    assert (L._DOMAIN_CAP, L._EVENT_CAP, L._BUDGET) == (21, 10, 7)


def test_rerun_is_deterministic(family_of) -> None:
    """같은 입력 두 번 실행 → 전체 행 동일(상태 누수 없음)."""
    a = L.build_schedule_observed(family_of, days=60)
    b = L.build_schedule_observed(family_of, days=60)
    assert a.rows == b.rows
    assert a.daily_state == b.daily_state
