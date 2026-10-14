"""일주 사전 재물 주장 태그 — 문장 유형 기준 생략(2026-10-13 데굴님 확정) 회귀 고정.

사고: 재성이 구신인 명식의 '오늘 운세' 답변이 "타고난 재물 감각이 있는 명식"이라고 썼다. 원천은
일주 사전(60일주 공용 문안)의 己亥 문장이 [명식 해석 자료]에 그대로 실린 것이었다.
규칙: 재성 역할이 아니라 **문장 유형**으로 정한다 — 재물복 단정·축재 결과·능력 평가(현재 엔진이
능력 종류별 근거를 구분하지 못해 근거 부족)는 생략, 관심·성향과 띠 동물 상징은 유지. 생략은
문장 단위이며 고쳐 쓰지 않는다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_engines.chart_interpretation import (
    _ILJU_OMIT_CLAIM_TYPES,
    _ilju_by_ganji,
    _serialize_ilju,
    build_chart_interpretation,
)
from saju_engines.context_reducer import ILJU_WEALTH_USE_RULE
from saju_engines.dictionaries import IljuFile, _lint_ilju
from saju_engines.event_scoring import favorability_map
from saju_engines.wealth_capacity import analyze_wealth_capacity
from saju_shared_types.birth_input import BirthInput

_ILJU_PATH = (
    Path(__file__).resolve().parents[2] / "dictionaries" / "interpretations" / "ilju.json"
)


def _items() -> list[dict]:
    return json.loads(_ILJU_PATH.read_text(encoding="utf-8"))["items"]


def _omitted(entry: dict) -> list[dict]:
    return [c for c in entry.get("wealth_claims", []) if c["type"] in _ILJU_OMIT_CLAIM_TYPES]


def test_omit_policy_is_type_based():
    """생략 유형은 재물복 단정·축재 결과·능력 평가 셋이고, 관심·성향·상징은 유지한다."""
    assert _ILJU_OMIT_CLAIM_TYPES == {"fortune_assertion", "accumulation", "ability"}


def test_tag_inventory_snapshot():
    """태그 전수(22일주·46문장)와 상징 6건 — 태그가 조용히 빠지거나 늘면 여기서 드러난다."""
    items = _items()
    claims = [(e["ganji"], c) for e in items for c in e.get("wealth_claims", [])]
    assert len(claims) == 46
    assert sum(1 for e in items if e.get("wealth_claims")) == 22
    symbols = sorted(g for g, c in claims if c["type"] == "cultural_symbol")
    assert symbols == sorted(["乙亥", "丁亥", "戊子", "辛亥", "癸亥", "己酉"])
    # '타고난 재물 감각'은 재물복 단정이 아니라 능력 평가(C)이며, 성실함과 묶인 복합 문장이다.
    gihae = {c["text"]: c for g, c in claims if g == "己亥"}
    claim = gihae["타고난 재물 감각과 성실함"]
    assert claim["type"] == "ability" and claim["ability_kind"] == "wealth_sense"
    assert claim["split_review"] is True
    assert {"text": "성실함", "type": "other"} in claim["clauses"]


@pytest.mark.parametrize("entry", _items(), ids=lambda e: e["ganji"])
def test_serialized_block_drops_omitted_and_keeps_others(entry):
    """60일주 전부 — 생략 유형 문장은 블록에 없고, 관심·상징 문장은 남는다."""
    text = _serialize_ilju(entry)
    for claim in _omitted(entry):
        assert claim["text"] not in text, (entry["ganji"], claim["text"])
    for claim in entry.get("wealth_claims", []):
        if claim["type"] not in _ILJU_OMIT_CLAIM_TYPES:
            assert claim["text"] in text, (entry["ganji"], claim["text"])
    narrative_line = text.split("\n")[1]
    assert "  " not in narrative_line and narrative_line == narrative_line.strip()


def test_gihae_block_after_omission():
    """사고 일주 己亥 — 재물 감각·실속 문장이 빠지고 무관한 성향 문장은 남는다."""
    text = _serialize_ilju(_ilju_by_ganji()["己亥"])
    assert "재물 감각" not in text and "실속" not in text
    assert "정원사 같은 외면" in text
    assert (
        "밝은 면: 다정하고 단정해 어디서나 환영받음 / 분위기를 부드럽게 만드는 유머와 여유" in text
    )


def test_imagery_omission_keeps_header():
    """戊子 물상이 재물복 단정이라 빠져도 머리줄(일주·동물)은 남는다."""
    text = _serialize_ilju(_ilju_by_ganji()["戊子"])
    assert text.split("\n")[0] == "일주 戊子 (노란 쥐)"
    assert "재물의 샘" not in text
    assert "노란 쥐는 알뜰하게 곳간을 채우는 영리한 동물이에요." in text  # 상징 유지


# 태그된 일주 × 재성 역할 5종 — 생략은 역할과 무관해야 한다(용·희신이어도 같은 규칙).
_ROLE_SAMPLES = [
    ("희신", date(1970, 1, 10), "庚寅"),
    ("구신", date(1970, 1, 17), "丁酉"),
    ("기신", date(1970, 3, 14), "癸巳"),
    ("한신", date(1970, 5, 9), "己丑"),
    ("용신", date(1970, 8, 22), "甲戌"),
]


@pytest.mark.parametrize(("role", "birth_date", "ganji"), _ROLE_SAMPLES)
def test_omission_is_independent_of_wealth_role(role, birth_date, ganji):
    """실제 해석 경로(build_chart_interpretation) — 재성 역할 5종 모두에서 생략 유형 문장이 없다."""
    from saju_api.services.manse_service import calculate

    result = calculate(BirthInput(
        birth_date=birth_date, birth_time="09:30:00", birth_place_name="서울", gender="male",
    ))
    assert result.pillars is not None and result.pillars.day.ganji == ganji
    wealth_element = analyze_wealth_capacity(result).wealth_element
    assert favorability_map(result).get(wealth_element) == role
    ci = build_chart_interpretation(result)
    assert ci is not None and ci.ilju_text
    omitted = _omitted(_ilju_by_ganji()[ganji])
    assert omitted
    for claim in omitted:
        assert claim["text"] not in ci.ilju_text, (role, claim["text"])


def test_lint_catches_drifted_claim_text():
    """태그 원문이 본문과 어긋나면(사전 수정 후 태그 미갱신) lint 가 잡는다."""
    data = json.loads(_ILJU_PATH.read_text(encoding="utf-8"))
    gihae = next(e for e in data["items"] if e["ganji"] == "己亥")
    gihae["wealth_claims"][0]["text"] = "본문에 없는 문장이에요."
    errors = _lint_ilju(IljuFile.model_validate(data))
    assert any("원문 없음" in e for e in errors)


def test_lint_requires_ability_kind_and_split_clauses():
    """능력 평가는 능력 종류 필수, split_review 는 재물 무관 절 기록 필수."""
    data = json.loads(_ILJU_PATH.read_text(encoding="utf-8"))
    gihae = next(e for e in data["items"] if e["ganji"] == "己亥")
    gihae["wealth_claims"][2].pop("ability_kind")
    gihae["wealth_claims"][3]["clauses"] = [{"text": "타고난 재물 감각", "type": "ability"}]
    errors = _lint_ilju(IljuFile.model_validate(data))
    assert any("ability_kind" in e for e in errors)
    assert any("재물 무관 절" in e for e in errors)


def test_use_rule_follows_ilju_block_in_fixed_prefix():
    """일주 자료 사용 규칙은 일주 블록 바로 뒤에 항상 붙는다(질문 종류 무관 고정 prefix)."""
    from saju_api.services.manse_service import calculate
    from saju_engines.context_reducer import build_birth_summary, serialize_chart_prefix

    result = calculate(BirthInput(
        birth_date=date(1980, 11, 22), birth_time="09:40:00", birth_place_name="서울",
        gender="male",
    ))
    ci = build_chart_interpretation(result)
    assert ci is not None
    lines = serialize_chart_prefix(build_birth_summary(result), ci)
    idx = lines.index(ci.ilju_text)
    assert lines[idx + 1] == ILJU_WEALTH_USE_RULE
    assert "재물 감각" not in ci.ilju_text  # 사고 명식(재성 水=구신)


def test_use_rule_wording_is_neutral():
    """규칙은 미화·부정 단정을 모두 막고 운 확인을 요구하며, 금지 문형을 예문으로 싣지 않는다."""
    assert "구체적인 시기와 축재 결과는 운을 함께 확인" in ILJU_WEALTH_USE_RULE
    assert "미화하거나 부정적으로 단정하지 않는다" in ILJU_WEALTH_USE_RULE
    assert "띠 동물 상징" in ILJU_WEALTH_USE_RULE
    assert "타고난 재물 감각" not in ILJU_WEALTH_USE_RULE
    assert "못 번다" not in ILJU_WEALTH_USE_RULE
