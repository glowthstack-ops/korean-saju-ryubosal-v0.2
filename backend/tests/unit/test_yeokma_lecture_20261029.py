"""역마살 강의 반영 고정 (2026-10-29 데굴님 결정 — "제안대로").

엔진 역마 정의(2026-10-06 통일: 寅申巳亥 보유=이동지 표지, 역마살=연지·일지 삼합 기준 12신살)는
유지한다. 강의의 글자별 결(寅·申·巳·亥)과 조언은 **역마 성립 자리**에만 붙는다.
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
    pillar = next(p for p in luck_years(b, [2028]) if p.label == "2028")
    lines = [x for x in build_luck_grounding(calculate(b), pillar)["sinsal_lines"] if "역마" in x]
    assert lines and "申 역마" in lines[0] and "조언: " in lines[0]


def test_natal_excerpt_prefers_established_yeokma_over_marker() -> None:
    r = calculate(_birth("1984-01-12"))
    ex = {e.key: e.text for e in _sinsal_excerpts(r)}
    assert "역마살" in ex and "이동지" not in ex
    day_branch = r.pillars.day.branch
    assert f"{day_branch} 역마" in ex["역마살"]


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
    assert "위치: 연주(亥), 일주(巳), 시주(巳)" in (move.prompt_preview or "")
    assert "[역마 — 원국 성립" not in (wealth.prompt_preview or "")


def test_luck_yeokma_block_uses_question_year_when_candidates_empty() -> None:
    from saju_api.services import chat_service

    b = BirthInput(
        calendar_type="solar", birth_date="1970-10-12", birth_time="10:00",
        birth_place_name="서울", gender="male", reference_date="2026-10-29",
    )
    t = date(2026, 10, 29)
    p = chat_service.chat(b, "2028년에 이사나 이동 운이 있을까요?", t, dry_run=True).prompt_preview
    assert p and "[운 역마" in p and "- 2028 戊申:" in p and "申 역마" in p
    none = chat_service.chat(b, "2027년에 이직할 수 있을까요?", t, dry_run=True).prompt_preview
    assert "[운 역마" not in (none or "")


def test_luck_yeokma_lines_month_expands_to_year_and_caps() -> None:
    from saju_engines.chart_interpretation import _YEOKMA_PERIOD_MAX, yeokma_period_lines

    r = calculate(_birth("1970-10-12").model_copy(update={"reference_date": date(2026, 10, 29)}))
    pillars = list(r.luck_cycles.yearly_luck)  # 기준일이 있어야 세운 표가 채워진다
    block = yeokma_period_lines(pillars, ["2028-03"])  # 월 후보 → 그 해 세운 2028 戊申
    assert block and any(x.startswith("- 2028 戊申:") for x in block)
    assert block[-1].startswith("조언: ") and sum(x.startswith("조언") for x in block) == 1
    many = yeokma_period_lines(pillars, [str(y) for y in range(2000, 2100)])
    assert len([x for x in many if x.startswith("- ")]) <= _YEOKMA_PERIOD_MAX
