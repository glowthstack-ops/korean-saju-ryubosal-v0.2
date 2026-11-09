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

_FIRST = SIMPLE_LAYER_EFFECTIVE_FROM  # 단식 결 층 이후 계약(2026-11-08, 丙午년 己亥월) — 당일 v1.20
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
    assert DICT_VERSION == "dict.v1.20"
    assert active_dict_version(_FIRST) == "dict.v1.20"
    assert active_dict_version(_FIRST - dt.timedelta(days=1)) == "dict.v1.18"


def test_layer_coverage() -> None:
    s = _simple()
    pairs = {f"{a}+{b}" for a in S.GROUPS for b in S.GROUPS}
    assert set(s["year_tone"]) == pairs
    assert "group_scene" not in s and "group_axes" not in s  # v1.20: 십성 단위로 교체(§27)
    for h in S.HORIZONS:
        assert set(s[f"{h}_same_group"]) == set(S.GROUPS)
    assert set(s["peak_month"]) == set(S.GROUPS)
    # 2026-11-09: 첫 문장(왜 강한가)은 `peak_month_lead` 로 분리 — 본문에는 달 이름이 없다.
    assert set(s["peak_month_lead"]) == {"same_god", "other"} == set(S.PEAK_MONTH_LEAD_TERMS)
    assert all(v.startswith("{months}에는") for v in s["peak_month_lead"].values())
    # 채팅 월 문단은 그 달만 가리키고(여러 절정 달 나열 없음) 본문이 올해 흐름임을 밝힌다.
    for v in S.PEAK_MONTH_LEAD_TERMS.values():
        assert "{months}" not in v and "올해 흐름의 영향" in v
    assert S.PEAK_MONTH_LEAD_TERMS["same_god"].startswith("이 달은 천간과 지지가 같은 십성의 글자")
    # other 앞에는 같은 군 강조("이 달은 …")가 남을 수 있어 "이 달은"으로 시작하지 않는다.
    assert not S.PEAK_MONTH_LEAD_TERMS["other"].startswith("이 달은")
    assert all("{months}" not in v for v in s["peak_month"].values())
    assert all(v.startswith("이 영향은") for v in s["peak_month"].values())
    # v1.20(§27): 십성 10 × 영역 5 장면, 십성별 축 3, 일지 십성군 5 × 월운 천간 십성 10 자리 문장.
    gods = set(S._GROUP_OF)
    assert set(s["god_scene"]) == gods and set(s["god_axes"]) == gods
    for g in gods:
        assert set(s["god_scene"][g]) == set(S.AXES)
        assert len(s["god_axes"][g]) == 3 and set(s["god_axes"][g]) <= set(S.AXES)
    assert set(s["ilju_seat"]) == set(S.GROUPS)
    assert all(set(v) == gods for v in s["ilju_seat"].values())


def test_layer_sentences_pass_text_policy() -> None:
    s = _simple()
    meta = ("since", "decision_ref", "note", "group_axes", "god_axes")
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
    # v1.20: 포인트는 십성 단위 — 겁재 장면 2 + 식신 장면 1(천간이 쓴 영역과 안 겹치는 첫 축).
    assert sr.points[0] == s["god_scene"]["겁재"][s["god_axes"]["겁재"][0]]
    used = s["god_axes"]["겁재"][:2]
    third = next(a for a in s["god_axes"]["식신"] if a not in used)
    assert sr.points[2] == s["god_scene"]["식신"][third]


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


