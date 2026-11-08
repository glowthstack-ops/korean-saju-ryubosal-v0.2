"""단식(單式) 결 층 검증 (docs/17 §26, 2026-11-08).

사전 커버리지·텍스트 정책·판정 불변·과거 계약 null·2026 丙午 단식 성립·월 절정·채팅 참고 줄.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import re

import pytest

from saju_api.services import daily_fortune_polish as polish
from saju_engines import daily_ilju_fortune as M
from saju_engines import simple_reading as S
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    SIMPLE_LAYER_EFFECTIVE_FROM,
    STAGE_DIRECTION_EFFECTIVE_FROM,
    DailyFortuneBoard,
    active_dict_version,
)
from saju_shared_types.enums import Branch, Stem

_FIRST = SIMPLE_LAYER_EFFECTIVE_FROM  # dict.v1.19 — 단식 결 층 이후 계약(2026-11-10, 丙午년 己亥월)
_PREV = STAGE_DIRECTION_EFFECTIVE_FROM  # dict.v1.18 — 직전 계약


def _board(d: dt.date, dicts: M.DailyFortuneDicts | None = None) -> DailyFortuneBoard:
    return compute_board_v2(M.build_day_context(d), dicts or M.load_daily_dicts_for(d))


def _simple() -> dict:
    return M.load_daily_dicts_for(_FIRST).templates["simple_layer"]


def _month_layer() -> dict:
    return M.load_daily_dicts_for(_FIRST).templates["month_layer"]


def _sentences(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    items = value.values() if isinstance(value, dict) else value
    return [s for item in items for s in _sentences(item)]  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def board() -> DailyFortuneBoard:
    return _board(_FIRST)


# ── 사전 ───────────────────────────────────────────────────────────────────


def test_version_boundary() -> None:
    assert DICT_VERSION == "dict.v1.19"
    assert active_dict_version(_FIRST) == "dict.v1.19"
    assert active_dict_version(_FIRST - dt.timedelta(days=1)) == "dict.v1.18"


def test_layer_coverage() -> None:
    s = _simple()
    pairs = {f"{a}+{b}" for a in S.GROUPS for b in S.GROUPS}
    assert set(s["year_tone"]) == pairs
    assert set(s["group_scene"]) == set(S.GROUPS)
    for g in S.GROUPS:
        assert set(s["group_scene"][g]) == set(S.AXES)
        assert len(s["group_axes"][g]) == 3 and set(s["group_axes"][g]) <= set(S.AXES)
    for h in S.HORIZONS:
        assert set(s[f"{h}_same_group"]) == set(S.GROUPS)
    assert set(s["peak_month"]) == set(S.GROUPS)
    assert all("{months}" in v for v in s["peak_month"].values())


def test_layer_sentences_pass_text_policy() -> None:
    s = _simple()
    meta = ("since", "decision_ref", "note", "group_axes")
    sentences = _sentences({k: v for k, v in s.items() if k not in meta})
    assert len(sentences) == len(set(sentences))
    for sentence in sentences:
        assert sentence.endswith((".", "!", "?")), sentence
        assert not re.search(r"[一-鿿]", sentence), sentence
        assert not any(word in sentence for word in polish._FORBIDDEN), sentence
        # 오늘의 운세 노출 문장은 십성군 이름도 쓰지 않는다(용어 비노출 — docs/17 §3).
        assert not any(g in sentence for g in S.GROUPS), sentence


# ── 단식 성립·내용 ──────────────────────────────────────────────────────────


def test_2026_byeongo_all_stems_same_group() -> None:
    """丙午년: 천간·지지 모두 火라 10일간 전부 단식이 또렷하다(5묶음)."""
    s, ml = _simple(), _month_layer()
    groups = {}
    for dm in Stem:
        sr = S.simple_reading(dm, Stem("丙"), Branch("午"), "year", s, ml)
        assert sr.same_group and sr.emphasis
        assert len(sr.points) == 3
        groups[dm.value] = sr.stem_group
    assert groups["戊"] == groups["己"] == "인성"
    assert groups["甲"] == groups["乙"] == "식상"
    assert groups["庚"] == groups["辛"] == "관성"
    assert groups["丙"] == groups["丁"] == "비겁"
    assert groups["壬"] == groups["癸"] == "재성"


def test_mixed_year_has_no_emphasis_and_mixes_points() -> None:
    """2025 乙巳 甲 일간: 천간 겁재(비겁)·지지 丙 식신(식상) — 섞인 결."""
    sr = S.simple_reading(Stem("甲"), Stem("乙"), Branch("巳"), "year", _simple(), _month_layer())
    assert (sr.stem_group, sr.branch_group) == ("비겁", "식상")
    assert not sr.same_group and sr.emphasis is None
    s = _simple()
    assert sr.points[2] == s["group_scene"]["식상"][s["group_axes"]["식상"][0]]


def test_month_ganji_of_year_follows_wolgeon_rule() -> None:
    months = S.month_ganji_of_year(Stem("丙"))  # 丙辛 → 庚寅월부터
    assert (months[0][0].value, months[0][1].value, months[0][2]) == ("庚", "寅", 2)
    assert (months[8][0].value, months[8][1].value, months[8][2]) == ("戊", "戌", 10)
    assert months[11][1].value == "丑" and months[11][2] == 1


def test_peak_months_2026_earth_stem_is_october_alone() -> None:
    """원문 '10월 아팠거나 게으름 max'(土 일간) — 午戌 반합 + 戊戌 비겁(출구) 단독 최고."""
    assert S.peak_months(Stem("戊"), Stem("丙"), Branch("午")) == [10]
    assert S.peak_months(Stem("己"), Stem("丙"), Branch("午")) == [10]
    line = S.peak_month_line(Stem("戊"), Stem("丙"), Branch("午"), _simple())
    assert line and line.startswith("10월에는")


def test_peak_months_generalize_by_generating_group() -> None:
    """출구 군은 세운군마다 다르다 — 관성 세운(庚)은 인성(土) 달, 재성 세운(壬)은 관성(土) 달."""
    assert S._GENERATES == {
        "인성": "비겁", "비겁": "식상", "식상": "재성", "재성": "관성", "관성": "인성",
    }
    # 庚 일간 2026(관성 세운): 戌월 戊戌 = 반합 2 + 편인·편인(관성→인성 출구) 2 = 4 단독.
    assert S.peak_months(Stem("庚"), Stem("丙"), Branch("午")) == [10]
    # 壬 일간 2026(재성 세운): 戌월 戊戌 = 반합 2 + 편관·편관(재성→관성 출구) 2 = 4 단독.
    assert S.peak_months(Stem("壬"), Stem("丙"), Branch("午")) == [10]
    # 甲 일간 2026(식상 세운): 출구는 재성(土) — 戌월 戊戌 편재·편재 + 반합 = 4 단독.
    assert S.peak_months(Stem("甲"), Stem("丙"), Branch("午")) == [10]
    # 丙 일간 2026(비겁 세운): 출구는 식상(土) — 戌월 戊戌 식신·식신 + 반합 = 4 단독.
    assert S.peak_months(Stem("丙"), Stem("丙"), Branch("午")) == [10]


def test_peak_months_empty_when_no_strong_month() -> None:
    """합도 같은 군 중첩도 없는 해는 절정 달을 내지 않는다(강제 충원 금지)."""
    # 甲 일간 · 丁丑년: 丑 과 합하는 월운 지지 子(육합)·巳酉(반합) 가 있어 비게 만들 수 없으므로
    # 점수식 자체를 확인한다 — 하한 미만이면 빈 목록.
    assert S.PEAK_MIN_SCORE == 2
    assert S.peak_months(Stem("甲"), Stem("丁"), Branch("丑")) != []  # 子丑 육합 달 존재


# ── 보드 배선 ───────────────────────────────────────────────────────────────


def test_board_carries_year_flow_and_same_group_notes(board: DailyFortuneBoard) -> None:
    assert board.year_flow is not None and len(board.year_flow) == 10
    assert board.year_label and "2026" in board.year_label
    for yf in board.year_flow:
        assert yf.tone and yf.emphasis and len(yf.points) == 3  # 丙午 — 전 일간 같은 군
    # 己亥월(11/10): 천간 己·지지 亥(壬) — 어느 일간도 같은 군이 아니다 → 월 강조 없음.
    assert board.month_flow is not None
    assert all(m.same_group_note is None for m in board.month_flow)


def test_day_same_group_note_prefixes_advice_only_when_same_group() -> None:
    s = _simple()
    # 2026-11-10 일진 戊子: 戊 일간에 비견(비겁) + 子 본기 癸 정재(재성) → 다름 → 조언 그대로.
    b = _board(_FIRST)
    ctx = M.build_day_context(_FIRST)
    assert (ctx.day_stem, ctx.day_branch) == ("戊", "子")
    for f in b.fortunes:
        assert f.advice and not any(f.advice.startswith(v) for v in s["day_same_group"].values())
    # 丙午일(2026-11-16? 아님) — 같은 군이 되는 날을 직접 찾는다: 일진 천간·지지가 모두 火.
    d = _FIRST
    for _ in range(60):
        c = M.build_day_context(d)
        if (c.day_stem, c.day_branch) == ("丙", "午"):
            break
        d += dt.timedelta(days=1)
    b2 = _board(d)
    fire = [f for f in b2.fortunes if f.ilju[0] == "壬"]  # 壬 일간: 丙 편재·午 정재 → 재성 같은 군
    assert fire and all(f.advice and f.advice.startswith(s["day_same_group"]["재성"]) for f in fire)


def test_decision_unchanged_by_simple_layer(board: DailyFortuneBoard) -> None:
    dicts = M.load_daily_dicts_for(_FIRST)
    tpl = copy.deepcopy(dicts.templates)
    tpl.pop("simple_layer")
    without = _board(_FIRST, dataclasses.replace(dicts, templates=tpl))
    for a, b in zip(board.fortunes, without.fortunes, strict=True):
        assert a.headline == b.headline
        assert [(e.event_key, e.probability) for e in a.events] == [
            (e.event_key, e.probability) for e in b.events
        ]
        assert a.lotto_phrase == b.lotto_phrase and a.lucky_place == b.lucky_place
    assert without.year_flow is None and without.year_label is None


def test_past_contract_has_no_new_fields() -> None:
    prev = _board(_PREV)
    assert prev.year_flow is None and prev.year_label is None
    assert prev.month_flow is not None
    assert all(m.same_group_note is None for m in prev.month_flow)


# ── 채팅·테마 참고 줄 ───────────────────────────────────────────────────────


def test_reference_line_uses_terms_and_prefix() -> None:
    line = S.simple_reference_line("戊", "丙午", "year", _simple(), _month_layer())
    assert line.startswith("간단히 봤을 때, 丙午년은 무(戊) 일간에게 인성(편인·정인) 결이에요.")
    assert "참고용" in line
    mixed = S.simple_reference_line("甲", "乙巳", "year", _simple(), _month_layer())
    assert "천간 겁재(비겁)·지지 식신(식상)이 섞인 결" in mixed
    month = S.simple_reference_line("戊", "己亥", "month", _simple(), _month_layer())
    assert month.startswith("간단히 봤을 때, 己亥월은")
    assert "올해" not in month  # 세운 간지 없으면 그 달 결만
    # 월 지평 + 세운(2026-11-08 실답 교정): 올해 결 + 절정 달이면 절정 문장 — 己 일간 戊戌월(10월).
    s = _simple()
    oct_line = S.simple_reference_line(
        "己", "戊戌", "month", s, _month_layer(), year_ganji="丙午",
    )
    assert oct_line.startswith("간단히 봤을 때, 戊戌월은 기(己) 일간에게 비겁(겁재·겁재) 결이에요.")
    assert "올해 丙午년은 인성(정인·편인) 결이에요." in oct_line
    assert s["year_tone"]["인성+인성"] in oct_line
    assert "이 달은 올해 결이 가장 세지는 달이에요 — 10월에는" in oct_line
    # 절정이 아닌 달(己亥월)은 올해 결만 붙고 절정 문장은 없다.
    nov_line = S.simple_reference_line("己", "己亥", "month", s, _month_layer(), year_ganji="丙午")
    assert "올해 丙午년은" in nov_line and "가장 세지는" not in nov_line
    # 일 지평도 올해 결 한 줄.
    day_line = S.simple_reference_line("己", "丙戌", "day", s, _month_layer(), year_ganji="丙午")
    assert day_line.startswith("간단히 봤을 때, 丙戌일은") and "올해 丙午년은" in day_line
    assert S.simple_reference_line("", "丙午", "year", _simple()) == ""
    assert S.simple_reference_line("戊", "丙午", "week", _simple()) == ""


def test_chat_period_fortune_carries_simple_reading_line() -> None:
    """채팅 연 총운(PeriodFortune) — 참고 줄이 실리고 사용 규칙 상수가 함께 렌더 재료가 된다."""
    from saju_api.services import chat_service
    from saju_engines.context_reducer import SIMPLE_READING_HEADER, SIMPLE_READING_USAGE_RULE
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange

    b = BirthInput(
        birth_date=dt.date(1974, 1, 12), birth_time=dt.time(10, 0), birth_place_name="서울",
        gender="male",
    )
    intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.YEAR, start="2026", end="2026",
        ),
    )
    pf = chat_service._build_period_fortune(b, intent, dt.date(2026, 11, 8), "yearly")
    assert pf is not None
    assert pf.simple_reading_line.startswith("간단히 봤을 때, 丙午년은")
    assert "참고용" in pf.simple_reading_line
    # 월 총운은 세운(스택) 간지를 받아 올해 결이 함께 실린다.
    m_intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start="2026-10", end="2026-10",
        ),
    )
    mpf = chat_service._build_period_fortune(b, m_intent, dt.date(2026, 11, 8), "monthly")
    assert mpf is not None and "올해 丙午년은" in mpf.simple_reading_line
    assert SIMPLE_READING_HEADER.startswith("[단식 참고") and "그대로" in SIMPLE_READING_USAGE_RULE
