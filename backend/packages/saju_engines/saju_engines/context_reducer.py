"""Context Reduction Engine + LLM 입력 직렬화기 (v2.2 Phase 3 T3.4·T3.5).

LLM 입력 직전 최종 필터(docs/03 B5 — 규칙 전체):
1. **간지 계층 압축**: 대운 전체 / 선택된 세운만 / 선택 세운 내 월운만 / 택일 시에만 일운
2. 그래프 노드: intent graphScope의 evidence path만
3. 사전: dictionaryScope 외 로드 금지(Planner가 결정 — 본 모듈은 사전을 싣지 않음)
4. 이벤트 후보: Top N(기본 5) + score 임계값(40 미만 = 언급 생략 구간, docs/06 톤 표)
5. 모든 후보에 해당 간지와 대운 맥락 필수 — LLM은 간지를 계산할 수 없다

직렬화(T3.5)는 docs/06 "좋은 입력 예" 형태의 한국어 사실 문장으로 만들고,
llm_guard로 입력 토큰을 호출 전 검증한다(초과 시 후보 수를 줄여 재축소).
"""

from __future__ import annotations

from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.graph import EvidenceBundle
from saju_shared_types.intent import IntentJson, QueryType
from saju_shared_types.llm_input import (
    BirthChartSummary,
    DaewoonEntry,
    LlmBudget,
    LlmCalendarContext,
    LlmEventCandidate,
    LlmEvidence,
    LlmInput,
    LlmStyleRules,
    SelectedDay,
    SelectedMonth,
    SelectedYear,
    UsefulGods,
)
from saju_shared_types.manse_result import ManseV2Result

from .event_scoring import EventScorer, favorability_map
from .llm_guard import CALL_LIMITS, LLMCallGuard, TokenBudgetExceeded

TOP_N_CANDIDATES = 5  # 기본 Top N (docs/03 B5 — 3~5)
SCORE_FLOOR = 40  # docs/06 톤 표: <40은 언급 생략 구간 → LLM 미전달
MAX_PATHS_PER_EVENT = 3  # 근거 경로 상한(토큰 절약, 초안)

# docs/06 점수→표현 강도 매핑(toneGuide 기본).
_TONE_GUIDE = (
    "85+: '~신호가 매우 강합니다' / 70~84: '~가능성이 높습니다' / "
    "55~69: '~흐름이 나타날 수 있습니다' / 40~54: '~조짐이 약하게 있습니다' / "
    "40 미만: 언급 생략 또는 '뚜렷한 신호는 없습니다'"
)
_BASE_PROHIBITED = ["반드시 이직한다", "무조건 헤어진다", "확정적으로 발생한다"]
_BASE_INSTRUCTION = (
    "사건 발생이 아니라 '변화 에너지의 활성화'로 표현하고, Trigger→진행→결과 구조로 "
    "설명할 것. 제공된 간지·점수·근거 외의 명리 계산을 시도하지 말 것 — 데이터에 없으면 "
    "'해당 정보는 제공되지 않았다'로 처리."
)


def tone_for_score(score: int) -> str:
    """점수 → 표현 강도(docs/06 매핑표)."""
    if score >= 85:
        return "신호가 매우 강합니다"
    if score >= 70:
        return "가능성이 높습니다"
    if score >= 55:
        return "흐름이 나타날 수 있습니다"
    if score >= 40:
        return "조짐이 약하게 있습니다"
    return "뚜렷한 신호는 없습니다"


def reduce_candidates(
    candidates: list[EventCandidate],
    graph_scope: list[EventKey],
    top_n: int = TOP_N_CANDIDATES,
    score_floor: int = SCORE_FLOOR,
) -> list[EventCandidate]:
    """이벤트 후보 축소 — graphScope 내 + 임계값 + Top N (docs/03 B5 규칙 4)."""
    scoped = [
        c for c in candidates
        if (not graph_scope or c.event_key in graph_scope) and c.score >= score_floor
    ]
    return sorted(scoped, key=lambda c: (-c.score, c.period, str(c.event_key)))[:top_n]


def _daewoon_lookup(result: ManseV2Result) -> dict[int, str]:
    """연도 → 대운 간지(대운 맥락 필수 동반용)."""
    lookup: dict[int, str] = {}
    if result.luck_cycles is None:
        return lookup
    for d in result.luck_cycles.daewoon_table:
        for y in range(d.approx_start_date.year, d.approx_end_date.year):
            lookup[y] = d.ganji
    return lookup


