"""현실 신호 캘리브레이션 — 주요 ~10개 연도의 연도별 발생 이벤트 선택 질문 생성·적재.

doc/v2_2/LIFE_EVENT_INFERENCE.md §5. 성년 이후 현재까지에서 엔진 사건화 강도·대운 교운 인접·
생애 분산으로 ~10개 연도를 고르고, 연도별 후보 이벤트(한글 라벨 + 신호 지문)를 제시한다.
사용자 선택은 LifeEventRow(원자 행)로 변환한다. **수집만** — 랭킹 미반영(코호트 게이트는 별도).
"""

from __future__ import annotations

from saju_shared_types.event_engine import ConfidenceLevel, EventCandidateV2
from saju_shared_types.event_taxonomy_v2 import event_ko_v2
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    OccurredEvent,
    RealityCalibrationEvent,
    RealityCalibrationQuestionSet,
    RealityCalibrationSubmission,
    RealityCalibrationYear,
    RealityCalibrationYearAnswer,
    SignalFingerprint,
)
from saju_shared_types.manse_result import ManseV2Result

from .event_engine_v2 import EventEngineV2
from .personal_calibration import candidate_fingerprint as fingerprint_of  # 신호 지문(공용)

_CONF_RANK: dict[ConfidenceLevel, int] = {
    ConfidenceLevel.THEME_ONLY: 0,
    ConfidenceLevel.WEAK_EVENT_CANDIDATE: 1,
    ConfidenceLevel.EVENT_CANDIDATE: 2,
    ConfidenceLevel.STRONG_EVENT_CANDIDATE: 3,
    ConfidenceLevel.HIGH_PROBABILITY_EVENT: 4,
}
_ADULT_AGE = 19  # 성년(만 19세) 이후를 회상 대상으로 본다
_DEFAULT_N_YEARS = 10
_MAX_EVENTS_PER_YEAR = 6


def _birth_year(chart: ManseV2Result) -> int | None:
    raw = (chart.input_summary or {}).get("birth_date", "")
    return int(raw[:4]) if isinstance(raw, str) and raw[:4].isdigit() else None


def _jiao_years(chart: ManseV2Result) -> set[int]:
    if chart.luck_cycles is None:
        return set()
    out: set[int] = set()
    for d in chart.luck_cycles.trace.get("exact_jiao_un_dates", []):
        if isinstance(d, str) and d[:4].isdigit():
            out.add(int(d[:4]))
    return out


def build_reality_calibration(
    chart: ManseV2Result,
    engine: EventEngineV2,
    current_year: int,
    *,
    subject_id: str | None = None,
    n_years: int = _DEFAULT_N_YEARS,
    max_events_per_year: int = _MAX_EVENTS_PER_YEAR,
) -> RealityCalibrationQuestionSet:
    """성년~현재에서 주요 ~n_years개 연도를 골라 연도별 발생 이벤트 선택 질문을 만든다."""
    by = _birth_year(chart)
    if by is None:
        return RealityCalibrationQuestionSet(subject_id=subject_id)
    start = by + _ADULT_AGE
    candidate_years = [y for y in range(start, current_year + 1)]
    if not candidate_years:
        return RealityCalibrationQuestionSet(subject_id=subject_id)

    scored = engine.score_years(chart, candidate_years)
    by_year: dict[int, list[EventCandidateV2]] = {}
    for c in scored:
        if c.period.isdigit():
            by_year.setdefault(int(c.period), []).append(c)
    jiao = _jiao_years(chart)

    # 연도 salience = 그 해 최고 사건화 강도 + 대운 교운 인접 가점.
    def salience(year: int) -> float:
        cands = by_year.get(year, [])
        top = max((_CONF_RANK.get(c.confidence_level, 0) for c in cands), default=0)
        return top + (1.5 if year in jiao else 0.0)

    ranked = sorted(candidate_years, key=lambda y: (-salience(y), y))[:n_years]
    ganji_by_year = _sewoon_ganji(chart)

    years_out: list[RealityCalibrationYear] = []
    for year in sorted(ranked):
        cands = sorted(
            by_year.get(year, []),
            key=lambda c: (-_CONF_RANK.get(c.confidence_level, 0), -c.score),
        )[:max_events_per_year]
        events = [
            RealityCalibrationEvent(
                event_key=str(c.event_key),
                label=event_ko_v2(c.event_key),
                fingerprint=fingerprint_of(c),
            )
            for c in cands
        ]
        years_out.append(RealityCalibrationYear(
            year=year,
            ganji=ganji_by_year.get(year, ""),
            salience=round(salience(year), 2),
            daewoon_transition=year in jiao,
            events=events,
        ))
    return RealityCalibrationQuestionSet(subject_id=subject_id, years=years_out)


