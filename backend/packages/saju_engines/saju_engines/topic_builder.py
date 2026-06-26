"""Topic Context Builder (v2.2 Phase 2.5 T2.5.6·T2.5.7, docs/09 4장 — 모듈 전체 15종 규격).

각 모듈은 `(subjects, period, LuckComposite[], dictionaries) => TopicContext` 순수 함수다.
**M01~M15가 전체이며 새 주제는 모듈 추가로만 대응한다(기존 모듈에 분기 추가 금지).**

구현: M01(love_timing)·M02(marriage)·M07(career)·M08(business)·M09(wealth)·M11(health)·
M12(education_exam) — 도메인 신호형(공용 _domain_topic), M03(personality_traits — trait_mapping),
M10(relocation_composite — relocation.py S1~S10 위임), M14(past_validation — past_validation.py
역방향, extras=birth/scorer/compute), M15(lifestyle — format_slots.json).
미구현(계획): M04 부모·M05 자녀·M06 직장관계·M13 비교(호출 시 NotImplementedError).

T0 데이터(원국 십성 분포·용신 오행)가 필요한 모듈(M03/M10)은 extras 키워드로 받는다 —
LuckComposite 스키마(규격)에 없는 정적 차트 정보는 Static Chart Layer(T0, docs/09 1장)
소관이므로 호출 측(오케스트레이터)이 공급한다.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectRef
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.relocation import RelocationQuery
from saju_shared_types.topic_context import (
    CalendarContextEntry,
    Finding,
    PeriodSpec,
    StyleRules,
    TimeSeriesPoint,
    TokenBudget,
    TopicContext,
    TraitShift,
)

from .event_engine_v2 import EventEngineV2
from .llm_guard import CALL_LIMITS
from .past_validation import ComputeFn, generate_past_candidates
from .relocation import RelocationResolver

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

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

# 빌더 공통 시그니처: (subjects, period, composites, **extras) → TopicContext.
BuilderFn = Callable[..., TopicContext]

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


def build_personality_context(
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
    *,
    natal_ten_god_dist: dict[str, float],
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> TopicContext:
    """M03 personality_traits — 시기별 성향 변화 (docs/09 6장 계산식 전체).

    effectiveDist(period) = natalDist×W_natal + 대운기여×W_daewoon + 세운기여×W_year.
    contribution = 운 간지의 십성(천간 1.0 + 지지 본기 0.7). favorability는 분포를
    조정하지 않고 quality_flag('발현 질')로만 반영한다(docs/09 6장).

    natal_ten_god_dist는 T0(force_analysis.ten_god_analysis.distribution)에서 공급.
    """
    mapping = json.loads((dictionaries_dir / "trait_mapping.json").read_text("utf-8"))
    w = mapping["weights"]
    traits: dict[str, dict] = {t["tenGod"]: t for t in mapping["traits"]}
    natal_top = _top_keys(natal_ten_god_dist, 3)

    daewoon_contrib: dict[str, dict[str, float]] = {}
    shifts: list[TraitShift] = []
    targets = [
        c for c in composites
        if (
            (c.level is CompositeLevel.DAEWOON)
            or (c.level is CompositeLevel.YEAR and _in_period(c.period_key, period))
        )
    ]
    for c in sorted(targets, key=lambda x: (x.level != CompositeLevel.DAEWOON, x.period_key)):
        contribution = {c.ten_god.stem: w["stem"], c.ten_god.branch_main: w["branchMain"]}
        if c.level is CompositeLevel.DAEWOON:
            daewoon_contrib[c.period_key] = contribution
            scale = w["daewoon"]
            parent_dw: dict[str, float] = {}
        else:
            scale = w["year"]
            dw_key = f"DW:{c.parent_context.daewoon}" if c.parent_context.daewoon else ""
            parent_dw = daewoon_contrib.get(dw_key, {})

        effective: dict[str, float] = {
            tg: v * w["natal"] for tg, v in natal_ten_god_dist.items()
        }
        for tg, v in parent_dw.items():
            effective[tg] = effective.get(tg, 0.0) + v * w["daewoon"]
        for tg, v in contribution.items():
            effective[tg] = effective.get(tg, 0.0) + v * scale

        dominant = _top_keys(effective, 3)
        rising = [tg for tg in dominant if tg not in natal_top]
        fading = [tg for tg in natal_top if tg not in dominant]
        quality = (
            "pressured" if c.favorability in ("기신", "구신")
            else "favorable" if c.favorability in ("용신", "희신")
            else "mixed"
        )
        shifts.append(TraitShift(
            period_key=c.period_key,
            dominant_ten_gods=dominant,
            rising_traits=[
                t for tg in rising for t in traits.get(tg, {}).get("rising", [])
            ],
            fading_traits=[
                t for tg in fading for t in traits.get(tg, {}).get("fading", [])
            ],
            quality_flag=quality,
            evidence=[
                f"{c.period_key} {c.ganji.stem}{c.ganji.branch} — "
                f"천간 {c.ten_god.stem}·지지 본기 {c.ten_god.branch_main} 가산"
            ],
        ))

    findings = [
        Finding(
            key=f"trait_shift@{s.period_key}",
            summary=(
                f"{s.period_key}: 활성 십성 {'·'.join(s.dominant_ten_gods)}"
                + (f", 부상 성향 {'·'.join(s.rising_traits[:3])}" if s.rising_traits else "")
            ),
            score=70 if s.rising_traits else 50,  # 변화 유무 표시용 초안 점수
            period_key=s.period_key,
            signals=s.dominant_ten_gods,
        )
        for s in shifts if s.rising_traits or s.fading_traits
    ]
    return TopicContext(
        module_id="M03",
        subjects=subjects,
        period=period,
        calendar_context=_calendar_context(targets),
        findings=findings[:5],
        trait_shifts=shifts,
        style_rules=StyleRules(
            prohibited_expressions=[*_BASE_STYLE.prohibited_expressions, "MBTI식 고정 유형화"],
            tone_notes=[*_BASE_STYLE.tone_notes, "성격검사화 금지(docs/02 E5)"],
        ),
        budget=_DEFAULT_BUDGET,
    )


def build_lifestyle_context(
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
    *,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> TopicContext:
    """M15 lifestyle — 일일/주간/연간 종합운, 고정 슬롯 점수 (docs/02 E9 전체 슬롯).

    슬롯 목록은 templates/format_slots.json(전체 규격)을 그대로 사용하며 임의
    추가·삭제하지 않는다. 모든 슬롯을 findings로 채운다(부분 누락 금지).
    """
    slots_spec = json.loads(
        (dictionaries_dir / "templates" / "format_slots.json").read_text("utf-8")
    )
    fortune_type = _fortune_type(period)
    slot_names: list[str] = slots_spec[fortune_type]["slots"]

    selected = [
        c for c in composites
        if c.level in (CompositeLevel.DAY, CompositeLevel.MONTH, CompositeLevel.YEAR)
        and _in_period(c.period_key, period)
    ]
    day_comps = [c for c in selected if c.level is CompositeLevel.DAY]
    # 일 단위 운세의 활성 월은 일운의 절기 부모월을 따른다 — 캘린더 월 prefix로 잡으면 절입
    # 이전 초순일이 다음 절기월로 오인된다(예: 2026-07-04는 甲午인데 乙未로 표시되던 결함).
    if day_comps and day_comps[0].parent_context.month:
        parent_month = day_comps[0].parent_context.month
        seolgi_month = next(
            (c for c in composites
             if c.level is CompositeLevel.MONTH
             and f"{c.ganji.stem}{c.ganji.branch}" == parent_month),
            None,
        )
        if seolgi_month is not None:
            selected = [c for c in selected if c.level is not CompositeLevel.MONTH]
            selected.append(seolgi_month)
    scores = _lifestyle_scores(selected)

    findings = [
        Finding(
            key=f"slot:{name}",
            summary=_slot_summary(name, scores, selected, day_comps),
            score=_slot_score(name, scores),
            signals=[],
        )
        for name in slot_names
    ]
    return TopicContext(
        module_id="M15",
        subjects=subjects,
        period=period,
        calendar_context=_calendar_context(selected),
        findings=findings,  # 슬롯 전체 — Top N 축약 금지(고정 템플릿)
        style_rules=_BASE_STYLE,
        budget=_DEFAULT_BUDGET,
    )


def build_relocation_context(
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
    *,
    relocation_query: RelocationQuery,
    composites_by_subject: dict[str, list[LuckComposite]],
    yongsin_by_subject: dict[str, str],
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> TopicContext:
    """M10 relocation_composite — S1~S10은 RelocationResolver에 위임 (docs/09 7장)."""
    from saju_shared_types.topic_context import GroupAggReport, RankedItem

    resolver = RelocationResolver(dictionaries_dir)
    result = resolver.resolve(relocation_query, composites_by_subject, yongsin_by_subject)

    ranked = [
        RankedItem(
            label=f"{c.date} ({c.ganji})",
            score=c.final_score,
            reasons=c.reasons,
            cautions=[w.signal for w in c.member_warnings],
        )
        for c in result.move_dates
    ]
    # R2 — 이유분류 findings(해석 라벨, score=0)를 이사일 findings 앞에 배치
    # (사용자 14장 출력 순서: 요약→이유→집성격→리스크→체크리스트→택일).
    reason_findings = [
        Finding(
            key=f"reason@{p.ten_god}",
            summary=(
                f"{p.source} {p.ten_god} → {p.type}: "
                f"이유 {'·'.join(p.move_reason[:3])} / 집 {'·'.join(p.property_tendency[:2])} / "
                f"리스크({p.risk_level}) {'·'.join(p.risk[:2])}"
            ),
            score=0,  # 분류 라벨 — 점수 미개입(절대원칙 1·12)
            signals=p.required_checks,  # 계약 전 확인 체크리스트
        )
        for p in result.reason_profiles
    ]
    move_findings = [
        Finding(
            key=f"move@{c.date}",
            summary=(
                f"{c.date} {c.ganji} — 일운 {c.scores.day_execution} · "
                f"월적합 {c.scores.month_fit}"
                + (" · 손없는 날" if c.son_eomneun_nal else "")
            ),
            score=c.final_score,
            period_key=c.date,
        )
        for c in result.move_dates
    ]
    findings = reason_findings + move_findings
    return TopicContext(
        module_id="M10",
        subjects=subjects,
        period=period,
        calendar_context=_calendar_context(
            [c for c in composites if _in_period(c.period_key, period)][:40]
        ),
        findings=findings,
        ranked_results=ranked,
        group_aggregation=GroupAggReport(
            rule=relocation_query.aggregation_rule,
            member_scores={},  # 월별 상세는 result.group_summary — LLM 입력 시 별도 직렬화
            conflicts=result.group_summary.conflicts,
        ),
        style_rules=StyleRules(
            prohibited_expressions=[*_BASE_STYLE.prohibited_expressions, "반드시 이직한다"],
            tone_notes=[
                *_BASE_STYLE.tone_notes,
                "이사 발생 단정 금지 — 가능성·단계 표현, 십성 리스크 체크리스트 동반",
            ],
        ),
        budget=TokenBudget(
            max_input_tokens=CALL_LIMITS["chat_compare"].max_input_tokens,
            max_output_chars=2_400,
        ),
    )


# ── M15 내부 헬퍼 ─────────────────────────────────────────────────

_SLOT_DOMAIN = {  # 슬롯 → 점수 카테고리(초안 매핑, 검수 대상)
    "일·공부": "work", "돈·소비": "money", "관계·연애": "relationship", "건강": "health",
    "직업": "work", "재물": "money", "관계": "relationship", "일·직업": "work",
}
_DOMAIN_TO_CATEGORY = {
    "career": "work", "education": "work", "wealth": "money",
    "relationship": "relationship", "health": "health", "relocation": "decision",
    "general": "decision",
}


def _fortune_type(period: PeriodSpec) -> str:
    """기간 범위 → daily/weekly/monthly/yearly (granularity·길이 기반)."""
    if period.granularity == "year":
        return "yearly"
    if period.granularity == "month":
        return "monthly"
    if period.start == period.end:
        return "daily"
    return "weekly"


# 종합운 점수의 레벨 가중 — 운의 위계(대운>세운>월>일, event_scoring._LEVEL_WEIGHT와
# 동일 철학)를 따른다. 대운·세운에서 형성된 기운을 월이 더하고 일에서 사건화(트리거)
# 되므로, 상위 운이 기운의 크기를 정하고 하위 운이 방아쇠를 당긴다(2026-06-12 사용자
# 확정). 일일 운세도 거시 형성 에너지를 점수에 반영하되, 출력 framing은 하루 단위
# 사건·조짐으로 한정한다(_DAILY_INSTRUCTION + 일진 grounding 담당).
_LIFESTYLE_LEVEL_WEIGHT = {
    CompositeLevel.DAEWOON: 1.0,
    CompositeLevel.YEAR: 0.85,
    CompositeLevel.MONTH: 0.6,
    CompositeLevel.DAY: 0.4,
    CompositeLevel.NATAL: 0.0,
}


def _lifestyle_scores(selected: list[LuckComposite]) -> dict[str, int]:
    """카테고리 5종 점수(50 중립 ± 부호화 신호 합, docs/02 E9 scores).

    운 위계 가중(대운>세운>월>일)으로 레벨을 결합하되, **레벨 안에서는 평균**해
    개수를 정규화한다 — 월간(그 달 ~30일)·연간(12개월)에서 하위 레벨 컴포지트 개수가
    많아 점수가 0/100으로 폭주하는 것을 막는다(2026-06-12 사용자 확정 보완). 하위
    기간은 '그 기간의 전형적 기운'으로 반영되고, 피크 시기는 주의/기회 시기 슬롯이
    담당한다. 일간은 레벨당 1개라 결과 불변.
    """
    cats = ("work", "money", "relationship", "health", "decision")
    by_level: dict[CompositeLevel, list[LuckComposite]] = {}
    for c in selected:
        by_level.setdefault(c.level, []).append(c)

    acc: dict[str, float] = dict.fromkeys(cats, 0.0)
    for level, comps in by_level.items():
        level_w = _LIFESTYLE_LEVEL_WEIGHT.get(level, 0.5)
        level_acc: dict[str, float] = dict.fromkeys(cats, 0.0)
        for c in comps:
            sign = (
                1.0 if c.favorability in ("용신", "희신")
                else -1.0 if c.favorability in ("기신", "구신")
                else 0.5
            )
            for s in c.domain_signals:
                category = _DOMAIN_TO_CATEGORY.get(s.domain, "decision")
                level_acc[category] += s.weight * sign
        # 레벨 내 평균(개수 정규화) 후 위계 가중 결합.
        for category in cats:
            acc[category] += (level_acc[category] / len(comps)) * level_w
    return {
        k: max(0, min(100, round(50 + v * 50)))
        for k, v in acc.items()
    }


def _slot_score(name: str, scores: dict[str, int]) -> int:
    """슬롯 대표 점수 — 매핑된 카테고리, 없으면 전체 평균."""
    if name in _SLOT_DOMAIN:
        return scores[_SLOT_DOMAIN[name]]
    return round(sum(scores.values()) / len(scores))


def _slot_summary(
    name: str, scores: dict[str, int],
    selected: list[LuckComposite], day_comps: list[LuckComposite],
) -> str:
    """슬롯별 서술 재료(수치 확정 — LLM은 문장화만)."""
    if name in ("핵심기운", "핵심흐름", "핵심주제"):
        ganji = ", ".join(
            f"{c.ganji.stem}{c.ganji.branch}({c.favorability})" for c in selected[:3]
        )
        return f"활성 간지: {ganji}" if ganji else "활성 신호 없음"
    if name in ("좋은날", "기회시기"):
        best = _extreme_periods(day_comps or selected, best=True)
        return f"상위: {', '.join(best)}" if best else "해당 없음"
    if name in ("주의할날", "주의시기", "주의행동"):
        worst = _extreme_periods(day_comps or selected, best=False)
        return f"주의: {', '.join(worst)}" if worst else "특이 주의 없음"
    if name == "일·돈·관계·건강":
        return (
            f"일 {scores['work']} · 돈 {scores['money']} · "
            f"관계 {scores['relationship']} · 건강 {scores['health']}"
        )
    if name == "상·하반기":
        return _half_year_summary(selected)
    if name in ("활용법", "행동전략"):
        return f"의사결정운 {scores['decision']} — 강한 분야 우선 활용"
    category = _SLOT_DOMAIN.get(name)
    return f"점수 {scores[category]}" if category else "점수 산출"


def _fav_sign(favorability: str) -> float:
    """기간 favorability → 부호(용·희 +1 / 기·구 −1 / 그 외 0.5)."""
    if favorability in ("용신", "희신"):
        return 1.0
    if favorability in ("기신", "구신"):
        return -1.0
    return 0.5


def _extreme_periods(comps: list[LuckComposite], *, best: bool, n: int = 2) -> list[str]:
    """부호화 신호 합 기준 상/하위 기간 키."""
    scored = [
        (sum(s.weight for s in c.domain_signals) * _fav_sign(c.favorability), c.period_key)
        for c in comps
    ]
    scored.sort(reverse=best)
    picked = scored[:n] if best else sorted(scored)[:n]
    return [k for v, k in picked if (v > 0) == best or v == 0]


def _half_year_summary(selected: list[LuckComposite]) -> str:
    """연간: 상·하반기 월 신호 집계."""
    h1 = [c for c in selected if c.level is CompositeLevel.MONTH and c.period_key[5:7] <= "06"]
    h2 = [c for c in selected if c.level is CompositeLevel.MONTH and c.period_key[5:7] > "06"]

    def net(group: list[LuckComposite]) -> float:
        return sum(
            sum(s.weight for s in c.domain_signals) * _fav_sign(c.favorability)
            for c in group
        )

    return f"상반기 {net(h1):+.2f} · 하반기 {net(h2):+.2f}"


def _top_keys(dist: dict[str, float], n: int) -> list[str]:
    """분포 상위 n개 키(값 내림차순, 동률은 키 순서)."""
    return [k for k, _v in sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


# ── 도메인 신호형 모듈 공용 헬퍼(M07 패턴) ───────────────────────────
_LEVELS_YM = {CompositeLevel.YEAR, CompositeLevel.MONTH}


def _domain_series_findings(
    composites: list[LuckComposite],
    period: PeriodSpec,
    *,
    domains: set[str],
    label: str,
    event_keys: set[str] | None = None,
    levels: set[CompositeLevel] | None = None,
) -> tuple[list[LuckComposite], list[TimeSeriesPoint], list[Finding]]:
    """기간 내 composite에서 도메인(+event_key) 신호를 시계열·findings로 확정(점수 최종).

    M07 패턴 공용 — 모듈별로 domain/event_keys/label만 바꿔 호출한다. 모든 수치는 여기서
    확정되며 LLM은 서술만 한다(docs/09 5장).
    """
    active_levels = levels if levels is not None else _LEVELS_YM
    selected = [
        c for c in composites
        if c.level in active_levels and _in_period(c.period_key, period)
    ]
    series: list[TimeSeriesPoint] = []
    findings: list[Finding] = []
    for c in sorted(selected, key=lambda x: x.period_key):
        sigs = [
            s for s in c.domain_signals
            if s.domain in domains and (event_keys is None or s.event_key in event_keys)
        ]
        if not sigs:
            continue
        score = max(0, min(100, round(sum(s.weight for s in sigs) * 100)))
        names = [s.source_interaction for s in sigs]
        gz = f"{c.ganji.stem}{c.ganji.branch}"
        series.append(TimeSeriesPoint(
            period_key=c.period_key, ganji=gz, score=score, signals=names,
        ))
        top = max(sigs, key=lambda s: s.weight)
        findings.append(Finding(
            key=f"{top.event_key or label}@{c.period_key}",
            summary=(
                f"{c.period_key} {gz} — {label} 신호 {len(sigs)}건"
                f"({top.event_key or label} 중심), {c.favorability} 기조"
            ),
            score=score, event_key=top.event_key, period_key=c.period_key, signals=names,
        ))
    findings.sort(key=lambda f: -f.score)
    return selected, series, findings


def _domain_topic(
    module_id: str,
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
    *,
    domains: set[str],
    label: str,
    style: StyleRules,
    event_keys: set[str] | None = None,
) -> TopicContext:
    """도메인 신호형 모듈의 TopicContext 조립(M01/M02/M09/M11/M12 공용)."""
    selected, series, findings = _domain_series_findings(
        composites, period, domains=domains, label=label, event_keys=event_keys,
    )
    return TopicContext(
        module_id=module_id,
        subjects=subjects,
        period=period,
        calendar_context=_calendar_context(selected),
        findings=findings[:5],
        time_series=series,
        style_rules=style,
        budget=_DEFAULT_BUDGET,
    )


# 모듈별 표현 제한(정책 — 절대원칙 3·8). _BASE_STYLE 위에 모듈 특화 톤을 얹는다.
_LOVE_STYLE = StyleRules(
    prohibited_expressions=[*_BASE_STYLE.prohibited_expressions, "반드시 만난다", "꼭 사귄다"],
    tone_notes=[*_BASE_STYLE.tone_notes, "연애는 가능성·시기·임하는 태도로(만남 단정 금지)"],
)
_MARRIAGE_STYLE = StyleRules(
    prohibited_expressions=[
        *_BASE_STYLE.prohibited_expressions, "반드시 결혼한다", "반드시 이혼한다",
    ],
    tone_notes=[
        *_BASE_STYLE.tone_notes,
        "결혼·이혼은 흐름·적합 시기로. 운 저점의 큰 결정은 보류 권고(조급함=신호)",
    ],
)
_WEALTH_STYLE = StyleRules(
    prohibited_expressions=[
        *_BASE_STYLE.prohibited_expressions, "당첨된다", "반드시 번다", "수익 보장",
    ],
    tone_notes=[
        *_BASE_STYLE.tone_notes,
        "재물은 흐름·유리 시기·태도로. 생활형 횡재는 소액·분산·재미 범위(번호·종목 픽 금지·"
        "당첨/수익 단정 금지·과몰입 권유 금지 — 절대원칙 8)",
    ],
)
_HEALTH_STYLE = StyleRules(
    prohibited_expressions=[
        *_BASE_STYLE.prohibited_expressions, "반드시 아프다", "완치된다", "이 병이다",
    ],
    tone_notes=[
        *_BASE_STYLE.tone_notes,
        "건강은 리스크 시기·관리 포인트로(진단·완치 단정 금지, 증상은 전문의 상담 안내)",
    ],
)
_EXAM_STYLE = StyleRules(
    prohibited_expressions=[
        *_BASE_STYLE.prohibited_expressions, "반드시 합격", "반드시 불합격", "당락 확정",
    ],
    tone_notes=[
        *_BASE_STYLE.tone_notes,
        "시험은 상대 우열·준비 시기·집중 구간까지만. 당락 확정 표현 금지(절대원칙 8)",
    ],
)


def build_love_context(
    subjects: list[SubjectRef], period: PeriodSpec, composites: list[LuckComposite],
) -> TopicContext:
    """M01 love_timing — 연애 시기·재회 (docs/09 4장: relationship 도메인 연애 이벤트)."""
    return _domain_topic(
        "M01", subjects, period, composites,
        domains={"relationship"}, label="연애",
        event_keys={"relationship_start", "relationship_end"}, style=_LOVE_STYLE,
    )


def build_marriage_context(
    subjects: list[SubjectRef], period: PeriodSpec, composites: list[LuckComposite],
) -> TopicContext:
    """M02 marriage — 결혼/이혼/재혼 (docs/09 4장: relationship 도메인 결혼·가정 이벤트)."""
    return _domain_topic(
        "M02", subjects, period, composites,
        domains={"relationship"}, label="결혼·가정",
        event_keys={"marriage", "childbirth", "family_change"}, style=_MARRIAGE_STYLE,
    )


def build_wealth_context(
    subjects: list[SubjectRef], period: PeriodSpec, composites: list[LuckComposite],
) -> TopicContext:
    """M09 wealth — 재물/유산/횡재/투기 (docs/09 4장: wealth 도메인 전체)."""
    return _domain_topic(
        "M09", subjects, period, composites,
        domains={"wealth"}, label="재물", style=_WEALTH_STYLE,
    )


def build_health_context(
    subjects: list[SubjectRef], period: PeriodSpec, composites: list[LuckComposite],
) -> TopicContext:
    """M11 health — 건강/수술 시기 (docs/09 4장: health 도메인)."""
    return _domain_topic(
        "M11", subjects, period, composites,
        domains={"health"}, label="건강", style=_HEALTH_STYLE,
    )


def build_education_context(
    subjects: list[SubjectRef], period: PeriodSpec, composites: list[LuckComposite],
) -> TopicContext:
    """M12 education_exam — 시험/입시/자격 (docs/09 4장: education 도메인)."""
    return _domain_topic(
        "M12", subjects, period, composites,
        domains={"education"}, label="시험·학업", style=_EXAM_STYLE,
    )


_BUSINESS_STYLE = StyleRules(
    prohibited_expressions=[
        *_BASE_STYLE.prohibited_expressions, "반드시 성공한다", "대박난다",
    ],
    tone_notes=[
        *_BASE_STYLE.tone_notes,
        "창업·동업은 적합 구조·시기·리스크로(성공 단정 금지). 동업은 관계·지분 점검 권고",
    ],
)


def build_business_context(
    subjects: list[SubjectRef], period: PeriodSpec, composites: list[LuckComposite],
) -> TopicContext:
    """M08 business — 창업/사업/동업 (docs/09 4장: 창업 신호 + 사업 계약·재물 흐름)."""
    return _domain_topic(
        "M08", subjects, period, composites,
        domains={"career", "wealth"}, label="사업",
        event_keys={"business_start", "contract", "document"}, style=_BUSINESS_STYLE,
    )


_PAST_STYLE = StyleRules(
    prohibited_expressions=[*_BASE_STYLE.prohibited_expressions, "분명히 ~였다"],
    tone_notes=[
        *_BASE_STYLE.tone_notes,
        "과거 검증은 맞춘 항목으로 신뢰도를 보정하는 용도 — 콜드리딩 금지(연 ≤2건·근거 필수·"
        "이미 일어난 일은 사실 확인형으로만)",
    ],
)


def build_past_validation_context(
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
    *,
    birth: BirthInput,
    scorer: EventEngineV2,
    compute: ComputeFn,
) -> TopicContext:
    """M14 past_validation — 과거 이벤트 복원·검증 (docs/09 4장, E7 역방향 재사용).

    composites(미래/현재 사전계산)가 아니라 past_validation 엔진으로 과거창을 역산한다 — birth/
    scorer/compute를 extras로 받는다(M03/M10처럼 정적·서비스 의존을 호출 측이 공급). 후보의 점수·
    근거는 엔진이 확정하고 LLM은 사실 확인형으로만 서술(콜드리딩 금지).
    """
    start_year = int(period.start[:4])
    end_year = int(period.end[:4])
    result = generate_past_candidates(birth, scorer, compute, start_year, end_year)
    findings = [
        Finding(
            key=f"{c.event_key}@{c.year_range}",
            summary=(
                f"{c.year_range} {c.event_key} — {' · '.join(c.readable)}"
                if c.readable else f"{c.year_range} {c.event_key} (검증 후보)"
            ),
            score=c.score,
            event_key=c.event_key,
            period_key=c.year_range,
        )
        for c in result.candidates
    ]
    findings.sort(key=lambda f: -f.score)
    return TopicContext(
        module_id="M14",
        subjects=subjects,
        period=period,
        findings=findings[:8],  # 과거 후보는 다소 넉넉히(연 ≤2 콜드리딩 가드는 엔진에서)
        style_rules=_PAST_STYLE,
        budget=_DEFAULT_BUDGET,
    )


# 모듈 레지스트리 — 구현된 모듈만 빌더 연결, 나머지는 계획 상태.
BUILDERS: dict[str, BuilderFn | None] = {mid: None for mid in MODULES}
BUILDERS["M01"] = build_love_context
BUILDERS["M02"] = build_marriage_context
BUILDERS["M03"] = build_personality_context  # extras: natal_ten_god_dist
BUILDERS["M07"] = build_career_context
BUILDERS["M08"] = build_business_context
BUILDERS["M09"] = build_wealth_context
BUILDERS["M10"] = build_relocation_context  # extras: relocation_query 외 2종
BUILDERS["M11"] = build_health_context
BUILDERS["M12"] = build_education_context
BUILDERS["M14"] = build_past_validation_context  # extras: birth/scorer/compute
BUILDERS["M15"] = build_lifestyle_context  # extras 선택


def build_topic_context(
    module_id: str,
    subjects: list[SubjectRef],
    period: PeriodSpec,
    composites: list[LuckComposite],
    **extras: object,
) -> TopicContext:
    """모듈 디스패치 — 미등록 ID·미구현 모듈은 명시적 오류.

    extras: T0 데이터가 필요한 모듈용 키워드(M03 natal_ten_god_dist,
    M10 relocation_query/composites_by_subject/yongsin_by_subject 등).

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
    return builder(subjects, period, composites, **extras)
