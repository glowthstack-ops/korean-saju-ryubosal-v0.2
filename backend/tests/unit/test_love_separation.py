"""남녀 이별운 강의 번역층 회귀 고정 (2026-10-29 데굴님 결정 3건).

점수층(연애 실험 키 separation_*, 기본 OFF)과 서술층(관계 질문 전용 문구·무인성 원국 분류 해설)을
함께 고정한다. 픽스처는 2026년 월운에서 조건이 성립하는 명식을 탐색해 잡았다(2026-10-29).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate, luck_months
from saju_engines.dictionaries import LoveSeparationTextFile, _lint_love_separation_text
from saju_engines.event_engine_config import build_event_engine_v2
from saju_engines.love_separation import (
    SEP_OFFICER_OUTPUT,
    SEP_PALACE_JIECAI,
    SEP_PEER_BRANCH_WEIGHT,
    SEP_RESOURCE_INFLOW,
    SEP_ZHENGCAI_PEER,
    SEPARATION_KEYS,
    love_separation_block,
    love_separation_natal_lines,
    produce_love_separation_seeds,
    separation_natal,
)
from saju_engines.love_timing import LOVE_EXPERIMENT_KEYS, resolve_love_experiments
from saju_engines.ten_god_brancher import TransitSignal
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2, LuckLayer, TenGod
from saju_shared_types.ganji_calendar import GanjiLevel

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _birth(d: str, g: str) -> BirthInput:
    return BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울", gender=g,
    )


# ① 여 — 관성 3%, 2026-10 戊戌(상관 간여지동). 무인성(missing)이기도 하다.
_F_OFFICER_WEAK = _birth("1980-05-24", "female")
# ② 남 — 일지 정재, 2026-11 己亥(겁재 천간) / 2026-07 乙未(겁재 지지만).
_M_PALACE = _birth("1980-07-14", "male")
# ③ 여 — 정인 missing, 2026-07 乙未(정인 천간). 정인 hidden_only 대조군 1980-01-04 여.
_F_NO_RESOURCE = _birth("1980-03-04", "female")
_F_WEAK_RESOURCE = _birth("1980-01-04", "female")
# ④ 여 — 원국 정재, 2026-08 丙申(겁재 천간) / 2026-05 癸巳(겁재 지지만).
_F_ZHENGCAI = _birth("1980-05-04", "female")
# 대조 — 원국 정재 없음 남, 2026-09 丁酉(겁재 천간).
_M_NO_ZHENGCAI = _birth("1980-01-04", "male")


def _month(birth: BirthInput, period: str, experiments: list[str] | None = None):
    year = int(period[:4])
    chart = calculate(birth)
    c2 = chart.model_copy(deep=True)
    c2.luck_cycles.monthly_luck = luck_months(birth, year - 1) + luck_months(birth, year)
    eng = build_event_engine_v2(_DICTS, love_experiments=experiments or [])
    return [c for c in eng.score(c2, levels={GanjiLevel.MONTH}) if c.period == period]


def _rel_codes(cands) -> set[str]:
    return {
        code for c in cands if c.event_key is EventKeyV2.RELATIONSHIP_CHANGE
        for code in c.reason_codes
    }


def test_experiment_keys_registered_and_default_off() -> None:
    assert set(SEPARATION_KEYS) <= set(LOVE_EXPERIMENT_KEYS)
    flags = resolve_love_experiments([])
    assert not any(flags[k] for k in SEPARATION_KEYS)


def test_natal_facts_of_fixtures() -> None:
    a = separation_natal(calculate(_F_OFFICER_WEAK))
    assert a is not None and a.officer_weak and a.gender == "female"
    b = separation_natal(calculate(_M_PALACE))
    assert b is not None and b.day_palace_zhengcai and b.gender == "male"
    c = separation_natal(calculate(_F_NO_RESOURCE))
    assert c is not None and c.zhengyin_state == "missing"
    d = separation_natal(calculate(_F_WEAK_RESOURCE))
    assert d is not None and d.zhengyin_state == "hidden_only"
    e = separation_natal(calculate(_F_ZHENGCAI))
    assert e is not None and e.natal_zhengcai
    f = separation_natal(calculate(_M_NO_ZHENGCAI))
    assert f is not None and not f.natal_zhengcai


@pytest.mark.parametrize(("birth", "period"), [
    (_F_OFFICER_WEAK, "2026-10"), (_M_PALACE, "2026-11"), (_F_NO_RESOURCE, "2026-07"),
    (_F_ZHENGCAI, "2026-08"),
])
def test_off_baseline_has_no_separation_codes(birth: BirthInput, period: str) -> None:
    assert not any(code.startswith("LOVE_SEP_") for code in _rel_codes(_month(birth, period)))


@pytest.mark.parametrize(("key", "birth", "period", "code"), [
    (SEP_OFFICER_OUTPUT, _F_OFFICER_WEAK, "2026-10", "LOVE_SEP_OFFICER_OUTPUT"),
    (SEP_PALACE_JIECAI, _M_PALACE, "2026-11", "LOVE_SEP_PALACE_JIECAI"),
    (SEP_RESOURCE_INFLOW, _F_NO_RESOURCE, "2026-07", "LOVE_SEP_RESOURCE_INFLOW"),
    (SEP_ZHENGCAI_PEER, _F_ZHENGCAI, "2026-08", "LOVE_SEP_ZHENGCAI_PEER"),
])
def test_each_rule_seeds_relationship_change(
    key: str, birth: BirthInput, period: str, code: str,
) -> None:
    assert code in _rel_codes(_month(birth, period, [key]))


def test_rules_respect_gender_and_natal_conditions() -> None:
    # 남성 명식에는 여성 규칙(①③)이 서지 않는다.
    m = _month(_M_PALACE, "2026-11", [SEP_OFFICER_OUTPUT, SEP_RESOURCE_INFLOW])
    assert not any(c.startswith("LOVE_SEP_") for c in _rel_codes(m))
    # 원국 정재가 없으면 ④가 서지 않는다.
    n = _month(_M_NO_ZHENGCAI, "2026-09", [SEP_ZHENGCAI_PEER])
    assert "LOVE_SEP_ZHENGCAI_PEER" not in _rel_codes(n)


def test_branch_weight_variant_swaps_stem_and_branch_bases() -> None:
    """데굴님 결정 ①(케이스로 판단) — 두 변형이 천간/지지 기준점을 맞바꾼다."""
    chart = calculate(_F_ZHENGCAI)
    stem = [TransitSignal(TenGod.JIECAI, LuckLayer.WOLWOON, "stem")]
    branch = [TransitSignal(TenGod.JIECAI, LuckLayer.WOLWOON, "branch_main")]
    base = {SEP_ZHENGCAI_PEER: True}
    heavy = {SEP_ZHENGCAI_PEER: True, SEP_PEER_BRANCH_WEIGHT: True}

    def score(sig, flags) -> int:
        out = produce_love_separation_seeds(sig, LuckLayer.WOLWOON, chart, "2026-08", flags)
        assert len(out) == 1
        return out[0].score

    assert score(stem, base) > score(branch, base)
    assert score(branch, heavy) > score(stem, heavy)
    assert score(stem, base) == score(branch, heavy)


def test_seeds_merge_to_one_candidate_and_skip_other_layers() -> None:
    chart = calculate(_F_OFFICER_WEAK)
    flags = {k: True for k in SEPARATION_KEYS[:4]}
    sig = [
        TransitSignal(TenGod.SHANGGUAN, LuckLayer.WOLWOON, "stem"),
        TransitSignal(TenGod.JIECAI, LuckLayer.WOLWOON, "branch_main"),
    ]
    out = produce_love_separation_seeds(sig, LuckLayer.WOLWOON, chart, "2026-10", flags)
    assert len(out) <= 1
    assert produce_love_separation_seeds(sig, LuckLayer.ILWOON, chart, "2026-10-01", flags) == []


# ── 서술층 ──────────────────────────────────────────────────────────────────


def test_text_dictionary_lint() -> None:
    path = _DICTS / "interpretations" / "love_separation_lecture_text.json"
    parsed = LoveSeparationTextFile.model_validate(json.loads(path.read_text("utf-8")))
    assert _lint_love_separation_text(parsed) == []


def test_natal_classification_lines() -> None:
    missing = love_separation_natal_lines(calculate(_F_NO_RESOURCE))
    assert missing and "무인성(정인 없음)" in missing[0] and "판정 아님" in missing[0]
    hidden = love_separation_natal_lines(calculate(_F_WEAK_RESOURCE))
    assert hidden and "지장간에만" in hidden[0]
    assert love_separation_natal_lines(calculate(_M_PALACE)) == []


def test_hour_unknown_chart_is_not_classified() -> None:
    """시주 미상 — 시주에 정인이 있을 수 있어 무인성으로 분류하지 않는다(HOUR_UNKNOWN 규칙 3)."""
    unknown = BirthInput(
        birth_date=date(1980, 3, 4), birth_time=None, birth_time_unknown=True,
        birth_place_name="서울", gender="female",
    )
    nat = separation_natal(calculate(unknown))
    assert nat is not None and nat.zhengyin_state == "unknown"
    assert love_separation_natal_lines(calculate(unknown)) == []


def test_relationship_block_once_per_ganji() -> None:
    block = love_separation_block(
        calculate(_F_ZHENGCAI), [("2026-08", "丙申"), ("2026-08", "丙申"), ("2026-03", "辛卯")],
    )
    assert block and block[0].startswith("[연애·관계 운 결 — 이별운 강의 번역층")
    body = [x for x in block[1:] if x.startswith("- ")]
    assert len(body) == 1 and body[0].startswith("- 2026-08 丙申: ")
    assert "쟁재" in body[0] and "이사" in body[0]
    assert love_separation_block(calculate(_F_ZHENGCAI), [("2026-03", "辛卯")]) == []
