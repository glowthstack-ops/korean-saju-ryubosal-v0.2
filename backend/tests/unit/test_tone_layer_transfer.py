"""표현 결 층 이식(daily docs/17 §23 → chat·report, 2026-09-10) — 문체 전용·점수 불변.

- `incoming_stage_note`: 운 간지의 일간 기준 12운성 → twelve_stages_text.incoming 첫 문장.
- chat: 후보 블록에 '결(12운성):' 줄 + 지시문에 표현 결 규칙.
- report: 기간 클러스터에 '운 결(문체 전용): 행동=… / 흐름=…' 줄 + 전 섹션 공통 지시.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import saju_api.services.chat_service as chat_service
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import incoming_stage_note
from saju_engines.report_event_input import _tone_line
from saju_engines.structural_context import TONE_LAYER_DIRECTIVE
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch, Stem

_BACKEND = Path(__file__).resolve().parents[2]
_STAGES = _BACKEND / "dictionaries" / "interpretations" / "twelve_stages_text.json"
_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def test_incoming_stage_note_uses_incoming_sentence_of_computed_stage() -> None:
    items = {it["stage"]: it for it in json.loads(_STAGES.read_text("utf-8"))["items"]}
    for day_master, ganji in (("己", "甲申"), ("甲", "己丑"), ("庚", "丙寅")):
        stage = twelve_unseong(Stem(day_master), Branch(ganji[1]))
        note = incoming_stage_note(day_master, ganji)
        assert note and items[stage]["incoming"].startswith(note[:10])
        assert not items[stage]["natal"].startswith(note[:10])
    assert incoming_stage_note("", "甲申") == ""
    assert incoming_stage_note("己", "甲") == ""


def test_chat_prompt_carries_stage_note_and_tone_directive() -> None:
    res = chat_service.chat(_BIRTH, "올해 이직운 어때?", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    text = res.prompt_preview or ""
    assert "결(12운성):" in text, "후보 블록에 12운성 결 줄이 없다"
    assert "해석:" in text  # 십성 유입(행동 결)은 기존 줄
    assert TONE_LAYER_DIRECTIVE in text, "표현 결 지시가 지시문에 없다"


def test_report_tone_line_and_directive() -> None:
    chart = calculate(_BIRTH)
    day_master = chart.pillars.day_master
    line = _tone_line(chart, "甲申", {})
    assert line.startswith("  운 결(문체 전용): 행동=") and " / 흐름=" in line
    assert incoming_stage_note(day_master, "甲申") in line
    assert _tone_line(chart, "甲", {}) == ""
    svc = _BACKEND / "apps" / "api" / "saju_api" / "services" / "report_service.py"
    assert "TONE_LAYER_DIRECTIVE,\n        ]" in svc.read_text("utf-8"), (
        "리포트 전 섹션 공통 prefix 에 표현 결 지시가 없다"
    )


def test_tone_layer_is_style_only() -> None:
    """결 층은 문체 전용 — 지시문이 점수·판정 불변을 명시한다."""
    assert "점수·판정·간지 사실을 바꾸지 않는다" in TONE_LAYER_DIRECTIVE
