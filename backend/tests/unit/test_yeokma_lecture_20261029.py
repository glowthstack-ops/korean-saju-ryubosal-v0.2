"""역마살 강의 반영 고정 (2026-10-29 데굴님 결정 — "제안대로").

엔진 역마 정의(2026-10-06 통일: 寅申巳亥 보유=이동지 표지, 역마살=삼합 기준 12신살)는 유지한다.
기준 자리는 2026-11-12 부터 일지만이다(종전 연지·일지) — 표본의 역마 자리·연도를 그에 맞췄다.
강의의 글자별 결(寅·申·巳·亥)과 조언은 **역마 성립 자리**에만 붙는다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate, luck_years
from saju_engines.chart_interpretation import (
    _sinsal_branch_advice_note,
    _sinsal_excerpts,
    build_luck_grounding,
)
from saju_engines.dictionaries import SinsalTextFile
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _birth(d: str) -> BirthInput:
    return BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    )


def _yeokma() -> dict:
    path = _DICTS / "interpretations" / "sinsal_text.json"
    data = json.loads(path.read_text("utf-8"))
    SinsalTextFile.model_validate(data)
    return next(it for it in data["items"] if it["name"] == "역마살")


def test_dictionary_has_four_branches_and_advice_only_on_yeokma() -> None:
    item = _yeokma()
    assert set(item["byBranch"]) == {"寅", "申", "巳", "亥"}
    assert "조언을 구해" in item["advice"] and "함께하는 사람" in item["advice"]
    data = json.loads((_DICTS / "interpretations" / "sinsal_text.json").read_text("utf-8"))
    marker = next(it for it in data["items"] if it["name"] == "이동지")
    assert "byBranch" not in marker and "advice" not in marker


def test_note_helper_picks_matching_branch_once() -> None:
    item = _yeokma()
    note = _sinsal_branch_advice_note(item, ["申", "申", "子"])
    assert note.count("申 역마") == 1 and "子" not in note and " 조언: " in note
    assert _sinsal_branch_advice_note({}, ["申"]) == ""


def test_luck_yeokma_line_carries_branch_note_and_advice() -> None:
    b = _birth("1970-10-12")
    # 庚戌·丙戌·乙丑·辛巳 — 일지 丑(巳酉丑국)의 역마는 亥 → 2031 辛亥 세운.
    pillar = next(p for p in luck_years(b, [2031]) if p.label == "2031")
    lines = [x for x in build_luck_grounding(calculate(b), pillar)["sinsal_lines"] if "역마" in x]
    assert lines and "亥 역마" in lines[0] and "조언: " in lines[0]
    # 반례: 2028 戊申은 연지 戌(寅午戌국) 기준으로만 역마 — 연지 기준은 인정하지 않는다.
    y2028 = next(p for p in luck_years(b, [2028]) if p.label == "2028")
    assert not [
        x for x in build_luck_grounding(calculate(b), y2028)["sinsal_lines"] if "역마" in x
    ]


def test_natal_excerpt_prefers_established_yeokma_over_marker() -> None:
    r = calculate(_birth("1984-01-12"))
    ex = {e.key: e.text for e in _sinsal_excerpts(r)}
    assert "역마살" in ex and "이동지" not in ex
    # 癸亥·乙丑·乙巳·辛巳 — 일지 巳(巳酉丑국)의 역마 亥가 연주에 선다. 일주 자리가 아니어도 싣는다.
    assert "亥 역마" in ex["역마살"] and "연주" in ex["역마살"]


def test_marker_only_chart_gets_no_branch_note() -> None:
    r = calculate(_birth("1970-01-12"))
    assert all("글자별 결" not in e.text for e in _sinsal_excerpts(r))


# ── 후속(2026-10-29): 이사·직업 질문 전용 원국 역마 블록·운 역마 블록 ──────────────────


def test_natal_yeokma_block_for_movement_questions_only() -> None:
    from saju_api.services import chat_service

    b = BirthInput(
        calendar_type="solar", birth_date="1984-01-12", birth_time="10:00",
        birth_place_name="서울", gender="male", reference_date="2026-10-29",
    )
    t = date(2026, 10, 29)
    move = chat_service.chat(b, "2028년에 이사나 이동 운이 있을까요?", t, dry_run=True)
    wealth = chat_service.chat(b, "2028년 재물운 어때요?", t, dry_run=True)
    assert "[역마 — 원국 성립" in (move.prompt_preview or "")
    assert "위치: 연주(亥) —" in (move.prompt_preview or "")
    # 반례: 일주·시주 巳는 연지 亥 기준으로만 역마 — 위치에 적지 않는다.
    assert "위치: 연주(亥), 일주(巳)" not in (move.prompt_preview or "")
    assert "[역마 — 원국 성립" not in (wealth.prompt_preview or "")


def test_luck_yeokma_block_uses_question_year_when_candidates_empty() -> None:
    from saju_api.services import chat_service

    b = BirthInput(
        calendar_type="solar", birth_date="1970-10-12", birth_time="10:00",
        birth_place_name="서울", gender="male", reference_date="2026-10-29",
    )
    t = date(2026, 10, 29)
    p = chat_service.chat(b, "2031년에 이사나 이동 운이 있을까요?", t, dry_run=True).prompt_preview
    assert p and "[운 역마" in p and "- 2031 辛亥:" in p and "亥 역마" in p
    none = chat_service.chat(b, "2027년에 이직할 수 있을까요?", t, dry_run=True).prompt_preview
    assert "[운 역마" not in (none or "")


def test_luck_yeokma_lines_month_expands_to_year_and_caps() -> None:
    from saju_engines.chart_interpretation import _YEOKMA_PERIOD_MAX, yeokma_period_lines

    r = calculate(_birth("1970-10-12").model_copy(update={"reference_date": date(2026, 10, 29)}))
    pillars = list(r.luck_cycles.yearly_luck)  # 기준일이 있어야 세운 표가 채워진다
    block = yeokma_period_lines(pillars, ["2031-03"])  # 월 후보 → 그 해 세운 2031 辛亥
    assert block and any(x.startswith("- 2031 辛亥:") for x in block)
    assert block[-1].startswith("조언: ") and sum(x.startswith("조언") for x in block) == 1
    many = yeokma_period_lines(pillars, [str(y) for y in range(2000, 2100)])
    assert len([x for x in many if x.startswith("- ")]) <= _YEOKMA_PERIOD_MAX


# ── 이동지 양면 서술 상시 동반(2026-11-03 데굴님 "양면 서술이 반드시 함께 표시되는 정도로 충분") ──
_FLIP = "합(육합·삼합·방합)으로 묶이면 발이 묶이듯"  # 2026-11-03 고전 대조 문구


def test_marker_flip_side_survives_when_marker_absorbed_into_yeokma() -> None:
    """역마살 성립으로 이동지 발췌를 뺄 때도 양면 문장은 역마살 줄에 남는다."""
    r = calculate(_birth("1984-01-12"))
    ex = {e.key: e.text for e in _sinsal_excerpts(r)}
    assert "이동지" not in ex and _FLIP in ex["역마살"]


def test_marker_flip_line_in_movement_block_without_yeokma() -> None:
    """亥×4(역마살 없음, 이동지만) — 이사·직업 질문 블록에 이동지 양면 줄이 선다."""
    from saju_engines.chart_interpretation import mobility_marker_flip_lines, yeokma_natal_lines

    b = BirthInput(birth_date=date(1995, 11, 28), birth_time="22:00:00",
                   birth_place_name="서울", gender="female")
    r = calculate(b)
    lines = yeokma_natal_lines(r)
    assert lines == mobility_marker_flip_lines(r) and len(lines) == 1
    assert lines[0].startswith("[이동지 양면") and _FLIP in lines[0]
    # 사실 병기(2026-11-03 데굴님 "예외 사례라면 거기까지") — 값 그대로.
    held = "보유: 연주 亥(겁재·제왕)·월주 亥(겁재·제왕)·일주 亥(겁재·제왕)·시주 亥(겁재·제왕)"
    assert held in lines[0]
    assert "같은 글자 반복: 亥×4(자형 1그룹)" in lines[0]
    assert "역마 성립: 없음(일지 亥 기준 亥=지살)" in lines[0]
    assert "이동지 충·형: 없음" in lines[0] and "방합: 미완성(亥: 子丑 부재)" in lines[0]
    assert "같은 계절 글자와 묶이면" not in lines[0]


def test_marker_flip_line_follows_yeokma_block() -> None:
    """역마살 성립 명식(1984-01-12)도 역마 블록 뒤에 이동지 양면 줄이 따라온다."""
    from saju_engines.chart_interpretation import yeokma_natal_lines

    lines = yeokma_natal_lines(calculate(_birth("1984-01-12")))
    assert lines[0].startswith("[역마 — 원국 성립") and lines[-1].startswith("[이동지 양면")


def test_marker_flip_line_reaches_chat_movement_question() -> None:
    from saju_api.services import chat_service

    b = BirthInput(
        calendar_type="solar", birth_date="1995-11-28", birth_time="22:00",
        birth_place_name="서울", gender="female", reference_date="2026-11-03",
    )
    move = chat_service.chat(b, "나는 이사나 이동수가 있어?", date(2026, 11, 3), dry_run=True)
    assert "[이동지 양면" in (move.prompt_preview or "") and _FLIP in (move.prompt_preview or "")


def test_marker_facts_for_clash_and_established_yeokma_chart() -> None:
    """申亥亥巳(1980-11-22 09:40 남) — 역마 성립(일지 亥 기준 巳)·巳亥 충·亥×2 반복이 실린다."""
    from saju_engines.chart_interpretation import mobility_marker_flip_lines

    b = BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울 구로구",
        gender="male", latitude=37.4944, longitude=126.8563, timezone="Asia/Seoul",
    )
    line = mobility_marker_flip_lines(calculate(b))[0]
    assert "역마 성립: 시주 巳(일지 亥 기준)" in line
    assert "亥巳 충" in line and "같은 글자 반복: 亥×2(자형 1그룹)" in line
    assert "방합: 미완성" in line
