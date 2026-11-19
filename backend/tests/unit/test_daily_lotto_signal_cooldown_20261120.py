"""docs/17 §36 — 오늘의 운세 로또 문구의 쉬는 기간 규칙 교체 (2026-11-19 데굴님 지시).

"오늘의 운세에서 왜 로또 구매 권유와 연애운 한마디가 빠졌는지 체크하고(신호강한 일주에만 표시)
개발 과정에서 빠진 거라면 개선해서 다시 적용해줘."

로또 문구에는 일주별 쉬는 기간이 있다(§12 "최근 14일 내 같은 일주 미사용"). 종전 구현은 이력 없이
이를 흉내 낸 날짜 산술 슬롯 `(날짜 서수 + 일주 번호) % 7 == 0` 이었다. 이 슬롯은 신호와 무관하게
7일 중 하루만 열려, 유입 표지 게이트(§33, 11/18) 뒤로는 편재가 표면에 온 날의 6/7 을 버렸다.
경계(LOTTO_SIGNAL_COOLDOWN_EFFECTIVE_FROM, 11/21)부터는 그 일주에게 직전 13일 안에 로또 조건이
성립한 날이 없을 때만 낸다. 과거 날짜는 그날 계약(model.v2.5 이하)으로 재생된다.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping

import pytest

from saju_engines import daily_fortune_v2 as V
from saju_engines import daily_ilju_fortune as M
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_shared_types.daily_fortune import (
    LOTTO_COOLDOWN_DAYS,
    LOTTO_SIGNAL_COOLDOWN_EFFECTIVE_FROM,
    DailyFortuneBoard,
    DayGanjiContext,
    active_dict_version,
    lotto_uses_signal_cooldown,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION,
    MODEL_V2_VERSION_BEFORE_LOTTO_SIGNAL_COOLDOWN,
    active_model_v2_version,
)

_FROM = LOTTO_SIGNAL_COOLDOWN_EFFECTIVE_FROM  # 2026-11-21
_BEFORE = _FROM - dt.timedelta(days=1)
_STEM_OF = {
    f"{st.value}{br.value}": st for st, br in (ganzi_from_index(i) for i in range(60))
}
#: 11/24 = 편재가 표면에 온 庚 일간 세 일주에 조건이 성립하는 날. 종전 슬롯으로는 한 장도 안 나간다.
_STRONG_DAY = dt.date(2026, 11, 24)
#: 11/26 = 庚申 에 조건이 다시 성립하지만 이틀 전(11/24)에 성립했으므로 쉬는 날.
_RESTING_DAY = dt.date(2026, 11, 26)


def _board(d: dt.date) -> DailyFortuneBoard:
    return V.compute_board_v2(M.build_day_context(d), M.load_daily_dicts_for(d))


def _lotto(board: DailyFortuneBoard) -> set[str]:
    return {f.ilju for f in board.fortunes if f.lotto_phrase}


class _Scorer:
    """v2 채점기(날짜별 결과 보관) — 여러 날을 훑는 검사에서 같은 날을 다시 채점하지 않는다."""

    def __init__(self) -> None:
        self._catalog = V.load_catalog_v2_for(_FROM)
        self._rows: dict[dt.date, Mapping[str, list[M._ScoredEvent]]] = {}

    def __call__(self, ctx: DayGanjiContext) -> Mapping[str, list[M._ScoredEvent]]:
        if ctx.the_date not in self._rows:
            rows: dict[str, list[M._ScoredEvent]] = {}
            for idx in range(60):
                stem, branch = ganzi_from_index(idx)
                pool, _eligible, _fallback = V.build_pool_v2(
                    self._catalog, V.day_channels(stem, branch, ctx)
                )
                rows[f"{stem.value}{branch.value}"] = pool
            self._rows[ctx.the_date] = rows
        return self._rows[ctx.the_date]


def test_boundary_selects_model_version_and_keeps_dict_version() -> None:
    assert not lotto_uses_signal_cooldown(_BEFORE) and lotto_uses_signal_cooldown(_FROM)
    assert active_model_v2_version(_BEFORE) == MODEL_V2_VERSION_BEFORE_LOTTO_SIGNAL_COOLDOWN
    assert MODEL_V2_VERSION_BEFORE_LOTTO_SIGNAL_COOLDOWN == "model.v2.5"
    assert active_model_v2_version(_FROM) == MODEL_V2_VERSION == "model.v2.6"
    # 사전 문구는 그대로다 — dict 버전은 경계 앞뒤가 같고, 캐시 키는 model 버전으로 갈린다.
    assert active_dict_version(_BEFORE) == active_dict_version(_FROM)
    assert V.content_version_v2_for(_BEFORE) != V.content_version_v2_for(_FROM)
    assert LOTTO_COOLDOWN_DAYS == 14  # §12 "최근 14일 내 같은 일주 미사용"


def test_strong_signal_day_shows_lotto_that_date_slot_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """편재가 표면에 온 날의 문구가 실제로 나간다 — 종전 날짜 슬롯은 같은 날 한 장도 내지 않았다."""
    ctx = M.build_day_context(_STRONG_DAY)
    board = _board(_STRONG_DAY)
    shown = _lotto(board)
    assert shown == {"庚午", "庚申", "庚辰"}
    for ilju in shown:
        gods = M.surface_ten_gods(_STEM_OF[ilju], ctx)
        assert "편재" in gods and not (gods & {"비견", "겁재"}), (ilju, gods)
    assert board.content_version.endswith("model.v2.6")
    # 반례: 같은 날을 종전 규칙(날짜 슬롯)으로 만들면 조건이 성립한 세 일주가 전부 버려진다.
    with monkeypatch.context() as mp:
        mp.setattr(M, "lotto_uses_signal_cooldown", lambda _d: False)
        legacy = _board(_STRONG_DAY)
    assert _lotto(legacy) == set()
    # 규칙은 로또 문구 유무만 바꾼다 — 사건·확률·Top5·헤드라인·장소·연애 줄·조언은 그대로.
    assert board.top5 == legacy.top5
    for new, old in zip(board.fortunes, legacy.fortunes, strict=True):
        assert new.model_dump(exclude={"lotto_phrase"}) == old.model_dump(exclude={"lotto_phrase"})


def test_ilju_rests_when_signal_was_met_within_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이틀 전에 조건이 성립한 일주는 오늘 조건이 다시 성립해도 쉰다."""
    ctx = M.build_day_context(_RESTING_DAY)
    scorer = _Scorer()
    assert M.lotto_signal_iljus(ctx, scorer(ctx)) == ["庚申"]  # 오늘 조건은 성립한다
    two_days_ago = M.build_day_context(_RESTING_DAY - dt.timedelta(days=2))
    assert "庚申" in M.lotto_signal_iljus(two_days_ago, scorer(two_days_ago))
    assert M.lotto_iljus_with_cooldown(ctx, scorer(ctx), scorer) == []
    assert _lotto(_board(_RESTING_DAY)) == set()
    # 반례: 쉬는 일주가 없다고 하면 같은 날 庚申 이 문구를 받는다 — 막은 것은 쉬는 기간이다.
    with monkeypatch.context() as mp:
        mp.setattr(M, "_lotto_recent_signal_iljus", lambda _d, _rows_for: frozenset())
        assert M.lotto_iljus_with_cooldown(ctx, scorer(ctx), scorer) == ["庚申"]


