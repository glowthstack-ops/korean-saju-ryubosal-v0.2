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
    serialize_chart_prefix,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.report_builder import ReportBuilder
from saju_engines.report_event_input import precise_candidate_clusters, score_table_lines
from saju_engines.report_plan import build_section_plans
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN as _EVENT_DOMAIN_V2
from saju_shared_types.events import EventCandidate
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.report import ReportResult, ReportSpec, SectionContext, SectionPlan

from . import llm_client
from .manse_service import calculate
from .personalization import fetch_personal_inputs

_BACKEND = Path(__file__).resolve().parents[4]
_DICTS = _BACKEND / "dictionaries"
_SCORE_LEVELS = {GanjiLevel.YEAR, GanjiLevel.MONTH}
_TOP_CANDIDATES = 8
# 이벤트 종류 → 도메인(21키 EventKeyV2 기준, Phase 7). FOCUS 주제 스코핑에 쓴다.
_EVENT_DOMAIN: dict[str, str] = {str(k): v for k, v in _EVENT_DOMAIN_V2.items()}
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
    # ── 재물운 테마 전용(W-01~W-09) ──
    "W-01": "핵심만 5줄 이내로 요약할 것 — 어느 시점에 무엇이, 확장/변동/주의 중 무엇인지.",
    "W-02": "명식에서 드러나는 재물에 대한 성향·태도(정재/편재·안정/확장 지향)를 짧게 서술할 것.",
    "W-03": "재성(정재·편재)·재성궁(일지·월지)·식상생재 경로·재고 등 재물 '구조'만 설명할 것.",
    "W-04": "운에서 재물을 어떻게 모으고 키우는지(축재) 발현 형태를 서술할 것 — 발생≠결과.",
    "W-05": "횡재(편재)·상속(인성·재고)은 가능성으로만. 당첨·복권 단정 금지(로또 번호 거부).",
    "W-06": "향후 5년 재물 흐름을 시점 클러스터로 타임라인화할 것 — 같은 시점 사건은 묶어서.",
    "W-07": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
    "W-08": "행동 전략을 시기별로 구체화 — 확장/소액 검증/계약 보류/현금 확보/레버리지 금지 단위.",
    "W-09": "아래 점수표를 그대로 표로 제시하고, 표 밖 새 수치를 만들지 말 것.",
    # ── 직업·사업운 테마 전용(J-01~J-08) ──
    "J-01": "핵심만 5줄 이내로 요약할 것 — 어느 시점에 무엇이, 변동/안정/도전 중 무엇인지.",
    "J-02": "명식에 드러나는 일에 대한 태도(관성/식상·조직형/자유형, 안정/도전)를 짧게 서술할 것.",
    "J-03": "격국·관성(직장)·재성(사업·보상)·식상(표현·기술) 등 직업 '구조'만 설명할 것.",
    "J-04": "운에서 직업이 어떻게 움직이는지(이직·승진·창업·확장) 발현 형태만 — 발생≠결과.",
    "J-05": "향후 5년 직업 흐름을 시점 클러스터로 타임라인화할 것 — 같은 시점 사건은 묶어서.",
    "J-06": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
    "J-07": "행동 전략을 시기별로 — 이동/유지/준비/네트워킹/도전 보류 단위. 승진·합격 단정 금지.",
    "J-08": "아래 점수표를 그대로 표로 제시하고, 표 밖 새 수치를 만들지 말 것.",
    # ── 관계·애정운 테마 전용(R-01~R-08, 단독 모드 베이스) ──
    "R-01": "핵심만 5줄 이내로 — 어느 시점에 어떤 인연 에너지(만남/안정/갈등)가 활성인지.",
    "R-02": "명식에 드러나는 애정 성향(재성/관성·도화·표현 방식, 거리감/몰입)을 짧게 서술할 것.",
    "R-03": "일지(배우자궁)·재성/관성·도화/홍염 등 배우자·인연 '구조'만. 단정·낙인 표현 금지.",
    "R-04": "운에서 인연이 어떻게 움직이는지(만남·결혼 신호·갈등·정리) 발현 형태만 — 발생≠결과.",
    "R-05": "향후 5년 애정 흐름을 시점 클러스터로 타임라인화할 것 — 같은 시점 사건은 묶어서.",
    "R-06": "주목할 달을 정밀 십성·관계로 풀되, 같은 원국 설명을 반복하지 말 것.",
    "R-07": "행동 전략을 — 다가서기/거리두기/대화/정리 준비 단위. 상대 강요·운명론 표현 금지.",
    "R-08": "아래 점수표를 그대로 표로 제시하고, 표 밖 새 수치를 만들지 말 것.",
}
_DEFAULT_GUIDE = "아래 데이터 블록의 사실만 사용해 섹션 제목에 맞는 이야기로 서술할 것."
# 명식 구조 섹션(운 데이터 블록 미부착) — 인사·원국 재설명 1회 원칙.
_NATAL_SECTIONS = {
    "F-01", "F-02", "F-03", "F-04", "F-05", "F-06", "C-02",
    "W-02", "W-03", "J-02", "J-03", "R-02", "R-03",
}
# 부록 점수표 섹션(실제 표 부착).
_SCORE_TABLE_SECTIONS = {"C-08", "W-09", "J-08", "R-08"}


