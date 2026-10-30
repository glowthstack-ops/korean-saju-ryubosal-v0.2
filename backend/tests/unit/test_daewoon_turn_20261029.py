"""교운 방향 조언 고정 — 외부 강의 「길흉은 혼자 오지 않는다」(2026-10-29 데굴님 결정).

방향: 강한·부분 용신운 → 강한·부분 기신운(과열 경계) / 그 반대(마지막 고비·준비). 혼합·평운·트리거운
제외. 범위: 엔진 교운 가중(라플라스형 스케일 365일) e^-1 이상 = 앞뒤 1년 핵심,
e^-2 이상 = 앞뒤 2년 여파.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.daewoon_turn import (
    BAD_CODES,
    CORE_WEIGHT,
    EXTENDED_WEIGHT,
    GOOD_CODES,
    daewoon_turn_lines,
)
from saju_engines.dictionaries import DaewoonTurnTextFile, _lint_daewoon_turn_text
from saju_engines.event_scoring import DAEWOON_TRANSITION_SCALE_DAYS, daewoon_transition_weight
from saju_engines.structural_context import DAEWOON_TRANSITION_SIGNALS_DIRECTIVE
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(d: str):
    return calculate(BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    ))


def test_dictionary_lint() -> None:
    path = _DICTS / "interpretations" / "daewoon_turn_text.json"
    parsed = DaewoonTurnTextFile.model_validate(json.loads(path.read_text("utf-8")))
    assert _lint_daewoon_turn_text(parsed) == []


def test_window_thresholds_follow_engine_model() -> None:
    """앞뒤 1년·2년이 엔진 가중 e^-1·e^-2 와 일치한다(데굴님 결정 2: 엔진 기준)."""
    assert DAEWOON_TRANSITION_SCALE_DAYS == 365.0
    jiao = date(2030, 6, 1)
    assert daewoon_transition_weight(date(2031, 6, 1), [jiao]) == pytest.approx(CORE_WEIGHT)
    assert daewoon_transition_weight(date(2032, 5, 31), [jiao]) == pytest.approx(
        EXTENDED_WEIGHT, rel=0.01,
    )
    assert math.isclose(CORE_WEIGHT, math.exp(-1)) and math.isclose(EXTENDED_WEIGHT, math.exp(-2))


def test_mixed_and_neutral_labels_excluded() -> None:
    assert GOOD_CODES == {"pure_yongsin_luck", "partial_yongsin"}
    assert BAD_CODES == {"pure_gisin_luck", "partial_gisin"}


@pytest.mark.parametrize(("d", "lo", "hi", "direction", "span"), [
    ("1974-01-12", 2026, 2030, "맞는 흐름에서 맞지 않는", "교운기 핵심"),
    ("1966-01-12", 2026, 2030, "맞지 않는 흐름에서 맞는", "교운기 핵심"),
    ("1974-05-12", 2026, 2030, "맞지 않는 흐름에서 맞는", "교운기 여파"),
    ("1967-01-12", 2032, 2032, "맞는 흐름에서 맞지 않는", "교운기 여파"),
])
def test_direction_and_span(d: str, lo: int, hi: int, direction: str, span: str) -> None:
    lines = daewoon_turn_lines(_chart(d), lo, hi)
    assert lines and lines[0].startswith("[교운 방향")
    assert any(direction in x and span in x for x in lines[1:])


def test_far_window_has_no_block() -> None:
    """교운일(2055-01·2065-01)에서 2년 넘게 떨어진 창은 블록이 없다 — e^-2 밖(2026-10-30 강화)."""
    chart = _chart("1967-01-12")
    assert daewoon_turn_lines(chart, 2060, 2061) == []
    assert daewoon_turn_lines(chart, 2050, 2051) == []


def test_omen_clause_in_transition_signals() -> None:
    assert "사소한 문제·작은 징조가 잦아질 수" in DAEWOON_TRANSITION_SIGNALS_DIRECTIVE
