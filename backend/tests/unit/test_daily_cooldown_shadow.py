"""OA-6f — 종단 cooldown 재배정의 불변식.

cooldown 은 숫자만 개선하고 콘텐츠를 망가뜨릴 수 있다. 그래서 회귀가 지키는 것은
"반복이 줄었는가"가 아니라 **무엇을 하지 않는가**다.

  · 점수·band·원래 순위를 바꾸지 않는다
  · 카드에 표시되지 않는 사건을 제목으로 만들지 않는다
  · 반복을 반복으로 바꾸지 않는다
  · 예산 밖 손실을 감수하지 않는다 — 미해소로 남긴다
  · 카드당 1회만 이동한다(ping-pong 금지)
  · 같은 입력이면 같은 결과다
"""

from __future__ import annotations

import pytest

from saju_engines.daily_board_constraints import HeadlineCandidate
from saju_engines.daily_cooldown_shadow import (
    ALL_CANDIDATES_COOLDOWN_BLOCKED,
    CONSECUTIVE_EVENT_REPEAT,
    COOLDOWN_ALTERNATIVE_SELECTED,
    LOSS_BUDGET_EXCEEDED,
    NO_ELIGIBLE_HEADLINE_EVENT,
    ROLLING_7D_THIRD_OCCURRENCE,
    cooldown_violation,
    rebalance_with_cooldown,
)

_BIG = 60


def _c(key: str, domain: str, p: int) -> HeadlineCandidate:
    return HeadlineCandidate(event_key=key, domain=domain, probability=p)


# ── 위반 판정 ──────────────────────────────────────────────────────────────


def test_consecutive_repeat_is_detected() -> None:
    assert cooldown_violation(["a", "b", "money"], "money") == (CONSECUTIVE_EVENT_REPEAT,)


def test_third_occurrence_in_seven_days_is_detected() -> None:
    """오늘 것을 더해 3회가 되면 위반 — 2회까지는 허용한다."""
    assert cooldown_violation(["money", "x", "money", "y"], "money") == (
        ROLLING_7D_THIRD_OCCURRENCE,
    )
    assert cooldown_violation(["money", "x", "y", "z"], "money") == ()


def test_window_is_seven_days_inclusive_of_today() -> None:
    """7일 창은 오늘 포함 — 6일 전까지만 본다."""
    # 6일 전·5일 전에 두 번 → 오늘이 3번째라 위반
    assert ROLLING_7D_THIRD_OCCURRENCE in cooldown_violation(
        ["money", "money", "a", "b", "c", "d"], "money"
    )
    # 7일 전이 창 밖으로 나가면 위반이 아니다
    assert cooldown_violation(
        ["money", "a", "b", "c", "d", "e", "f"], "money"
    ) == ()


def test_empty_history_never_violates() -> None:
    assert cooldown_violation([], "money") == ()


# ── 대체 계약 ──────────────────────────────────────────────────────────────


def test_alternative_is_selected_within_budget() -> None:
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80), _c("rest", "health", 76)]}
    r = rebalance_with_cooldown(
        raw, cands, {"甲子": ["money"]}, domain_cap=_BIG, max_displacement_cost=5
    )
    assert r.selections["甲子"].event_key == "rest"
    assert r.codes["甲子"] == COOLDOWN_ALTERNATIVE_SELECTED
    assert r.cooldown_unresolved == 0


def test_loss_budget_keeps_the_original_event() -> None:
    """예산 밖이면 바꾸지 않는다 — 15p 낮은 사건을 억지로 올리지 않는다."""
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80), _c("rest", "health", 65)]}
    r = rebalance_with_cooldown(
        raw, cands, {"甲子": ["money"]}, domain_cap=_BIG, max_displacement_cost=7
    )
    assert r.selections["甲子"].event_key == "money"
    assert r.codes["甲子"] == LOSS_BUDGET_EXCEEDED
    assert r.cooldown_unresolved == 1


def test_no_candidate_is_reported_not_invented() -> None:
    """후보가 없으면 미해소로 남긴다 — 표시되지 않는 사건을 만들지 않는다."""
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80)]}
    r = rebalance_with_cooldown(raw, cands, {"甲子": ["money"]}, domain_cap=_BIG)
    assert r.selections["甲子"].event_key == "money"
    assert r.codes["甲子"] == NO_ELIGIBLE_HEADLINE_EVENT


