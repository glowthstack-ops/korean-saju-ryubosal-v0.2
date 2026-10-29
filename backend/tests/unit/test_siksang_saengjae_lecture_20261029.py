"""식상생재 강의 반영 고정 (2026-10-29 데굴님 결정 — "제안대로").

서술층: 원국 재성만·식상만 해설, 식상 약할 때 인연 구절, 식상 발휘 제약(엔진 구조 패턴 성립 그대로),
식신·상관 화법 차이(십성 해설). 직업 사전: '인성→일간→식상' 조합에 강의 직업명 7개.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.wealth_lecture import (
    OUTPUT_BLOCKING_PATTERNS,
    _texts,
    output_blocked_lines,
    wealth_vessel_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Constraints, Domain, IntentJson, QueryType

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(d: str):
    return calculate(BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울",
        gender="male",
    ))


def test_wealth_only_chart_gets_natal_text_and_bond_clause() -> None:
    t = _texts()
    lines = wealth_vessel_lines(_chart("1970-07-12"))
    assert ("재성만 있는 원국: " + t["natal_wealth_only"]) in lines
    assert t["bond_support"] in lines
    assert lines[-1] == t["perspective"]


def test_output_only_chart_gets_natal_text_without_bond_clause() -> None:
    t = _texts()
    lines = wealth_vessel_lines(_chart("1971-07-12"))
    assert ("식상만 있는 원국: " + t["natal_output_only"]) in lines
    assert t["bond_support"] not in lines


def test_output_blocked_uses_engine_pattern_names() -> None:
    blocked = output_blocked_lines(_chart("1970-01-12"))
    assert blocked and blocked[0].startswith("식상 발휘 제약(관다신약): ")
    assert output_blocked_lines(_chart("1971-04-12")) == []
    assert set(OUTPUT_BLOCKING_PATTERNS) == {
        "SEOLGI_TAEGWA", "GWANDA_SINYAK", "INDA_SINYAK", "PYEONIN_DOSIK", "JAEDA_SINYAK",
    }


def test_output_blocked_reaches_career_question() -> None:
    intent = IntentJson(
        intent_id="t", query_type=QueryType.CHART_ANALYSIS, domain=Domain.CAREER,
        constraints=Constraints(),
    )
    out = chat_service._structural_context(
        _chart("1970-01-12"), intent, date(2026, 10, 29), "제 적성에 맞는 일은?",
    )
    assert any(x.startswith("식상 발휘 제약(") for x in out)


def test_ten_god_speech_clauses() -> None:
    items = {
        it["tenGod"]: it["natal"]
        for it in json.loads(
            (_DICTS / "interpretations" / "ten_gods_text.json").read_text("utf-8"),
        )["items"]
    }
    assert "본론을 바로 꺼내는 직선적인" in items["식신"]
    assert "듣기 좋게 포장해 전하는 화법" in items["상관"]


def test_resource_output_combination_has_lecture_jobs() -> None:
    d = json.loads((_DICTS / "career_fields.json").read_text("utf-8"))
    combo = next(c for c in d["combinations"] if c["name"] == "인성→일간→식상")
    for job in ("유튜버", "카피라이터", "웹 디자이너", "학원 강사", "교수", "마케팅 기획", "공방"):
        assert job in combo["jobs"]
    assert {"교육 설계", "기술 문서", "연구개발", "지식 콘텐츠"} <= set(combo["jobs"])
