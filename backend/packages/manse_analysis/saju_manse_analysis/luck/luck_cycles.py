"""대운·세운·월운·일운 산출 + 용신 후보 관계.

운은 원국 분포를 바꾸지 않는다(별도 레이어). 대운표는 출생 기준 결정론적으로 산출하고,
세운/월운/일운은 날짜 함수라 결정론적이되 '현재' 구간은 reference_date 가 있을 때만 채운다.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, timedelta

from saju_manse_core.calendar.sexagenary_cycle import (
    day_ganzi,
    ganzi_from_index,
    ganzi_index,
    year_ganzi,
)
from saju_manse_core.calendar.solar_terms import SolarTermTable
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    MONTH_BRANCH_ORDER,
    MONTH_STEM_START,
    SIX_COMBINATIONS,
    STEM_COMBINATIONS,
    STEM_ELEMENT,
    STEM_INDEX,
    STEMS,
    THREE_HARMONY,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.luck import DaewoonItem, LuckCycles, LuckPillar
from saju_shared_types.pillars import FourPillarsResult


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29 → Feb 28
        return d.replace(year=d.year + years, day=28)


def _alignment(elements: set[str], useful: set[str], unfavorable: set[str]) -> str:
    hit_u = bool(elements & useful)
    hit_g = bool(elements & unfavorable)
    if hit_u and hit_g:
        return "혼합"
    if hit_u:
        return "용신운"
    if hit_g:
        return "기신운"
    return "평운"


def _relations_to_chart(stem: Stem, branch: Branch, pillars: FourPillarsResult) -> list[str]:
    natal_branches = [Branch(p.branch) for p in _natal(pillars)]
    natal_stems = [Stem(p.stem) for p in _natal(pillars)]
    out: list[str] = []
    for nb in natal_branches:
        key = frozenset({branch, nb})
        if branch != nb and key in BRANCH_CLASHES:
            out.append(f"충:{branch}-{nb}")
        if branch != nb and key in SIX_COMBINATIONS:
            out.append(f"육합:{branch}-{nb}")
    for ns in natal_stems:
        if stem != ns and frozenset({stem, ns}) in STEM_COMBINATIONS:
            out.append(f"천간합:{stem}-{ns}")
    for members, element, _royal in THREE_HARMONY:
        if branch in members and (members - {branch}) & set(natal_branches):
            out.append(f"삼합기여:{element}")
    return out


def _transformed_elements(branch: Branch, pillars: FourPillarsResult) -> list[str]:
    """운 지지가 원국과 육합/삼합으로 만들어내는 변환 오행(target element)."""
    natal_branches = [Branch(p.branch) for p in _natal(pillars)]
    out: set[str] = set()
    for nb in natal_branches:
        key = frozenset({branch, nb})
        if branch != nb and key in SIX_COMBINATIONS:
            out.add(str(SIX_COMBINATIONS[key]))
    for members, element, _royal in THREE_HARMONY:
        if branch in members and (members - {branch}) & set(natal_branches):
            out.add(str(element))
    return sorted(out)


def _natal(pillars: FourPillarsResult) -> list:
    items = [pillars.year, pillars.month, pillars.day]
    if pillars.hour is not None:
        items.append(pillars.hour)
    return items


def _volatility(relations: list[str]) -> float:
    return round(sum(3.0 if r.startswith("충") else 1.0 for r in relations), 2)


def _luck_pillar(
    label: str,
    period_type: str,
    stem: Stem,
    branch: Branch,
    pillars: FourPillarsResult,
    dm: Stem,
    useful: set[str],
    unfavorable: set[str],
    solar_range: str | None = None,
) -> LuckPillar:
    rels = _relations_to_chart(stem, branch, pillars)
    elements = {str(STEM_ELEMENT[stem]), str(BRANCH_ELEMENT[branch])}
    return LuckPillar(
        label=label,
        period_type=period_type,
        ganji=f"{stem}{branch}",
        stem=str(stem),
        branch=str(branch),
        stem_ten_god=str(ten_god(dm, stem)),
        branch_ten_god=str(ten_god(dm, main_hidden_stem(branch))),
        raw_elements=sorted(elements),
        relations_to_chart=rels,
        yongsin_alignment=_alignment(elements, useful, unfavorable),
        solar_term_range=solar_range,
    )


def _daewoon_start(absolute_instant: datetime, direction: str, table: SolarTermTable) -> float:
    # 대운수: 절기(월령 節)까지의 거리 / 3 (3일=1년). 中氣가 아니라 節 경계를 사용.
    prev_jeol, next_jeol = table.bounding_month_terms(absolute_instant)
    if direction == "forward":
        diff = next_jeol - absolute_instant
    else:
        diff = absolute_instant - prev_jeol
    return max(diff.total_seconds() / 86400.0 / 3.0, 0.0)


def compute_luck_cycles(
    pillars: FourPillarsResult,
    absolute_instant: datetime,
    birth_date: date,
    direction: str,
    useful_elements: set[str],
    unfavorable_elements: set[str],
    table: SolarTermTable,
    reference_date: date | None = None,
) -> LuckCycles:
    dm = Stem(pillars.day.stem)
    step = 1 if direction == "forward" else -1
    month_idx = ganzi_index(Stem(pillars.month.stem), Branch(pillars.month.branch))

    start_exact = _daewoon_start(absolute_instant, direction, table)
    start_age = max(int(round(start_exact)), 0)

    daewoon: list[DaewoonItem] = []
    exact_jiao_un: list[str] = []
    for i in range(9):
        stem, branch = ganzi_from_index(month_idx + step * (i + 1))
        age = start_age + 10 * i
        sdate = _add_years(birth_date, age)
        edate = _add_years(birth_date, age + 10)
        # 정밀 교운일시(소수 나이 기반): 출생 절대시각 + (정확 시작나이 + 10i)년.
        exact_dt = absolute_instant + timedelta(days=(start_exact + 10 * i) * 365.2425)
        exact_jiao_un.append(exact_dt.date().isoformat())
        rels = _relations_to_chart(stem, branch, pillars)
        raw = sorted({str(STEM_ELEMENT[stem]), str(BRANCH_ELEMENT[branch])})
        transformed = _transformed_elements(branch, pillars)
        daewoon.append(DaewoonItem(
            index=i, start_age=age, approx_start_date=sdate, approx_end_date=edate,
            ganji=f"{stem}{branch}", stem=str(stem), branch=str(branch),
            stem_ten_god=str(ten_god(dm, stem)),
            branch_ten_god=str(ten_god(dm, main_hidden_stem(branch))),
            twelve_unseong=twelve_unseong(dm, branch),
            relations_to_chart=rels,
            raw_elements=raw,
            transformed_elements=transformed,
            yongsin_relation=_alignment(set(raw), useful_elements, unfavorable_elements),
            volatility_score=_volatility(rels),
        ))

    cycles = LuckCycles(
        direction=direction,
        start_age=start_age,
        start_age_exact=round(start_exact, 3),
        daewoon_table=daewoon,
        trace={
            "rule": "3일=1년 절기거리",
            "month_pillar_index": month_idx,
            "exact_jiao_un_dates": exact_jiao_un,
            "approx_date_note": "approx_*_date는 정수나이 기반 근사; 정밀일은 exact_jiao_un_dates",
        },
    )

    if reference_date is not None:
        before_birthday = (reference_date.month, reference_date.day) < (
            birth_date.month, birth_date.day
        )
        current_age = reference_date.year - birth_date.year - (1 if before_birthday else 0)
        cycles.current_age = current_age
        for item in daewoon:
            if item.start_age <= current_age < item.start_age + 10:
                cycles.current_daewoon_index = item.index
                break
        cycles.yearly_luck = _yearly(
            pillars, dm, useful_elements, unfavorable_elements,
            range(reference_date.year - 2, reference_date.year + 3),
        )
        cycles.monthly_luck = _monthly(
            pillars, dm, useful_elements, unfavorable_elements, reference_date.year, table
        )
        cycles.daily_luck = _daily(
            pillars, dm, useful_elements, unfavorable_elements,
            reference_date.year, reference_date.month,
        )

    return cycles


def _yearly(pillars, dm, useful, unfavorable, years) -> list[LuckPillar]:
    out = []
    for y in years:
        stem, branch = year_ganzi(y)
        out.append(_luck_pillar(str(y), "year", stem, branch, pillars, dm, useful, unfavorable))
    return out


def _monthly(
    pillars, dm, useful, unfavorable, year: int, table: SolarTermTable
) -> list[LuckPillar]:
    out = []
    year_stem, _yb = year_ganzi(year)
    for inst, name, branch in table.month_terms_in_solar_year(year):
        offset = MONTH_BRANCH_ORDER.index(branch)
        stem = STEMS[(STEM_INDEX[MONTH_STEM_START[year_stem]] + offset) % 10]
        label = f"{inst.year}-{inst.month:02d}"
        out.append(_luck_pillar(
            label, "month", stem, branch, pillars, dm, useful, unfavorable, solar_range=name
        ))
    return out


def _daily(pillars, dm, useful, unfavorable, year: int, month: int) -> list[LuckPillar]:
    out = []
    days = _cal.monthrange(year, month)[1]
    d = date(year, month, 1)
    for _ in range(days):
        stem, branch = day_ganzi(d)
        out.append(_luck_pillar(
            d.isoformat(), "day", stem, branch, pillars, dm, useful, unfavorable
        ))
        d = d + timedelta(days=1)
    return out