def test_replacement_must_itself_be_clean() -> None:
    """반복을 반복으로 바꾸지 않는다 — 대체 후보도 창 규칙을 지켜야 한다."""
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80), _c("rest", "health", 79)]}
    # rest 가 이미 창 안에서 2회 → 오늘 고르면 3회째라 대체 후보가 아니다.
    r = rebalance_with_cooldown(
        raw, cands, {"甲子": ["rest", "rest", "money"]}, domain_cap=_BIG
    )
    assert r.selections["甲子"].event_key == "money"
    assert r.codes["甲子"] == ALL_CANDIDATES_COOLDOWN_BLOCKED


def test_two_occurrences_in_the_window_are_allowed() -> None:
    """규칙은 3회째부터 막는다 — 2회까지는 정상 대체 후보다."""
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80), _c("rest", "health", 79)]}
    r = rebalance_with_cooldown(
        raw, cands, {"甲子": ["rest", "x", "money"]}, domain_cap=_BIG
    )
    assert r.selections["甲子"].event_key == "rest"


def test_candidates_outside_the_card_are_never_used() -> None:
    """후보 맵 밖의 사건은 어떤 경우에도 선택되지 않는다."""
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80), _c("rest", "health", 78)]}
    r = rebalance_with_cooldown(raw, cands, {"甲子": ["money"]}, domain_cap=_BIG)
    assert r.selections["甲子"].event_key in {"money", "rest"}


# ── 세 축 동시 처리 ────────────────────────────────────────────────────────


def test_domain_cap_is_not_broken_by_a_cooldown_move() -> None:
    """cooldown 교체가 도메인 캡을 깨면 새 위반이 생긴다 — 그러면 이동하지 않는다."""
    raw = {
        "A": _c("money", "money", 80),
        "B": _c("talk", "social", 70),
        "C": _c("meet", "social", 70),
    }
    cands = {
        "A": [_c("money", "money", 80), _c("chat", "social", 79)],
        "B": [_c("talk", "social", 70)],
        "C": [_c("meet", "social", 70)],
    }
    r = rebalance_with_cooldown(
        raw, cands, {"A": ["money"]}, domain_cap=2, max_displacement_cost=5
    )
    assert r.selections["A"].event_key == "money", "social 이 이미 캡(2)이라 이동 불가"
    assert r.domain_overflow == 0


def test_move_relieving_two_axes_is_preferred() -> None:
    """도메인 초과와 반복을 동시에 푸는 이동이 먼저 선택된다."""
    raw = {
        "A": _c("money", "money", 80),
        "B": _c("money2", "money", 80),
        "C": _c("money3", "money", 80),
    }
    cands = {
        "A": [_c("money", "money", 80), _c("rest", "health", 79)],
        "B": [_c("money2", "money", 80), _c("walk", "leisure", 79)],
        "C": [_c("money3", "money", 80)],
    }
    r = rebalance_with_cooldown(
        raw, cands, {"A": ["money"]}, domain_cap=2, max_displacement_cost=5
    )
    # A 는 반복+도메인 두 축을 풀고 B 는 도메인 한 축만 푼다 → A 가 먼저 이동한다.
    assert r.selections["A"].event_key == "rest"


def test_each_card_moves_at_most_once() -> None:
    """ping-pong 금지 — 한 번 옮긴 카드는 다시 옮기지 않는다."""
    raw = {f"I{i}": _c("money", "money", 80) for i in range(6)}
    cands = {
        f"I{i}": [_c("money", "money", 80), _c("rest", "health", 79),
                  _c("walk", "leisure", 78)]
        for i in range(6)
    }
    hist = {f"I{i}": ["money"] for i in range(6)}
    r = rebalance_with_cooldown(
        raw, cands, hist, domain_cap=3, event_cap=3, max_displacement_cost=5
    )
    assert len(r.moves) == len(r.moved_iljus)


def test_result_is_deterministic() -> None:
    raw = {f"I{i}": _c("money", "money", 80) for i in range(8)}
    cands = {
        f"I{i}": [_c("money", "money", 80), _c("rest", "health", 79),
                  _c("walk", "leisure", 78)]
        for i in range(8)
    }
    hist = {f"I{i}": ["money"] for i in range(8)}
    kwargs = dict(domain_cap=4, event_cap=4, max_displacement_cost=5)
    a = rebalance_with_cooldown(raw, cands, hist, **kwargs)
    b = rebalance_with_cooldown(raw, cands, hist, **kwargs)
    assert {k: v.event_key for k, v in a.selections.items()} == {
        k: v.event_key for k, v in b.selections.items()
    }


