"""OA-6c1 — domain·event cap 통합 재배정 불변식 (**정책값 미확정 상태**).

여기서 검증하는 것은 상한을 9건으로 할지 10건으로 할지가 아니라 **알고리즘 계약**이다.
테스트 없이 D5·D6·D7을 측정하면 안마다 재배정 동작이 달라져 비교를 신뢰할 수 없다.
"""

from __future__ import annotations

import collections
import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_board_constraints import (
    HeadlineCandidate,
    cap_count,
    rebalance_headlines_with_constraints,
)


def C(event: str, domain: str, probability: int = 70) -> HeadlineCandidate:
    return HeadlineCandidate(event_key=event, domain=domain, probability=probability)


def run(raw, cands, *, domain_cap=99, event_cap=99, budget=None):
    return rebalance_headlines_with_constraints(
        raw, cands, domain_cap=domain_cap, event_cap=event_cap,
        max_displacement_cost=budget,
    )


# ── 상한 계산 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ratio", "expected"), [(0.30, 18), (0.20, 12), (0.18, 11), (0.15, 9), (1 / 6, 10)]
)
def test_cap_count_uses_ceil(ratio, expected) -> None:
    """비율이 아니라 **정수 상한**이 계약이다(60일주 기준)."""
    assert cap_count(60, ratio) == expected


# ── 왕복·재이동 금지 ───────────────────────────────────────────────────────


def test_unified_cap_does_not_ping_pong_between_domains() -> None:
    """한 축을 풀다가 다른 축을 넘겨 되돌아오는 왕복이 없어야 한다."""
    raw = {f"i{n}": C("money_a", "money") for n in range(6)}
    cands = {
        f"i{n}": [C("money_a", "money"), C("work_a", "work", 69)] for n in range(6)
    }

    result = run(raw, cands, domain_cap=3, event_cap=3)

    counts = collections.Counter(c.domain for c in result.selections.values())
    assert max(counts.values()) <= 3 or result.overrides
    assert len(result.moves) == len({m.ilju for m in result.moves})


def test_moved_card_is_never_moved_again() -> None:
    raw = {f"i{n}": C("a", "d1") for n in range(8)}
    cands = {
        f"i{n}": [C("a", "d1"), C("b", "d2", 69), C("c", "d3", 68)] for n in range(8)
    }

    result = run(raw, cands, domain_cap=3, event_cap=3)

    moved = [m.ilju for m in result.moves]
    assert len(moved) == len(set(moved))


# ── 목적지 여유 ────────────────────────────────────────────────────────────


def test_event_cap_replacement_cannot_overfill_destination_domain() -> None:
    """event 초과를 풀면서 목적지 domain 을 넘기면 안 된다."""
    raw = {"a1": C("e1", "d1"), "a2": C("e1", "d1"), "b1": C("e2", "d2"),
           "b2": C("e3", "d2")}
    cands = {
        "a1": [C("e1", "d1"), C("e9", "d2", 69)],
        "a2": [C("e1", "d1"), C("e8", "d2", 69)],
        "b1": [C("e2", "d2")], "b2": [C("e3", "d2")],
    }

    result = run(raw, cands, domain_cap=2, event_cap=1)

    domains = collections.Counter(c.domain for c in result.selections.values())
    assert domains["d2"] <= 2


def test_domain_cap_replacement_cannot_overfill_destination_event() -> None:
    """domain 초과를 풀면서 목적지 event 를 넘기면 안 된다."""
    raw = {f"i{n}": C(f"e{n}", "d1") for n in range(4)}
    cands = {f"i{n}": [C(f"e{n}", "d1"), C("shared", "d2", 69)] for n in range(4)}

    result = run(raw, cands, domain_cap=2, event_cap=1)

    events = collections.Counter(c.event_key for c in result.selections.values())
    assert max(events.values()) <= 1 or result.overrides


# ── 이동 선택 우선순위 ─────────────────────────────────────────────────────


def test_lower_cost_valid_move_is_selected_first() -> None:
    """같은 완화량이면 손실이 작은 이동이 먼저다."""
    raw = {"cheap": C("a", "d1", 70), "pricey": C("a", "d1", 70)}
    cands = {
        "cheap": [C("a", "d1", 70), C("x", "d2", 69)],    # 손실 1
        "pricey": [C("a", "d1", 70), C("y", "d3", 60)],   # 손실 10
    }

    result = run(raw, cands, domain_cap=99, event_cap=1)

    assert result.moves
    assert result.moves[0].ilju == "cheap"
    assert result.moves[0].displacement_cost == 1


