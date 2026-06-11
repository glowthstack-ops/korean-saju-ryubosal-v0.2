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

import json
import re
from datetime import date as date_cls
from pathlib import Path

from saju_shared_types.events import EventCandidate, EventKey
from saju_shared_types.graph import EvidenceBundle
from saju_shared_types.intent import IntentJson, QueryType
from saju_shared_types.llm_input import (
    BirthChartSummary,
    DaewoonEntry,
    DateSelectionBlock,
    LlmBudget,
    LlmCalendarContext,
    LlmEventCandidate,
    LlmEvidence,
    LlmInput,
    LlmStyleRules,
    MonthOverviewRow,
    ReferenceFrame,
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
# v1 [오늘 날짜]·자체 검증 체크리스트 계승 — LLM은 어떤 계산도 할 수 없다는 전제.
_REFERENCE_INSTRUCTION = (
    "[기준 시점]의 오늘 날짜를 기준으로 과거·현재·미래를 판단할 것 — 임의로 다른 "
    "날짜를 기준으로 삼지 말 것. 질문의 시점 표현(올해/내년/다음 달 등)은 [기준 시점]에 "
    "해석되어 있다."
)
_LABEL_INSTRUCTION = (
    "이벤트는 반드시 한글 라벨로 부를 것(예: '이직·직업 변화') — career_change 같은 "
    "영문 내부 키를 답변에 노출하지 말 것."
)
_SELF_CHECK_INSTRUCTION = (
    "답변 작성 후 자체 검증: 답변에 등장한 모든 연도·월·날짜·간지·점수가 위 입력에 "
    "실제로 존재하는지 확인하고, 입력에 없는 항목은 삭제하거나 '해당 정보는 제공되지 "
    "않았다'로 바꿀 것."
)
_OUT_OF_RANGE_INSTRUCTION = (
    "[참고 — 질문 기간 외 흐름]은 배경 맥락으로만 짧게 인용하고 메인 서술로 삼지 말 것. "
    "답변의 중심은 질문 기간 내 데이터다."
)
_DATE_TABLE_INSTRUCTION = (
    "[택일 결과] 표가 제공되었으므로 '날짜 정보가 없다' 류의 회피성 답변을 절대 하지 말 "
    "것. 표의 날짜·간지·사유를 그대로 인용해 1~3개 날짜를 명확히 추천할 것. 표 밖의 "
    "날짜를 임의로 만들지 말 것."
)

# 이벤트 한글 라벨(taxonomy) — 내부 키 노출 방지.
_TAXONOMY_PATH = Path(__file__).resolve().parents[3] / "dictionaries" / "events" / "taxonomy.json"
_EVENT_KO: dict[str, str] = {
    i["eventKey"]: i["ko"]
    for i in json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))["items"]
}
# 근거 경로 내부 노트 제거(예: "(docs/05 회귀 기준 케이스)").
_INTERNAL_NOTE_RE = re.compile(r"\s*\((?:docs?/|내부|회귀)[^)]*\)")


_POLARITY_KO = {
    "positive": "우호적", "negative_or_forced": "부담·비자발 계열",
    "conditional": "조건부", "neutral": "중립",
}


def polarity_ko(value: str) -> str:
    """극성 → 한글(내부 어휘 노출 방지)."""
    return _POLARITY_KO.get(value, value)


def event_ko(key: EventKey | str) -> str:
    """EventKey → 한글 라벨(미등록 시 키 그대로)."""
    return _EVENT_KO.get(str(key), str(key))


def _period_bounds(period: str) -> tuple[str, str]:
    """후보 기간 라벨('2026'/'2026-05'/'2026-05-03') → ISO 구간."""
    if len(period) == 4:
        return f"{period}-01-01", f"{period}-12-31"
    if len(period) == 7:
        return f"{period}-01", f"{period}-31"
    return period, period


def in_question_range(period: str, start: str | None, end: str | None) -> bool:
    """후보 기간이 질문 기간과 겹치는가(ISO 문자열 비교)."""
    if not start and not end:
        return True
    p_start, p_end = _period_bounds(period)
    q_start, _ = _period_bounds(start) if start else ("0000-01-01", "")
    _, q_end = _period_bounds(end or start or "9999")
    return p_start <= q_end and p_end >= q_start


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
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[EventCandidate]:
    """이벤트 후보 축소 — graphScope + 임계값 + **질문 기간 필터** + Top N.

    기간 필터(P2): '올해' 질문에 과거 100점 후보가 메인이 되는 문제 차단.
    기간 외 상위 후보는 reduce_with_context()로 별도 분리 제공.
    """
    scoped = [
        c for c in candidates
        if (not graph_scope or c.event_key in graph_scope) and c.score >= score_floor
        and in_question_range(c.period, period_start, period_end)
    ]
    return sorted(scoped, key=lambda c: (-c.score, c.period, str(c.event_key)))[:top_n]


