"""이번 달 흐름 십성별 단식(docs/17 §27, dict.v1.20, 2026-11-08).

데굴님 "일주가 빠진다" · "내년 얘기 금지" · "단식 자료 미반영" · "비견·겁재를 묶으면 두 달씩 같은
내용 → 십성별 정의".

- 공통 줄: 십성 장면 3 + 12운성 + 행동, 다음 달/내년 연결 없음. 戊戌(겁재)·己亥(비견) 달이 다르다.
- 일주별: 60일주 전부. 관계(충·육합·삼합·반합, 왕지 없는 반합 포함) 문장 또는 자리 문장. 내년 세운
  지지 무관.
- 채팅 참고 줄 '이 달만 따로 보면' 도 십성 장면.
"""

from __future__ import annotations

import datetime as dt

from saju_engines import daily_ilju_fortune as M
from saju_engines import daily_month_layer as L
from saju_engines import simple_reading as S
from saju_shared_types.enums import Branch, Stem

_GIHAE = dt.date(2026, 11, 8)  # 월운 己亥 (亥·子·丑 연말 구간 — 종전엔 내년 未 관계·내년 연결 문장)
_MUSUL = dt.date(2026, 10, 20)  # 월운 戊戌


def _dicts(d: dt.date):
    tpl = M.load_daily_dicts_for(d).templates
    return tpl["month_layer"], tpl["simple_layer"]


def test_every_ilju_has_a_line_and_no_next_year_talk() -> None:
    layer, simple = _dicts(_GIHAE)
    ctx = M.build_day_context(_GIHAE)
    flows = L.month_flow(ctx, layer, None, simple)
    assert len(flows) == 10
    for flow in flows:
        assert len(flow.ilju_notes) == 6
        assert len({n.note for n in flow.ilju_notes}) >= 3  # 같은 일간 안에서 문장이 갈린다
        assert "내년" not in flow.common and "다음 달" not in flow.common
        assert not any("내년" in n.note for n in flow.ilju_notes)
        assert not any(v in flow.common for v in layer["next_year"].values())
        assert not any(v in flow.common for v in layer["next_month"].values())
    assert sum(len(f.ilju_notes) for f in flows) == 60


def test_relation_beats_seat_and_weak_half_counts() -> None:
    layer, simple = _dicts(_GIHAE)
    ctx = M.build_day_context(_GIHAE)
    note = L._ilju_note
    gi = Stem("己")
    assert note(Branch("巳"), ctx, layer, gi, simple) == layer["ilju_note"]["month_chung"]
    assert note(Branch("卯"), ctx, layer, gi, simple) == layer["ilju_note"]["month_samhap"]
    # 亥未 = 왕지 없는 반합도 삼합 문장.
    assert note(Branch("未"), ctx, layer, gi, simple) == layer["ilju_note"]["month_samhap"]
    assert note(Branch("寅"), ctx, layer, Stem("甲"), simple) == layer["ilju_note"]["month_yukhap"]
    # 관계 없음 → 자리 문장(일지 십성군 × 월운 천간 십성). 丑未충은 내년 지지라 더는 보지 않는다.
    assert note(Branch("丑"), ctx, layer, gi, simple) == simple["ilju_seat"]["비겁"]["비견"]
    assert note(Branch("申"), ctx, layer, Stem("甲"), simple) == simple["ilju_seat"]["관성"]["정재"]
    # 과거 계약(simple 없음)은 종전 그대로 — 내년 관계·빈 문자열.
    assert note(Branch("丑"), ctx, layer) == layer["ilju_note"]["year_chung"]
    assert note(Branch("子"), ctx, layer) == ""


def test_consecutive_bigeop_months_differ_by_ten_god() -> None:
    """己 일간: 戊戌(겁재)·己亥(비견)이 같은 '비겁' 군이라 종전엔 같은 결 — 이제 십성으로 갈린다."""
    layer, simple = _dicts(_GIHAE)
    a = L._stem_common_line(Stem("己"), M.build_day_context(_MUSUL), layer, simple)
    b = L._stem_common_line(Stem("己"), M.build_day_context(_GIHAE), layer, simple)
    assert a != b
    assert simple["god_scene"]["겁재"]["돈"] in a and simple["god_scene"]["비견"]["사람"] in b
    seat_a = L._ilju_note(Branch("酉"), M.build_day_context(_MUSUL), layer, Stem("己"), simple)
    seat_b = L._ilju_note(Branch("酉"), M.build_day_context(_GIHAE), layer, Stem("己"), simple)
    assert seat_a == simple["ilju_seat"]["식상"]["겁재"]
    assert seat_b == simple["ilju_seat"]["식상"]["비견"]


def test_reference_line_uses_ten_god_scene_for_this_month() -> None:
    layer, simple = _dicts(_GIHAE)
    line = S.simple_reference_line("己", "己亥", "month", simple, layer, year_ganji="丙午")
    assert "이 달만 따로 보면 " + simple["god_scene"]["비견"]["사람"][0].lower() in line
    assert layer["month_tone"]["비겁+재성"] not in line
    sr = S.simple_reading(Stem("己"), Stem("己"), Branch("亥"), "month", simple, layer)
    assert sr.points[0] == simple["god_scene"]["비견"]["사람"]
    assert sr.points[2] == simple["god_scene"]["정재"]["돈"]  # 지지 정재, 천간이 안 쓴 첫 축


def test_board_at_boundary_carries_v120_month_flow() -> None:
    from saju_engines.daily_fortune_v2 import compute_board_v2

    board = compute_board_v2(M.build_day_context(_GIHAE), M.load_daily_dicts_for(_GIHAE))
    assert board.month_flow is not None and len(board.month_flow) == 10
    assert all(len(f.ilju_notes) == 6 for f in board.month_flow)
    assert board.content_version.split("|")[1] == "dict.v1.20"