def _ganji_lookup(result: ManseV2Result) -> dict[str, str]:
    """기간 라벨 → 간지(세운/월운/일운)."""
    out: dict[str, str] = {}
    if result.luck_cycles is None:
        return out
    lc = result.luck_cycles
    for p in [*lc.yearly_luck, *lc.monthly_luck, *lc.daily_luck]:
        out[p.label] = p.ganji
    return out


def build_calendar_context(
    result: ManseV2Result,
    selected: list[EventCandidate],
    intent: IntentJson,
) -> LlmCalendarContext:
    """간지 계층 압축(docs/03 B5 규칙 1).

    대운: 장기 질문(fortune_overview/대운 단위)이면 전체, 아니면 선택 후보가 속한
    대운만. 세운: 선택 후보 연도만. 월운: 선택 세운 안에서만. 일운: 택일에서만.
    """
    if result.luck_cycles is None:
        return LlmCalendarContext()
    lc = result.luck_cycles
    dw_by_year = _daewoon_lookup(result)
    ganji = _ganji_lookup(result)

    selected_years_set: set[str] = set()
    months: list[SelectedMonth] = []
    days: list[SelectedDay] = []
    for c in selected:
        year_label = c.period[:4]
        selected_years_set.add(year_label)
        if len(c.period) == 7:  # 월운 후보 — 선택 세운 내에서만
            months.append(SelectedMonth(
                period=c.period, ganji=ganji.get(c.period, ""), year=year_label,
            ))
        elif len(c.period) == 10:  # 일운 — 택일 질의에서만
            if intent.query_type is QueryType.DATE_RECOMMENDATION:
                days.append(SelectedDay(date=c.period, ganji=ganji.get(c.period, "")))

    years = [
        SelectedYear(
            year=int(y),
            ganji=ganji.get(y, ""),
            daewoon=dw_by_year.get(int(y), ""),
            reason_selected=_selection_reason(y, selected),
        )
        for y in sorted(selected_years_set)
        if y.isdigit()
    ]

    long_term = intent.query_type is QueryType.FORTUNE_OVERVIEW or (
        intent.time_scope.value in ("long_term", "life_stage", "daewoon_unit")
    )
    wanted_dw = {dw_by_year.get(int(y), "") for y in selected_years_set if y.isdigit()}
    daewoon = [
        DaewoonEntry(
            period=f"{d.approx_start_date.year}~{d.approx_end_date.year}",
            ganji=d.ganji,
            age_range=f"{d.start_age}~{d.start_age + 9}세",
        )
        for d in lc.daewoon_table
        if long_term or d.ganji in wanted_dw
    ]
    return LlmCalendarContext(
        daewoon=daewoon, selected_years=years, selected_months=months, selected_days=days,
    )


def _selection_reason(year_label: str, selected: list[EventCandidate]) -> str:
    """세운 선별 사유 — 그 해 최고 후보."""
    in_year = [c for c in selected if c.period[:4] == year_label]
    if not in_year:
        return ""
    top = max(in_year, key=lambda c: c.score)
    return f"{top.event_key} {top.score}점"


def _birth_summary(result: ManseV2Result) -> BirthChartSummary:
    """원국 요약(확정값만 — LLM 재판정 금지)."""
    assert result.pillars is not None
    p = result.pillars
    pillars = {"year": p.year.ganji, "month": p.month.ganji, "day": p.day.ganji}
    if p.hour is not None:
        pillars["hour"] = p.hour.ganji
    strength = ""
    if result.force_analysis is not None:
        strength = result.force_analysis.strength.band
    fav = favorability_map(result)
    return BirthChartSummary(
        day_master=p.day_master,
        pillars=pillars,
        void_branches=list(p.gongmang_branches),
        strength=strength,
        useful_gods=UsefulGods(
            yongsin=[el for el, role in fav.items() if role == "용신"],
            gisin=[el for el, role in fav.items() if role == "기신"],
        ),
    )


