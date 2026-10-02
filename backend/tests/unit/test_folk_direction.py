"""민속 흉방 레이어(docs/19 §5, 2026-09-21 데굴님 승인) 회귀.

고정하는 것: ①연간 4종 표(삼살·대장군·태세·세파)가 자료와 일치(2026 병오년 = 북 삼살+세파·동 대장군·
남 태세, 대장군 3년 고정) ②손방 음력 끝자리 규칙 + 손 없는 날 정합(기존 택일 규칙 불변) ③문구가
사전 템플릿 '민속에서는 ○쪽은 …라는 이유로 피하는 방향' 형식 ④채팅: 이사·공사 질문=전체 블록,
그 외 방향 질문=고지 한 줄, 방향 무관 질문=무소음 ⑤리포트 F-20b/Y-11b ⑥택일 근거 줄 ⑦세운 카드 부착
⑧기원 분리(삼살방 표는 12신살 BASE_MAPS 를 참조하지 않음) ⑨스키마·lint
⑩계층(2026-09-22 데굴님 승인): MOVE(삼살·대장군·손방)만 판정·고지·택일 근거·세운 배지,
GROUND(태세·세파)는 참고 줄, 중첩은 MOVE끼리만(2022 壬寅 북=삼살+대장군), 좌향 완화 문구·원거리
고지 병기.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import saju_api.services.chat_service as cs
import saju_api.services.report_service as report_service
from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import build_llm_input, serialize_llm_input
from saju_engines.dictionaries import _lint_folk_taboo
from saju_engines.folk_direction import (
    annual_folk_taboos,
    folk_note_for_day,
    folk_taboo_summary,
    format_folk_taboo_lines,
    phrase_for_note,
    son_direction,
)
from saju_engines.query_parser import parse_message
from saju_engines.relocation import is_son_eomneun_nal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.folk_direction import FolkTabooDict
from saju_shared_types.intent import Domain, IntentJson, QueryType, SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_TODAY = date(2026, 9, 20)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-09-20",
)


@pytest.fixture(scope="module")
def chart():
    return calculate(_BIRTH)


def _raw() -> dict:
    return json.loads((_DICTS / "folk_taboo_direction.json").read_text("utf-8"))


# ── ① 연간 표 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("year,samsal,daejanggun,taese,sepa", [
    (2026, "북", "동", "남", "북"),  # 丙午: 寅午戌→북 / 巳午未→동 / 午→남 / 子→북
    (2025, "동", "동", "남", "북"),  # 乙巳: 巳酉丑→동 / 巳午未→동
    (2027, "서", "동", "남", "북"),  # 丁未: 亥卯未→서 / 巳午未→동 / 未→남 / 丑→북
    (2030, "북", "남", "서", "동"),  # 庚戌: 寅午戌→북 / 申酉戌→남 / 戌→서 / 辰→동
    (2032, "남", "서", "북", "남"),  # 壬子: 申子辰→남 / 亥子丑→서 / 子→북 / 午→남
])
def test_annual_tables_match_material(year, samsal, daejanggun, taese, sepa) -> None:
    hits = {h.key: h for h in annual_folk_taboos(year)}
    assert hits["samsal"].direction == samsal and len(hits["samsal"].branches) == 3
    assert hits["daejanggun"].direction == daejanggun and hits["daejanggun"].period == "year3"
    assert hits["taese"].direction == taese and len(hits["taese"].branches) == 1
    assert hits["sepa"].direction == sepa and len(hits["sepa"].branches) == 1


def test_daejanggun_fixed_for_three_years() -> None:
    assert {annual_folk_taboos(y)[1].direction for y in (2025, 2026, 2027)} == {"동"}
    assert {annual_folk_taboos(y)[1].direction for y in (2028, 2029, 2030)} == {"남"}


def test_2026_tiers_split_and_overlap_counts_move_only() -> None:
    """2026: 북=삼살(판정)+세파(참고) → 중첩 아님. 남=태세는 참고층만(판정 없음). 2022 壬寅은
    북에 삼살+대장군이 겹쳐 STRONG."""
    s = folk_taboo_summary(2026)
    by = {n.direction: n for n in s.notes}
    assert by["북"].grade == "FOLK_TABOO"
    assert [h.key for h in by["북"].hits] == ["samsal"]
    assert [h.key for h in by["북"].ground_hits] == ["sepa"]
    assert by["동"].grade == "FOLK_TABOO" and [h.key for h in by["동"].hits] == ["daejanggun"]
    assert by["동"].hits[0].span_ko == "2025~2027"
    assert by["남"].hits == [] and [h.key for h in by["남"].ground_hits] == ["taese"]
    assert "서" not in by and s.year_ganji == "丙午" and s.son is None and s.son_free_day is None
    s22 = folk_taboo_summary(2022)
    north = next(n for n in s22.notes if n.direction == "북")
    assert north.grade == "STRONG_FOLK_TABOO"
    assert {h.key for h in north.hits} == {"samsal", "daejanggun"}
    assert {h.tier for h in annual_folk_taboos(2026)} == {"MOVE", "GROUND"}


def test_samsal_origin_is_separate_from_twelve_sinsal() -> None:
    """삼살방은 사전 표에서만 읽는다 — 12신살 BASE_MAPS 참조 없음(기원 분리, docs/19 §0-4)."""
    import inspect

    import saju_engines.folk_direction as fd

    src = inspect.getsource(fd).split('"""', 2)[2]  # 모듈 독스트링(설명 문장) 제외
    assert "BASE_MAPS" not in src and "twelve_sinsal" not in src


