"""활동 키워드·개운 행동 사전 + J-07 배선 검증 (상담 사례 파생 P1·P2).

doc/v2_2/cases/1980_1122_job_report_case.md §5 — 사전은 reviewed:false 초안(서술 재료
전용), 블록 선별은 엔진 확정 용희기구한·원국 신살 기준 결정론(원칙 1·5). J-07에만
부착하고 감수 통과 후 타 테마 확장(2026-07-03 데굴님 확정 스코프).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_api.services.report_service import (
    _ReportData,
    build_section_context,
)
from saju_engines.dictionaries import schema_for
from saju_engines.report_plan import build_section_plans
from saju_engines.structural_context import (
    activity_keyword_lines,
    remedy_action_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"

# 사례 명식(1980-11-22 09:40 서울 남) — 용신 土·희신 火·기신 木·구신 水, 원국 현침.
_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male",
)
_SPEC = ReportSpec(
    product_code="RPT_FOCUS",
    subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
    topic="career", period=ReportPeriod(start="2026-07", end="2031-12"),
)


def _load(name: str) -> dict:
    return json.loads(
        (_DICTS / "interpretations" / name).read_text(encoding="utf-8")
    )


def test_dictionaries_validate_against_registered_schema() -> None:
    """두 사전이 SCHEMA_BY_PATH 등록 스키마를 통과하고 전 항목 reviewed:false다."""
    for name in ("activity_keyword_map.json", "remedy_action_map.json"):
        rel = f"interpretations/{name}"
        schema = schema_for(rel)
        assert schema is not None, f"{rel} 스키마 미등록"
        model = schema.model_validate(_load(name))
        dumped = json.dumps(model.model_dump(), ensure_ascii=False)
        assert '"reviewed": true' not in dumped  # 감수 전 초안 보장(원칙 5)


def test_activity_keyword_lines_deterministic_selection() -> None:
    """용신·희신은 '살리면', 기신·구신은 '기준', 원국 신살(현침)은 star 항목이 뽑힌다."""
    lines = activity_keyword_lines(
        favorable=[("土", "용신"), ("火", "희신")],
        cautious=[("木", "기신"), ("水", "구신")],
        natal_sinsal={"현침"},
        keyword_map=_load("activity_keyword_map.json"),
    )
    joined = "\n".join(lines)
    assert lines[0].startswith("[활동 키워드")
    assert "살리면 좋은 기운 土(용신)" in joined
    assert "살리면 좋은 기운 火(희신)" in joined
    assert "기준을 세울 기운 水(구신)" in joined
    assert "현침살" in joined and "글쓰기" in joined
    assert "직업 단정 금지" in lines[0]


def test_activity_keyword_lines_empty_when_no_match() -> None:
    """매칭 항목이 없으면 빈 목록(블록 미부착) — 헤더만 남는 블록 방지."""
    assert activity_keyword_lines([], [], set(), _load("activity_keyword_map.json")) == []


def test_remedy_action_lines_behavior_first_and_no_certainty() -> None:
    """개운 행동은 용신·희신 오행만 + not_magic 원칙 문구를 동반한다."""
    lines = remedy_action_lines(["土", "火"], _load("remedy_action_map.json"))
    joined = "\n".join(lines)
    assert "土 보완 행동" in joined and "火 보완 행동" in joined
    assert "水 보완 행동" not in joined  # 기신·구신 오행 미부착
    assert "결과를 보장" in joined and "반드시 된다" in joined  # 확언 금지 원칙


def test_j07_section_includes_activity_and_remedy_blocks() -> None:
    """J-07(직업 행동 전략)에 활동 키워드·개운 행동 블록과 번역 지시가 부착된다."""
    data = _ReportData(_BIRTH, _SPEC, date(2026, 7, 3), owner_id=None, subject_id=None)
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-07")
    ctx = build_section_context(plan, _SPEC, data)
    assert "[활동 키워드" in ctx.body_prompt
    assert "[개운 행동" in ctx.body_prompt
    assert "[활동 키워드 번역]" in ctx.body_prompt
    assert "[극복 아니라 관리]" in ctx.body_prompt
    assert "[운 품질 → 의사결정 태도]" in ctx.body_prompt


def test_j06_section_has_date_certainty_guard_but_no_keyword_block() -> None:
    """J-06(주목할 달)엔 시기 단정 금지만 붙고 활동 키워드 블록은 J-07 전용이다."""
    data = _ReportData(_BIRTH, _SPEC, date(2026, 7, 3), owner_id=None, subject_id=None)
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-06")
    ctx = build_section_context(plan, _SPEC, data)
    assert "[시기 단정 금지]" in ctx.body_prompt
    assert "[활동 키워드" not in ctx.body_prompt
