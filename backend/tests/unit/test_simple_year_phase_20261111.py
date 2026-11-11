"""단식 연 지평 확장 검증 (docs/17 §31, dict.v1.21, 2026-11-11).

외부 '내년 단식' 글(2027 丁未)의 읽는 법 네 가지를 옮긴 층 — 연내 구간(가장 강한 때·전환) /
여러 해 흐름(세운 지지 계절 3년 묶음) / 일주별 올해 한 줄 / 조건 줄(신강약·필요한 기운·지지 충형·
과다). 사전 커버리지·텍스트 정책·규칙 전수·원문 대조·판정 불변·과거 계약 null·채팅·리포트 배선.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import re

import pytest

from saju_api.services import chat_service
from saju_api.services import daily_fortune_polish as polish
from saju_engines import daily_ilju_fortune as M
from saju_engines import simple_reading as S
from saju_engines.context_reducer import SIMPLE_CONDITION_HEADER, SIMPLE_CONDITION_RULE
from saju_engines.daily_fortune_v2 import compute_board_v2
from saju_engines.speech_style import has_haeyo_ending
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.daily_fortune import (
    DICT_VERSION,
    YEAR_PHASE_EFFECTIVE_FROM,
    DailyFortuneBoard,
    active_dict_version,
)
from saju_shared_types.enums import Branch, Element, Stem
from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange

_FROM = YEAR_PHASE_EFFECTIVE_FROM  # 2026-11-12 — 丙午년 己亥월(가장 강한 구간 5~7월은 이미 지남)
_BEFORE = _FROM - dt.timedelta(days=1)
_JEONGMI = (Stem("丁"), Branch("未"))  # 2027 — 원문 단식의 대상 해
_HANJA = re.compile(r"[一-鿿]")
#: 조건 줄에만 허용하는 용어(사용자가 자기 명식과 맞춰 봐야 해서 이름을 그대로 쓴다).
_COND_TERMS = ("용신", "기신")


def _simple() -> dict:
    return M.load_daily_dicts_for(_FROM).templates["simple_layer"]


def _board(d: dt.date, dicts: M.DailyFortuneDicts | None = None) -> DailyFortuneBoard:
    return compute_board_v2(M.build_day_context(d), dicts or M.load_daily_dicts_for(d))


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    items = value.values() if isinstance(value, dict) else value
    return [s for item in items for s in _strings(item)]  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def board() -> DailyFortuneBoard:
    return _board(_FROM)


# ── 사전 ───────────────────────────────────────────────────────────────────


def test_version_boundary() -> None:
    assert DICT_VERSION == "dict.v1.21"
    assert active_dict_version(_FROM) == "dict.v1.21"
    assert active_dict_version(_BEFORE) == "dict.v1.20"


def test_layer_coverage() -> None:
    s = _simple()
    assert "{this}" in s["year_phase_peak"] and "{months}" in s["year_phase_peak"]
    assert len(s["year_phase_turn"]) == 10
    assert all("{month}월부터는" in v for v in s["year_phase_turn"].values())
    assert set(s["season_tone"]) == set(S.GROUPS)
    assert set(s["year_span"]) == {"1", "2", "3"}
    assert set(s["year_ilju"]) == {"chung", "yukhap", "samhap", "hyeong", "same", "none"}
    cond = s["year_cond"]
    assert set(cond["strength"]) == set(S.GROUPS)
    assert all(set(v) == {"weak", "strong"} for v in cond["strength"].values())
    assert set(cond["strength_lead"]) == {"weak", "strong"}
    for key in ("need", "clash", "excess"):
        assert "{this}" in cond[key]


def test_every_turn_pair_the_rule_can_produce_is_in_the_dictionary() -> None:
    """10일간 × 세운 천간 10 전수 — 전환이 있는 해는 사전에 그 쌍의 문장이 있다."""
    pool = _simple()["year_phase_turn"]
    seen: set[str] = set()
    for dm in Stem:
        for ys in Stem:
            phase = S.year_phase(dm, ys)
            if phase is None or phase.turn_group is None:
                continue
            key = f"{phase.year_group}>{phase.turn_group}"
            assert key in pool, (dm.value, ys.value, key)
            seen.add(key)
    assert seen == set(pool)  # 쓰이지 않는 문장도 없다


def test_new_sentences_pass_text_policy() -> None:
    s = _simple()
    keys = ("year_phase_peak", "year_phase_turn", "year_span", "year_ilju")
    plain = _strings({k: s[k] for k in keys})
    for sentence in plain:
        assert sentence.endswith("."), sentence
        assert not _HANJA.search(sentence), sentence
        assert not any(word in sentence for word in polish._FORBIDDEN), sentence
        assert not any(g in sentence for g in S.GROUPS), sentence
    for phrase in s["season_tone"].values():  # 관형구 — 종결어미 없이 '흐름' 앞에 끼운다
        assert not phrase.endswith(".") and not _HANJA.search(phrase)
        assert not any(g in phrase for g in S.GROUPS)
    # 조건 줄: 용신·희신·기신·구신·신약·신강만 예외로 쓰고 나머지 정책은 같다.
    cond = s["year_cond"]
    for sentence in _strings(cond):
        assert not _HANJA.search(sentence), sentence
        assert not any(g in sentence for g in S.GROUPS), sentence
        banned = [w for w in polish._FORBIDDEN if w not in _COND_TERMS and w in sentence]
        assert not banned, (sentence, banned)
    for key in ("need", "clash", "excess"):
        assert cond[key].endswith(".")
    assert all(v.endswith(".") for pair in cond["strength"].values() for v in pair.values())


# ── 연내 구간 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("year_stem", "peak", "turn"),
    [
        ("甲", (2, 3, 4), 5), ("乙", (2, 3, 4), 5),
        ("丙", (5, 6, 7), 8), ("丁", (5, 6, 7), 8),
        ("庚", (8, 9, 10), 11), ("辛", (8, 9, 10), 11),
        ("壬", (11, 12, 1), None), ("癸", (11, 12, 1), None),
    ],
)
def test_peak_is_the_season_of_the_year_stem_element(
    year_stem: str, peak: tuple[int, ...], turn: int | None
) -> None:
    phase = S.year_phase(Stem("甲"), Stem(year_stem))
    assert phase is not None
    assert phase.peak_months == peak and phase.turn_month == turn
    assert (phase.turn_group is None) == (turn is None)


def test_earth_years_have_no_phase() -> None:
    """戊·己년은 같은 계절이 없다 — 규칙 미정(보류)이라 구간 문장을 내지 않는다."""
    s = _simple()
    for ys in ("戊", "己"):
        assert S.year_phase(Stem("甲"), Stem(ys)) is None
        assert S.year_phase_lines(Stem("甲"), Stem(ys), s) == []
        assert not S.phase_peak_passed(Stem(ys), Branch("子"))


def test_2027_turn_groups_match_the_source_reading() -> None:
    """원문(2027 丁未): 목 = 하반기 관운 / 토 = 수확 / 금 = 고비 뒤 풀림 / 수 = 하반기 차분."""
    expected = {"甲": "관성", "丙": "재성", "戊": "식상", "辛": "비겁", "壬": "인성"}
    for dm, group in expected.items():
        phase = S.year_phase(Stem(dm), _JEONGMI[0])
        assert phase is not None and phase.turn_group == group and phase.turn_month == 8
    lines = S.year_phase_lines(Stem("甲"), _JEONGMI[0], _simple())
    assert lines[0] == "올해 흐름이 가장 강한 때는 5~7월이에요."
    assert lines[1].startswith("8월부터는 벌여 둔 일이 평가받는 흐름이에요.")


def test_water_year_label_and_no_turn() -> None:
    lines = S.year_phase_lines(Stem("甲"), Stem("壬"), _simple())
    assert lines == ["올해 흐름이 가장 강한 때는 11월~다음 해 1월이에요."]


def test_peak_passed_uses_the_month_branch_not_the_calendar_month() -> None:
    assert not S.phase_peak_passed(Stem("丙"), Branch("寅"))
    assert not S.phase_peak_passed(Stem("丙"), Branch("未"))  # 구간 마지막 달은 아직 안 지남
    assert S.phase_peak_passed(Stem("丙"), Branch("申"))
    assert S.phase_peak_passed(Stem("丙"), Branch("丑"))  # 다음 해 1월도 같은 세운의 끝
    assert not S.phase_peak_passed(Stem("壬"), Branch("丑"))  # 겨울이 절정인 해
    lines = S.year_phase_lines(Stem("戊"), Stem("丙"), _simple(), peak_passed=True)
    assert lines[0] == "올해 흐름이 가장 강한 때는 5~7월이었어요."
    assert "흐름이에요" in lines[1]  # 전환 문장은 시제에 매이지 않는다


def test_passed_on_only_inside_the_same_sewoon() -> None:
    byeongo = (Stem("丙"), Branch("午"))
    assert S.year_phase_passed_on(dt.date(2026, 11, 11), 2026, *byeongo)
    assert not S.year_phase_passed_on(dt.date(2026, 6, 20), 2026, *byeongo)
    # 2026-08-07 은 아직 未월(입추 전) — 양력 8월이라고 지난 것으로 세지 않는다.
    assert not S.year_phase_passed_on(dt.date(2026, 8, 6), 2026, *byeongo)
    assert not S.year_phase_passed_on(dt.date(2026, 11, 11), 2027, *_JEONGMI)  # 내년 질문
    assert S.year_phase_passed_on(dt.date(2027, 1, 20), 2026, *byeongo)  # 입춘 전 1월


# ── 여러 해 흐름 ─────────────────────────────────────────────────────────────


def test_season_run_position_and_start_year() -> None:
    assert S.year_branch_of(2027) == Branch("未") and S.year_branch_of(1984) == Branch("子")
    run = S.season_run(Stem("戊"), 2027)
    assert (run.start_year, run.position, run.element, run.group) == (2025, 3, Element.FIRE, "인성")
    assert S.season_run(Stem("戊"), 2022).position == 1  # 壬寅 = 봄 3년의 첫 해
    assert S.season_run(Stem("戊"), 2028).element == Element.METAL
    far = S.season_run(Stem("戊"), 1962)  # 60년 전 壬寅 — 먼 과거도 같은 식으로 구한다
    assert (far.start_year, far.position, far.group) == (1962, 1, "관성")


def test_season_history_goes_back_as_far_as_asked() -> None:
    """원문 "토 일간은 임인년부터" — 2027 에서 거슬러 올라가면 2022 壬寅 이 관성 묶음의 첫 해다."""
    hist = S.season_history(Stem("戊"), 2027, spans=5)
    assert [(r.start_year, r.group) for r in hist] == [
        (2025, "인성"), (2022, "관성"), (2019, "재성"), (2016, "식상"), (2013, "인성"),
    ]
    assert hist[0].position == 3 and all(r.position == 3 for r in hist[1:])
    metal = S.season_history(Stem("辛"), 2027, spans=2)
    assert [(r.start_year, r.group) for r in metal] == [(2025, "관성"), (2022, "재성")]
    assert len(S.season_history(Stem("甲"), 2027, spans=12)) == 12  # 36년 전까지


def test_span_line_templates_by_position() -> None:
    s = _simple()
    first = S.year_span_line(Stem("戊"), 2025, s)
    assert first == (
        "2022년부터 3년은 책임과 압박이 따르는 흐름이었고, "
        "올해부터 3년은 쉬고 배우며 채우는 흐름이에요."
    )
    second = S.year_span_line(Stem("戊"), 2026, s)
    assert second.endswith("올해는 2025년부터 이어진 쉬고 배우며 채우는 흐름의 두 번째 해예요.")
    last = S.year_span_line(Stem("戊"), 2027, s)
    assert "흐름의 마지막 해예요." in last
    assert last.endswith("2028년부터는 일을 벌이고 표현하는 흐름이에요.")
    assert "{" not in first + second + last
    # 연도와 간지가 어긋나면 싣지 않는다(다른 출처에서 온 호출 방어).
    assert S.year_span_line(Stem("戊"), 2027, s, year_branch=Branch("午")) == ""
    assert S.year_span_line(Stem("戊"), 2027, s, year_branch=Branch("未")) == last


# ── 일주별 올해 한 줄 ─────────────────────────────────────────────────────────


def test_year_ilju_kind_for_mi_and_o_years() -> None:
    mi = {b.value: S.year_ilju_kind(b, Branch("未")) for b in Branch}
    assert mi["丑"] == "chung" and mi["戌"] == "hyeong"  # 원문이 짚은 두 글자
    assert mi["午"] == "yukhap" and mi["亥"] == mi["卯"] == "samhap" and mi["未"] == "same"
    assert [k for k, v in mi.items() if v == "none"] == ["子", "寅", "辰", "巳", "申", "酉"]
    o = {b.value: S.year_ilju_kind(b, Branch("午")) for b in Branch}
    assert o["子"] == "chung" and o["未"] == "yukhap" and o["寅"] == o["戌"] == "samhap"
    assert o["午"] == "hyeong"  # 자형
    assert S.year_ilju_kind(Branch("申"), Branch("巳")) == "yukhap"  # 형합은 합을 먼저


def test_year_clash_branches() -> None:
    assert [b.value for b in S.year_clash_branches(Branch("未"))] == ["丑", "戌"]
    assert [b.value for b in S.year_clash_branches(Branch("午"))] == ["子", "午"]
    assert [b.value for b in S.year_clash_branches(Branch("卯"))] == ["子", "酉"]


# ── 조건 줄 ─────────────────────────────────────────────────────────────────


def test_panel_condition_lines_state_conditions_without_judging() -> None:
    lines = S.year_condition_lines(Stem("辛"), *_JEONGMI, _simple())
    assert len(lines) == 4
    assert lines[0].startswith("신약한 명식이면 책임과 압박이") and "신강한 명식이면" in lines[0]
    assert lines[1].startswith("올해 들어오는 화(불)·토(흙) 기운이 용신·희신인 명식이면")
    assert lines[2].startswith("사주 지지에 축(丑)·술(戌) 글자가 있으면")
    assert lines[3].startswith("화(불)·토(흙) 기운이 이미 많은 명식이면 올해")
    # 전부 조건절('~이면'·'~있으면') — 일주 버킷은 판정하지 않는다.
    assert all(re.search(r"(이면|있으면) ", ln) for ln in lines)
    byeongo = S.year_condition_lines(Stem("辛"), Stem("丙"), Branch("午"), _simple())
    assert "화(불) 기운이 용신" in byeongo[1] and "자(子)·오(午)" in byeongo[2]


def test_condition_hits_only_carry_confirmed_conditions() -> None:
    s = _simple()
    weak = S.year_condition_hits(Stem("辛"), *_JEONGMI, s, band="신약")
    assert weak == ["이 명식은 신약이라 책임과 압박이 버겁게 느껴져 고비가 될 수 있어요."]
    strong = S.year_condition_hits(Stem("辛"), *_JEONGMI, s, band="태신강")
    assert strong == ["이 명식은 태신강이라 책임이 자리와 인정으로 이어지기 좋아요."]
    # 반례: 중화 3단계·미상은 신강약 항목 없음.
    for band in ("중화", "중화신약", "중화신강", ""):
        assert S.year_condition_hits(Stem("辛"), *_JEONGMI, s, band=band) == []
    # 과다: 그 해에 들어오는 오행(화·토)이 엔진 과다 오행일 때만.
    excess = S.year_condition_hits(Stem("辛"), *_JEONGMI, s, excessive_elements=["土"])
    assert len(excess) == 1 and excess[0].startswith("이 명식은 토(흙) 기운이 이미 많아, 이 해")
    assert S.year_condition_hits(Stem("辛"), *_JEONGMI, s, excessive_elements=["木", "水"]) == []
    both = S.year_condition_hits(
        Stem("辛"), *_JEONGMI, s, band="신약", excessive_elements=["火", "土"],
    )
    assert len(both) == 2 and "화(불)·토(흙)" in both[1]


def test_condition_hit_is_dropped_when_it_contradicts_the_role() -> None:
    """강약과 용신이 반대로 가는 명식(종격 등) — 방향은 운 줄 역할 표기가 정하므로 싣지 않는다."""
    s = _simple()
    burden_but_favorable = S.year_condition_hits(
        Stem("辛"), *_JEONGMI, s, band="신약", roles={"火": "용신"},
    )
    assert burden_but_favorable == []
    help_but_adverse = S.year_condition_hits(
        Stem("戊"), *_JEONGMI, s, band="신약", roles={"火": "기신"},  # 인성 해 + 신약 = 도움 문장
    )
    assert help_but_adverse == []
    consistent = S.year_condition_hits(
        Stem("辛"), *_JEONGMI, s, band="신약", roles={"火": "기신", "土": "희신"},
    )
    assert len(consistent) == 1
    neutral = S.year_condition_hits(Stem("辛"), *_JEONGMI, s, band="신약", roles={"火": "한신"})
    assert len(neutral) == 1


# ── 오늘의 운세 보드 ─────────────────────────────────────────────────────────


def test_board_carries_the_four_new_blocks(board: DailyFortuneBoard) -> None:
    assert board.content_version.split("|")[1] == "dict.v1.21"
    assert board.year_flow is not None and len(board.year_flow) == 10
    for flow in board.year_flow:
        assert flow.phase is not None and len(flow.phase) == 2
        assert flow.phase[0] == "올해 흐름이 가장 강한 때는 5~7월이었어요."  # 11/12 는 亥월
        assert flow.span is not None and "두 번째 해예요" in flow.span  # 2026 = 여름 3년의 둘째 해
        assert len(flow.ilju_notes) == 6 and len({n.ilju for n in flow.ilju_notes}) == 6
        assert len(flow.conditions) == 4
        assert flow.peak_months is None
    earth = next(f for f in board.year_flow if f.day_stem_ko == "무")
    assert earth.span is not None and earth.span.startswith("2022년부터 3년은 책임과 압박이 따르는")
    notes = {n.ilju: n.note for n in earth.ilju_notes}
    s = _simple()
    assert notes["戊子"] == s["year_ilju"]["chung"] and notes["戊午"] == s["year_ilju"]["hyeong"]
    assert notes["戊寅"] == notes["戊戌"] == s["year_ilju"]["samhap"]
    assert notes["戊辰"] == notes["戊申"] == s["year_ilju"]["none"]


def test_decision_unchanged_by_year_extension(board: DailyFortuneBoard) -> None:
    """새 키를 뺀 사전으로 만든 보드와 사건·확률·장소·로또·조언·이번 달 흐름이 같다(문체 전용)."""
    dicts = M.load_daily_dicts_for(_FROM)
    tpl = copy.deepcopy(dicts.templates)
    for key in ("year_phase_peak", "year_phase_turn", "season_tone", "year_span", "year_ilju",
                "year_cond"):
        tpl["simple_layer"].pop(key)
    without = _board(_FROM, dataclasses.replace(dicts, templates=tpl))
    for a, b in zip(board.fortunes, without.fortunes, strict=True):
        assert a.headline == b.headline and a.advice == b.advice
        assert [(e.event_key, e.probability) for e in a.events] == [
            (e.event_key, e.probability) for e in b.events
        ]
        assert a.lotto_phrase == b.lotto_phrase and a.lucky_place == b.lucky_place
    assert board.month_flow == without.month_flow
    assert without.year_flow is not None
    for new, old in zip(board.year_flow or [], without.year_flow, strict=True):
        assert (new.tone, new.emphasis, new.points) == (old.tone, old.emphasis, old.points)
        assert old.phase is None and old.span is None
        assert old.ilju_notes == [] and old.conditions == []


def test_previous_contract_board_has_no_new_blocks() -> None:
    prev = _board(_BEFORE)
    assert prev.content_version.split("|")[1] == "dict.v1.20"
    assert prev.year_flow is not None
    for flow in prev.year_flow:
        assert flow.phase is None and flow.span is None
        assert flow.ilju_notes == [] and flow.conditions == []


# ── 채팅·테마 ───────────────────────────────────────────────────────────────


def test_reference_line_appends_phase_and_span_for_the_year_horizon() -> None:
    s = _simple()
    line = S.simple_reference_line("己", "丁未", "year", s, year=2027, today=dt.date(2026, 11, 11))
    assert line.startswith("간단히 봤을 때, 丁未년은 기(己) 일간에게")
    assert "이 해 흐름이 가장 강한 때는 5~7월이에요." in line  # 내년 질문 — 현재형
    assert "8월부터는 쉬며 준비한 것을 꺼내 놓는 흐름이에요." in line
    assert "이 해는 2025년부터 이어진 쉬고 배우며 채우는 흐름의 마지막 해예요." in line
    assert "올해" not in line and line.endswith("참고용이에요.)")
    # 올해 질문 + 구간이 지남 → 그 문장만 과거형.
    now = S.simple_reference_line("己", "丙午", "year", s, year=2026, today=dt.date(2026, 11, 11))
    assert "가장 강한 때는 5~7월이었어요." in now and "두 번째 해예요." in now
    assert "내놓아 보세요." in now  # 조언은 그대로
    # 지난 해 질문 → 문단 전체 과거형(권유 문장 제외).
    past = S.simple_reference_line(
        "己", "乙巳", "year", s, year=2025, today=dt.date(2026, 11, 11), past=True,
    )
    assert "세요" not in past and "흐름이었어요." in past
    # 연도 없이 부르면(종전 호출) 여러 해 흐름만 빠진다.
    no_year = S.simple_reference_line("己", "丁未", "year", s)
    assert "가장 강한 때는 5~7월이에요." in no_year and "년부터" not in no_year
    # 월·일 지평은 그대로 — 연 문장이 섞이지 않는다.
    month = S.simple_reference_line(
        "己", "己亥", "month", s, M.load_daily_dicts_for(_FROM).templates["month_layer"],
        year=2026, today=dt.date(2026, 11, 11),
    )
    assert "가장 강한 때" not in month and "3년" not in month


def test_reference_line_restyles_without_haeyo_residue() -> None:
    from saju_engines.speech_style import restyle

    line = S.simple_reference_line("甲", "丁未", "year", _simple(), year=2027)
    for style in ("hapsyo", "banmal_chae", "hagae"):
        out = restyle(line, style)
        for sentence in re.split(r"(?<=[.!?])\s+", out):
            assert not has_haeyo_ending(sentence), (style, sentence)


def _birth() -> BirthInput:
    return BirthInput(
        birth_date=dt.date(1985, 7, 20), birth_time=dt.time(14, 30), birth_place_name="서울",
        gender="male",
    )


def _year_intent(year: int) -> IntentJson:
    return IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.YEAR, start=str(year), end=str(year),
        ),
    )


def test_chat_yearly_fortune_carries_phase_span_and_confirmed_conditions() -> None:
    """庚 일간·신강·土 과다 명식의 2027 丁未 — 연 문단에 구간·3년 흐름, 조건 줄은 확인된 항목만."""
    today = dt.date(2026, 11, 11)
    chart = chat_service.calculate(_birth())
    assert chart.force_analysis is not None
    assert chart.force_analysis.strength.band == "신강"
    assert "土" in chart.force_analysis.five_elements.excessive_elements
    pf = chat_service._build_period_fortune(_birth(), _year_intent(2027), today, "yearly")
    assert pf is not None
    assert "이 해 흐름이 가장 강한 때는 5~7월이에요." in pf.simple_reading_line
    assert "2025년부터 이어진" in pf.simple_reading_line
    assert any(c.startswith("이 명식은 토(흙) 기운이 이미 많아") for c in pf.simple_condition_lines)
    assert all(c.startswith("이 명식은") for c in pf.simple_condition_lines)
    # 반례: 월 총운에는 조건 줄·연 문장이 없다(그 달에 집중).
    m_intent = IntentJson(
        intent_id="t", query_type=QueryType.FORTUNE_OVERVIEW,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start="2026-11", end="2026-11",
        ),
    )
    mpf = chat_service._build_period_fortune(_birth(), m_intent, today, "monthly")
    assert mpf is not None and mpf.simple_condition_lines == []
    assert "가장 강한 때" not in mpf.simple_reading_line
    assert "엔진 확인" in SIMPLE_CONDITION_HEADER and "새로 판정" in SIMPLE_CONDITION_RULE


def test_serialized_prompt_places_condition_block_after_the_simple_rules() -> None:
    """프롬프트 직렬화 — 조건 블록은 단식 사용·방향 규칙 **뒤**에, 해당 항목이 있을 때만 실린다."""
    from pathlib import Path

    from saju_engines import EventEngineV2, GraphIndex, load_event_graph
    from saju_engines.context_reducer import build_llm_input, serialize_llm_input
    from saju_shared_types.events import EventKey
    from saju_shared_types.ganji_calendar import GanjiLevel

    backend = Path(__file__).resolve().parents[2]
    today = dt.date(2026, 11, 11)
    chart = chat_service.calculate(_birth())
    scorer = EventEngineV2(backend / "dictionaries")
    candidates = scorer.score_legacy(chart, levels={GanjiLevel.YEAR})
    graph = load_event_graph(backend / "compiled" / "event_graph_v1.1.0.json")
    bundles = GraphIndex(graph).retrieve([EventKey.CAREER_CHANGE])
    pf = chat_service._build_period_fortune(_birth(), _year_intent(2027), today, "yearly")
    assert pf is not None and pf.simple_condition_lines

    def text(fortune: object) -> str:
        return serialize_llm_input(build_llm_input(
            "내년 운세 어때?", _year_intent(2027), chart, candidates, bundles, scorer,
            today=today, period_fortune=fortune,  # type: ignore[arg-type]
        ))

    with_cond = text(pf)
    head = with_cond.index(SIMPLE_CONDITION_HEADER)
    assert with_cond.index("[단식 참고") < with_cond.index("단식 다음 문단 기준") < head
    assert head < with_cond.index(SIMPLE_CONDITION_RULE)
    for line in pf.simple_condition_lines:
        assert f"- {line}" in with_cond
    # 반례: 확인된 조건이 없으면 머리·규칙 줄도 싣지 않는다(빈 블록 금지).
    without = text(pf.model_copy(update={"simple_condition_lines": []}))
    assert SIMPLE_CONDITION_HEADER not in without and SIMPLE_CONDITION_RULE not in without
    assert "[단식 참고" in without


def test_report_yearly_block_carries_the_same_lines() -> None:
    from saju_api.services.report_service import _ReportData
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    spec = ReportSpec(
        product_code="RPT_YEAR", topic="general",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2027-01", end="2027-12"),
    )
    block = _ReportData(_birth(), spec, dt.date(2026, 11, 11)).yearly_sewoon_block(2027)
    simple = next(ln for ln in block if ln.startswith("[단식 참고"))
    assert "이 해 흐름이 가장 강한 때는 5~7월이에요." in simple and "마지막 해예요." in simple
    head = block.index(SIMPLE_CONDITION_HEADER)
    assert block[head + 1].startswith("- 이 명식은") and SIMPLE_CONDITION_RULE in block


def test_audit_keeps_the_longer_year_paragraph_when_copied_verbatim() -> None:
    """문단이 길어져도 감사는 그대로 동작한다 — 그대로 옮기면 불변, 없으면 한 번만 삽입."""
    from saju_shared_types.llm_input import LlmInput, PeriodFortune

    line = S.simple_reference_line("己", "丁未", "year", _simple(), year=2027)
    pf = PeriodFortune(
        fortune_type="yearly", period_label="2027", ganji="丁未", pillar_line="-",
        simple_reading_line=line,
    )
    payload = LlmInput.model_construct(period_fortune=pf)
    verbatim = "\n\n".join(
        ["내년은 유리한 흐름이 우세해요.", line, "다만 이 명식에서는 火가 희신이에요."]
    )
    assert chat_service._ensure_simple_reading_line(verbatim, payload, "t") == verbatim
    missing = "내년은 유리한 흐름이 우세해요.\n\n재물은 하반기에 움직여요."
    fixed = chat_service._ensure_simple_reading_line(missing, payload, "t")
    assert fixed.count("가장 강한 때는 5~7월이에요.") == 1
    assert fixed.split("\n\n")[1] == line
