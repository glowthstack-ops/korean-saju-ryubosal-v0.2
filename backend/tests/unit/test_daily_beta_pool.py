"""`beta-daily-pool.c10.v1` — 계약 동결과 날짜 게이트.

풀은 테스터에게 "지금 우리가 만든 완성 후보"를 보여주기 위한 **불변 snapshot** 이다.
두 가지를 지킨다.

  · 계약이 동결돼 있다 — 승인 대기 패치가 섞이면 피드백이 무엇을 대상으로 한 것인지
    알 수 없다.
  · 선생성돼 있어도 **KST 오늘까지만** 열린다. 선생성과 미래 노출은 다른 문제다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines.daily_beta_pool import (
    BETA_POOL_SELECTION_DRIFT,
    DATE_AFTER_POOL,
    DATE_BEFORE_POOL,
    FUTURE_DATE_NOT_PUBLISHABLE,
    KST,
    RENDERER_CONTRACT_VERSION,
    BetaPoolError,
    load_day,
    pool_metadata,
    render_board,
    render_result_fingerprint,
    today_kst,
    validate_pool,
)
from saju_engines.daily_selection_contracts import (
    DISPLAY_SELECTION_POLICY_C10_V1,
    HISTORY_CONTRACT_VERSION,
)

_POOL = "beta-daily-pool.c10.v1"
_ANCHOR = dt.date(2026, 7, 30)


@pytest.fixture(scope="module")
def meta() -> dict:
    return pool_metadata(_POOL)


def _now(d: dt.date) -> dt.datetime:
    """그 날짜의 KST 정오."""
    return dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=KST)


# ── 계약 동결 ──────────────────────────────────────────────────────────────


def test_contracts_are_frozen(meta) -> None:
    """승인 대기 패치가 섞이지 않았다."""
    assert meta["pool_version"] == _POOL
    assert meta["display_selection_policy_version"] == DISPLAY_SELECTION_POLICY_C10_V1
    assert meta["history_contract_version"] == HISTORY_CONTRACT_VERSION
    assert meta["g0_enabled"] is False           # G0 는 비활성
    assert meta["history_lookback_days"] == 90
    assert meta["bootstrap_warmup_days"] == 90


def test_fingerprints_are_recorded(meta) -> None:
    """같은 입력으로 다시 만들었을 때 비교할 지문이 남아 있다."""
    for key in ("engine_input_fingerprint", "bootstrap_fingerprint",
                "pool_result_fingerprint"):
        assert len(meta[key]) == 64, key


def test_generated_at_is_outside_the_fingerprint(meta) -> None:
    """생성 시각이 지문에 섞이면 재현이 깨진다 — 지문 계산 뒤에 찍는다."""
    assert "generated_at" in meta
    assert meta["generated_at"] not in meta["pool_result_fingerprint"]


def test_public_window_is_thirty_days(meta) -> None:
    start = dt.date.fromisoformat(meta["public_start"])
    end = dt.date.fromisoformat(meta["public_end"])
    assert start == _ANCHOR
    assert (end - start).days + 1 == meta["public_days"] == 30


def test_bootstrap_is_before_the_anchor(meta) -> None:
    """bootstrap 은 공개 전 구간이다 — 사용자에게 제공된 적이 없다."""
    assert dt.date.fromisoformat(meta["bootstrap_end"]) < _ANCHOR
    span = (dt.date.fromisoformat(meta["bootstrap_end"])
            - dt.date.fromisoformat(meta["bootstrap_start"])).days + 1
    assert span == meta["bootstrap_warmup_days"] + meta["history_lookback_days"]


def test_pool_declares_per_date_publication(meta) -> None:
    assert meta["publishable_per_date_only"] is True


# ── 날짜 게이트 ────────────────────────────────────────────────────────────


def test_today_is_open() -> None:
    day = load_day(_POOL, _ANCHOR, now=_now(_ANCHOR))
    assert day.fortune_date == _ANCHOR
    assert len(day.cards) == 60


def test_past_days_within_the_pool_stay_open() -> None:
    later = _ANCHOR + dt.timedelta(days=5)
    day = load_day(_POOL, _ANCHOR, now=_now(later))
    assert day.fortune_date == _ANCHOR


def test_future_day_is_refused_even_though_pregenerated() -> None:
    """선생성돼 있어도 열지 않는다."""
    with pytest.raises(BetaPoolError) as e:
        load_day(_POOL, _ANCHOR + dt.timedelta(days=1), now=_now(_ANCHOR))
    assert e.value.code == FUTURE_DATE_NOT_PUBLISHABLE


def test_admin_path_may_read_future(meta) -> None:
    """관리자·감사 경로만 열 수 있다."""
    day = load_day(
        _POOL, _ANCHOR + dt.timedelta(days=10), now=_now(_ANCHOR), allow_future=True
    )
    assert len(day.cards) == 60


def test_dates_outside_the_pool_are_refused() -> None:
    with pytest.raises(BetaPoolError) as before:
        load_day(_POOL, _ANCHOR - dt.timedelta(days=1), now=_now(_ANCHOR))
    assert before.value.code == DATE_BEFORE_POOL

    far = _ANCHOR + dt.timedelta(days=99)
    with pytest.raises(BetaPoolError) as after:
        load_day(_POOL, far, now=_now(far), allow_future=True)
    assert after.value.code == DATE_AFTER_POOL


def test_kst_boundary_uses_korean_midnight() -> None:
    """UTC 15:00 = KST 다음날 00:00 — 경계에서 하루가 넘어간다."""
    utc_before = dt.datetime(2026, 7, 30, 14, 59, tzinfo=dt.UTC)
    utc_after = dt.datetime(2026, 7, 30, 15, 0, tzinfo=dt.UTC)
    assert today_kst(utc_before) == dt.date(2026, 7, 30)
    assert today_kst(utc_after) == dt.date(2026, 7, 31)


# ── 카드 불변식 ────────────────────────────────────────────────────────────


def test_every_day_has_sixty_distinct_iljus() -> None:
    for i in (0, 7, 29):
        day = load_day(
            _POOL, _ANCHOR + dt.timedelta(days=i), now=_now(_ANCHOR), allow_future=True
        )
        iljus = [c["ilju"] for c in day.cards]
        assert len(iljus) == 60
        assert len(set(iljus)) == 60


def test_cards_carry_both_semantic_family_axes() -> None:
    """C10 은 두 축을 각각 쓴다 — 원장과 같은 규약으로 담는다."""
    day = load_day(_POOL, _ANCHOR, now=_now(_ANCHOR))
    for c in day.cards:
        assert c["display_good_semantic_family"]
        assert c["final_headline_semantic_family"]


def test_headline_is_one_of_the_displayed_events() -> None:
    day = load_day(_POOL, _ANCHOR, now=_now(_ANCHOR))
    for c in day.cards:
        shown = {c["display_good_representative"], c["support_event"], c["caution_event"]}
        assert c["final_headline"] in shown


def test_loss_budget_and_s5_protection_hold() -> None:
    """C10 계약이 풀 전체에서 지켜졌다."""
    for i in range(0, 30, 6):
        day = load_day(
            _POOL, _ANCHOR + dt.timedelta(days=i), now=_now(_ANCHOR), allow_future=True
        )
        for c in day.cards:
            assert 0 <= c["display_displacement_loss"] <= 7
            if c["raw_good_winner"] == c["display_good_representative"]:
                assert c["display_displacement_loss"] == 0


# ── 시작 시 전수 검증 ─────────────────────────────────────────────────────


def test_startup_validation_passes() -> None:
    """하나라도 실패하면 베타 pool 을 활성 상태로 올리지 않는다."""
    index = validate_pool(_POOL)
    assert len(index) == 30 * 60
    assert len({d for d, _i in index}) == 30
    assert len({i for _d, i in index}) == 60


def test_realized_representative_is_recorded_not_intent() -> None:
    """`_select_slots` 는 good 후보를 `slots` 로 고른다 — 의도가 아니라 **실현**을 담는다.

    의도를 담으면 snapshot 이 실제 카드와 어긋난다(초판에서 96/1800 슬롯 중복).
    """
    day = load_day(_POOL, _ANCHOR, now=_now(_ANCHOR))
    for c in day.cards:
        assert "intended_good_representative" in c
        assert "representative_realized" in c
        if c["representative_realized"]:
            assert c["display_good_representative"] == c["intended_good_representative"]
    unrealized = [c for c in day.cards if not c["representative_realized"]]
    assert unrealized, "미실현 사례가 없으면 이 회귀가 아무것도 검증하지 못한다"


def test_loss_baseline_is_the_good_slot_pool_top() -> None:
    """손실 기준선은 헤드라인 자격 pool 이 아니라 good 슬롯 pool 의 1위다."""
    day = load_day(_POOL, _ANCHOR, now=_now(_ANCHOR))
    for c in day.cards:
        assert 0 <= c["display_displacement_loss"] <= 7
        if c["display_good_representative"] == c["raw_good_winner"]:
            assert c["display_displacement_loss"] == 0


# ── 렌더링: snapshot 이 SSOT ──────────────────────────────────────────────


def test_render_matches_the_snapshot_selection() -> None:
    board = render_board(_POOL, _ANCHOR, now=_now(_ANCHOR))
    day = load_day(_POOL, _ANCHOR, now=_now(_ANCHOR))
    by_ilju = {c["ilju"]: c for c in day.cards}
    assert len(board.fortunes) == 60
    for f in board.fortunes:
        c = by_ilju[f.ilju]
        assert [e.event_key for e in f.events] == [
            c["display_good_representative"], c["caution_event"], c["support_event"]
        ]
        assert str(f.headline_event_key) == c["final_headline"]


def test_render_is_deterministic() -> None:
    """같은 카드를 다시 열면 문장까지 같아야 한다."""
    a = render_board(_POOL, _ANCHOR, now=_now(_ANCHOR))
    b = render_board(_POOL, _ANCHOR, now=_now(_ANCHOR))
    assert render_result_fingerprint(a) == render_result_fingerprint(b)
    assert [f.headline for f in a.fortunes] == [f.headline for f in b.fortunes]


def test_beta_path_never_calls_selection_functions(monkeypatch) -> None:
    """베타 경로에서 선택 함수가 호출되면 snapshot 이 SSOT 가 아니게 된다."""
    import saju_engines.daily_ilju_fortune as engine

    called: list[str] = []
    for name in ("_select_slots", "_headline_candidates", "_rebalance_headlines"):
        original = getattr(engine, name)

        def spy(*a, _n=name, _o=original, **kw):
            called.append(_n)
            return _o(*a, **kw)

        monkeypatch.setattr(engine, name, spy)

    render_board(_POOL, _ANCHOR, now=_now(_ANCHOR))
    assert called == [], f"베타 경로가 선택 함수를 호출했다: {sorted(set(called))}"


def test_render_refuses_future_dates() -> None:
    with pytest.raises(BetaPoolError) as e:
        render_board(_POOL, _ANCHOR + dt.timedelta(days=3), now=_now(_ANCHOR))
    assert e.value.code == FUTURE_DATE_NOT_PUBLISHABLE


def test_renderer_contract_is_declared() -> None:
    assert RENDERER_CONTRACT_VERSION == "daily-beta-render.c10.v1"
    assert BETA_POOL_SELECTION_DRIFT == "BETA_POOL_SELECTION_DRIFT"


# ── 라이브 경로 불변 ──────────────────────────────────────────────────────


def test_live_path_is_unchanged_without_override() -> None:
    """`selection_override=None` 이면 라이브 보드가 바이트 단위로 같다."""
    import saju_engines.daily_ilju_fortune as engine

    day = dt.date(2026, 8, 3)
    dicts = engine.load_daily_dicts_for(day)
    ctx = engine.build_day_context(day)
    a = engine.compute_board(ctx, dicts)
    b = engine.compute_board(ctx, dicts, selection_override=None)
    assert a.model_dump() == b.model_dump()
