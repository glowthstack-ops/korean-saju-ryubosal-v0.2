"""OA-6f2 — 선택 정책(P1~P4)의 불변식.

정책은 후보를 **고르는 순서와 범위**만 바꾼다. 점수·명리 판정·표시 가능한 사건 집합은
그대로다. 회귀가 지키는 것은 그 경계다.
"""

from __future__ import annotations

import datetime as dt

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_board_constraints import HeadlineCandidate
from saju_engines.daily_selection_policy_shadow import (
    SEVERITY_CLEAN,
    SEVERITY_CONSECUTIVE,
    SEVERITY_FOURTH_OR_MORE,
    SEVERITY_THIRD_IN_WINDOW,
    PolicyResult,
    SelectionPolicy,
    repeat_severity,
    select_board,
)

_BIG = 60
_SWAP = SelectionPolicy(global_swap=True)
_TIERS = SelectionPolicy(global_swap=True, severity_tiers=True)


def _c(key: str, domain: str, p: int) -> HeadlineCandidate:
    return HeadlineCandidate(event_key=key, domain=domain, probability=p)


# ── 반복 강도 (P2) ─────────────────────────────────────────────────────────


def test_severity_orders_consecutive_worst() -> None:
    assert repeat_severity(["x", "m"], "m") == SEVERITY_CONSECUTIVE
    assert repeat_severity(["m", "x", "m", "y"], "m") == SEVERITY_THIRD_IN_WINDOW
    assert repeat_severity(["m", "m", "m", "y"], "m") == SEVERITY_FOURTH_OR_MORE
    assert repeat_severity(["a", "b"], "m") == SEVERITY_CLEAN


def test_tiers_never_create_a_consecutive_repeat() -> None:
    """강도 계층을 허용해도 '어제와 같은 사건'은 새로 만들지 않는다."""
    raw = {"A": _c("m", "money", 80)}
    cands = {"A": [_c("m", "money", 80), _c("y", "health", 79)]}
    # y 가 어제 나왔다 → 연속이 되므로 P2 라도 고르면 안 된다.
    r = select_board(
        raw, cands, {"A": ["m", "m", "y"]}, domain_cap=_BIG,
        max_displacement_cost=7, policy=_TIERS,
    )
    assert r.selections["A"].event_key == "m"


def test_tiers_allow_moving_to_a_weaker_repeat() -> None:
    """연속 반복(3) → 7일 세 번째(1)로 내려가는 이동은 허용된다."""
    raw = {"A": _c("m", "money", 80)}
    cands = {"A": [_c("m", "money", 80), _c("y", "health", 79)]}
    hist = {"A": ["y", "a", "y", "b", "m"]}  # m 은 연속, y 는 창 안 2회(→ 세 번째)
    strict = select_board(
        raw, cands, hist, domain_cap=_BIG, max_displacement_cost=7, policy=_SWAP
    )
    lenient = select_board(
        raw, cands, hist, domain_cap=_BIG, max_displacement_cost=7, policy=_TIERS
    )
    assert strict.selections["A"].event_key == "m"
    assert lenient.selections["A"].event_key == "y"


# ── 전역 swap (P1) ─────────────────────────────────────────────────────────


def test_global_swap_resolves_a_blocked_card() -> None:
    """A 가 X 를 선점해 B 가 막히던 상황을 A→Y, B→X 로 함께 푼다."""
    raw = {"A": _c("m", "money", 80), "B": _c("m2", "money", 80)}
    cands = {
        "A": [_c("m", "money", 80), _c("x", "health", 79), _c("y", "leisure", 78)],
        "B": [_c("m2", "money", 80), _c("x", "health", 79)],
    }
    hist = {"A": ["m"], "B": ["m2"]}
    greedy = select_board(
        raw, cands, hist, domain_cap=_BIG, event_cap=1,
        max_displacement_cost=7, policy=SelectionPolicy(),
    )
    swap = select_board(
        raw, cands, hist, domain_cap=_BIG, event_cap=1,
        max_displacement_cost=7, policy=_SWAP,
    )
    assert swap.cooldown_unresolved <= greedy.cooldown_unresolved
    assert swap.cooldown_moved >= greedy.cooldown_moved


def test_chain_never_revisits_a_card() -> None:
    """사슬 안에 같은 카드가 두 번 들어가지 않는다 — 순환 이동 0."""
    raw = {f"I{i}": _c(f"e{i}", "money", 80) for i in range(6)}
    cands = {
        f"I{i}": [_c(f"e{i}", "money", 80), _c("shared", "health", 79),
                  _c(f"alt{i}", "leisure", 78)]
        for i in range(6)
    }
    hist = {f"I{i}": [f"e{i}"] for i in range(6)}
    r = select_board(
        raw, cands, hist, domain_cap=_BIG, event_cap=2,
        max_displacement_cost=7, policy=_SWAP,
    )
    assert len(r.moves) == len({m.ilju for m in r.moves})


