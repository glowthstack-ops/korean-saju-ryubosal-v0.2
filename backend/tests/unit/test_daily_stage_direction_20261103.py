"""docs/17 §25 — 오늘의 운세 12운성 방향 교정 (2026-11-03 데굴님 "전체 로직 점검" → "그래 진행해").

종전에는 '오늘(월운) 천간이 내 일지에서 갖는 12운성'을 썼다. 통설·만세력 엔진(luck_cycles)·
간지달력 일운 오버레이는 모두 '일간이 운 지지에서 갖는 12운성'이라 같은 서비스 안에서도
11/3 己 일간이 간지달력에선 巳 제왕, 오늘의 운세에선 己巳 死 로 갈렸다. 날짜 경계
(STAGE_DIRECTION_EFFECTIVE_FROM, 11/5)로 방향을 고르고 과거 날짜는 그날 계약으로 재생된다.
"""

from __future__ import annotations

import datetime as dt

from saju_engines import daily_ilju_fortune as M
from saju_engines import daily_month_layer as L
from saju_engines.daily_fortune_v2 import (
    compute_board_v2,
    content_version_v2_for,
    day_channels,
)
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    STAGE_DIRECTION_EFFECTIVE_FROM,
    active_dict_version,
    stage_direction_forward,
)
from saju_shared_types.daily_fortune_v2 import (
    MODEL_V2_VERSION,
    MODEL_V2_VERSION_BEFORE_STAGE_DIRECTION,
    active_model_v2_version,
)
from saju_shared_types.enums import Branch, Stem

_FROM = STAGE_DIRECTION_EFFECTIVE_FROM  # 2026-11-05 일진 癸未
_BEFORE = _FROM - dt.timedelta(days=1)  # 2026-11-04 일진 壬午
_GIHAE = dt.date(2026, 11, 8)  # 일진 丙戌, 월운 己亥


def _board(d: dt.date):
    return compute_board_v2(M.build_day_context(d), M.load_daily_dicts_for(d))


def test_boundary_selects_direction_dict_and_model() -> None:
    assert not stage_direction_forward(_BEFORE) and stage_direction_forward(_FROM)
    assert active_dict_version(_BEFORE) == "dict.v1.17"
    assert active_dict_version(_FROM) == "dict.v1.18"  # 11/10 부터는 v1.19(단식 결 층 §26)
    assert DICT_VERSION == "dict.v1.21"  # 11/12 부터(단식 연 지평 확장 §31)
    assert active_model_v2_version(_BEFORE) == MODEL_V2_VERSION_BEFORE_STAGE_DIRECTION
    assert MODEL_V2_VERSION_BEFORE_STAGE_DIRECTION == "model.v2.2"
    # 11/5~11/13 은 model.v2.3, 11/14 부터 v2.4(백호 일주 기준 — docs/17 §32).
    assert active_model_v2_version(_FROM) == "model.v2.3"
    assert MODEL_V2_VERSION == "model.v2.4"
    assert content_version_v2_for(_BEFORE) != content_version_v2_for(_FROM)  # 캐시 namespace 분리


def test_day_channels_use_day_master_on_day_branch_from_boundary() -> None:
    """11/8 丙戌 — 己 일간은 戌 에서 養(재생 .5·구상 .8).

    종전 방향이면 己巳 는 丙→巳 建祿(활동↑ 1.0)이었다.
    """
    ctx = M.build_day_context(_GIHAE)
    for branch in ("巳", "卯", "丑", "亥", "酉", "未"):
        ch = day_channels(Stem("己"), Branch(branch), ctx)
        assert ch["renewal"] == 0.5 and ch["incubation"] == 0.8, branch
        assert ch["activity_up"] == 0.0, branch
    # 같은 날 같은 일간은 일지와 무관하게 같은 12운성 — 일지 차이는 관계·신살·공망 채널이 맡는다.


