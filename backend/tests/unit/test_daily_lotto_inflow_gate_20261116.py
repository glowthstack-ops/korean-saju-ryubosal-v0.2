"""docs/17 §33 — 오늘의 운세 로또 문구의 횡재 유입 표지 게이트 (2026-11-16 데굴님 지시).

"오늘의 운세의 횡재 관련 부분에도 적용할 수 있는 부분은 적용해."

횡재의 별은 편재이고 비견·겁재는 편재를 나누는 쪽이다(doc/v2_2/WINDFALL_SIGNAL_REVIEW.md). 종전
로또 문구 게이트는 '공돈' 사건 확률만 보아, 그 사건이 인성 방향만으로 뜬 날(편재가 지장간에도 없는
날)에도 로또 문구가 나갔다. 날짜 경계(LOTTO_INFLOW_GATE_EFFECTIVE_FROM, 11/18)부터 오늘 일진의 표면
십성(천간·지지 본기)에 편재가 있고 비견·겁재가 없을 때만 문구를 낸다. 과거 날짜는 그날 계약
(model.v2.4)으로 재생된다.
"""

from __future__ import annotations

import datetime as dt

import pytest

from saju_engines import daily_ilju_fortune as M
from saju_engines.daily_fortune_v2 import compute_board_v2, content_version_v2_for
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_shared_types.daily_fortune import (
    LOTTO_INFLOW_GATE_EFFECTIVE_FROM,
    DayGanjiContext,
    active_dict_version,
    lotto_requires_windfall_star,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION_BEFORE_LOTTO_INFLOW_GATE,
    MODEL_V2_VERSION_BEFORE_LOTTO_SIGNAL_COOLDOWN,
    active_model_v2_version,
)
from saju_shared_types.enums import Stem as S

_FROM = LOTTO_INFLOW_GATE_EFFECTIVE_FROM  # 2026-11-18
_BEFORE = _FROM - dt.timedelta(days=1)
_STEM_OF = {
    f"{st.value}{br.value}": st for st, br in (ganzi_from_index(i) for i in range(60))
}


def _ctx_with_day(base: DayGanjiContext, stem: str, branch: str) -> DayGanjiContext:
    return base.model_copy(update={"day_stem": stem, "day_branch": branch})


def test_boundary_selects_model_version_and_keeps_dict_version() -> None:
    assert not lotto_requires_windfall_star(_BEFORE) and lotto_requires_windfall_star(_FROM)
    assert active_model_v2_version(_BEFORE) == MODEL_V2_VERSION_BEFORE_LOTTO_INFLOW_GATE
    assert MODEL_V2_VERSION_BEFORE_LOTTO_INFLOW_GATE == "model.v2.4"
    # 11/18~11/20 은 model.v2.5, 11/21 부터 v2.6(로또 쉬는 기간 규칙 — docs/17 §36).
    assert active_model_v2_version(_FROM) == MODEL_V2_VERSION_BEFORE_LOTTO_SIGNAL_COOLDOWN
    assert MODEL_V2_VERSION_BEFORE_LOTTO_SIGNAL_COOLDOWN == "model.v2.5"
    # 사전 문구는 그대로다 — dict 버전은 경계 앞뒤가 같고, 캐시 키는 model 버전으로 갈린다.
    assert active_dict_version(_BEFORE) == active_dict_version(_FROM)
    assert content_version_v2_for(_BEFORE) != content_version_v2_for(_FROM)


