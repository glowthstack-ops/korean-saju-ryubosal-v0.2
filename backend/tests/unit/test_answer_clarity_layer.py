"""명확한 답 계약(2026-08-10 테스터 피드백) + 리포트 문서 서술 레이어 배선 검증.

테스터 공통 피드백("그래서 어쩌라고 — 명확하지 않아 더 답답")의 반영:
①ANSWER_CLARITY_DIRECTIVE가 챗·리포트 양쪽에 상시 주입되는가
②문서·계약 주의점/대비 블록이 리포트 도메인 섹션(career/relocation)에 조건부 주입되는가
(조건 미성립 명식·비도메인 섹션은 미주입 — 기존 프롬프트 불변).
전부 서술 전용(inert) — 점수·판정·목차 불변.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.report_plan import build_section_plans
from saju_engines.structural_context import ANSWER_CLARITY_DIRECTIVE
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_SPEC = ReportSpec(
    product_code="RPT_FOCUS",
    subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
    topic="career", period=ReportPeriod(start="2026-01", end="2030-12"),
)


def _birth(birth_date: str) -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date=birth_date, birth_time="10:30",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    )


def _data(birth_date: str) -> _ReportData:
    return _ReportData(_birth(birth_date), _SPEC, date(2026, 8, 10))


def test_answer_clarity_directive_invariants() -> None:
    """계약 핵심 불변식 — 3진 판정 선언·조건문 번역·결과어 번역·중요도 순 서술을 명시한다."""
    for needle in ("유리/불리/조건부", "조건문으로 번역", "결과어로 번역", "중요한 것부터"):
        assert needle in ANSWER_CLARITY_DIRECTIVE, needle
    # 단정 금지 원칙과의 양립 명시 — 사건 성사·발생 단정 요구가 아님을 계약 안에서 밝힌다.
    assert "단정하라는 뜻이 아니다" in ANSWER_CLARITY_DIRECTIVE


def test_answer_clarity_in_chat_prompt() -> None:
    """챗 — 모든 실질 풀이 질문의 trailing에 상시 주입."""
    import saju_api.services.chat_service as chat_service

    res = chat_service.chat(
        _birth("1988-01-10"), "올해 하반기 운세 어때?", date(2026, 8, 10), dry_run=True,
    )
    assert res.prompt_preview is not None
    assert "[명확한 답 계약" in res.prompt_preview


def test_answer_clarity_in_report_prefix() -> None:
    """리포트 — 전 섹션 공통 prefix에 주입(chat과 공용 상수)."""
    assert ANSWER_CLARITY_DIRECTIVE in _data("1988-01-10").prefix_lines


def test_report_career_section_gets_document_block() -> None:
    """인성 과다 명식 × career 도메인 섹션(J-05) — 주의점 블록 + 물상 디렉티브 주입."""
    data = _data("1988-01-10")  # 인성군 30% — 주의점(묶는 문서) 성립
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-05")
    body = build_section_context(plan, _SPEC, data).body_prompt
    assert "[문서·계약 주의점" in body
    assert "[문서운 물상 어휘" in body


def test_report_natal_section_no_document_block() -> None:
    """같은 명식이라도 비도메인 섹션(J-02 명식)에는 미주입(도메인 한정)."""
    data = _data("1988-01-10")
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-02")
    body = build_section_context(plan, _SPEC, data).body_prompt
    assert "[문서·계약 주의점" not in body


def test_report_neutral_chart_no_document_block() -> None:
    """조건 미성립 명식(인성 한신·적정 세력) — career 섹션에도 미주입(기존 불변)."""
    data = _data("1988-03-10")  # 인성 18%·한신 — 주의점·대비 모두 미성립
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-05")
    body = build_section_context(plan, _SPEC, data).body_prompt
    assert "[문서·계약 주의점" not in body
    assert "[문서·계약 대비 관점" not in body
