"""Topic Context Builder (v2.2 Phase 2.5 T2.5.6, docs/09 4장 — 모듈 전체 15종 규격).

각 모듈은 `(subjects, period, LuckComposite[], dictionaries) => TopicContext` 순수 함수다.
**M01~M15가 전체이며 새 주제는 모듈 추가로만 대응한다(기존 모듈에 분기 추가 금지).**

이번 구현: M07(career). M03(trait_mapping 사전)·M10(이사 — region_elements/housing_rules
사전 + S1~S10)·M15(format_slots 템플릿)는 전용 사전 신설이 필요해 후속 단위로 보류.
나머지 모듈은 등록만 된 계획 상태(빌더 미구현 — 호출 시 NotImplementedError).
"""

from __future__ import annotations

from collections.abc import Callable

from saju_shared_types.intent import SubjectRef
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.topic_context import (
    CalendarContextEntry,
    Finding,
    PeriodSpec,
    StyleRules,
    TimeSeriesPoint,
    TokenBudget,
    TopicContext,
)

from .llm_guard import CALL_LIMITS

# 모듈 전체 목록 (docs/09 4장 표 — id, 담당 질의, 구현 여부는 레지스트리로 관리).
MODULES: dict[str, str] = {
    "M01": "love_timing",
    "M02": "marriage",
    "M03": "personality_traits",
    "M04": "parents_fortune",
    "M05": "children",
    "M06": "workplace_relations",
    "M07": "career",
    "M08": "business",
    "M09": "wealth",
    "M10": "relocation_composite",
    "M11": "health",
    "M12": "education_exam",
    "M13": "bond_compare",
    "M14": "past_validation",
    "M15": "lifestyle",
}

BuilderFn = Callable[[list[SubjectRef], PeriodSpec, list[LuckComposite]], TopicContext]

# 대화형 단건 기준 예산(docs/09 8장 chat_single) — 출력 글자수는 초안(검수 대상).
_DEFAULT_BUDGET = TokenBudget(
    max_input_tokens=CALL_LIMITS["chat_single"].max_input_tokens,
    max_output_chars=1_800,
)

# 단정 표현 금지(절대 원칙 3) — 모든 모듈 공통 기본.
_BASE_STYLE = StyleRules(
    prohibited_expressions=["반드시", "확실히 ~한다", "100% ~된다"],
    tone_notes=["단정 대신 단계(awareness→exploration→action→decision) 표현 사용"],
)


def _in_period(period_key: str, period: PeriodSpec) -> bool:
    """period_key('2026'/'2026-06'/'2026-06-10')가 기간 범위에 드는지(문자열 비교).

    ISO 정렬 가능 라벨 전제. 연 키는 'start[:4] <= key <= end[:4]'로 비교한다.
    """
    if len(period_key) == 4:
        return period.start[:4] <= period_key <= period.end[:4]
    return period.start[: len(period_key)] <= period_key <= period.end[: len(period_key)]


def _calendar_context(composites: list[LuckComposite]) -> list[CalendarContextEntry]:
    """압축 간지달력 — 선택된 composite의 간지+상위 맥락만(전체 달력 투입 금지)."""
    return [
        CalendarContextEntry(
            period_key=c.period_key,
            ganji=f"{c.ganji.stem}{c.ganji.branch}",
            parent_daewoon=c.parent_context.daewoon,
            parent_year=c.parent_context.year,
        )
        for c in composites
    ]


def build_career_context(
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
) -> TopicContext:
    """M07 career — 취업/이직/승진/퇴사 (docs/09 4장: natal+daewoon+year+month 참조).

    LuckComposite의 career 도메인 신호를 기간 내 시계열로 합산하고, 상위 시기를
    findings로 확정한다. 모든 수치는 여기서 확정되며 LLM은 서술만 한다.
    """
    wanted_levels = {CompositeLevel.YEAR, CompositeLevel.MONTH}
    selected = [
        c for c in composites
        if c.level in wanted_levels and _in_period(c.period_key, period)
    ]

    series: list[TimeSeriesPoint] = []
    findings: list[Finding] = []
    for c in sorted(selected, key=lambda x: x.period_key):
        signals = [s for s in c.domain_signals if s.domain == "career"]
        if not signals:
            continue
        score = max(0, min(100, round(sum(s.weight for s in signals) * 100)))
        names = [s.source_interaction for s in signals]
        series.append(TimeSeriesPoint(
            period_key=c.period_key,
            ganji=f"{c.ganji.stem}{c.ganji.branch}",
            score=score,
            signals=names,
        ))
        top = max(signals, key=lambda s: s.weight)
        findings.append(Finding(
            key=f"{top.event_key}@{c.period_key}",
            summary=(
                f"{c.period_key} {c.ganji.stem}{c.ganji.branch} — "
                f"직업 신호 {len(signals)}건({top.event_key} 중심), {c.favorability} 기조"
            ),
            score=score,
            event_key=top.event_key,
            period_key=c.period_key,
            signals=names,
        ))

    findings.sort(key=lambda f: -f.score)
    return TopicContext(
        module_id="M07",
        subjects=subjects,
        period=period,
        calendar_context=_calendar_context(selected),
        findings=findings[:5],  # Top N — Context Reduction 기본(docs/03 B5)
        time_series=series,
        style_rules=_BASE_STYLE,
        budget=_DEFAULT_BUDGET,
    )


# 모듈 레지스트리 — 구현된 모듈만 빌더 연결, 나머지는 계획 상태.
BUILDERS: dict[str, BuilderFn | None] = {mid: None for mid in MODULES}
BUILDERS["M07"] = build_career_context


def build_topic_context(
    module_id: str,
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
) -> TopicContext:
    """모듈 디스패치 — 미등록 ID·미구현 모듈은 명시적 오류.

    Raises:
        KeyError: M01~M15 밖의 모듈 ID(새 주제는 모듈 추가로만 대응).
        NotImplementedError: 등록은 됐으나 아직 구현 전인 모듈.
    """
    if module_id not in MODULES:
        raise KeyError(f"미정의 모듈: {module_id} — docs/09 4장 15종 외 추가 금지")
    builder = BUILDERS[module_id]
    if builder is None:
        raise NotImplementedError(
            f"{module_id}({MODULES[module_id]}) 미구현 — 후속 단위에서 추가"
        )
    return builder(subjects, period, composites)
