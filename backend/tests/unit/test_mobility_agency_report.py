"""리포트 — 이동 주체 미상 지시문 부착(2026-10-15 데굴님 지시 "리포트에도 동일하게").

섹션 후보에 직장·역할 이동(career_change)이 있으면 이벤트 후보 블록 뒤에 채팅과 같은 지시문이 붙고,
없으면 붙지 않는다. 섹션 본문 감사는 로그 전용(`mobility_agency_claims`, 채팅과 동일 어구).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.report_service import _ReportData, build_section_context
from saju_engines.mobility_agency import MOBILITY_AGENCY_DIRECTIVE, has_mobility_candidate
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


def test_luck_block_attaches_directive_only_with_mobility_candidate() -> None:
    data = _data()
    assert has_mobility_candidate(data.candidates), "커리어 집중 풀이 후보에 이동 사건 필요"
    with_mob = "\n".join(data.luck_block(data.candidates))
    assert MOBILITY_AGENCY_DIRECTIVE in with_mob
    others = [c for c in data.candidates if str(c.event_key) != "career_change"]
    without = "\n".join(data.luck_block(others))
    assert MOBILITY_AGENCY_DIRECTIVE not in without
    # 이벤트 후보 블록을 끈 호출(대운표만)에는 붙지 않는다.
    assert MOBILITY_AGENCY_DIRECTIVE not in "\n".join(
        data.luck_block(data.candidates, include_event_candidates=False)
    )


def test_career_luck_section_prompt_has_directive_and_natal_section_does_not() -> None:
    data = _data()
    plans = build_section_plans(_SPEC)
    j04 = build_section_context(next(p for p in plans if p.section_id == "J-04"), _SPEC, data)
    assert "[이동 주체 미상]" in j04.body_prompt
    j02 = build_section_context(next(p for p in plans if p.section_id == "J-02"), _SPEC, data)
    assert "[이동 주체 미상]" not in j02.body_prompt
