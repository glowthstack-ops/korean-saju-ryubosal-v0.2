"""원국 12운성 궁위별 서사(2026-10-15, 외부 교재 4장 번역 — 데굴님 '적용 후 감수').

연·월·일·시 기둥의 12운성마다 `natal_by_palace` 한 줄이 명식 해석 자료(excerpts)에 실린다. 문체·서사
전용이라 점수·후보에는 닿지 않는다. 시주 미상 명식은 시주 줄이 없다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_chart_interpretation
from saju_shared_types.birth_input import BirthInput

_DICT = Path(__file__).resolve().parents[2] / "dictionaries" / "interpretations"
_CASE = BirthInput(
    birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울", gender="male",
)
_PALACES = ("year", "month", "day", "hour")


def test_dictionary_has_four_palace_sentences_for_all_twelve_stages() -> None:
    d = json.loads((_DICT / "twelve_stages_text.json").read_text(encoding="utf-8"))
    assert len(d["items"]) == 12
    seen: set[str] = set()
    for it in d["items"]:
        nb = it["natal_by_palace"]
        assert set(nb) == set(_PALACES), it["stage"]
        for palace, text in nb.items():
            assert len(text) >= 15 and text.endswith("."), (it["stage"], palace)
            assert text not in seen, (it["stage"], palace)  # 48문장 전부 고유
            seen.add(text)


def test_chart_excerpts_carry_one_palace_line_per_pillar() -> None:
    result = calculate(_CASE)
    ci = build_chart_interpretation(result)
    assert ci is not None and result.pillars is not None
    palace_ex = [e for e in ci.excerpts if e.kind == "twelve_stage_palace"]
    assert [e.key.split(" ")[0] for e in palace_ex] == ["연주", "월주", "일주", "시주"]
    d = json.loads((_DICT / "twelve_stages_text.json").read_text(encoding="utf-8"))
    by_stage = {it["stage"]: it["natal_by_palace"] for it in d["items"]}
    for palace, ex in zip(_PALACES, palace_ex, strict=True):
        pillar = getattr(result.pillars, palace)
        assert ex.key.endswith(pillar.twelve_unseong)
        assert ex.text == by_stage[pillar.twelve_unseong][palace]
    # 기존 일지 운성 발췌(core+natal)는 그대로 남는다.
    assert any(e.kind == "twelve_stage" for e in ci.excerpts)


def test_hour_unknown_chart_has_no_hour_palace_line() -> None:
    hu = BirthInput(
        birth_date=date(1980, 11, 22), birth_time=None, birth_place_name="서울", gender="male",
    )
    ci = build_chart_interpretation(calculate(hu))
    assert ci is not None
    keys = [e.key.split(" ")[0] for e in ci.excerpts if e.kind == "twelve_stage_palace"]
    assert "시주" not in keys and keys[:3] == ["연주", "월주", "일주"]
