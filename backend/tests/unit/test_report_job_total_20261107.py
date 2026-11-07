"""리포트 잡 진행률 분모 — 생성 시점에 확장 후 섹션 수(2026-11-07 데굴님 "1/16으로 시작하던데").

이전엔 고정 목차 수로 시작해 생성 중 분모가 바뀌었다(총운 16→25). 세 상품 모두
`_expand_report_plans` 결과와 같아야 한다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import report_service
from saju_api.services.report_service import _ReportData, expected_section_total
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 11, 7)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-11-07",
)


def _spec(code: str, start: str, end: str, topic: str | None = None) -> ReportSpec:
    return ReportSpec(
        product_code=code, topic=topic,
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start=start, end=end),
    )


def _expanded(spec: ReportSpec) -> int:
    data = _ReportData(_BIRTH, spec, _TODAY)
    return len(report_service._expand_report_plans(build_section_plans(spec), data))


def test_expected_total_matches_expansion_for_all_products() -> None:
    full = _spec("RPT_FULL", "1980-01", "2070-12")
    year = _spec("RPT_YEAR", "2026-01", "2026-12")
    focus = _spec("RPT_FOCUS", "2026-01", "2030-12", topic="wealth")
    assert expected_section_total(_BIRTH, full, _TODAY) == _expanded(full) > 16
    assert expected_section_total(_BIRTH, year, _TODAY) == _expanded(year)
    assert expected_section_total(_BIRTH, focus, _TODAY) == _expanded(focus)
