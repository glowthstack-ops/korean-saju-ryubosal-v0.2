"""리포트/테마 운(運) 천간합 모드 블록 검증 (Phase 2a — 테마운세 적용 완성).

원국 합은 prefix(공용)로 이미 들어가고, 운 합은 luck_block(운 섹션 데이터)에 들어간다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male", apply_true_solar_time=False,
)
_SPEC = ReportSpec(
    product_code="RPT_FOCUS",
    subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
    topic="career", period=ReportPeriod(start="2024-01", end="2030-12"),
)


def _data() -> _ReportData:
    return _ReportData(_BIRTH, _SPEC, date(2026, 6, 15), owner_id=None, subject_id=None)


def test_luck_hap_lines_present_and_mode_aware() -> None:
    data = _data()
    lines = data.luck_hap_lines(data.candidates)
    assert lines  # 후보 기간 운 천간합 존재
    joined = " ".join(lines)
    assert any(k in joined for k in ("합화", "합반", "본신지합"))
    assert "운 " in joined  # 운 합 접두


def test_luck_block_section_includes_hap_block() -> None:
    """운 발현 섹션(J-04)에 '합 작용(운)' 블록이 들어간다."""
    data = _data()
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-04")
    ctx = build_section_context(plan, _SPEC, data)
    assert "[합 작용(운)" in ctx.body_prompt


def test_natal_section_has_no_luck_hap_block() -> None:
    """명식 섹션(J-02)은 운 데이터 미부착 — 운 합 블록 없음(원국 합은 prefix에 있음)."""
    data = _data()
    plan = next(p for p in build_section_plans(_SPEC) if p.section_id == "J-02")
    ctx = build_section_context(plan, _SPEC, data)
    assert "[합 작용(운)" not in ctx.body_prompt