class _ReportData:
    """보고서 1건의 공유 데이터 — 섹션마다 재계산하지 않는다(사전계산 우선)."""

    def __init__(
        self, birth: BirthInput, spec: ReportSpec, today: date,
        *, owner_id: str | None = None, subject_id: str | None = None,
    ) -> None:
        chart_birth = birth.model_copy(update={"reference_date": today})
        self.result: ManseV2Result = calculate(chart_birth)
        self.scorer = EventEngineV2(_DICTS)
        # 개인화(저장된 subject 한정): 현실 신호 시그니처 + 활성 코호트 → LEI 정렬축.
        # 미설정·실패 시 무개인화 폴백(규칙11).
        sig, cohort = fetch_personal_inputs(owner_id, subject_id, self.result)
        scored = self.scorer.score_legacy_personalized(
            self.result, levels=_SCORE_LEVELS, signature=sig, cohort=cohort,
        )
        in_period = [
            c for c in scored
            if spec.period.start[:4] <= c.period[:4] <= spec.period.end[:4]
        ]
        # LEI 정렬축(현실적합>과거유사>점수) — 개인 시그니처 미배선 시 -c.score와 동치.
        pool = sorted(in_period or scored, key=lambda c: (-c.life_fit, -c.personal_match, -c.score))
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
        lines.append(
            "[이벤트 후보 — 시점 클러스터·정밀 십성/관계. 점수는 확정값, 재계산 금지. "
            "아래 십성·관계 라벨만 사용하고 '재성 지지 충' 같은 임의 표현을 만들지 말 것]"
        )
        lines += precise_candidate_clusters(self.result, self.candidates)
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
    sid = plan.section_id
    is_natal_section = sid in _NATAL_SECTIONS
    lines = list(data.prefix_lines)
    lines += [
        "",
        f"[섹션 과제 — {sid}. {plan.title}]",
        f"분량: {plan.target_chars.min}~{plan.target_chars.max}자(공백 포함).",
        guide,
        "입력에 없는 간지·점수·연도를 만들지 말 것. 단정 표현 금지.",
        "인사말·원국 전체 재설명은 생략하고(앞 섹션에서 1회면 충분) 이 섹션 과제에 바로 집중할 것.",
    ]
    if sid in _SCORE_TABLE_SECTIONS:
        lines.append("")
        lines.append("[점수표 — 아래 표를 그대로 인용. 표 밖 새 수치 생성 금지]")
        lines += score_table_lines(data.result, data.candidates)
    elif not is_natal_section:
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
    *,
    owner_id: str | None = None,
    subject_id: str | None = None,
) -> ReportResult:
    """보고서 실생성 — ReportBuilder에 실데이터 컨텍스트 + llm_client 주입.

    owner_id·subject_id가 있으면 개인화(현실 신호 시그니처·코호트) LEI 정렬축이 후보 선별에 반영.

    Raises:
        RuntimeError: LLM 키 미설정(메인·폴백 모두) — 호출 측에서 dry-run 안내.
    """
    if not llm_client.is_available():
        raise RuntimeError("LLM API 키 미설정 — plan_report(dry-run)로 검증하세요")
    data = _ReportData(
        birth, spec, today or date.today(), owner_id=owner_id, subject_id=subject_id,
    )
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
