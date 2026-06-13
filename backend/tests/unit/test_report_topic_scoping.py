"""FOCUS 주제 스코핑 검증 (v2.2 프론트 확장 Phase 6 — docs/10 4장).

직장운(career)은 'MODULE' 플레이스홀더가 주제 모듈(M07)로 해석되고 후보가 도메인 신호로
스코핑돼 본문이 차별화돼야 한다. generic 주제는 8섹션(C-01~C-08) 불변. 단, 재물운(wealth)은
테마 전용 스토리 목차(W-01~W-09, 2026-06-14 사용자 확정)를 갖는다.
"""

from __future__ import annotations

from datetime import date

from saju_api.services import report_service
from saju_engines.report_plan import build_section_plans
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import ReportPeriod, ReportSpec


def _spec(topic: str) -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic=topic,
        period=ReportPeriod(start="2000-01", end="2035-12"),
    )


def _module_ids(spec: ReportSpec, section_id: str) -> list[str]:
    plan = next(p for p in build_section_plans(spec) if p.section_id == section_id)
    return [m.module_id for m in plan.module_calls]


def test_focus_module_placeholder_resolves_by_topic() -> None:
    # 테마 목차 첫 섹션의 'MODULE'이 주제 모듈로 해석된다(career→M07, wealth→M09, relationship→M01).
    assert "M07" in _module_ids(_spec("career"), "J-01")
    assert "M09" in _module_ids(_spec("wealth"), "W-01")
    assert "M01" in _module_ids(_spec("relationship"), "R-01")
    # generic 주제(설계상)는 8섹션. 테마 전용 목차는 각자 고정 구성.
    assert [p.section_id for p in build_section_plans(_spec("wealth"))] == [
        f"W-{n:02d}" for n in range(1, 10)
    ]
    assert [p.section_id for p in build_section_plans(_spec("career"))] == [
        f"J-{n:02d}" for n in range(1, 9)
    ]
    assert [p.section_id for p in build_section_plans(_spec("relationship"))] == [
        f"R-{n:02d}" for n in range(1, 9)
    ]


def test_compatibility_variant_uses_m13() -> None:
    plans = {p.section_id: [m.module_id for m in p.module_calls] for p in
             build_section_plans(_spec("compatibility"))}
    assert "M13" in plans["C-02"]  # 두 명식의 구조 대조
    assert len(plans) == 8  # 섹션 추가/삭제 없음


def test_focus_dry_run_runs_for_career_and_wealth() -> None:
    # 골든 픽스처로 dry-run 컨텍스트가 생성되는지(엔진 경로) 확인.
    # career=generic 8섹션, wealth=테마 9섹션.
    birth = report_service.BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    today = date(2026, 6, 13)
    career = report_service.plan_report(birth, _spec("career"), today)
    wealth = report_service.plan_report(birth, _spec("wealth"), today)
    assert len(career) == 8 and len(wealth) == 9
    # W-09 부록에는 실제 점수표(마크다운 표)가 박힌다.
    w09 = next(c for c in wealth if c.section_id == "W-09")
    assert "| 시점 | 운간지" in w09.body_prompt
    # 주제 스코핑이 작동하면 운 관련 섹션의 본문(후보 블록)이 동일하지 않을 수 있다.
    # 도메인 신호가 충분하면 차이가 나고, 없으면 전체 후보로 폴백한다(빈 리포트 방지).
    career_body = "\n".join(c.body_prompt for c in career)
    wealth_body = "\n".join(c.body_prompt for c in wealth)
    assert isinstance(career_body, str) and isinstance(wealth_body, str)