def reduce_with_context(
    candidates: list[EventCandidate],
    graph_scope: list[EventKey],
    period_start: str | None,
    period_end: str | None,
    top_n: int = TOP_N_CANDIDATES,
    score_floor: int = SCORE_FLOOR,
    out_of_range_n: int = 2,
) -> tuple[list[EventCandidate], list[EventCandidate]]:
    """(질문 기간 내 선별, 기간 외 참고 상위) — 참고는 배경 맥락 전용."""
    selected = reduce_candidates(
        candidates, graph_scope, top_n, score_floor, period_start, period_end,
    )
    out_scoped = [
        c for c in candidates
        if (not graph_scope or c.event_key in graph_scope) and c.score >= score_floor
        and not in_question_range(c.period, period_start, period_end)
    ]
    out_top = sorted(out_scoped, key=lambda c: (-c.score, c.period))[:out_of_range_n]
    return selected, out_top


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
    seen_months: set[str] = set()
    days: list[SelectedDay] = []
    for c in selected:
        year_label = c.period[:4]
        selected_years_set.add(year_label)
        if len(c.period) == 7 and c.period not in seen_months:  # 월운 — 중복 제거
            seen_months.add(c.period)
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

    # 대운 전체는 장기 질문에서만 — 시점이 연 단위 이하로 좁혀졌으면 선택 대운만.
    has_bounded_period = intent.time_range is not None and intent.time_range.start is not None
    long_term = intent.time_scope.value in ("long_term", "life_stage", "daewoon_unit") or (
        intent.query_type is QueryType.FORTUNE_OVERVIEW and not has_bounded_period
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


def _to_llm_candidate(
    c: EventCandidate, ganji: dict[str, str], dw_by_year: dict[int, str]
) -> LlmEventCandidate:
    return LlmEventCandidate(
        event_key=c.event_key,
        event_ko=event_ko(c.event_key),
        period=c.period,
        ganji=ganji.get(c.period, ""),
        daewoon_context=dw_by_year.get(int(c.period[:4]), "") if c.period[:4].isdigit() else "",
        score=c.score,
        signal_count=len(c.signals),
        confidence=str(c.confidence),
        polarity=str(c.polarity),
    )


_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def build_reference_frame(
    today: date_cls, intent: IntentJson, result: ManseV2Result
) -> ReferenceFrame:
    """기준 시점(P1) — v1 [오늘 날짜] 원칙: LLM은 오늘이 언제인지 모른다."""
    ganji = _ganji_lookup(result)
    start = intent.time_range.start if intent.time_range else None
    end = intent.time_range.end if intent.time_range else None
    period = f"{start} ~ {end}" if start and end and start != end else (start or "")
    note = (
        f"질문의 시점 표현은 {period} 구간으로 해석되었다."
        if period else "질문에 시점이 명시되지 않았다 — 오늘 기준 흐름으로 안내."
    )
    return ReferenceFrame(
        today=f"{today.isoformat()} ({_WEEKDAY_KO[today.weekday()]})",
        this_year=str(today.year),
        this_year_ganji=ganji.get(str(today.year), ""),
        question_period=period,
        question_period_note=note,
    )


def build_monthly_overview(
    result: ManseV2Result, candidates: list[EventCandidate], year: int
) -> list[MonthOverviewRow]:
    """해당 연도 12개월 요약(P4 — v1 monthSummaryText 계승). 신호 없는 달도 표기."""
    ganji = _ganji_lookup(result)
    by_month: dict[str, EventCandidate] = {}
    for c in candidates:
        if len(c.period) == 7 and c.period.startswith(str(year)):
            cur = by_month.get(c.period)
            if cur is None or c.score > cur.score:
                by_month[c.period] = c
    rows: list[MonthOverviewRow] = []
    for m in range(1, 13):
        period = f"{year}-{m:02d}"
        top = by_month.get(period)
        rows.append(MonthOverviewRow(
            period=period,
            ganji=ganji.get(period, ""),
            top_event_ko=event_ko(top.event_key) if top else "",
            score=top.score if top else None,
            polarity=str(top.polarity) if top else "",
        ))
    return rows


def build_llm_input(
    user_question: str,
    intent: IntentJson,
    result: ManseV2Result,
    candidates: list[EventCandidate],
    bundles: list[EvidenceBundle],
    scorer: EventScorer,
    call_type: str = "chat_single",
    today: date_cls | None = None,
    monthly_overview: list[MonthOverviewRow] | None = None,
    date_selection: DateSelectionBlock | None = None,
) -> LlmInput:
    """축소 → 계약 조립 (T3.4+T3.5). 모든 수치는 입력 시점에 확정 완료.

    P1: today 제공 시 [기준 시점] 동반(LLM은 오늘을 모른다).
    P2: 질문 기간 내 후보 우선 — 기간 외 상위는 참고 블록으로 분리.
    """
    graph_scope = [k for k in [intent.event_key, *intent.event_keys] if k is not None]
    period_start = intent.time_range.start if intent.time_range else None
    period_end = intent.time_range.end if intent.time_range else None
    selected, out_of_range = reduce_with_context(
        candidates, graph_scope or [b.event_key for b in bundles],
        period_start, period_end,
    )
    dw_by_year = _daewoon_lookup(result)
    ganji = _ganji_lookup(result)

    llm_candidates = [_to_llm_candidate(c, ganji, dw_by_year) for c in selected]
    out_candidates = [_to_llm_candidate(c, ganji, dw_by_year) for c in out_of_range]
    selected_keys = {c.event_key for c in [*selected, *out_of_range]}
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
        out_of_range_candidates=out_candidates,
        no_candidates_in_period=bool(period_start or period_end) and not llm_candidates,
        reference=build_reference_frame(today, intent, result) if today else None,
        monthly_overview=monthly_overview or [],
        date_selection=date_selection,
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
    lines: list[str] = []
    # [기준 시점] — 항상 최상단(P1): LLM은 오늘이 언제인지 모른다.
    if payload.reference is not None:
        r = payload.reference
        lines += [
            "[기준 시점]",
            f"오늘: {r.today} · 올해: {r.this_year}년"
            + (f"({r.this_year_ganji})" if r.this_year_ganji else ""),
            (f"질문 기간: {r.question_period} — {r.question_period_note}"
             if r.question_period else r.question_period_note),
            "",
        ]
    lines += [
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
        period = d.period.replace("~", "-")
        ages = d.age_range.replace("~", "-")
        lines.append(f"대운 {d.ganji} ({period}, {ages})")
    for y in payload.calendar_context.selected_years:
        lines.append(f"세운 {y.year} {y.ganji} (대운 {y.daewoon} 내) — 선별: {y.reason_selected}")
    for m in payload.calendar_context.selected_months:
        lines.append(f"월운 {m.period} {m.ganji}")
    for day in payload.calendar_context.selected_days:
        lines.append(f"일운 {day.date} {day.ganji}")
    def candidate_line(c: LlmEventCandidate) -> str:
        label = c.event_ko or event_ko(c.event_key)
        return (
            f"{label} @ {c.period}({c.ganji}, 대운 {c.daewoon_context}) "
            f"{c.score}점(신호 {c.signal_count}건) · {polarity_ko(c.polarity)} · "
            f"신뢰도 {c.confidence} → {tone_for_score(c.score)}"
        )

    lines.append("")
    lines.append("[이벤트 후보 — 점수는 확정값, 재계산 금지]")
    if payload.no_candidates_in_period:
        lines.append(
            "질문 기간 내 해당 도메인 후보 없음 — '해당 기간에는 뚜렷한 신호가 "
            "없습니다'로 정직하게 안내할 것(추측 금지)."
        )
    for c in payload.event_candidates:
        lines.append(candidate_line(c))
    if payload.out_of_range_candidates:
        lines.append("")
        lines.append("[참고 — 질문 기간 외 흐름(메인 서술 금지, 배경 맥락 전용)]")
        for c in payload.out_of_range_candidates:
            lines.append(candidate_line(c))
    if payload.monthly_overview:
        lines.append("")
        lines.append("[월별 요약 — 질문 연도 12개월(값 그대로 사용, 추측 금지)]")
        for row in payload.monthly_overview:
            if row.score is not None:
                lines.append(
                    f"{row.period} {row.ganji}: {row.top_event_ko} {row.score}점 "
                    f"· {polarity_ko(row.polarity)} → {tone_for_score(row.score)}"
                )
            elif not row.ganji:
                lines.append(f"{row.period}: 입춘 전 — 전년 세운 구간(월운 정보 없음)")
            else:
                lines.append(f"{row.period} {row.ganji}: 특이 신호 없음")
    if payload.date_selection is not None:
        ds = payload.date_selection
        lines.append("")
        lines.append(f"[택일 결과 — {ds.purpose_ko} · {ds.period} · 엔진 확정값]")
        for drow in ds.rows:
            notes = " · ".join(drow.notes) if drow.notes else ""
            lines.append(
                f"{drow.date}({drow.weekday}) {drow.ganji} {drow.score}점 "
                f"[{drow.recommendation}]" + (f" — {notes}" if notes else "")
            )
        for avoid in ds.avoid[:5]:
            lines.append(f"회피일 {avoid.get('date')} — {avoid.get('reason')}")
        for caution in ds.cautions:
            lines.append(f"주의: {caution}")
    lines.append("")
    lines.append("[근거 경로]")
    for e in payload.evidence:
        label = event_ko(e.event_key)
        for path in e.readable_paths:
            cleaned = [_INTERNAL_NOTE_RE.sub("", step) for step in path]
            lines.append(f"{label}: " + " → ".join(cleaned))
        if e.contradicts:
            cleaned_contra = [_INTERNAL_NOTE_RE.sub("", x) for x in e.contradicts]
            lines.append(f"{label} 반대 근거: {', '.join(cleaned_contra)}")
    lines.append("")
    lines.append("[지시]")
    lines.append(payload.style_rules.llm_instruction)
    if payload.reference is not None:
        lines.append(_REFERENCE_INSTRUCTION)
    lines.append(_LABEL_INSTRUCTION)
    if payload.out_of_range_candidates:
        lines.append(_OUT_OF_RANGE_INSTRUCTION)
    if payload.date_selection is not None:
        lines.append(_DATE_TABLE_INSTRUCTION)
    lines.append(_SELF_CHECK_INSTRUCTION)
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
