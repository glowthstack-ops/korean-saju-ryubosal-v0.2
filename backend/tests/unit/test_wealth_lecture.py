"""재물 강의 3편 번역층 회귀 고정 (2026-10-29 데굴님 결정 — 권유대로 + 점수층 측정).

서술층: 재물 그릇 4분류(원국 분류 해설)·식상/재성 부재 경로·관점, 운 간지별 식상·재성 보완·그릇×유입
만족도·재성×겁재 제안 경계. 점수층: 원국 한쪽 + 운 천간 다른 한쪽 식상생재 횡재 발동(실험 OFF).
픽스처는 2026년 월운에서 조건이 성립하는 명식을 탐색해 잡았다(2026-10-29).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines.dictionaries import WealthLectureTextFile, _lint_wealth_lecture_text
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.wealth_capacity import detect_wealth_activations
from saju_engines.wealth_lecture import (
    _texts,
    wealth_period_block,
    wealth_period_texts,
    wealth_vessel,
    wealth_vessel_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(d: str):
    return calculate(BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    ))


# 신왕재왕 / 신약재약 / 신약재왕 / 신왕재약(원국 재성만) / 신왕재약(원국 식상만)
_BIG, _SMALL, _WEAK_FIRM = "1973-01-12", "1972-01-12", "1972-07-12"
_WEALTH_ONLY, _OUTPUT_ONLY = "1973-04-12", "1973-10-12"


def test_text_dictionary_lint() -> None:
    path = _DICTS / "interpretations" / "wealth_lecture_text.json"
    parsed = WealthLectureTextFile.model_validate(json.loads(path.read_text("utf-8")))
    assert _lint_wealth_lecture_text(parsed) == []


@pytest.mark.parametrize(("d", "quadrant", "size"), [
    (_BIG, "신왕재왕", "big"), (_SMALL, "신약재약", "small"),
    (_WEAK_FIRM, "신약재왕", "mid"), (_WEALTH_ONLY, "신왕재약", "mid"),
])
def test_vessel_quadrant_and_size(d: str, quadrant: str, size: str) -> None:
    v = wealth_vessel(_chart(d))
    assert v is not None and v.quadrant == quadrant and v.size == size


def test_vessel_lines_are_classification_with_perspective() -> None:
    lines = wealth_vessel_lines(_chart(_BIG))
    assert lines[0].startswith("재물 그릇 분류(원국 해설 — 판정 아님): 신왕재왕")
    assert lines[-1] == _texts()["perspective"]
    t = _texts()
    no_ow = wealth_vessel_lines(_chart("1975-01-12"))
    assert any(t["no_output_wealth_resource_officer"] in x for x in no_ow)


def test_complement_texts_follow_which_side_luck_supplies() -> None:
    t = _texts()
    assert t["complement_wealth_natal"] in wealth_period_texts(_chart(_WEALTH_ONLY), "庚寅", None)
    assert t["complement_output_natal"] in wealth_period_texts(_chart(_OUTPUT_ONLY), "庚寅", None)


@pytest.mark.parametrize(("d", "score", "cell"), [
    (_BIG, 80, "satisfaction_big_high"), (_BIG, 40, "satisfaction_big_low"),
    (_SMALL, 80, "satisfaction_small_high"), (_SMALL, 40, "satisfaction_small_low"),
])
def test_satisfaction_cells(d: str, score: int, cell: str) -> None:
    assert _texts()[cell] in wealth_period_texts(_chart(d), "庚寅", score)


def test_satisfaction_skipped_for_mid_vessel_or_mid_inflow() -> None:
    t = _texts()
    cells = [t[k] for k in t if k.startswith("satisfaction_")]
    assert not set(cells) & set(wealth_period_texts(_chart(_WEAK_FIRM), "庚寅", 80))
    assert not set(cells) & set(wealth_period_texts(_chart(_BIG), "庚寅", 60))


@pytest.mark.parametrize(("d", "ganji", "key"), [
    ("1970-01-12", "癸巳", "peer_wealth_caution_officer"),
    ("1971-01-12", "庚寅", "peer_wealth_caution_weak"),
    (_BIG, "壬辰", "peer_wealth_caution"),
])
def test_peer_wealth_caution_variants(d: str, ganji: str, key: str) -> None:
    texts = wealth_period_texts(_chart(d), ganji, None)
    t = _texts()
    cautions = [x for x in texts if x in (
        t["peer_wealth_caution"], t["peer_wealth_caution_officer"], t["peer_wealth_caution_weak"],
    )]
    assert cautions == [t[key]]  # 경계 문구는 한 시기에 하나만(원칙 8)


def test_period_block_once_per_ganji() -> None:
    block = wealth_period_block(
        _chart(_BIG), [("2026-02", "庚寅", 80), ("2026-02", "庚寅", 80)],
    )
    assert block and block[0].startswith("[재물 운 결 — 재물 강의 번역층")
    assert len([x for x in block if x.startswith("- ")]) == 1


# ── 점수층(실험 OFF) ────────────────────────────────────────────────────────


def test_detect_activation_natal_complement_only_when_enabled() -> None:
    base = dict(
        day_element="土", wealth_element="水", natal_branches=set(), luck_branches=set(),
        luck_stem_elements={"金"}, natal_output_present=False, natal_wealth_present=True,
    )
    assert detect_wealth_activations(**base) == []
    assert detect_wealth_activations(**base, natal_complement=True) == ["식상생재(원국 보완)"]
    # 운 천간에 식상·재성이 함께 오면 기존 '식상생재' 하나만(중복 라벨 없음).
    both = {**base, "luck_stem_elements": {"金", "水"}}
    assert detect_wealth_activations(**both, natal_complement=True) == ["식상생재"]
    # 원국 쪽 전제가 없으면 운 한쪽만으로는 성립하지 않는다.
    none = {**base, "natal_wealth_present": False}
    assert detect_wealth_activations(**none, natal_complement=True) == []


def test_engine_flag_off_has_no_complement_reason() -> None:
    b = BirthInput(
        birth_date=date(1973, 4, 12), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    )
    c2 = calculate(b).model_copy(deep=True)
    c2.luck_cycles.monthly_luck = luck_months(b, 2025) + luck_months(b, 2026)
    off = build_event_engine_v2(_DICTS).score(c2, levels={GanjiLevel.MONTH})
    on = build_event_engine_v2(_DICTS, enable_wealth_natal_complement=True).score(
        c2, levels={GanjiLevel.MONTH},
    )
    assert not any("원국 보완" in rc for c in off for rc in c.reason_codes)
    assert any("원국 보완" in rc for c in on for rc in c.reason_codes)