# ── ② 손방 ───────────────────────────────────────────────────────────────────


def test_son_direction_follows_lunar_day_rule() -> None:
    table = {1: "동", 2: "동", 3: "남", 4: "남", 5: "서", 6: "서", 7: "북", 8: "북"}
    d = date(2026, 9, 1)
    seen: set[int] = set()
    for i in range(45):
        day = date.fromordinal(d.toordinal() + i)
        hit, label = son_direction(day)
        lunar_day = int(label.split()[-1].rstrip("일"))
        seen.add(lunar_day % 10)
        if lunar_day % 10 in (9, 0):
            assert hit is None and is_son_eomneun_nal(day)
        else:
            assert hit is not None and hit.direction == table[lunar_day % 10]
            assert not is_son_eomneun_nal(day)
    assert seen == set(range(10))


def test_summary_with_day_marks_son_and_lunar_label() -> None:
    s = folk_taboo_summary(2026, date(2026, 9, 21))  # 음력 8월 11일 → 동
    assert s.lunar_label == "음력 8월 11일" and s.son is not None and s.son.direction == "동"
    east = next(n for n in s.notes if n.direction == "동")
    assert east.son_today and east.grade == "FOLK_TABOO"  # 손방은 중첩 등급에 안 센다
    s2 = folk_taboo_summary(2026, date(2026, 9, 20))  # 음력 8월 10일 = 손 없는 날
    assert s2.son is None and s2.son_free_day is True


# ── ③ 문구 ───────────────────────────────────────────────────────────────────


def test_phrase_uses_template_and_reason_grammar() -> None:
    s = folk_taboo_summary(2026, date(2026, 9, 21))
    north = next(n for n in s.notes if n.direction == "북")
    text = phrase_for_note(north)
    assert text.startswith("민속에서는 북쪽은 ")
    assert "살(煞)이 모이는 자리라는 이유로 피하는 방향으로 봅니다(삼살방(亥·子·丑))" in text
    # 참고층은 판정 문구에 안 섞인다.
    assert "세파방" not in text and "강한 민속 주의 방향" not in text
    assert "다만 그쪽을 향해 가는 것은 전통적으로 허용하고" in text  # 좌향 완화(三煞可向不可坐)
    full = "\n".join(format_folk_taboo_lines(s, full=True))
    assert "[민속 흉방 — 2026 丙午년" in full and "손방(그날): 음력 8월 11일 → 동쪽" in full
    assert "오늘 손방도 이 방향입니다" in full and "범위:" in full
    assert "(대장군방 2025~2027 3년 고정)" in full
    assert "- 참고(동토·좌향 참고, 이사 판정 아님): 북쪽 세파방(子)" in full
    assert "남쪽 태세방(午) — 건축·증축·터파기·땅을 건드리는 행위·집 좌향에서만 꺼림" in full
    assert "太歲可坐不可向" in full and "- 원거리 고지: 전통 문헌은 현재 집에서 120보 이내" in full
    assert "남쪽[민속 주의 방향]" not in full  # 태세만 걸린 남쪽은 판정 줄이 없다
    assert "사고" not in full and "무조건" not in full
    brief = "\n".join(format_folk_taboo_lines(s, full=False))
    assert brief.startswith("\n[민속 흉방 고지 — 丙午년")
    assert "북쪽=삼살방 · 동쪽=대장군방(2025~2027 고정)" in brief
    assert "세파" not in brief and "태세" not in brief and "중첩" not in brief
    assert "배치(바라보기·머리·위치·출입구)에는 적용하지 않으며" in brief