def test_day_channels_keep_old_direction_before_boundary() -> None:
    """11/4 壬午 — 종전 '오늘 천간→일지': 壬→巳 絶(이탈 1.0), 壬→酉 沐浴(흔들림 1.0)."""
    ctx = M.build_day_context(_BEFORE)
    assert day_channels(Stem("己"), Branch("巳"), ctx)["disengage"] == 1.0
    assert day_channels(Stem("己"), Branch("酉"), ctx)["unsettled"] == 1.0
    # 통설 방향이었다면 己→午 臨官(활동↑ 1.0)이었을 것 — 과거 계약은 그대로다.
    assert day_channels(Stem("己"), Branch("巳"), ctx)["activity_up"] == 0.0


def test_day_tone_follows_the_same_boundary() -> None:
    before = M.day_tone(Stem("己"), Branch("巳"), M.build_day_context(_BEFORE))
    after = M.day_tone(Stem("己"), Branch("巳"), M.build_day_context(_GIHAE))
    assert before.stage == "JEOL"  # 壬→巳
    assert after.stage == "YANG"  # 己→戌


def test_month_common_line_carries_day_master_stage_and_label() -> None:
    board = _board(_GIHAE)
    layer = M.load_daily_dicts_for(_GIHAE).templates["month_layer"]
    gi = next(f for f in board.month_flow or [] if f.day_stem_ko == "기")
    assert layer["stem_stage"]["태"] in gi.common  # 己 → 亥 = 胎 (통설·간지달력과 동일)
    # v1.20(§27): 공통 줄은 군 결 대신 십성 장면(비견·정재) — 내년 연결 문장 없음.
    simple = M.load_daily_dicts_for(_GIHAE).templates["simple_layer"]
    assert simple["god_scene"]["비견"]["사람"] in gi.common
    assert layer["month_tone"]["비겁+재성"] not in gi.common
    assert "내년" not in gi.common
    # 6일주 전부 — 巳亥충·卯亥 반합·未亥(왕지 없는 반합)은 관계 문장, 丑·酉·亥는 자리 문장.
    assert [n.ilju for n in gi.ilju_notes] == ["己巳", "己卯", "己丑", "己亥", "己酉", "己未"]
    notes = {n.ilju: n.note for n in gi.ilju_notes}
    assert notes["己巳"] == layer["ilju_note"]["month_chung"]
    assert notes["己卯"] == notes["己未"] == layer["ilju_note"]["month_samhap"]
    assert notes["己丑"] == simple["ilju_seat"]["비겁"]["비견"]  # 丑 본기 己 = 비견 자리
    assert notes["己亥"] == simple["ilju_seat"]["재성"]["비견"]  # 亥 본기 壬 = 정재 자리
    assert not any("내년" in n for n in notes.values())
    assert board.month_label == "기해월(己亥) 11월 8일~12월 6일"
    assert board.next_month_label is None and gi.next_preview is None


def test_preview_appears_seven_days_before_month_change() -> None:
    board = _board(_FROM)  # 11/5 — 월운 戊戌, 11/8 己亥 전환까지 3일
    gi = next(f for f in board.month_flow or [] if f.day_stem_ko == "기")
    assert board.month_label == "무술월(戊戌) 10월 9일~11월 7일"
    assert board.next_month_label == "기해월(己亥) 11월 8일부터"
    expected = L._stem_common_line(Stem("己"), M.build_day_context(_GIHAE), _layer_of(_FROM))
    assert gi.next_preview == expected
    assert L.next_month_preview_context(M.build_day_context(dt.date(2026, 11, 20))) is None
    assert L.next_month_preview_context(M.build_day_context(dt.date(2026, 11, 30))) is not None


def _layer_of(d: dt.date) -> dict:
    return M.load_daily_dicts_for(d).templates["month_layer"]


def test_month_span_crosses_year_boundary() -> None:
    start, end, nxt = L.month_span(M.build_day_context(dt.date(2027, 1, 20)))
    assert start.year == 2027 and start.month == 1 and end.month == 2 and nxt is not None
    assert L.month_label(M.build_day_context(dt.date(2027, 1, 20))).startswith("신축월(辛丑)")


def test_past_contract_boards_have_no_label_fields() -> None:
    board = _board(_BEFORE)
    assert board.month_label is None and board.next_month_label is None
    assert all(f.next_preview is None for f in board.month_flow or [])