def _sewoon_ganji(chart: ManseV2Result) -> dict[int, str]:
    """연도 → 세운 간지(질문 표시용)."""
    out: dict[int, str] = {}
    lc = chart.luck_cycles
    if lc is None:
        return out
    for p in lc.yearly_luck:
        if p.label.isdigit():
            out[int(p.label)] = p.ganji
    for d in lc.daewoon_table:
        for p in d.sewoon or []:
            if p.label.isdigit():
                out.setdefault(int(p.label), p.ganji)
    return out


def pillars_signature(chart: ManseV2Result) -> tuple[str, str, str, str | None, str | None]:
    """코호트 지문 = (年,月,日,時 간지, 성별). 시간 미상이면 時=None."""
    assert chart.pillars is not None
    p = chart.pillars
    hour = getattr(p.hour, "ganji", None) if p.hour is not None else None
    gender = (chart.input_summary or {}).get("gender")
    return p.year.ganji, p.month.ganji, p.day.ganji, hour, gender


def month_event_fingerprints(
    month_candidates: list[EventCandidateV2], ym: str
) -> dict[str, SignalFingerprint]:
    """그 달(ym='YYYY-MM') 월운 후보 → 이벤트 키별 월운 지문(발생 월 정밀화용)."""
    return {
        str(c.event_key): fingerprint_of(c)
        for c in month_candidates if c.period == ym
    }


def prior_answers_from_rows(
    rows: list[LifeEventRow],
) -> list[RealityCalibrationYearAnswer]:
    """저장된 확인 사건(LifeEventRow) → 이전 답변으로 복원(수정 모드 프리필).

    period('YYYY'/'YYYY-MM')에서 연도·월을, outcome에서 발생 여부를 되살린다. 그 해에 행은
    있으나 confirmed가 하나도 없으면 '해당 없음'으로 재구성(제출 당시 전부 not_happened).
    """
    by_year: dict[int, list[LifeEventRow]] = {}
    for r in rows:
        try:
            year = int(r.period[:4])
        except (ValueError, IndexError):
            continue
        by_year.setdefault(year, []).append(r)

    answers: list[RealityCalibrationYearAnswer] = []
    for year, yr_rows in sorted(by_year.items()):
        occurred: list[OccurredEvent] = []
        for r in yr_rows:
            if r.outcome != LifeEventOutcome.CONFIRMED:
                continue
            month = int(r.period[5:7]) if len(r.period) >= 7 and "-" in r.period else None
            occurred.append(OccurredEvent(event_key=r.event_key, month=month))
        answers.append(RealityCalibrationYearAnswer(
            year=year, occurred=occurred, none_of_them=not occurred,
        ))
    return answers


def rows_from_submission(
    submission: RealityCalibrationSubmission,
    question: RealityCalibrationQuestionSet,
    pillars_sig: tuple[str, str, str, str | None, str | None],
    month_fp: dict[tuple[int, int, str], SignalFingerprint] | None = None,
) -> list[LifeEventRow]:
    """연도별 선택 → LifeEventRow(원자 행). 선택=confirmed, 미선택 후보=not_happened.

    발생 사건에 월이 있고 month_fp에 그 월운 지문이 있으면 period='YYYY-MM' + 월운 지문으로
    정밀 적재한다(없으면 연도 지문 폴백 — 규칙11).
    """
    py, pm, pd, ph, gender = pillars_sig
    month_fp = month_fp or {}
    events_by_year = {y.year: y.events for y in question.years}
    answer_by_year = {a.year: a for a in submission.answers}
    rows: list[LifeEventRow] = []
    for year, events in events_by_year.items():
        ans = answer_by_year.get(year)
        if ans is None:
            continue  # 미응답 연도는 적재하지 않음(미입력 무해 — 규칙11)
        months = {} if ans.none_of_them else {o.event_key: o.month for o in ans.occurred}
        for ev in events:
            occurred = ev.event_key in months
            month = months.get(ev.event_key)
            if occurred and month and (year, month, ev.event_key) in month_fp:
                period = f"{year}-{month:02d}"
                fingerprint = month_fp[(year, month, ev.event_key)]
            else:
                period = str(year)
                fingerprint = ev.fingerprint
            rows.append(LifeEventRow(
                event_row_id=f"{submission.subject_id}:{period}:{ev.event_key}",
                subject_id=submission.subject_id,
                owner_id=submission.owner_id,
                pillar_year=py, pillar_month=pm, pillar_day=pd, pillar_hour=ph,
                gender=gender,
                event_key=ev.event_key,
                period=period,
                signal_fingerprint=fingerprint,
                outcome=(
                    LifeEventOutcome.CONFIRMED if occurred
                    else LifeEventOutcome.NOT_HAPPENED
                ),
                source=LifeEventSource.REALITY_SIGNAL_CALIBRATION,
                weight=1.0,
            ))
    return rows