# ── ④ 채팅 배선 ──────────────────────────────────────────────────────────────


def test_chat_relocation_question_gets_full_block_and_sleep_gets_notice(chart) -> None:
    q = "이사는 어느 방향으로 가면 좋을까"
    intent = parse_message(q, _TODAY).intents[0]
    text = serialize_llm_input(
        build_llm_input(q, intent, chart, [], [], cs._get_scorer(), today=_TODAY)
    )
    assert "[민속 흉방 — 2026 丙午년" in text and "[민속 흉방 지침]" in text
    assert "손방(그날): 음력 8월 10일 = 손 없는 날" in text  # 시점 없으면 오늘
    assert "[방위 활용 — 12신살 기준" in text  # 개인 층은 그대로 병기
    q2 = "잘때는 어떤방향이 좋을까"
    i2 = parse_message(q2, _TODAY).intents[0]
    t2 = serialize_llm_input(build_llm_input(q2, i2, chart, [], [], cs._get_scorer(), today=_TODAY))
    assert "[민속 흉방 고지 — 丙午년" in t2 and "[민속 흉방 — " not in t2
    assert "[민속 흉방 지침]" in t2
    edu = IntentJson(intent_id="a", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.EDUCATION)
    t3 = serialize_llm_input(
        build_llm_input("공부운 어때", edu, chart, [], [], cs._get_scorer(), today=_TODAY)
    )
    assert "민속 흉방" not in t3
    # 공사 어휘가 있는 방향 질문은 전체 블록.
    q4 = "집 증축은 어느 방향으로 하면 좋아"
    i4 = parse_message(q4, _TODAY).intents[0]
    assert i4.direction_question
    t4 = serialize_llm_input(build_llm_input(q4, i4, chart, [], [], cs._get_scorer(), today=_TODAY))
    assert "[민속 흉방 — 2026 丙午년" in t4


# ── ⑤ 리포트 ─────────────────────────────────────────────────────────────────


def _spec(product_code: str, year: int = 2026) -> ReportSpec:
    return ReportSpec(
        product_code=product_code,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start=f"{year}-01-01", end=f"{year}-12-31"),
    )


def test_report_sections_carry_folk_taboo_for_year() -> None:
    full = {c.section_id: c for c in report_service.plan_report(_BIRTH, _spec("RPT_FULL"), _TODAY)}
    body = full["F-20b"].body_prompt
    assert "[민속 흉방 — 2026 丙午년" in body and "손방(그날)" not in body
    assert "[민속 흉방 지침]" in body
    assert "민속 흉방" not in full["F-20"].body_prompt
    y30 = {
        c.section_id: c
        for c in report_service.plan_report(_BIRTH, _spec("RPT_YEAR", 2030), _TODAY)
    }
    assert "[민속 흉방 — 2030 庚戌년" in y30["Y-11b"].body_prompt
    body30 = y30["Y-11b"].body_prompt
    assert "남쪽[민속 주의 방향]: 민속에서는 남쪽은 그해 방합 기준으로 대장군이" in body30


def test_theme_report_sections_carry_folk_taboo_and_verdicts() -> None:
    """테마사주(RPT_FOCUS): 이사 테마 RL-07 은 전체 블록, 다른 테마 행동 전략 섹션은 고지 한 줄
    (2026-09-21 데굴님 지시)."""
    def _focus(topic: str) -> dict[str, object]:
        spec = ReportSpec(
            product_code="RPT_FOCUS", topic=topic,
            subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
            period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
        )
        return {c.section_id: c for c in report_service.plan_report(_BIRTH, spec, _TODAY)}

    rl = _focus("relocation")["RL-07"].body_prompt
    assert "◆ 목적 '이사·환경 변화'" in rl and "[민속 흉방 — 2026 丙午년" in rl
    assert "[민속 흉방 지침]" in rl
    assert "[주의(목적 충돌)]" in rl  # 5등급 verdict 라벨
    w = _focus("wealth")["W-08"].body_prompt
    assert "◆ 목적 '영업·장사'" in w and "[민속 흉방 고지 — 丙午년" in w
    assert "[민속 흉방 — " not in w
    assert "[민속 흉방 지침]" in w


