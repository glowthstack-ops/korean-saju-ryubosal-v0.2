"""OA-6d2 — 선택 계약 v2(후보 해시) shadow.

확정 계약:
    event_merit_key = (probability,)   ← 실사로 확인된 현행 계약
    동점  = probability 동일           → v2 tie-break 개입 허용
    비동점 = probability 상이           → v2 변경 금지(결함)

`activation`은 probability 산출의 입력일 뿐 독립 순위 항목이 아니다. 이를 순위에 넣는
것은 결함 수정이 아니라 새 사건 선택 정책이므로 여기서 다루지 않는다.
"""

from __future__ import annotations

import datetime as dt

import pytest

import saju_engines.daily_ilju_fortune as M
from saju_engines.daily_selection_shadow import compare_contracts

_DATE = dt.date(2026, 7, 28)
_ILJU = "甲子"


def _ev(key: str, probability: int, *, activation: float = 0.5, domain: str = "work",
        valence: str = "good", slots: tuple[str, ...] = ("good", "support")):
    return M._ScoredEvent(
        event_key=key, domain=domain, valence=valence, slots=slots,
        headline_slots=slots, synonym_group=None, activation=activation,
        probability=probability, supporting_groups=1, contradiction=0.0,
    )


@pytest.fixture(scope="module")
def dicts():
    return M.load_daily_dicts()


# ── merit 계약 ─────────────────────────────────────────────────────────────


def test_higher_probability_always_wins() -> None:
    cands = [_ev("a", 60), _ev("b", 61), _ev("c", 59)]

    for _ in range(20):  # 해시가 어떻든 결과가 뒤집히지 않는다
        assert select(cands).event_key == "b"


def select(cands, *, target_date=_DATE, ilju=_ILJU):
    return M.select_event_v2(cands, target_date=target_date, ilju=ilju)


def test_v2_tiebreak_uses_probability_as_the_only_merit_key() -> None:
    """activation이 달라도 probability가 같으면 동점이다(현행 계약 회귀).

    activation이 영원히 무의미하다는 명리 판단이 아니라, **현재 선택 계약에 별도 순위로
    포함돼 있지 않다**는 사실을 고정하는 것이다.
    """
    low = _ev("low_act", 70, activation=0.10)
    high = _ev("high_act", 70, activation=0.99)

    assert M.event_merit_key(low) == M.event_merit_key(high)
    # 승자는 activation이 아니라 후보 해시가 정한다.
    winner = select([low, high])
    expected = min(
        [low, high], key=lambda c: (M._tiebreak_v2(c, _DATE, _ILJU), c.event_key)
    )
    assert winner.event_key == expected.event_key


def test_activation_does_not_break_probability_tie() -> None:
    """activation이 높다는 이유만으로 이기지 않는다."""
    winners = set()
    for i in range(40):
        a = _ev("alpha", 70, activation=0.99)
        b = _ev("beta", 70, activation=0.01)
        winners.add(select([a, b], ilju=f"ilju{i}").event_key)
    assert winners == {"alpha", "beta"}, "한쪽이 activation으로 독점하고 있다"


# ── candidate hash 적용 범위 ───────────────────────────────────────────────


def test_candidate_hash_only_breaks_equal_probability() -> None:
    """해시는 최고 동치류 안에서만 작동한다."""
    tied = [_ev(f"t{i}", 80) for i in range(5)]
    lower = [_ev(f"low{i}", 79) for i in range(5)]

    for i in range(30):
        w = select(tied + lower, ilju=f"x{i}")
        assert w.probability == 80


def test_candidate_hash_cannot_override_higher_probability() -> None:
    """해시가 아무리 작아도 낮은 probability를 끌어올리지 못한다."""
    best = _ev("only_best", 90)
    others = [_ev(f"o{i}", 89) for i in range(20)]

    for i in range(30):
        assert select([*others, best], ilju=f"y{i}").event_key == "only_best"


def test_full_hash_collision_falls_back_to_event_key(monkeypatch) -> None:
    """전체 해시가 충돌해도 `event_key`가 결정론적으로 해소한다."""
    monkeypatch.setattr(M, "_stable_hash", lambda _text: 42)
    a, b = _ev("zeta", 70), _ev("alpha", 70)

    assert select([a, b]).event_key == "alpha"
    assert select([b, a]).event_key == "alpha"   # 입력 순서와 무관


