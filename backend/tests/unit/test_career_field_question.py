"""직업 분야·직종·적성 질문 (docs/08 career_field, 2026-09-10 데굴님 지적·자료).

실사례: '9월중에 이직운' 뒤 '이직 제안이 온다면 어떤 분야가 확률이 높을까'가 시점형 이직 답으로
처리됐다. ①파서가 분야 질문을 표시 ②직전 시점을 승계하지 않음 ③원국 십성 기능 근거 블록과
전용 지시가 프롬프트에 실림 ④사전 스키마·원칙 문구를 고정한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import saju_api.services.chat_service as cs
from saju_api.services.manse_service import calculate
from saju_engines.career_field import (
    build_career_field_facts,
    load_career_fields,
    render_career_field_lines,
)
from saju_engines.query_parser import detect_career_field, parse_message
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.career_fields import TEN_GOD_KO
from saju_shared_types.intent import Domain

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TODAY = date(2026, 9, 10)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-09-10",
)


@pytest.mark.parametrize("q", [
    "내게 이직 제안이 온다면 어떤 분야가 가장 확률이 높을까?",
    "나한테 맞는 직업이 뭘까",
    "어떤 일을 해야 잘 풀릴까",
    "적성에 맞는 분야는?",
    "무슨 직종이 저한테 어울릴까요",
])
def test_parser_marks_career_field(q: str) -> None:
    assert detect_career_field(q)
    intent = parse_message(q, _TODAY).intents[0]
    assert intent.career_field and intent.domain is Domain.CAREER


@pytest.mark.parametrize("q", [
    "9월중에 이직운이 있을까?",
    "이번에 어떤 주식 살까",
    "어느 지역이 살기 좋아",
    "올해 재물운 어때",
])
def test_parser_does_not_mark_non_field_questions(q: str) -> None:
    intent = parse_message(q, _TODAY).intents[0]
    assert not intent.career_field


def test_dictionary_covers_ten_gods_and_keeps_principles() -> None:
    d = load_career_fields(_DICTS)
    assert set(d.ten_gods) == set(TEN_GOD_KO)
    assert d.runtime_status == "ACTIVE" and d.reviewed is False
    assert d.review_status == "PENDING"
    names = {c.name for c in d.combinations}
    expected = {"식신생재", "상관생재", "관인상생", "살인상생", "식신제살", "상관패인", "재생관"}
    assert expected <= names
    for c in d.combinations:
        assert c.pattern_id or c.derived_rule, c.name
    assert any("개발자" in p for p in d.principles)  # 일대일 고정 금지 예시
    assert any("없다고" in p and "부적합" in p for p in d.principles)
    raw = json.loads((_DICTS / "career_fields.json").read_text("utf-8"))
    assert raw["thresholds"]["note"]  # 문턱은 자료에 없는 기계 기본값임을 선언


@pytest.fixture(scope="module")
def chart():
    return calculate(_BIRTH)


def test_facts_from_reference_chart(chart) -> None:
    facts = build_career_field_facts(chart, incoming=[("2026", "정관"), ("2026-09", "편인")])
    assert facts.day_master == "己" and facts.geokguk == "정재격"
    tgs = [p.ten_god for p in facts.prominent]
    assert "정재" in tgs and "겁재" in tgs  # 분포 상위(33%·29%)
    assert all(p.job_groups and p.caution for p in facts.prominent)
    assert any(c.name == "상관생재" for c in facts.combinations)  # 구조 패턴 감지기 연동
    assert [i.ten_god for i in facts.incoming] == ["정관", "편인"]
    lines = render_career_field_lines(facts)
    assert lines[0].startswith("[직업 분야 근거")
    assert any("제안·기회 통로 2026-09" in ln for ln in lines)
    assert any("원칙:" in ln for ln in lines)
    # 점수·판정 아님 — 확률·점수 숫자를 만들지 않는다(비중 % 만 사실로 표기).
    assert not any("점" in ln and "%" not in ln for ln in lines[1:2])


def test_chat_prompt_has_field_block_and_directive_without_time_inheritance() -> None:
    from saju_engines.conversation_store import ConversationStore

    store = ConversationStore()
    r1 = cs.chat(
        _BIRTH, "9월중에 이직운이 있을까?", _TODAY, dry_run=True, store=store, owner_id="t",
    )
    assert r1.status == "dry_run"
    q2 = "내게 이직 제안이 온다면 어떤 분야가 가장 확률이 높을까?"
    r2 = cs.chat(
        _BIRTH, q2, _TODAY, dry_run=True, store=store, owner_id="t",
        thread_id=r1.thread_id, prior_answer="(9월 이직운 답변)",
    )
    if r1.thread_id:
        store.delete(r1.thread_id)
    assert r2.status == "dry_run", r2.answer
    intent = r2.intents[0]
    assert intent.career_field and intent.domain is Domain.CAREER
    assert intent.time_range is None  # 직전 턴의 2026-09 를 잇지 않는다
    text = r2.prompt_preview or ""
    assert "[직업 분야 근거" in text and "[직업 분야 풀이" in text
    assert "제안·기회 통로" in text


def test_field_question_does_not_inherit_previous_month_scope() -> None:
    """직전 턴이 '9월 이직운'이어도 분야 질문은 2026-09 창을 잇지 않는다(원국 축)."""
    from saju_engines.conversation import ConversationEngine
    from saju_shared_types.conversation import ConversationState
    from saju_shared_types.intent import Granularity, IntentJson, QueryType, TimeRange

    last = IntentJson(
        intent_id="t1", query_type=QueryType.DOMAIN_ANALYSIS, domain=Domain.CAREER,
        time_range=TimeRange(
            type="absolute", granularity=Granularity.MONTH, start="2026-09", end="2026-09",
        ),
    )
    state = ConversationState(
        thread_id="x", turn_no=1, active_topic=Domain.CAREER, last_intent=last, last_offer="",
    )
    parsed, _ns, _res, _link = ConversationEngine().process_turn(
        state, "내게 이직 제안이 온다면 어떤 분야가 가장 확률이 높을까?", _TODAY
    )
    intent = parsed.intents[0]
    assert intent.career_field and intent.domain is Domain.CAREER
    assert intent.time_range is None
    # 대조: 분야 어휘가 없는 후속 질문은 종전대로 9월 창을 잇는다.
    parsed2, *_ = ConversationEngine().process_turn(state, "그럼 승진은 어때?", _TODAY)
    assert parsed2.intents[0].time_range is not None
    assert parsed2.intents[0].time_range.start == "2026-09"


# ── 테마사주(리포트) — F-15·J-04·J-07 에 같은 근거 블록·지침 ─────────────────────


def _report_data(product_code: str, topic: str | None):
    from saju_api.services.report_service import _ReportData
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    )
    kwargs = {"topic": topic} if topic else {}
    spec = ReportSpec(
        product_code=product_code,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2024-01", end="2030-12"), **kwargs,
    )
    return spec, _ReportData(birth, spec, date(2026, 6, 15), owner_id=None, subject_id=None)


def test_report_career_sections_carry_field_block_and_directive() -> None:
    from saju_api.services.report_service import build_section_context
    from saju_engines.report_plan import build_section_plans

    spec, data = _report_data("RPT_FOCUS", "career")
    plans = {p.section_id: p for p in build_section_plans(spec)}
    for sid in ("J-04", "J-07"):
        ctx = build_section_context(plans[sid], spec, data)
        assert "[직업 분야 근거" in ctx.body_prompt, sid
        assert "[직업 분야 지침" in ctx.body_prompt, sid
        assert "제안·기회 통로 대운" in ctx.body_prompt, sid
    # 타임라인 섹션(J-05)은 분야 블록을 싣지 않는다.
    ctx5 = build_section_context(plans["J-05"], spec, data)
    assert "[직업 분야 근거" not in ctx5.body_prompt


def test_report_full_f15_has_block_and_org_scale_together() -> None:
    from saju_api.services.report_service import build_section_context
    from saju_engines.report_plan import build_section_plans

    spec, data = _report_data("RPT_FULL", None)
    plans = {p.section_id: p for p in build_section_plans(spec)}
    ctx = build_section_context(plans["F-15"], spec, data)
    assert "[직업 분야 근거" in ctx.body_prompt and "[직업 분야 지침" in ctx.body_prompt
    assert "[조직 규모 적합" in ctx.body_prompt
    other = build_section_context(plans["F-02"], spec, data)
    assert "[직업 분야 근거" not in other.body_prompt
    assert data.career_field_block() == data.career_field_block()  # 캐시·결정론