def test_no_violation_means_no_move() -> None:
    """반복도 초과도 없으면 라이브 결과를 건드리지 않는다."""
    raw = {"A": _c("money", "money", 80), "B": _c("rest", "health", 70)}
    cands = {
        "A": [_c("money", "money", 80), _c("walk", "leisure", 78)],
        "B": [_c("rest", "health", 70)],
    }
    r = rebalance_with_cooldown(raw, cands, {}, domain_cap=_BIG, max_displacement_cost=7)
    assert not r.moves
    assert r.selections["A"].event_key == "money"


@pytest.mark.parametrize("budget", [5, 6, 7])
def test_displacement_never_exceeds_budget(budget: int) -> None:
    raw = {f"I{i}": _c("money", "money", 80) for i in range(10)}
    cands = {
        f"I{i}": [_c("money", "money", 80), _c("a", "health", 80 - i)]
        for i in range(10)
    }
    hist = {f"I{i}": ["money"] for i in range(10)}
    r = rebalance_with_cooldown(
        raw, cands, hist, domain_cap=_BIG, max_displacement_cost=budget
    )
    assert all(m.displacement_cost <= budget for m in r.moves)


# ── 분모 분할 (OA-6f 정정) ─────────────────────────────────────────────────


def test_card_partition_is_mutually_exclusive() -> None:
    """cooldown 트리거 = 대체 성공 + 미해소(전 사유). 캡 이동은 섞이지 않는다.

    이 동치가 깨지면 "미해소 8.9%"와 "미해소 21.4%"가 동시에 나온다(실제로 겪었다).
    """
    raw = {f"I{i}": _c("money", "money", 80) for i in range(10)}
    cands = {}
    for i in range(10):
        alts = [_c("money", "money", 80)]
        if i % 2 == 0:
            alts.append(_c(f"alt{i}", "health", 79 - i))
        cands[f"I{i}"] = alts
    hist = {f"I{i}": ["money"] for i in range(0, 8)}  # 8장만 반복 위반

    r = rebalance_with_cooldown(
        raw, cands, hist, domain_cap=6, event_cap=6, max_displacement_cost=5
    )
    assert r.cooldown_triggered == 8
    assert r.cooldown_moved + r.cooldown_unresolved == r.cooldown_triggered
    assert (
        r.unresolved_by_absence + r.unresolved_by_constraint + r.unresolved_by_budget
        == r.cooldown_unresolved
    )


def test_cap_only_moves_are_not_counted_as_cooldown() -> None:
    """캡 때문에 옮긴 카드는 cooldown 분모 밖이다."""
    raw = {f"I{i}": _c("money", "money", 80) for i in range(6)}
    cands = {
        f"I{i}": [_c("money", "money", 80), _c(f"alt{i}", "health", 78)]
        for i in range(6)
    }
    r = rebalance_with_cooldown(
        raw, cands, {}, domain_cap=3, event_cap=3, max_displacement_cost=5
    )
    assert r.cooldown_triggered == 0
    assert r.cooldown_unresolved == 0
    assert r.cap_only_moves == len(r.moves)


def test_loss_budget_card_reports_required_uplift() -> None:
    """예산만 모자란 카드는 '몇 점이 더 있으면 되는가'를 남긴다 — G2 의 표적."""
    raw = {"甲子": _c("money", "money", 80)}
    cands = {"甲子": [_c("money", "money", 80), _c("rest", "health", 70)]}
    r = rebalance_with_cooldown(
        raw, cands, {"甲子": ["money"]}, domain_cap=_BIG, max_displacement_cost=7
    )
    (card,) = r.unresolved_cards
    assert card.reason == LOSS_BUDGET_EXCEEDED
    assert card.best_alternative_event_key == "rest"
    assert card.probability_gap == 10
    assert card.required_uplift_to_fit == 3


def test_absence_and_constraint_reasons_are_separated() -> None:
    """'사건이 없다'와 '제약으로 막혔다'를 같은 코드로 묶지 않는다."""
    absent = rebalance_with_cooldown(
        {"A": _c("money", "money", 80)}, {"A": [_c("money", "money", 80)]},
        {"A": ["money"]}, domain_cap=_BIG,
    )
    assert absent.unresolved_by_absence == 1
    assert absent.unresolved_by_constraint == 0

    blockedr = rebalance_with_cooldown(
        {"A": _c("money", "money", 80)},
        {"A": [_c("money", "money", 80), _c("rest", "health", 79)]},
        {"A": ["rest", "rest", "money"]}, domain_cap=_BIG,
    )
    assert blockedr.unresolved_by_constraint == 1
    assert blockedr.unresolved_by_absence == 0