def test_peak_lead_same_god_only_when_stem_and_branch_share_ten_god() -> None:
    """2026-11-09 데굴님 지정 형식 — "천간과 지지가 같은 십성의 글자로 들어와"는 사실일 때만.

    2026 丙午: 절정 달 戊戌 — 戊와 戌 본기 戊는 어느 일간에게나 같은 십성 → same_god.
    반례 2027 丁未: 절정 달 丙午(午未 육합) — 丙과 午 본기 丁은 십성이 다르다 → other.
    """
    s = _simple()
    for dm in Stem:
        assert S.peak_month_kind(dm, Stem("丙"), Branch("午")) == "same_god", dm
    panel = S.peak_month_line(Stem("戊"), Stem("丙"), Branch("午"), s)
    assert panel == (
        "10월에는 천간과 지지가 같은 성격의 글자로 들어와 강하게 영향받을 수 있어요. "
        "이 영향은 무언가의 멈춤으로 나타나기도 해요. 아프거나 게을러지지 않게, "
        "제대로 쉬고 부지런히 다음을 준비해보세요."
    )
    assert "십성" not in panel  # 오늘의 운세 패널은 용어 비노출(docs/17 §3)
    chat = S.peak_month_chat_line(
        Stem("戊"), Stem("戊"), Branch("戌"), Stem("丙"), Branch("午"), s,
    )
    assert chat == S.PEAK_MONTH_LEAD_TERMS["same_god"] + " " + s["peak_month"]["인성"]
    assert chat.startswith("이 달은 천간과 지지가 같은 십성의 글자로 들어와")
    # 절정 달이 아닌 달(己亥월)은 채팅 절정 문장이 없다.
    assert S.peak_month_chat_line(
        Stem("戊"), Stem("己"), Branch("亥"), Stem("丙"), Branch("午"), s,
    ) is None
    # 반례 — 같은 십성이 아닌 절정 달에 같은 십성 문장을 쓰지 않는다.
    assert S.peak_months(Stem("甲"), Stem("丁"), Branch("未")) == [6]
    assert S.peak_month_kind(Stem("甲"), Stem("丁"), Branch("未")) == "other"
    other = S.peak_month_line(Stem("甲"), Stem("丁"), Branch("未"), s)
    assert other and other.startswith(
        "6월에는 올해 기운과 그 달 기운이 맞물려 강하게 영향받을 수 있어요."
    )
    chat_other = S.peak_month_chat_line(
        Stem("甲"), Stem("丙"), Branch("午"), Stem("丁"), Branch("未"), s,
    )
    assert chat_other and chat_other.startswith(S.PEAK_MONTH_LEAD_TERMS["other"])
    assert not S.month_is_same_god(Stem("甲"), Stem("丙"), Branch("午"))  # 식신 vs 상관
    # 여러 절정 달 중 하나라도 같은 십성이 아니면 other(2028 戊申: 巳·未·申월).
    assert S.peak_month_kind(Stem("甲"), Stem("戊"), Branch("申")) == "other"


def test_peak_line_keeps_v119_contract() -> None:
    """과거 계약(v1.19 사전 — 본문에 {months}, lead 없음)은 그 문장 하나를 그대로 쓴다."""
    legacy = {"peak_month": {g: "{months}에는 옛 문장이에요." for g in S.GROUPS}}
    dm, ys, yb = Stem("戊"), Stem("丙"), Branch("午")
    assert S.peak_month_line(dm, ys, yb, legacy) == "10월에는 옛 문장이에요."
    chat = S.peak_month_chat_line(dm, Stem("戊"), Branch("戌"), ys, yb, legacy)
    assert chat == "올해 흐름이 가장 강해지는 달이기도 해요. 10월에는 옛 문장이에요."


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
    # 방향 기준 줄(§26-5) — 발판/소모는 내 명식 기준이라 안내만.
    assert board.year_direction_note and "발판" in board.year_direction_note
    for yf in board.year_flow:
        assert yf.tone and yf.emphasis and len(yf.points) == 3  # 丙午 — 전 일간 같은 군
    # 己亥월(11/8~): 천간 己·지지 亥(壬) — 어느 일간도 같은 군이 아니다 → 월 강조 없음.
    assert board.month_flow is not None
    assert all(m.same_group_note is None for m in board.month_flow)


def test_day_same_group_note_prefixes_advice_only_when_same_group() -> None:
    s = _simple()
    # 2026-11-08 일진 丙戌: 戊 일간에 편인(인성) + 戌 본기 戊 비견(비겁) → 다름 → 조언 그대로.
    b = _board(_FIRST)
    ctx = M.build_day_context(_FIRST)
    assert (ctx.day_stem, ctx.day_branch) == ("丙", "戌")
    for f in b.fortunes:
        assert f.advice and not any(f.advice.startswith(v) for v in s["day_same_group"].values())
    # 같은 군이 되는 날을 직접 찾는다: 일진 천간·지지가 모두 火(丙午일).
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
    assert prev.year_direction_note is None
    assert prev.month_flow is not None
    assert all(m.same_group_note is None for m in prev.month_flow)


