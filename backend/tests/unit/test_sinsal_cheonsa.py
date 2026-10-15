"""천사(天赦) 신살 — 월지 계절별 일주 4종(2026-10-15, 외부 교재 3장 대조 후 데굴님 승인).

evidence 전용(게이트·점수 비개입)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_DICT = Path(__file__).resolve().parents[2] / "dictionaries" / "interpretations"


def _birth(d: date) -> BirthInput:
    return BirthInput(birth_date=d, birth_time="12:00:00", birth_place_name="서울", gender="male")


def _names(result, position: str | None = None) -> list[str]:
    sinsal = result.traditional_extras.sinsal
    if position is None:
        return [s.name for s in sinsal.full_list]
    return list(sinsal.by_pillar.get(position, []))


@pytest.mark.parametrize(
    ("d", "month", "day"),
    [
        (date(1975, 1, 18), "丁丑", "甲子"),  # 亥子丑月 甲子日
        (date(1975, 4, 2), "己卯", "戊寅"),   # 寅卯辰月 戊寅日
        (date(1975, 6, 17), "壬午", "甲午"),  # 巳午未月 甲午日
        (date(1975, 8, 30), "甲申", "戊申"),  # 申酉戌月 戊申日
    ],
)
def test_cheonsa_detected_on_day_pillar_when_season_matches(d, month, day) -> None:
    r = calculate(_birth(d))
    assert r.pillars is not None and r.pillars.month.ganji == month and r.pillars.day.ganji == day
    assert "천사" in _names(r) and "천사" in _names(r, "day")
    item = next(s for s in r.traditional_extras.sinsal.full_list if s.name == "천사")
    assert item.category == "noble_stars"


def test_cheonsa_absent_when_day_pillar_does_not_match() -> None:
    r = calculate(_birth(date(1980, 11, 22)))  # 丁亥月 己亥日
    assert "천사" not in _names(r)


def test_cheonsa_text_item_is_auxiliary_and_hedged() -> None:
    d = json.loads((_DICT / "sinsal_text.json").read_text(encoding="utf-8"))
    it = next(x for x in d["items"] if x["name"] == "천사")
    assert it["polarity"] == "길신" and it["role"] == "auxiliary" and it["reviewed"] is False
    assert len(it["flipSide"]) >= 20
    text = it["meaning"] + it["manifestation"]
    assert not any(bad in text for bad in ("반드시", "무조건", "모친"))
