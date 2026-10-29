"""관계 결(「사귈 때 조심해야 할 사주」)·편인 도식 강의 반영 고정 (2026-10-29 데굴님 결정).

관계 결: 상관견관·관성 과다 신약·관성 미투출(성별) — 비낙인 경향 + 관계를 편하게 하는 방법.
편인 도식: 원국 식신 1개 → 도식(경제 활동 제약·큰 결정 조언), 2개 이상 → 약하게 + 식신 몰입 상담
(데굴님: 스스로 문제를 파악·교정하는 카운슬링). 점수·판정 불변.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from saju_api.services import chat_service
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import (
    _career_exit_text,
    career_exit_lecture_texts,
    natal_siksin_count,
)
from saju_engines.dictionaries import (
    RelationshipTendencyTextFile,
    _lint_relationship_tendency_text,
)
from saju_engines.event_scoring import favorability_map
from saju_engines.relationship_tendency import _texts, relationship_tendency_lines
from saju_engines.wealth_lecture import wealth_period_texts
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Constraints, Domain, IntentJson, QueryType

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _chart(d: str, g: str = "male"):
    return calculate(BirthInput(
        birth_date=date.fromisoformat(d), birth_time="10:00:00", birth_place_name="서울", gender=g,
    ))


def test_relationship_dictionary_lint_and_no_stigma() -> None:
    path = _DICTS / "interpretations" / "relationship_tendency_text.json"
    parsed = RelationshipTendencyTextFile.model_validate(json.loads(path.read_text("utf-8")))
    assert _lint_relationship_tendency_text(parsed) == []
    joined = " ".join(it.text for it in parsed.items)
    assert "마마보이" not in joined and "무속" not in joined
    assert "'조심해야 할 사람'이라는 판정이 아니며" in joined  # 머리말은 판정 부정으로만 언급


def test_sanggwan_gyeongwan_and_officer_heavy_weak() -> None:
    t = _texts()
    lines = relationship_tendency_lines(_chart("1970-01-12"))
    assert lines[0].startswith("[관계에서 나타나기 쉬운 결")
    joined = "\n".join(lines)
    assert t["sanggwan_gyeongwan"] in joined and t["sanggwan_gyeongwan_weak"] in joined
    assert t["officer_heavy_weak"] in joined


@pytest.mark.parametrize(("g", "key"), [
    ("male", "no_officer_male"), ("female", "no_officer_female"),
])
def test_no_officer_by_gender_with_output_clause(g: str, key: str) -> None:
    t = _texts()
    joined = "\n".join(relationship_tendency_lines(_chart("1971-01-12", g)))
    assert t[key] in joined
    if g == "male":
        assert t["no_officer_output_strong"] in joined


def test_label_goes_into_header_for_compatibility() -> None:
    lines = relationship_tendency_lines(_chart("1970-01-12"), "상대")
    assert lines[0].startswith("[상대 — 관계에서 나타나기 쉬운 결")


def test_chat_relationship_context_and_compat_block_carry_lines() -> None:
    intent = IntentJson(
        intent_id="t", query_type=QueryType.CHART_ANALYSIS, domain=Domain.RELATIONSHIP,
        constraints=Constraints(),
    )
    ctx = chat_service._structural_context
    out = ctx(_chart("1970-01-12"), intent, date(2026, 10, 29), "연애운")
    assert any(x.startswith("[관계에서 나타나기 쉬운 결") for x in out)
    partner = BirthInput(
        birth_date=date(1971, 1, 12), birth_time="10:00:00", birth_place_name="서울",
        gender="female",
    )
    block = chat_service._compat_prompt_block(
        _chart("1970-01-12"), partner, date(2026, 10, 29), "상대",
    )
    assert block and "[본인 — 관계에서" in block and "[상대 — 관계에서" in block


# ── 편인 도식 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("d", "ganji", "n", "expect", "absent"), [
    ("1971-10-12", "戊辰", 1, ["pianyin_dosik_single"], ["siksin_immersion"]),
    ("1971-01-12", "乙丑", 2,
     ["pianyin_dosik_ample", "siksin_immersion"], ["pianyin_dosik_single"]),
    ("1970-01-12", "庚午", 0, [], ["pianyin_dosik_single", "pianyin_dosik_ample"]),
])
def test_dosik_branches_by_natal_siksin(
    d: str, ganji: str, n: int, expect: list[str], absent: list[str],
) -> None:
    r = _chart(d)
    c = _career_exit_text()
    assert natal_siksin_count(r) == n if n < 2 else natal_siksin_count(r) >= 2
    tx = career_exit_lecture_texts(r.pillars.day_master, ganji, favorability_map(r), r)
    assert c["pianyin_leave"] in tx  # 편인 운 기본 문구는 그대로
    for k in expect:
        assert c[k] in tx
    for k in absent:
        assert c[k] not in tx


def test_dosik_reaches_wealth_period_texts() -> None:
    c = _career_exit_text()
    assert c["pianyin_dosik_single"] in wealth_period_texts(_chart("1971-10-12"), "戊辰", None)


def test_immersion_text_is_counseling_not_diagnosis() -> None:
    text = _career_exit_text()["siksin_immersion"]
    assert "해칠 수 있다" in text and "돌아보면 좋다" in text
    for bad in ("중독자", "중독이다", "반드시"):
        assert bad not in text