def build_llm_input(
    user_question: str,
    intent: IntentJson,
    result: ManseV2Result,
    candidates: list[EventCandidate],
    bundles: list[EvidenceBundle],
    scorer: EventScorer,
    call_type: str = "chat_single",
) -> LlmInput:
    """축소 → 계약 조립 (T3.4+T3.5). 모든 수치는 입력 시점에 확정 완료."""
    graph_scope = [k for k in [intent.event_key, *intent.event_keys] if k is not None]
    selected = reduce_candidates(candidates, graph_scope or [b.event_key for b in bundles])
    dw_by_year = _daewoon_lookup(result)
    ganji = _ganji_lookup(result)

    llm_candidates = [
        LlmEventCandidate(
            event_key=c.event_key,
            period=c.period,
            ganji=ganji.get(c.period, ""),
            daewoon_context=dw_by_year.get(int(c.period[:4]), "") if c.period[:4].isdigit() else "",
            score=c.score,
            confidence=str(c.confidence),
            polarity=str(c.polarity),
        )
        for c in selected
    ]
    selected_keys = {c.event_key for c in selected}
    evidence = [
        LlmEvidence(
            event_key=b.event_key,
            readable_paths=[p.readable for p in b.paths[:MAX_PATHS_PER_EVENT]],
            contradicts=b.contradicts,
        )
        for b in bundles
        if b.event_key in selected_keys
    ]
    prohibited = list(_BASE_PROHIBITED)
    for b in bundles:
        if b.event_key in selected_keys:
            prohibited += [p for p in b.prohibitions if p not in prohibited]

    limit = CALL_LIMITS[call_type]
    return LlmInput(
        user_question=user_question,
        resolved_intent=intent,
        birth_chart_summary=_birth_summary(result),
        calendar_context=build_calendar_context(result, selected, intent),
        event_candidates=llm_candidates,
        evidence=evidence,
        style_rules=LlmStyleRules(
            prohibited=prohibited,
            tone_guide=_TONE_GUIDE,
            llm_instruction=_BASE_INSTRUCTION,
        ),
        budget=LlmBudget(
            max_input_tokens=limit.max_input_tokens,
            max_output_chars=limit.max_output_chars or limit.max_output_tokens,
        ),
    )


def serialize_llm_input(payload: LlmInput) -> str:
    """계약 → LLM 프롬프트 본문(한국어 사실 서술 — docs/06 '좋은 입력 예' 형태).

    지시는 명령형으로, 데이터와 분리한다(표현 원칙 5).
    """
    s = payload.birth_chart_summary
    lines = [
        "[원국]",
        f"일간 {s.day_master} · 명식 "
        + " ".join(f"{k}:{v}" for k, v in s.pillars.items())
        + f" · 공망 {''.join(s.void_branches) or '없음'} · 강약 {s.strength}",
        f"용신 {','.join(s.useful_gods.yongsin) or '미정'} / "
        f"기신 {','.join(s.useful_gods.gisin) or '미정'}",
        "",
        "[간지달력(압축)]",
    ]
    for d in payload.calendar_context.daewoon:
        lines.append(f"대운 {d.ganji} ({d.period}, {d.age_range})")
    for y in payload.calendar_context.selected_years:
        lines.append(f"세운 {y.year} {y.ganji} (대운 {y.daewoon} 내) — 선별: {y.reason_selected}")
    for m in payload.calendar_context.selected_months:
        lines.append(f"월운 {m.period} {m.ganji}")
    for day in payload.calendar_context.selected_days:
        lines.append(f"일운 {day.date} {day.ganji}")
    lines.append("")
    lines.append("[이벤트 후보 — 점수는 확정값, 재계산 금지]")
    for c in payload.event_candidates:
        lines.append(
            f"{c.event_key} @ {c.period}({c.ganji}, 대운 {c.daewoon_context}) "
            f"{c.score}점 · {c.polarity} · 신뢰도 {c.confidence} → {tone_for_score(c.score)}"
        )
    lines.append("")
    lines.append("[근거 경로]")
    for e in payload.evidence:
        for path in e.readable_paths:
            lines.append(f"{e.event_key}: " + " → ".join(path))
        if e.contradicts:
            lines.append(f"{e.event_key} 반대 근거: {', '.join(e.contradicts)}")
    lines.append("")
    lines.append("[지시]")
    lines.append(payload.style_rules.llm_instruction)
    lines.append(f"표현 강도: {payload.style_rules.tone_guide}")
    lines.append("금기 표현: " + ", ".join(payload.style_rules.prohibited))
    if payload.persona.prompt_block:
        lines.append(payload.persona.prompt_block)
    lines.append(f"[질문] {payload.user_question}")
    return "\n".join(lines)


def serialize_with_guard(
    payload: LlmInput, call_type: str = "chat_single"
) -> tuple[str, int]:
    """직렬화 + 토큰 가드(docs/09 8장) — 초과 시 후보·근거를 줄여 1회 재축소.

    Returns:
        (프롬프트 본문, 측정 토큰). 재축소 후에도 초과면 TokenBudgetExceeded 전파.
    """
    guard = LLMCallGuard(call_type)
    text = serialize_llm_input(payload)
    try:
        return text, guard.check_input(text)
    except TokenBudgetExceeded:
        shrunk = payload.model_copy(update={
            "event_candidates": payload.event_candidates[:3],
            "evidence": [
                e.model_copy(update={"readable_paths": e.readable_paths[:1]})
                for e in payload.evidence[:3]
            ],
        })
        text = serialize_llm_input(shrunk)
        return text, guard.check_input(text)