# ── ⑥ 택일 · ⑦ 세운 카드 ────────────────────────────────────────────────────


def test_folk_note_for_day_and_luck_pillar_attachment(chart) -> None:
    note = folk_note_for_day(date(2026, 9, 21))
    assert note == "민속 흉방(추가 정보): 손방 동쪽 · 올해 삼살방 북 · 대장군방 동"
    assert "세파방" not in note and "태세방" not in note  # 참고층은 택일 근거에 안 싣는다
    assert folk_note_for_day(date(2026, 9, 20)).startswith("민속 흉방(추가 정보): 손 없는 날")
    years = {p.label: p for p in chart.luck_cycles.yearly_luck}
    assert [h.name_ko for h in years["2026"].folk_taboos] == ["삼살방", "대장군방"]  # 배지 2종
    assert years["2026"].folk_taboos[1].span_ko == "2025~2027"
    assert years["2026"].folk_taboos[0].direction == "북"
    assert all(m.folk_taboos == [] for m in chart.luck_cycles.monthly_luck)
    assert years["2026"].luck_score == calculate(_BIRTH).luck_cycles.yearly_luck[
        list(years).index("2026")
    ].luck_score  # 점수 불변


def test_date_selection_candidates_carry_folk_note_only_for_relocation_purposes() -> None:
    from saju_engines.date_selection import DateSelectionEngine
    from saju_engines.precompute import CompositeBuilder
    from saju_shared_types.events import EventKey

    chart = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date="2026-06-11",
    ))
    composites = CompositeBuilder(_DICTS).build(chart, "본인", "1.0.0", "2026-06-11T00:00:00+00:00")
    eng = DateSelectionEngine(_DICTS)
    res = eng.select(EventKey.RELOCATION, composites, "2026-06-01", "2026-06-30", top_n=5)
    assert res.candidates and all(c.folk_direction_note for c in res.candidates)
    assert all(
        c.folk_direction_note.startswith("민속 흉방(추가 정보)")
        and "올해 삼살방 북" in c.folk_direction_note
        for c in res.candidates
    )
    res2 = eng.select(EventKey.CONTRACT_DOCUMENT, composites, "2026-06-01", "2026-06-30", top_n=5)
    assert res2.candidates and all(c.folk_direction_note is None for c in res2.candidates)
    # 점수·등급 불변 — 근거 줄만 추가.
    assert [c.scores.final for c in res.candidates] == sorted(
        (c.scores.final for c in res.candidates), reverse=True
    )


# ── ⑨ 사전 ───────────────────────────────────────────────────────────────────


def test_dictionary_validates_and_lints() -> None:
    parsed = FolkTabooDict.model_validate(_raw())
    assert not _lint_folk_taboo(parsed) and parsed.reviewed is True
    assert [t.key for t in parsed.taboos] == ["samsal", "daejanggun", "taese", "sepa", "son"]
    assert parsed.version == "1.1.0"
    assert {t.key: t.tier for t in parsed.taboos} == {
        "samsal": "MOVE", "daejanggun": "MOVE", "son": "MOVE", "taese": "GROUND", "sepa": "GROUND",
    }
    # 참고층에 이사·이동을 되돌리면 lint 가 막는다.
    raw = _raw()
    next(t for t in raw["taboos"] if t["key"] == "sepa")["avoid_actions"].append("이사")
    errs = _lint_folk_taboo(FolkTabooDict.model_validate(raw))
    assert any("sepa(GROUND)" in e for e in errs)
    raw = _raw()
    raw["taboos"][0]["table"].pop("寅午戌")
    with pytest.raises(ValueError):
        FolkTabooDict.model_validate(raw)
    raw = _raw()
    raw["phrase_template"] = "민속에서는 {direction}쪽을 피합니다"
    errs = _lint_folk_taboo(FolkTabooDict.model_validate(raw))
    assert any("{reasons}" in e for e in errs)