def test_cooldown_window_is_previous_thirteen_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """쉬는 기간은 오늘을 뺀 직전 13일만 본다 — 14일 전 성립일은 세지 않는다."""
    seen: list[dt.date] = []

    def fake_signal(ctx: DayGanjiContext, _rows: object) -> list[str]:
        seen.append(ctx.the_date)
        return ["甲子"] if ctx.the_date == _FROM - dt.timedelta(days=14) else []

    monkeypatch.setattr(M, "lotto_signal_iljus", fake_signal)
    assert M._lotto_recent_signal_iljus(_FROM, lambda _ctx: {}) == frozenset()
    assert seen == [_FROM - dt.timedelta(days=k) for k in range(1, 14)]
    # 반례: 13일 전 성립일은 쉬는 기간 안이다.
    monkeypatch.setattr(
        M, "lotto_signal_iljus",
        lambda ctx, _rows: ["甲子"] if ctx.the_date == _FROM - dt.timedelta(days=13) else [],
    )
    assert M._lotto_recent_signal_iljus(_FROM, lambda _ctx: {}) == frozenset({"甲子"})


def test_same_ilju_never_repeats_within_cooldown_and_daily_cap_holds() -> None:
    """60일 재생 — 같은 일주는 14일 안에 다시 받지 않고, 하루 3개 이하이며, 전부 편재 표면일이다."""
    scorer = _Scorer()
    last: dict[str, dt.date] = {}
    total = shown_days = 0
    for offset in range(60):
        d = _FROM + dt.timedelta(days=offset)
        ctx = M.build_day_context(d)
        picked = M.lotto_iljus_with_cooldown(ctx, scorer(ctx), scorer)
        assert len(picked) <= 3 and len(set(picked)) == len(picked)
        total += len(picked)
        shown_days += bool(picked)
        for ilju in picked:
            gods = M.surface_ten_gods(_STEM_OF[ilju], ctx)
            assert "편재" in gods and not (gods & {"비견", "겁재"}), (d, ilju, gods)
            if ilju in last:
                assert (d - last[ilju]).days >= LOTTO_COOLDOWN_DAYS, (ilju, last[ilju], d)
            last[ilju] = d
    # 종전 날짜 슬롯(1년 측정에서 문구가 실린 날 28%)과 달리 절반 넘는 날에 실린다.
    assert shown_days >= 30 and total >= 40, (shown_days, total)