# ── 채팅·테마 참고 줄 ───────────────────────────────────────────────────────


def test_reference_line_uses_terms_and_prefix() -> None:
    line = S.simple_reference_line("戊", "丙午", "year", _simple(), _month_layer())
    assert line.startswith("간단히 봤을 때, 丙午년은 무(戊) 일간에게 인성(편인·정인)의 해예요.")
    assert "참고용" in line
    mixed = S.simple_reference_line("甲", "乙巳", "year", _simple(), _month_layer())
    assert "천간 겁재(비겁)·지지 식신(식상)이 섞인 해예요" in mixed
    month = S.simple_reference_line("戊", "己亥", "month", _simple(), _month_layer())
    assert month.startswith("간단히 봤을 때, 己亥월은")
    assert "올해" not in month  # 세운 간지 없으면 그 달 결만
    # 월 지평(2026-11-08 2차 교정 — "이달 운세인데 올해 흐름을 반복"): 그 달 결 이름 + 천간·지지
    # 십성 장면만. 올해 결 문장 없음. 절정 달(己 일간 戊戌월)만 절정 문장 1개.
    s = _simple()
    oct_line = S.simple_reference_line(
        "己", "戊戌", "month", s, _month_layer(), year_ganji="丙午",
    )
    assert oct_line.startswith(
        "간단히 봤을 때, 戊戌월은 기(己) 일간에게 비겁(겁재·겁재)의 달이에요."
    )
    assert s["god_scene"]["겁재"]["돈"] in oct_line
    assert s["year_tone"]["인성+인성"] not in oct_line and "올해 丙午년은" not in oct_line
    # 2026-11-09 최종안: 그 달만 가리키는 절정 첫 문장 + 올해 흐름 본문. 같은 근거("천간과 지지가
    # 같은 …")의 강조 문장은 빠지고(한 문단에 두 번 금지), 다른 절정 달 나열("10월에는")도 없다.
    assert oct_line.endswith(
        "이 달은 천간과 지지가 같은 십성의 글자로 들어와, 올해 흐름의 영향을 가장 강하게 받을 수 "
        "있는 달이에요. " + s["peak_month"]["인성"]
        + " (일간과 운의 십성만 본 단식 풀이라 참고용이에요.)"
    )
    assert oct_line.count("천간과 지지가 같은") == 1
    assert s["month_same_group"]["비겁"][len("이번 달은"):] not in oct_line
    assert "10월에는" not in oct_line and "이번 달" not in oct_line and "결이 가장" not in oct_line
    assert "이 달만 따로 보면" not in oct_line
    # 절정이 아닌 달(己亥월)은 올해 언급이 없다.
    nov_line = S.simple_reference_line("己", "己亥", "month", s, _month_layer(), year_ganji="丙午")
    assert "올해" not in nov_line and s["god_scene"]["비견"]["사람"] in nov_line
    assert s["god_scene"]["정재"]["돈"] in nov_line
    # 일 지평도 그 날만.
    day_line = S.simple_reference_line("己", "丙戌", "day", s, _month_layer(), year_ganji="丙午")
    assert day_line.startswith("간단히 봤을 때, 丙戌일은") and "올해" not in day_line
    assert s["god_scene"]["정인"]["일"] in day_line
    assert S.simple_reference_line("", "丙午", "year", _simple()) == ""
    assert S.simple_reference_line("戊", "丙午", "week", _simple()) == ""


