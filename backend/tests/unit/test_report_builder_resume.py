"""ReportBuilder 중단 재개 — prior_sections 재사용·section_sink 부분 보존 (2026-10-06)."""

from __future__ import annotations

from pathlib import Path

from saju_engines.report_builder import ReportBuilder
from saju_engines.report_plan import build_section_plans
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.report import (
    ReportPeriod,
    ReportSpec,
    SectionContext,
    SectionPlan,
    SectionResult,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _spec() -> ReportSpec:
    return ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="health",
        period=ReportPeriod(start="2026-01-01", end="2026-12-31"),
    )


def _good_section_text(plan: SectionPlan) -> str:
    body = (
        "丙午 흐름에서 변화 에너지가 단계적으로 활성화돼요. "
        "근거는 丙午 세운 → 정관 활성 경로이며 신호 강도는 72점이에요. "
        "2026년에는 탐색에서 실행으로 넘어가는 결이 보여요. "
    )
    target = plan.target_chars.min
    return (body * (target // len(body) + 1))[: target + 50]


def _ctx(plan: SectionPlan, spec: ReportSpec) -> SectionContext:
    return SectionContext(
        section_id=plan.section_id,
        allowed_ganji=["丙午"], allowed_scores=[72], allowed_years=[2026],
        yongsin_element="土", evidence_paths=["丙午 세운 → 정관 활성"],
    )


class _Interrupt(RuntimeError):
    """세 번째 섹션에서 생성이 끊긴 상황(LLM 서비스 중단 모의)."""


def test_sink_collects_passed_sections_until_interrupt() -> None:
    """생성 도중 예외 → 그때까지 확정된 섹션이 sink 에 남는다(부분 보존 재료)."""
    kept: list[SectionResult] = []
    generated: list[str] = []

    def gen(plan, context, attempt):
        if len(generated) == 2:
            raise _Interrupt("suspended")
        generated.append(plan.section_id)
        return _good_section_text(plan), 10, 10

    builder = ReportBuilder(_DICTS, _ctx, gen, section_sink=kept.append)
    try:
        builder.build(_spec())
    except _Interrupt:
        pass
    assert [s.section_id for s in kept] == generated and len(kept) == 2
    assert all(s.passed for s in kept)


def test_prior_sections_are_reused_without_regeneration() -> None:
    """재개 — 통과 섹션은 LLM 을 다시 부르지 않고 그대로 채택, 나머지만 생성."""
    spec = _spec()
    plans = build_section_plans(spec)
    first_two = plans[:2]
    prior = {
        p.section_id: SectionResult(
            section_id=p.section_id, title=p.title, text=_good_section_text(p),
            attempts=1, passed=True,
        )
        for p in first_two
    }
    # 통과하지 못한 항목은 재사용하지 않는다(새로 생성 대상).
    prior[plans[2].section_id] = SectionResult(
        section_id=plans[2].section_id, title=plans[2].title, text="", passed=False,
    )
    generated: list[str] = []
    progress: list[tuple[int, int]] = []

    def gen(plan, context, attempt):
        generated.append(plan.section_id)
        return _good_section_text(plan), 10, 10

    builder = ReportBuilder(
        _DICTS, _ctx, gen, progress_fn=lambda d, t: progress.append((d, t)),
    )
    result = builder.build(spec, prior_sections=prior)
    assert result.status == "completed", result.failed_sections
    assert len(result.sections) == len(plans)
    assert generated == [p.section_id for p in plans[2:]]  # 앞 2개는 재호출 없음
    # 재사용 섹션 본문이 결과에 그대로 들어간다.
    assert result.sections[0].text == prior[plans[0].section_id].text
    # 진행 보고는 재사용 섹션도 센다(1..N 단조).
    assert [d for d, _ in progress] == list(range(1, len(plans) + 1))