def test_gate_needs_surface_windfall_star_without_peers() -> None:
    after = M.build_day_context(_FROM)
    # 甲 일간 × 戊辰일: 천간 戊 = 편재, 지지 본기 戊 = 편재 → 통과.
    assert M.surface_ten_gods(S.GAP, _ctx_with_day(after, "戊", "辰")) == {"편재"}
    assert M.lotto_inflow_ok(S.GAP, _ctx_with_day(after, "戊", "辰"))
    # 반례 ①: 편재가 표면에 없다 — 甲 일간 × 壬申일(편인/편관). 申 중기 壬·여기 戊(편재)는
    # 지장간이라 표면이 아니다.
    assert "편재" not in M.surface_ten_gods(S.GAP, _ctx_with_day(after, "壬", "申"))
    assert not M.lotto_inflow_ok(S.GAP, _ctx_with_day(after, "壬", "申"))
    # 반례 ②: 편재와 겁재가 함께 표면에 있다 — 丙 일간 × 庚午일(천간 편재, 지지 본기 丁 겁재).
    assert M.surface_ten_gods(S.BYEONG, _ctx_with_day(after, "庚", "午")) == {"편재", "겁재"}
    assert not M.lotto_inflow_ok(S.BYEONG, _ctx_with_day(after, "庚", "午"))
    # 반례 ③: 정재만 있는 날 — 甲 일간 × 己丑일. 정재는 유입 표지가 아니다.
    assert not M.lotto_inflow_ok(S.GAP, _ctx_with_day(after, "己", "丑"))
    # 경계 이전 날짜는 종전 게이트 — 같은 간지라도 항상 통과(그날 계약 재생).
    before = M.build_day_context(_BEFORE)
    assert M.lotto_inflow_ok(S.GAP, _ctx_with_day(before, "壬", "申"))
    assert M.lotto_inflow_ok(S.BYEONG, _ctx_with_day(before, "庚", "午"))


def test_boards_after_boundary_only_show_lotto_with_windfall_star() -> None:
    shown = 0
    for offset in range(40):
        d = _FROM + dt.timedelta(days=offset)
        ctx = M.build_day_context(d)
        board = compute_board_v2(ctx, M.load_daily_dicts_for(d))
        for row in board.fortunes:
            if not row.lotto_phrase:
                continue
            shown += 1
            gods = M.surface_ten_gods(_STEM_OF[row.ilju], ctx)
            assert "편재" in gods and not (gods & {"비견", "겁재"}), (d, row.ilju, gods)
    assert shown > 0  # 게이트가 문구를 전부 막아 버린 것이 아니다


def test_gate_changes_lotto_phrase_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """게이트는 로또 문구 유무만 바꾼다 — 사건·확률·Top5·헤드라인·장소·연애 줄·조언은 그대로.

    유입 표지 게이트(v2.5)만 떼어 보려고 쉬는 기간 규칙은 종전 날짜 슬롯으로 고정한다 — 11/21
    부터의 v2.6 규칙(§36)은 유입 표지를 날짜 경계와 무관하게 요구해, 그대로 두면 두 보드가 같아진다.
    """
    monkeypatch.setattr(M, "lotto_uses_signal_cooldown", lambda _d: False)
    changed_days = 0
    for offset in range(20):
        d = _FROM + dt.timedelta(days=offset)
        ctx = M.build_day_context(d)
        dicts = M.load_daily_dicts_for(d)
        gated = compute_board_v2(ctx, dicts)
        with monkeypatch.context() as mp:
            mp.setattr(M, "lotto_requires_windfall_star", lambda _d: False)
            legacy = compute_board_v2(ctx, dicts)
        assert gated.top5 == legacy.top5
        gated_lotto = {r.ilju for r in gated.fortunes if r.lotto_phrase}
        legacy_lotto = {r.ilju for r in legacy.fortunes if r.lotto_phrase}
        if gated_lotto != legacy_lotto:
            changed_days += 1
        for g, lg in zip(gated.fortunes, legacy.fortunes, strict=True):
            assert g.model_dump(exclude={"lotto_phrase"}) == lg.model_dump(exclude={"lotto_phrase"})
    assert changed_days > 0  # 반례: 종전 게이트라면 나갔을 문구가 실제로 막힌다


def test_board_before_boundary_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """경계 이전 날짜(11/17)는 게이트 코드가 있어도 종전 보드와 완전히 같다."""
    ctx = M.build_day_context(_BEFORE)
    dicts = M.load_daily_dicts_for(_BEFORE)
    current = compute_board_v2(ctx, dicts)
    with monkeypatch.context() as mp:
        mp.setattr(M, "lotto_requires_windfall_star", lambda _d: False)
        legacy = compute_board_v2(ctx, dicts)
    assert current == legacy
    assert current.content_version.endswith("model.v2.4")
