"""보고서 생성 서비스 (v2.2.1 PR-E — Phase 9 파이프라인 운영 배선, docs/10).

ReportBuilder(테스트 전용이던 골격)에 **실데이터 컨텍스트 빌더**와 LLM 호출을
주입한다. 섹션 프롬프트 = 고정 prefix(원국·명식 구조+해석 자료 — 대화와 동일,
캐시 적중) + 섹션 과제 + 섹션별 데이터 블록(대운표·이벤트 후보·근거 경로).

분석은 엔진(만세 계산·스코어링)이, 본 서비스는 직렬화와 호출만 한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.context_reducer import (
    build_birth_summary,
    event_ko,
    polarity_ko,
    serialize_chart_prefix,
)
from saju_engines.event_scoring import EventScorer
from saju_engines.report_builder import ReportBuilder
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.events import EventCandidate
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.report import ReportResult, ReportSpec, SectionContext, SectionPlan

from . import llm_client
from .manse_service import calculate

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_SCORE_LEVELS = {GanjiLevel.YEAR, GanjiLevel.MONTH}
_TOP_CANDIDATES = 8
# 이벤트 종류 → 도메인(EventKey 기준). FOCUS 주제 스코핑에 쓴다. compatibility는 쌍방(M13)
# 으로 다뤄 여기서 필터하지 않는다. 매핑에 없는 키(contract·lawsuit·travel 등)는 일반.
_EVENT_DOMAIN: dict[str, str] = {
    "career_change": "career", "promotion": "career", "resignation": "career",
    "business_start": "career",
    "relationship_start": "relationship", "relationship_end": "relationship",
    "marriage": "relationship", "childbirth": "relationship", "family_change": "relationship",
    "relocation": "relocation",
    "wealth_change": "wealth", "income_change": "wealth", "expense_risk": "wealth",
    "windfall": "wealth", "speculation_risk": "wealth", "asset_volatility": "wealth",
    "education_start": "education", "education_complete": "education", "exam": "education",
    "health_issue": "health", "surgery": "health",
}
_TOPIC_DOMAINS = set(_EVENT_DOMAIN.values())

# 섹션별 작성 지침(docs/10 3·4장 데이터소스 요약 — 목차 규격은 report_plan이 강제).
_SECTION_GUIDES: dict[str, str] = {
    "F-01": "사주 원국의 전체 그림을 소개할 것 — 4주 구성과 각 주의 십성·운성을 쉬운 비유로.",
    "F-02": "일간 글자의 물상과 일주 서사를 중심으로 타고난 기질을 풀어낼 것.",
    "F-03": "원국 십성 구성([명식 해석 자료]의 십성 발췌)을 엮어 사회적 성향을 서술할 것.",
    "F-04": "강약·격국·용신 판정과 그 근거를 설명할 것 — 용신 오행을 명시적으로 표기할 것.",
    "F-05": "신살·공망·특수 구조를 양면(빛/그림자)으로 설명할 것 — 신살은 보조 자료임을 전제.",
    "F-06": "앞 섹션들의 재료를 종합해 성격·취향·행동 패턴의 이야기로 묶을 것.",
    "F-22": "간지 달력표를 요약하고 본문에 쓴 용어를 짧게 풀이할 것.",
    "C-01": "주제와 기간의 핵심 신호를 3~5줄로 요약할 것.",
    "C-02": "주제와 관련된 원국 글자(십성·궁위·관계)만 골라 구조를 설명할 것.",
    "C-04": "이벤트 후보 표의 시기·점수·동반 신호를 타임라인으로 서술할 것.",
    "C-08": "근거 경로와 점수표를 그대로 정리해 부록으로 제시할 것.",
}
_DEFAULT_GUIDE = "아래 데이터 블록의 사실만 사용해 섹션 제목에 맞는 이야기로 서술할 것."


class _ReportData:
    """보고서 1건의 공유 데이터 — 섹션마다 재계산하지 않는다(사전계산 우선)."""

    def __init__(self, birth: BirthInput, spec: ReportSpec, today: date) -> None:
        chart_birth = birth.model_copy(update={"reference_date": today})
        self.result: ManseV2Result = calculate(chart_birth)
        self.scorer = EventScorer(_DICTS)
        scored = self.scorer.score(self.result, levels=_SCORE_LEVELS)
        in_period = [
            c for c in scored
            if spec.period.start[:4] <= c.period[:4] <= spec.period.end[:4]
        ]
        pool = sorted(in_period or scored, key=lambda c: -c.score)
        # 주제 스코핑(FOCUS): 해당 도메인 신호를 가진 후보만 남겨 직장운·금전운 본문을
        # 차별화한다. 도메인 후보가 없으면 빈 리포트 방지를 위해 전체를 유지한다.
        if spec.product_code == "RPT_FOCUS" and spec.topic in _TOPIC_DOMAINS:
            domain_pool = [c for c in pool if _EVENT_DOMAIN.get(str(c.event_key)) == spec.topic]
            pool = domain_pool or pool
        self.candidates: list[EventCandidate] = pool[:_TOP_CANDIDATES]
        self.summary = build_birth_summary(self.result)
        self.prefix_lines = serialize_chart_prefix(
            self.summary, build_chart_interpretation(self.result),
        )
        self.evidence_paths = [
            " → ".join(self.scorer.readable_path(c)) for c in self.candidates[:3]
            if self.scorer.readable_path(c)
        ]
        self.allowed_ganji = self._collect_ganji()
        self.allowed_years = self._collect_years(spec)
        self.allowed_scores = sorted({c.score for c in self.candidates})

    def _collect_ganji(self) -> list[str]:
        ganji = list(self.summary.pillars.values())
        lc = self.result.luck_cycles
        if lc is not None:
            ganji += [d.ganji for d in lc.daewoon_table]
            ganji += [p.ganji for p in [*lc.yearly_luck, *lc.monthly_luck]]
        return sorted(set(ganji))

    def _collect_years(self, spec: ReportSpec) -> list[int]:
        years = {int(c.period[:4]) for c in self.candidates if c.period[:4].isdigit()}
        years |= {int(spec.period.start[:4]), int(spec.period.end[:4])}
        lc = self.result.luck_cycles
        if lc is not None:
            for d in lc.daewoon_table:
                years.update(range(d.approx_start_date.year, d.approx_end_date.year + 1))
        return sorted(years)

    def luck_block(self) -> list[str]:
        """[대운표]+[이벤트 후보 Top] — 운 관련 섹션의 데이터 블록."""
        lines = ["[대운표]"]
        lc = self.result.luck_cycles
        if lc is not None:
            for d in lc.daewoon_table:
                lines.append(
                    f"대운 {d.ganji} ({d.approx_start_date.year}-{d.approx_end_date.year}, "
                    f"{d.start_age}-{d.start_age + 9}세)"
                )
        lines.append("")
        lines.append("[이벤트 후보 Top — 점수는 확정값, 재계산 금지]")
        for c in self.candidates:
            signals = " / ".join(
                dict.fromkeys(s.effect or s.name for s in c.signals[:3])
            )
            lines.append(
                f"{event_ko(c.event_key)} @ {c.period} {c.score}점 · "
                f"{polarity_ko(str(c.polarity))}"
                + (f" · 동반 신호: {signals}" if signals else "")
            )
        if self.evidence_paths:
            lines.append("")
            lines.append("[근거 경로 — 최소 1개를 본문에 그대로 인용할 것]")
            lines += self.evidence_paths
        return lines


def build_section_context(
    plan: SectionPlan, spec: ReportSpec, data: _ReportData
) -> SectionContext:
    """섹션 1개의 실데이터 컨텍스트(docs/06 계약 + docs/10 검사 기준)."""
    yongsin = (
        data.summary.useful_gods.yongsin[0]
        if plan.section_id == "F-04" and data.summary.useful_gods.yongsin
        else None
    )
    guide = _SECTION_GUIDES.get(plan.section_id, _DEFAULT_GUIDE)
    is_natal_section = plan.section_id in ("F-01", "F-02", "F-03", "F-04", "F-05", "F-06", "C-02")
    lines = list(data.prefix_lines)
    lines += [
        "",
        f"[섹션 과제 — {plan.section_id}. {plan.title}]",
        f"분량: {plan.target_chars.min}~{plan.target_chars.max}자(공백 포함).",
        guide,
        "입력에 없는 간지·점수·연도를 만들지 말 것. 단정 표현 금지.",
    ]
    if not is_natal_section:
        lines.append("")
        lines += data.luck_block()
    elif data.evidence_paths:
        # 명식 섹션도 근거 인용 의무(docs/10 — 섹션당 evidence path ≥1).
        lines += ["", "[근거 경로 — 최소 1개를 본문에 그대로 인용할 것]", *data.evidence_paths]
    subject_label = spec.subjects[0].label if spec.subjects else "본인"
    return SectionContext(
        section_id=plan.section_id,
        subject_label=subject_label,
        allowed_ganji=data.allowed_ganji,
        allowed_scores=data.allowed_scores,
        allowed_years=data.allowed_years,
        yongsin_element=yongsin,
        evidence_paths=data.evidence_paths,
        multi_subject=len(spec.subjects) > 1,
        body_prompt="\n".join(lines),
    )


def plan_report(
    birth: BirthInput, spec: ReportSpec, today: date | None = None
) -> list[SectionContext]:
    """dry-run — 전 섹션의 실데이터 컨텍스트만 생성(LLM 미호출, 검증·개발용)."""
    data = _ReportData(birth, spec, today or date.today())
    return [build_section_context(p, spec, data) for p in build_section_plans(spec)]


def generate_report(
    birth: BirthInput,
    spec: ReportSpec,
    today: date | None = None,
    display_name: str = "회원",
) -> ReportResult:
    """보고서 실생성 — ReportBuilder에 실데이터 컨텍스트 + llm_client 주입.

    Raises:
        RuntimeError: LLM 키 미설정(메인·폴백 모두) — 호출 측에서 dry-run 안내.
    """
    if not llm_client.is_available():
        raise RuntimeError("LLM API 키 미설정 — plan_report(dry-run)로 검증하세요")
    data = _ReportData(birth, spec, today or date.today())
    call_type = (
        "report_full_section" if spec.product_code == "RPT_FULL" else "report_focus_section"
    )
    persona_block = None
    try:
        from saju_engines.persona import PersonaEngine

        persona_block = PersonaEngine(_DICTS).build_block(spec.persona, display_name)
    except ValueError:
        persona_block = None

    def generate_fn(plan: SectionPlan, context: SectionContext, attempt: int):
        system = llm_client._SYSTEM_PROMPT
        if persona_block:
            system = system + "\n\n" + persona_block
        prompt = context.body_prompt
        if attempt > 0:
            prompt += (
                f"\n\n[재생성 {attempt}회차] 직전 응답이 정합성 검사에 실패했다 — "
                "분량·간지·점수·근거 인용 규칙을 다시 확인해 작성할 것."
            )
        text = llm_client.generate_reading(
            prompt, call_type=call_type, system=system,
            product_code=f"{spec.product_code}:{plan.section_id}",
        )
        return text, 0, len(text)  # 토큰은 llm_client 장부가 집계(cached 포함)

    builder = ReportBuilder(
        dictionaries_dir=_DICTS,
        context_builder=lambda plan, s: build_section_context(plan, s, data),
        generate_fn=generate_fn,
    )
    return builder.build(spec, display_name=display_name)
