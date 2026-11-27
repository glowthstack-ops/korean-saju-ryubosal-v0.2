"""오늘의 운세 — 이번 달 흐름의 투자 참고·태어난 계절 문장 (dict.v1.23, docs/17 §35).

2026-11-18 데굴님 "이번에 진행하는 건 AI채팅상담과 테마사주, 오늘의 운세 모두 필요한 영역에
배선되어야 해." 두 문장은 일간과 무관한 달력 값이라 열 천간 공통 줄 끝에 같은 문장이 붙는다.
판정·사건·점수는 바뀌지 않는다.
"""

from __future__ import annotations

import datetime as dt
import re

from saju_api.services import daily_fortune_polish as polish
from saju_engines import daily_ilju_fortune as M
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_engines.season_fortune import autumn_phase, board_season_key
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    DICT_VERSION_BEFORE_MONTH_NOTES,
    MONTH_NOTES_EFFECTIVE_FROM,
    DailyFortuneBoard,
    active_dict_version,
)

_FROM = MONTH_NOTES_EFFECTIVE_FROM
_BEFORE = _FROM - dt.timedelta(days=1)
_HANJA_OR_DIGIT = re.compile(r"[一-鿿0-9]")


def _board(d: dt.date) -> DailyFortuneBoard:
    return compute_board_v2(M.build_day_context(d), M.load_daily_dicts_for(d))


def _layer(d: dt.date) -> dict:
    return M.load_daily_dicts_for(d).templates["month_layer"]


def test_version_boundary() -> None:
    assert DICT_VERSION == "dict.v1.25" and DICT_VERSION_BEFORE_MONTH_NOTES == "dict.v1.22"
    assert _FROM == dt.date(2026, 11, 20)
    assert active_dict_version(_FROM) == "dict.v1.23"
    assert active_dict_version(_BEFORE) == "dict.v1.22"
    # 이전 스냅샷에는 키가 없다 — 11/19 보드는 그대로다.
    assert "birth_season" not in _layer(_BEFORE) and "invest_month" not in _layer(_BEFORE)


def test_sentences_follow_text_policy() -> None:
    layer = _layer(_FROM)
    seasons = layer["birth_season"]
    assert set(seasons) == {
        "spring", "summer", "autumn_before", "autumn_split", "autumn_after", "winter",
    }
    for text in (*seasons.values(), layer["invest_month"]):
        assert not _HANJA_OR_DIGIT.search(text), text
        assert text.endswith("요.") and not any(w in text for w in polish._FORBIDDEN), text
    assert all(t.startswith("계절로만 보면 ") for t in seasons.values())
    # 투자 문장은 확정하지 않고 감당 범위를 말한다(절대원칙 8).
    assert "오르는 경우가 많다고 보는" in layer["invest_month"]
    assert "감당할 수 있는 만큼만" in layer["invest_month"]


def test_board_season_key_by_month_and_chuseok() -> None:
    assert board_season_key("卯", dt.date(2027, 3, 20)) == "spring"
    assert board_season_key("午", dt.date(2027, 6, 20)) == "summer"
    assert board_season_key("亥", dt.date(2026, 11, 20)) == "winter"
    # 2026 추석은 9/25(酉월) — 申월은 추석 전, 酉월은 추석이 든 달, 戌월은 추석 뒤.
    assert board_season_key("申", dt.date(2026, 8, 20)) == "autumn_before"
    assert board_season_key("酉", dt.date(2026, 9, 10)) == "autumn_split"
    assert board_season_key("酉", dt.date(2026, 9, 30)) == "autumn_split"  # 달 단위로 고정
    assert board_season_key("戌", dt.date(2026, 10, 20)) == "autumn_after"
    assert autumn_phase("2025-09") == "split" and autumn_phase("2025-10") == "after"
    assert board_season_key("", dt.date(2026, 11, 20)) is None


def test_month_panel_gets_season_note_from_the_boundary() -> None:
    old, new = _board(_BEFORE), _board(_FROM)
    winter = _layer(_FROM)["birth_season"]["winter"]
    assert new.content_version.split("|")[1] == "dict.v1.23"
    assert old.content_version.split("|")[1] == "dict.v1.22"
    assert new.month_flow and all(f.common.endswith(winter) for f in new.month_flow)
    assert old.month_flow and not any("계절로만 보면" in f.common for f in old.month_flow)
    # 반례: 己亥월(천간 己)에는 투자 문장이 붙지 않는다.
    assert not any("시세가 오르는" in f.common for f in new.month_flow)
    # 판정은 그대로다 — 같은 날짜를 이전 사전으로 계산한 보드와 순위·사건이 같다.
    prev = compute_board_v2(M.build_day_context(_FROM), M.load_daily_dicts_for(_BEFORE))
    assert new.model_dump(exclude={"month_flow", "content_version"}) == prev.model_dump(
        exclude={"month_flow", "content_version"},
    )


def test_invest_note_only_in_gui_and_jia_months() -> None:
    invest = _layer(_FROM)["invest_month"]
    # 2027-03-20 = 癸卯월, 2027-04-20 = 甲辰월, 2027-05-20 = 乙巳월.
    for day, expected in (
        (dt.date(2027, 3, 20), True), (dt.date(2027, 4, 20), True), (dt.date(2027, 5, 20), False),
    ):
        ctx = M.build_day_context(day)
        board = compute_board_v2(ctx, M.load_daily_dicts_for(day))
        assert (ctx.month_stem in ("癸", "甲")) is expected
        assert board.month_flow
        assert all(f.common.endswith(invest) for f in board.month_flow) is expected
        assert any(invest in f.common for f in board.month_flow) is expected