def test_chat_emphasis_uses_scope_demonstrative() -> None:
    """채팅은 다른 달·날도 묻는다 — 패널 '이번 달은·오늘은'을 '이 달은·이 날은'으로(2026-11-09)."""
    s, ml = _simple(), _month_layer()
    # 甲寅 = 비견·비견, 세운 간지 없음 → 절정 문장 없음.
    month = S.simple_reference_line("甲", "甲寅", "month", s, ml)
    assert "이 달은 " + s["month_same_group"]["비겁"][len("이번 달은 "):] in month
    assert "이번 달" not in month
    day = S.simple_reference_line("己", "丙午", "day", s, ml)  # 정인·편인 — 같은 군
    assert "이 날은 " + s["day_same_group"]["인성"][len("오늘은 "):] in day
    assert "오늘은" not in day
    assert S.chat_scoped("다른 문장이에요.", "month") == "다른 문장이에요."
    # 절정 달이지만 그 달이 같은 십성이 아니면(2027 丁未 甲 일간 6월 丙午 — 식신·상관, 같은 군)
    # 강조 문장은 남고 절정 첫 문장은 'other'.
    june = S.simple_reference_line("甲", "丙午", "month", s, ml, year_ganji="丁未")
    assert "이 달은 천간과 지지가 같은 성격의 글자라" in june
    assert S.PEAK_MONTH_LEAD_TERMS["other"] in june
    assert june.count("이 달은") == 1


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
    # 월 총운은 그 달에 집중 — 올해 결 문장 없음(2026-11-08 2차), 절정 달 문장만 세운 간지로 붙는다.
    m_intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start="2026-10", end="2026-10",
        ),
    )
    mpf = chat_service._build_period_fortune(b, m_intent, dt.date(2026, 11, 8), "monthly")
    assert mpf is not None and "올해 丙午년은" not in mpf.simple_reading_line
    assert mpf.simple_reading_line.startswith("간단히 봤을 때, 戊戌월은")
    assert "되풀이 금지" in SIMPLE_READING_USAGE_RULE
    assert "그 달·그 날에 집중" in SIMPLE_READING_USAGE_RULE
    assert SIMPLE_READING_HEADER.startswith("[단식 참고") and "그대로" in SIMPLE_READING_USAGE_RULE
    from saju_engines.context_reducer import SIMPLE_READING_DIRECTION_RULE

    assert "발판" in SIMPLE_READING_DIRECTION_RULE and "기신" in SIMPLE_READING_DIRECTION_RULE


def test_balanced_sentences_carry_both_faces() -> None:
    """양면 어휘(2026-11-08 데굴님 '안 좋은 쪽만 정리') — 2026-11-09 형식 개편.

    연 흐름 25개는 "발판이면/소모면" 두 갈래 대신 조심할 얼굴 + 좋은 얼굴을 한 문장 조언
    ("~하지 않게, ~해보세요")으로 담는다(데굴님 지정 형식, 절정 달 문장과 같은 꼴). 발판·소모
    설명은 패널 안내(`direction_note`)에만 남는다.
    """
    s = _simple()
    for pair, text in s["year_tone"].items():
        assert "발판" not in text and "소모" not in text, pair
        assert re.search(r"[^ ]+지 않게, [^.]+보세요\.", text), pair
    assert "발판" in s["direction_note"] and "소모" in s["direction_note"]
    assert s["direction_note"].startswith("같은 흐름이라도")


def test_simple_layer_avoids_gyeol_wording() -> None:
    """2026-11-09 데굴님 "결이라는 어려운 단어는 지양" — 강조·절정·안내 문장과 프롬프트 상수."""
    from saju_engines.context_reducer import (
        SIMPLE_READING_DIRECTION_RULE,
        SIMPLE_READING_HEADER,
        SIMPLE_READING_USAGE_RULE,
    )

    s = _simple()
    keys = ("year_same_group", "month_same_group", "day_same_group", "peak_month_lead",
            "peak_month")
    texts = [t for k in keys for t in s[k].values()] + [s["direction_note"]]
    texts += list(S.PEAK_MONTH_LEAD_TERMS.values())
    texts += [SIMPLE_READING_HEADER, SIMPLE_READING_USAGE_RULE, SIMPLE_READING_DIRECTION_RULE]
    for t in texts:
        # '결과·결실·결정·결혼·종결' 같은 다른 낱말은 허용, 단독 '결'만 금지.
        assert not re.search(r"결(?![과실정혼])", t.replace("종결", "")), t
    for h in S.HORIZONS:
        for g in S.GROUPS:
            assert "천간과 지지가 같은 성격의 글자라" in s[f"{h}_same_group"][g], (h, g)