# ── 공통 경계 ──────────────────────────────────────────────────────────────


def test_budget_and_caps_are_never_violated() -> None:
    raw = {f"I{i}": _c("m", "money", 80) for i in range(10)}
    cands = {
        f"I{i}": [_c("m", "money", 80), _c(f"a{i}", "health", 80 - i)]
        for i in range(10)
    }
    hist = {f"I{i}": ["m"] for i in range(10)}
    r = select_board(
        raw, cands, hist, domain_cap=5, event_cap=5, max_displacement_cost=5,
        policy=SelectionPolicy(global_swap=True, severity_tiers=True,
                               recency_rotation=True),
    )
    assert all(m.displacement_cost <= 5 for m in r.moves)
    assert r.domain_overflow == 0


def test_policy_is_deterministic() -> None:
    raw = {f"I{i}": _c("m", "money", 80) for i in range(8)}
    cands = {
        f"I{i}": [_c("m", "money", 80), _c("a", "health", 79), _c("b", "leisure", 78)]
        for i in range(8)
    }
    hist = {f"I{i}": ["m"] for i in range(8)}
    # dict 를 ** 로 펼치면 값 타입이 object 로 합쳐져 파라미터마다 오류가 난다(호출당 4건).
    # 이 테스트의 요점은 '같은 인자로 두 번' 이므로 헬퍼가 의도도 더 잘 드러낸다.
    def run_board() -> PolicyResult:
        return select_board(
            raw, cands, hist, domain_cap=4, event_cap=4,
            max_displacement_cost=7, policy=_TIERS,
        )

    a = run_board()
    b = run_board()
    assert {k: v.event_key for k, v in a.selections.items()} == {
        k: v.event_key for k, v in b.selections.items()
    }


def test_partition_holds() -> None:
    raw = {f"I{i}": _c("m", "money", 80) for i in range(10)}
    cands = {f"I{i}": [_c("m", "money", 80)] for i in range(10)}
    hist = {f"I{i}": ["m"] for i in range(6)}
    r = select_board(raw, cands, hist, domain_cap=_BIG, policy=_TIERS)
    assert r.cooldown_triggered == 6
    assert r.cooldown_moved + r.cooldown_unresolved == r.cooldown_triggered


# ── P4: good 슬롯 override 는 라이브를 건드리지 않는다 ─────────────────────


def test_good_override_default_leaves_live_unchanged() -> None:
    """`good_override=None` 이면 기존 선발과 완전히 같다."""
    day = dt.date(2026, 8, 3)
    dicts = M.load_daily_dicts_for(day)
    ctx = M.build_day_context(day)
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    for idx in range(60):
        stem, branch = ganzi_from_index(idx)
        seed = f"{day.isoformat()}|{stem.value}{branch.value}|x"
        scored = [
            M._score_event(k, e, stem, branch, ctx)
            for k, e in dicts.catalog["events"].items()
        ]
        assert M._select_slots(scored, seed) == M._select_slots(
            scored, seed, good_override=None
        )


def test_good_override_only_accepts_eligible_good_events() -> None:
    """자격 없는 키를 넘기면 무시하고 기존 1순위를 쓴다 — 표시 불변식 보호."""
    day = dt.date(2026, 8, 3)
    dicts = M.load_daily_dicts_for(day)
    ctx = M.build_day_context(day)
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    stem, branch = ganzi_from_index(0)
    seed = f"{day.isoformat()}|{stem.value}{branch.value}|x"
    scored = [
        M._score_event(k, e, stem, branch, ctx)
        for k, e in dicts.catalog["events"].items()
    ]
    base = M._select_slots(scored, seed)
    # caution 사건을 good 슬롯에 넣으려는 시도는 무시된다.
    assert M._select_slots(scored, seed, good_override="argument_caution") == base
    assert M._select_slots(scored, seed, good_override="존재하지않는키") == base


def test_good_override_keeps_card_invariants() -> None:
    """override 를 써도 3개·2도메인·중복 금지 불변식이 유지된다."""
    day = dt.date(2026, 8, 3)
    dicts = M.load_daily_dicts_for(day)
    ctx = M.build_day_context(day)
    events = dicts.catalog["events"]
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    for idx in range(0, 60, 7):
        stem, branch = ganzi_from_index(idx)
        seed = f"{day.isoformat()}|{stem.value}{branch.value}|x"
        scored = [M._score_event(k, e, stem, branch, ctx) for k, e in events.items()]
        goods = [
            s for s in scored
            if s.valence == "good"
            and "good" in (events[s.event_key].get("headline_slots")
                           or events[s.event_key]["slots"])
        ]
        for g in goods[:5]:
            trio = M._select_slots(scored, seed, good_override=g.event_key)
            keys = [s.event_key for s in trio]
            assert len(set(keys)) == 3
            assert len({s.domain for s in trio}) >= 2
            groups = [s.synonym_group for s in trio if s.synonym_group]
            assert len(groups) == len(set(groups))
