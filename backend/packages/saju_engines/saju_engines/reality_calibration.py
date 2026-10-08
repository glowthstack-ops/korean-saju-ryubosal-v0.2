"""현실 신호 캘리브레이션 — 주요 ~10개 연도의 연도별 발생 이벤트 선택 질문 생성·적재.

doc/v2_2/LIFE_EVENT_INFERENCE.md §5. 성년 이후 현재까지에서 엔진 사건화 강도·대운 교운 인접·
생애 분산으로 ~10개 연도를 고르고, 연도별 후보 이벤트(한글 라벨 + 신호 지문)를 제시한다.
사용자 선택은 LifeEventRow(원자 행)로 변환한다. **수집만** — 랭킹 미반영(코호트 게이트는 별도).
"""

from __future__ import annotations

from saju_shared_types.event_engine import ConfidenceLevel, EventCandidateV2
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN, event_ko_v2
from saju_shared_types.life_event import (
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    OccurredEvent,
    RealityCalibrationEvent,
    RealityCalibrationQuestionSet,
    RealityCalibrationSubmission,
    RealityCalibrationSubmitResult,
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
_MAX_EVENTS_PER_YEAR = 5  # CAL-R1: 6→5(도메인 cap 2·반복 회피 후 노출 수)
_EVENT_DOMAIN_CAP = 2  # 한 해 안 같은 도메인 사건 상한(직업 편중 완화)
_DOMAIN_BY_KEY: dict[str, str] = {str(k): v for k, v in EVENT_DOMAIN.items()}
# 생애 구간(만 나이) — 설계 §5 "생애 구간 분산(사회초년·30대 등)": 구간을 돌아가며 뽑아 한 시기에
# 몰리지 않게 한다(실측 결함: salience 동점을 오래된 해부터 채워 1999~2006 8년 연속).
_LIFE_BANDS: tuple[tuple[int, int, str], ...] = (
    (19, 25, "사회초년기"), (26, 32, "20대 후반~30대 초"), (33, 39, "30대"),
    (40, 49, "40대"), (50, 200, "50대 이후"),
)


def _band_of(age: int) -> tuple[int, int, str]:
    for lo, hi, ko in _LIFE_BANDS:
        if lo <= age <= hi:
            return lo, hi, ko
    return _LIFE_BANDS[-1]


def _year_hint(salience: float, jiao: bool) -> str:
    """이 해를 묻는 이유(사용자용, 템플릿 고정)."""
    if jiao:
        return "10년 대운이 바뀐 해예요 — 소속·거주·관계가 달라졌는지 떠올려 보세요."
    if salience >= 3:
        return "사건 신호가 강하게 뜬 해예요. 실제로 있었던 일만 골라 주세요."
    return "이 시기의 실제 사건을 확인해요."


def _pick_years_spread(
    candidate_years: list[int], salience, birth_year: int, n_years: int,
) -> list[int]:
    """생애 구간 round-robin + 이미 고른 해의 ±1년 후순위 + 동점은 최근 해(기억 선명)."""
    by_band: dict[str, list[int]] = {}
    for y in candidate_years:
        by_band.setdefault(_band_of(y - birth_year)[2], []).append(y)
    order = [ko for _lo, _hi, ko in _LIFE_BANDS if ko in by_band]
    for ko in order:
        by_band[ko].sort(key=lambda y: (-salience(y), -y))
    chosen: list[int] = []
    while len(chosen) < n_years and any(by_band.values()):
        progressed = False
        for ko in order:
            pool = by_band[ko]
            if not pool or len(chosen) >= n_years:
                continue
            pick = next((y for y in pool if all(abs(y - c) > 1 for c in chosen)), pool[0])
            pool.remove(pick)
            chosen.append(pick)
            progressed = True
        if not progressed:
            break
    return chosen


def _select_events(
    cands: list[EventCandidateV2], used: dict[str, int], limit: int,
) -> list[EventCandidateV2]:
    """강도순 후보에서 앞 연도에 덜 나온 사건 우선·도메인당 2건·주제성(THEME_ONLY) 후순위."""
    ranked = sorted(
        enumerate(cands),
        key=lambda t: (
            used.get(str(t[1].event_key), 0),
            -_CONF_RANK.get(t[1].confidence_level, 0), -t[1].score, t[0],
        ),
    )
    out: list[EventCandidateV2] = []
    per_dom: dict[str, int] = {}
    for _i, c in ranked:
        dom = _DOMAIN_BY_KEY.get(str(c.event_key), "other")
        if per_dom.get(dom, 0) >= _EVENT_DOMAIN_CAP:
            continue
        out.append(c)
        per_dom[dom] = per_dom.get(dom, 0) + 1
        if len(out) >= limit:
            break
    # 도메인 상한으로 3건도 못 채우면 최소 3건까지만 보충(그 이상은 상한을 지킨다).
    floor = min(3, len(cands))
    if len(out) < floor:
        for _i, c in ranked:
            if c not in out:
                out.append(c)
                if len(out) >= floor:
                    break
    for c in out:
        used[str(c.event_key)] = used.get(str(c.event_key), 0) + 1
    return out


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

    ranked = _pick_years_spread(candidate_years, salience, by, n_years)
    ganji_by_year = _sewoon_ganji(chart)

    years_out: list[RealityCalibrationYear] = []
    used_events: dict[str, int] = {}
    for year in sorted(ranked):
        cands = _select_events(by_year.get(year, []), used_events, max_events_per_year)
        events = [
            RealityCalibrationEvent(
                event_key=str(c.event_key),
                label=event_ko_v2(c.event_key),
                fingerprint=fingerprint_of(c),
            )
            for c in cands
        ]
        age = year - by
        years_out.append(RealityCalibrationYear(
            year=year,
            ganji=ganji_by_year.get(year, ""),
            salience=round(salience(year), 2),
            daewoon_transition=year in jiao,
            events=events,
            age=age,
            band_ko=_band_of(age)[2],
            hint=_year_hint(salience(year), year in jiao),
        ))
    return RealityCalibrationQuestionSet(subject_id=subject_id, years=years_out)


def submission_summary(
    rows: list[LifeEventRow], submission: RealityCalibrationSubmission, stored: int,
) -> RealityCalibrationSubmitResult:
    """제출 결과 사용자용 요약(템플릿) — 답한 연도 수·확인 사건·없었던 사건·용도 안내."""
    confirmed = sum(1 for r in rows if r.outcome is LifeEventOutcome.CONFIRMED)
    not_happened = sum(1 for r in rows if r.outcome is LifeEventOutcome.NOT_HAPPENED)
    answered_years = {int(r.period[:4]) for r in rows}
    n_years = len(answered_years)
    lines: list[str] = []
    if n_years == 0:
        lines.append("저장된 답이 없어요. 기억나는 해만 골라 저장해도 풀이에 도움이 돼요.")
    else:
        lines.append(
            f"{n_years}개 해에 대해 실제 있었던 일 {confirmed}건, 없었던 일 {not_happened}건을 "
            "개인 기록으로 저장했어요."
        )
        lines.append(
            "이 기록은 풀이에서 '이런 신호에 실제로 일이 생겼는가'를 참고하는 데 쓰이며, "
            "언제든 수정할 수 있어요."
        )
    return RealityCalibrationSubmitResult(
        stored=stored, confirmed=confirmed, not_happened=not_happened,
        years_answered=n_years, summary=lines,
    )


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