def test_board_before_boundary_keeps_date_slot_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """경계 이전 날짜(11/20)는 종전 계약 그대로다 — 이전 날짜 채점(쉬는 기간 판정)을 하지 않는다."""

    def boom(*_args: object, **_kwargs: object) -> frozenset[str]:
        raise AssertionError("경계 이전 날짜에서 쉬는 기간 판정이 호출됐다")

    monkeypatch.setattr(M, "_lotto_recent_signal_iljus", boom)
    board = _board(_BEFORE)
    assert board.content_version.endswith("model.v2.5")
    # 11/20 에는 甲申 에 조건이 성립하지만 날짜 슬롯이 닫혀 있어 종전 계약으로는 문구가 없다.
    ctx = M.build_day_context(_BEFORE)
    assert M.lotto_signal_iljus(ctx, _Scorer()(ctx)) == ["甲申"]
    assert _lotto(board) == set()


def test_v1_path_scores_previous_days_with_its_own_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    """채점기를 주입하지 않는 v1 경로도 같은 규칙을 쓴다 — 이전 날짜는 v1 채점기로 채점한다."""
    ctx = M.build_day_context(_STRONG_DAY)
    dicts = M.load_daily_dicts_for(_STRONG_DAY)
    calls: list[dt.date] = []
    real = M._v1_scored_rows

    def spy(prev_ctx: DayGanjiContext, d: M.DailyFortuneDicts) -> dict[str, list[M._ScoredEvent]]:
        calls.append(prev_ctx.the_date)
        return real(prev_ctx, d)

    monkeypatch.setattr(M, "_v1_scored_rows", spy)
    # 오늘 조건이 성립한 일주가 있다고 고정해 이전 날짜 채점 경로를 반드시 지나게 한다.
    real_signal = M.lotto_signal_iljus
    monkeypatch.setattr(
        M, "lotto_signal_iljus",
        lambda c, rows: ["甲子"] if c.the_date == _STRONG_DAY else real_signal(c, rows),
    )
    board = M.compute_board(ctx, dicts)
    assert calls == [_STRONG_DAY - dt.timedelta(days=k) for k in range(1, 14)]
    resting = M._lotto_recent_signal_iljus(_STRONG_DAY, lambda c: real(c, dicts))
    assert _lotto(board) == (set() if "甲子" in resting else {"甲子"})