def test_empty_candidates_raise() -> None:
    with pytest.raises(ValueError):
        select([])


# ── 순서·무관 후보 안정성 ──────────────────────────────────────────────────


def test_input_order_does_not_change_v2_selection() -> None:
    cands = [_ev(f"e{i}", 75) for i in range(8)]

    assert select(cands).event_key == select(list(reversed(cands))).event_key


def test_irrelevant_candidate_does_not_change_existing_winner() -> None:
    """최고 probability보다 낮은 후보를 추가해도 승자가 그대로다."""
    cands = [_ev("a", 80), _ev("b", 80), _ev("c", 80)]
    before = select(cands).event_key

    after = select([*cands, _ev("irrelevant", 40), _ev("irrelevant2", 79)]).event_key

    assert before == after


def test_equal_top_candidate_may_change_winner() -> None:
    """같은 최고 probability 후보 추가는 동치류 구성을 바꾼다 — 변경이 정상이다."""
    cands = [_ev("a", 80), _ev("b", 80)]
    winners = {select(cands).event_key}
    for i in range(20):
        winners.add(select([*cands, _ev(f"new{i}", 80)]).event_key)
    assert len(winners) >= 1   # 바뀔 수 있다(결함 아님)


def test_json_catalog_reversal_does_not_change_v2_selection(dicts) -> None:
    """사전 배열 순서를 뒤집어도 v2 선택이 같다(실제 보드 경로)."""
    from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index

    for day in range(3):
        ctx = M.build_day_context(dt.date(2026, 7, 1) + dt.timedelta(days=day))
        for idx in range(0, 60, 7):
            stem, branch = ganzi_from_index(idx)
            ilju = f"{stem.value}{branch.value}"
            scored = [
                M._score_event(k, e, stem, branch, ctx)
                for k, e in dicts.catalog["events"].items()
            ]
            seed = f"{ctx.the_date.isoformat()}|{ilju}|{M.EVENT_SELECTION_COMPAT_SALT}"

            def key(s, _d=ctx.the_date, _i=ilju):
                return M._rank_key_v2(s, _d, _i)

            a, _, _ = M._select_slots(scored, seed, rank=key)
            b, _, _ = M._select_slots(list(reversed(scored)), seed, rank=key)
            assert a.event_key == b.event_key, f"{ilju}: 배열 순서에 흔들린다"


# ── shadow 감사 ────────────────────────────────────────────────────────────


def test_shadow_never_violates_merit(dicts) -> None:
    """v2가 낮은 probability 후보를 고르는 일이 없어야 한다 — 절대 조건."""
    for day in range(5):
        report = compare_contracts(
            M.build_day_context(dt.date(2026, 7, 1) + dt.timedelta(days=day)), dicts
        )
        assert not report.has_violation, [v.__dict__ for v in report.violations[:3]]
        for row in report.comparisons:
            if row.legacy_event_key != row.v2_event_key:
                assert row.merit_tie, "비동점 후보로 이동했다"
                assert row.change_reason


def test_shadow_does_not_touch_live_selection(dicts) -> None:
    """shadow 계산이 라이브 보드를 바꾸지 않는다."""
    ctx = M.build_day_context(_DATE)
    before = [str(f.headline_event_key) for f in M.compute_board(ctx, dicts).fortunes]

    compare_contracts(ctx, dicts)

    after = [str(f.headline_event_key) for f in M.compute_board(ctx, dicts).fortunes]
    assert before == after


def test_legacy_frozen_contract_matches_v19_baseline(dicts) -> None:
    """v2 shadow를 추가해도 라이브(v1)는 배포 시점 결과 그대로다."""
    from saju_engines.daily_fortune_snapshot import load_snapshot

    old = load_snapshot("dict.v1.9")
    assert old is not None, "비교 기준 스냅샷이 없다"
    old_d = M.DailyFortuneDicts(
        catalog=old["catalog"], templates=old["templates"], places=old["places"]
    )
    for day in range(3):
        ctx = M.build_day_context(dt.date(2026, 7, 1) + dt.timedelta(days=day))
        base = M.compute_board(ctx, old_d)
        now = M.compute_board(ctx, dicts)
        assert [str(f.headline_event_key) for f in base.fortunes] == [
            str(f.headline_event_key) for f in now.fortunes
        ]