def test_move_relieving_both_constraints_beats_single_constraint_move() -> None:
    """두 축을 동시에 푸는 이동이 한 축만 푸는 이동보다 먼저다.

    money_small_gain → money_good_deal 은 사건 독점만 풀고 도메인 총량은 그대로다.
    money_small_gain → teamwork_flow 는 둘 다 푼다.
    """
    raw = {f"m{n}": C("money_a", "money", 70) for n in range(3)}
    cands = {
        "m0": [C("money_a", "money", 70), C("money_b", "money", 69)],  # relief 1
        "m1": [C("money_a", "money", 70), C("work_a", "work", 69)],    # relief 2
        "m2": [C("money_a", "money", 70)],
    }

    result = run(raw, cands, domain_cap=2, event_cap=2)

    assert result.moves[0].ilju == "m1"
    assert result.moves[0].constraint_relief == 2


# ── 조건부 제약: 유효 대안이 없을 때만 초과 허용 ────────────────────────────


def test_combined_constraints_allow_overflow_only_when_infeasible() -> None:
    """대안이 없으면 초과를 허용하되 사유를 남긴다 — 억지 교체 금지."""
    raw = {f"i{n}": C("only", "d1") for n in range(5)}
    cands = {f"i{n}": [C("only", "d1")] for n in range(5)}   # 대안 없음

    result = run(raw, cands, domain_cap=2, event_cap=2)

    assert not result.moves
    assert result.event_overflow > 0
    assert "no_cross_event_alternative" in result.overrides


def test_unified_rebalance_is_independent_of_ilju_order() -> None:
    """일주 처리 순서가 결과를 바꾸지 않는다."""
    raw = {f"i{n}": C("a", "d1", 70 + n % 3) for n in range(9)}
    cands = {
        f"i{n}": [C("a", "d1", 70 + n % 3), C(f"b{n % 4}", "d2", 68)] for n in range(9)
    }

    forward = run(raw, cands, domain_cap=5, event_cap=3)
    reverse = run(
        dict(reversed(list(raw.items()))), cands, domain_cap=5, event_cap=3
    )

    assert {k: v.event_key for k, v in forward.selections.items()} == {
        k: v.event_key for k, v in reverse.selections.items()
    }


# ── 손실 예산 ──────────────────────────────────────────────────────────────


def test_move_above_displacement_budget_is_rejected() -> None:
    raw = {f"i{n}": C("a", "d1", 80) for n in range(4)}
    cands = {f"i{n}": [C("a", "d1", 80), C("far", "d2", 60)] for n in range(4)}

    result = run(raw, cands, domain_cap=99, event_cap=2, budget=6)

    assert not result.moves, "예산(6p)을 넘는 20p 교체가 실행됐다"


def test_cost_budget_overflow_is_audited_not_forced() -> None:
    """예산 때문에 못 옮겼으면 초과를 허용하고 사유를 남긴다."""
    raw = {f"i{n}": C("a", "d1", 80) for n in range(4)}
    cands = {f"i{n}": [C("a", "d1", 80), C("far", "d2", 60)] for n in range(4)}

    result = run(raw, cands, domain_cap=99, event_cap=2, budget=6)

    assert result.event_overflow == 2
    assert result.overrides.get("cost_budget_exceeded")


def test_lower_probability_candidate_within_budget_can_replace() -> None:
    raw = {f"i{n}": C("a", "d1", 80) for n in range(4)}
    cands = {f"i{n}": [C("a", "d1", 80), C(f"n{n}", "d2", 75)] for n in range(4)}

    result = run(raw, cands, domain_cap=99, event_cap=2, budget=6)

    assert len(result.moves) == 2
    assert all(m.displacement_cost == 5 for m in result.moves)


def test_candidate_outside_budget_cannot_replace_even_to_meet_cap() -> None:
    """상한을 맞추기 위해서라도 예산 밖 후보를 쓰지 않는다."""
    raw = {f"i{n}": C("a", "d1", 80) for n in range(3)}
    cands = {
        f"i{n}": [C("a", "d1", 80), C(f"cheap{n}", "d2", 79), C(f"far{n}", "d3", 50)]
        for n in range(3)
    }

    result = run(raw, cands, domain_cap=99, event_cap=1, budget=2)

    assert all(m.displacement_cost <= 2 for m in result.moves)
    for chosen in result.selections.values():
        assert not chosen.event_key.startswith("far")


# ── 라이브 불변 ────────────────────────────────────────────────────────────


def test_shadow_path_does_not_change_live_v1_output() -> None:
    """shadow 재배정을 돌려도 라이브 보드가 그대로다."""
    from saju_engines.daily_selection_shadow import board_candidates_v2

    dicts = M.load_daily_dicts()
    ctx = M.build_day_context(dt.date(2026, 7, 28))
    before = [str(f.headline_event_key) for f in M.compute_board(ctx, dicts).fortunes]

    raw, cmap = board_candidates_v2(ctx, dicts)
    rebalance_headlines_with_constraints(
        raw, cmap, domain_cap=18, event_cap=10, max_displacement_cost=6
    )

    after = [str(f.headline_event_key) for f in M.compute_board(ctx, dicts).fortunes]
    assert before == after
    assert M.BOARD_REBALANCE_VERSION == "board-rebalance.v1-domain-only"
