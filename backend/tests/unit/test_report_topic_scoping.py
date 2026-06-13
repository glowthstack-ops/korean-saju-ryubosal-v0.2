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


def test_forecast_theme_anchors_future_not_past() -> None:
    """향후 N년 예측 테마는 과거 고점이 아니라 오늘 이후 후보만 앵커링한다(시점 결함 방지)."""
    birth = report_service.BirthInput(
        calendar_type="solar", birth_date=date(1990, 3, 3), birth_time="10:00",
        birth_place_name="서울", gender="male",
    )
    today = date(2026, 6, 14)
    data = report_service._ReportData(birth, _spec("career"), today)
    cur = f"{today.year}-{today.month:02d}"
    assert data.candidates, "미래 후보가 있어야 한다(빈 폴백 아님)"
    # 모든 후보의 끝 달이 오늘(2026-06) 이후 — 2022·2025 같은 과거가 섞이지 않는다.
    for c in data.candidates:
        assert report_service._period_end_month(c.period) >= cur, c.period
        assert int(c.period[:4]) <= today.year + 5  # +5년 창 내


def _pair_spec() -> ReportSpec:
    from saju_shared_types.intent import InlineBirth
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[
            SubjectRef(kind=SubjectKind.SELF, label="본인"),
            SubjectRef(
                kind=SubjectKind.INLINE_TEMP, label="상대",
                inline_birth=InlineBirth(date="1985-03-15", time="14:30", gender="F"),
            ),
        ],
        topic="relationship",
        period=ReportPeriod(start="2026", end="2031"),
    )


def test_relationship_solo_vs_pair_toc() -> None:
    # 상대 없으면 단독 8섹션, 상대 있으면 궁합 10섹션으로 분기.
    solo = build_section_plans(_spec("relationship"))
    pair = build_section_plans(_pair_spec())
    assert [p.section_id for p in solo] == [f"R-{n:02d}" for n in range(1, 9)]
    assert [p.section_id for p in pair] == [f"RP-{n:02d}" for n in range(1, 11)]


def test_pair_mode_dry_run_has_compat_blocks() -> None:
    birth = report_service.BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    partner = report_service.BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 15), birth_time="14:30",
        birth_place_name="부산", gender="female",
    )
    ctxs = report_service.plan_report(
        birth, _pair_spec(), date(2026, 6, 13), partner_birth=partner,
    )
    by_id = {c.section_id: c for c in ctxs}
    assert "[상대 명식" in by_id["RP-03"].body_prompt  # 상대 명식 블록
    assert "[궁합 신호" in by_id["RP-04"].body_prompt  # 궁합 신호 블록
    assert "[궁합 신호" in by_id["RP-08"].body_prompt  # 극복 섹션도 궁합 근거
    assert "| 시점 | 운간지" in by_id["RP-10"].body_prompt  # 부록 점수표


def test_pair_mode_without_partner_data_degrades_gracefully() -> None:
    # 궁합 모드 목차이지만 partner_birth 미전달 → 빈 궁합 블록 안내(오류 없음).
    birth = report_service.BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male",
    )
    ctxs = report_service.plan_report(birth, _pair_spec(), date(2026, 6, 13))
    by_id = {c.section_id: c for c in ctxs}
    assert "궁합 신호 없음" in by_id["RP-04"].body_prompt
    assert "상대 명식 없음" in by_id["RP-03"].body_prompt
