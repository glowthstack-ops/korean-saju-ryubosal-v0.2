"""보고서 생성 파이프라인 (v2.2 Phase 9, docs/10 2장).

ReportSpec → SectionPlan[](고정 목차) → 섹션별 컨텍스트 → LLM 생성(주입) →
정합성 검사(7장, 실패 섹션만 재생성 ≤2회) → 조립(표지/목차/부록 재현성 파라미터).

LLM 호출부는 함수 주입(generate_fn) — 테스트는 모의, 운영은 llm_client 경유
(sections 한도: 입력 5k/출력 3.5k, docs/09 8장). 페르소나는 생성 시점 스냅샷으로
고정(생성 도중 변경돼도 보고서 내 문체 일관 — docs/10 6장).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from saju_shared_types.report import (
    ReportCost,
    ReportResult,
    ReportSpec,
    SectionContext,
    SectionPlan,
    SectionResult,
)

from .report_checks import ReportChecker
from .report_plan import MAX_REGENERATIONS, build_section_plans

# generate_fn(plan, context, attempt) → (본문, 입력 토큰, 출력 토큰).
GenerateFn = Callable[[SectionPlan, SectionContext, int], tuple[str, int, int]]
# context_builder(plan, spec) → SectionContext (Topic Builder/모듈 실행 결과 직렬화).
ContextBuilder = Callable[[SectionPlan, ReportSpec], SectionContext]
# progress_fn(done, total) → None — 섹션 1개 완료마다 호출(잡 진행 업데이트용).
ProgressFn = Callable[[int, int], None]

_PRICES_PATH = Path(__file__).resolve().parents[3] / "config" / "model_prices.json"


def load_model_prices() -> dict[str, dict[str, float]]:
    """모델 단가표(설정 파일 분리 — docs/10 9장, 하드코딩 금지)."""
    data = json.loads(_PRICES_PATH.read_text(encoding="utf-8"))
    return data["prices"]


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """호출 원가 추정($)."""
    price = load_model_prices().get(model)
    if price is None:
        return 0.0
    return round(
        input_tokens / 1e6 * price["input"] + output_tokens / 1e6 * price["output"], 6
    )


class ReportBuilder:
    """섹션 생성→검사→재생성→조립 — 분석은 모듈/엔진이, LLM은 서술만."""

    def __init__(
        self,
        dictionaries_dir: Path,
        context_builder: ContextBuilder,
        generate_fn: GenerateFn,
        dict_version: str = "1.0.0",
        progress_fn: ProgressFn | None = None,
    ) -> None:
        """LLM·컨텍스트 빌더 주입(사이드이펙트는 서비스 계층 책임)."""
        self._checker = ReportChecker(dictionaries_dir)
        self._build_context = context_builder
        self._generate = generate_fn
        self._dict_version = dict_version
        self._progress = progress_fn

    def build(self, spec: ReportSpec, display_name: str = "회원") -> ReportResult:
        """보고서 생성 — dependsOn 순서 보장, 실패 섹션만 재생성(≤2회).

        2회 재생성 실패 섹션이 있으면 status='on_hold'(관리자 알림 대상) —
        부분 산출물은 보존한다.
        """
        plans = build_section_plans(spec)
        done: dict[str, SectionResult] = {}
        cost = ReportCost()
        yongsin: str | None = None

        for plan in plans:
            # dependsOn — 선행 섹션 실패 시 본 섹션은 시도하지 않음(일관성 보호).
            if any(dep in done and not done[dep].passed for dep in plan.depends_on):
                done[plan.section_id] = SectionResult(
                    section_id=plan.section_id, title=plan.title,
                    violations=["선행 섹션 실패로 미생성"],
                )
                continue

            context = self._build_context(plan, spec)
            if yongsin and context.yongsin_element is None:
                # F-04 확정 용신을 이후 섹션 검사 기준으로 전파(검사 4).
                context = context.model_copy(update={"yongsin_element": yongsin})

            result = self._generate_with_retry(plan, context, spec, display_name, cost)
            done[plan.section_id] = result
            if plan.section_id == "F-04" and result.passed:
                yongsin = context.yongsin_element
            # 섹션 1개 완료 — 잡 진행 업데이트(실패해도 생성은 계속).
            if self._progress is not None:
                try:
                    self._progress(len(done), len(plans))
                except Exception:  # noqa: BLE001 — 진행 보고 실패가 생성을 막지 않도록
                    pass

        sections = [done[p.section_id] for p in plans]
        failed = [s.section_id for s in sections if not s.passed]
        total_chars = sum(len(s.text) for s in sections if s.passed)
        return ReportResult(
            spec=spec,
            status="on_hold" if failed else "completed",
            sections=sections,
            failed_sections=failed,
            total_chars=total_chars,
            cost=cost,
            meta={
                "dict_version": self._dict_version,
                "persona_snapshot": spec.persona.model_dump(),
                "chart_variant": "original",  # 쌍둥이 active 변형은 호출 측이 덮어씀
                "subject_labels": [s.label for s in spec.subjects],
            },
        )

    def _generate_with_retry(
        self,
        plan: SectionPlan,
        context: SectionContext,
        spec: ReportSpec,
        display_name: str,
        cost: ReportCost,
    ) -> SectionResult:
        """섹션 1개 생성 — 정합성 실패 시 해당 섹션만 재생성(최대 2회)."""
        violations: list[str] = []
        text = ""
        in_tok = out_tok = 0
        attempts = 0
        for attempt in range(1 + MAX_REGENERATIONS):
            attempts = attempt + 1
            text, in_tok, out_tok = self._generate(plan, context, attempt)
            cost.calls += 1
            cost.input_tokens += in_tok
            cost.output_tokens += out_tok
            violations = self._checker.check_section(
                plan, context, text, spec.persona, display_name,
            )
            if not violations:
                return SectionResult(
                    section_id=plan.section_id, title=plan.title, text=text,
                    attempts=attempts, passed=True,
                    input_tokens=in_tok, output_tokens=out_tok,
                )
        return SectionResult(
            section_id=plan.section_id, title=plan.title, text=text,
            attempts=attempts, passed=False, violations=violations,
            input_tokens=in_tok, output_tokens=out_tok,
        )


def assemble_markdown(result: ReportResult) -> str:
    """조립 — 표지/자동 목차/본문/부록(재현성 파라미터). docx/pdf 변환은 출시 단계.

    docs/10 8장: 표지(상품명/대상/생성일/사전 버전), 자동 목차, 부록에 dictVersion·
    생성 파라미터(chartVariant 포함).
    """
    spec = result.spec
    subjects = ", ".join(result.meta.get("subject_labels", []))
    lines = [
        f"# {spec.product_code} 풀이 보고서",
        "",
        f"- 대상: {subjects}",
        f"- 기간: {spec.period.start} ~ {spec.period.end}",
        f"- 사전 버전: {result.meta.get('dict_version')}",
        "",
        "## 목차",
    ]
    for s in result.sections:
        lines.append(f"- {s.section_id}. {s.title}")
    for s in result.sections:
        lines += ["", f"## {s.section_id}. {s.title}", "", s.text]
    lines += [
        "", "## 부록 — 생성 파라미터(재현성)", "",
        f"- dictVersion: {result.meta.get('dict_version')}",
        f"- chartVariant: {result.meta.get('chart_variant')}",
        f"- persona: {json.dumps(result.meta.get('persona_snapshot'), ensure_ascii=False)}",
    ]
    return "\n".join(lines)
