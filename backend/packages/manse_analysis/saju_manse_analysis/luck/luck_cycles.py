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
    hidden_stems_for,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.luck import DaewoonItem, LuckCycles, LuckPillar, LuckPolarity
from saju_shared_types.pillars import FourPillarsResult

# 운 종류별 (천간, 지지) 가중치 — 긴 운일수록 지지(기반) 비중↑.
_PERIOD_WEIGHTS: dict[str, tuple[float, float]] = {
    "daewoon": (0.35, 0.65), "year": (0.45, 0.55),
    "month": (0.40, 0.60), "day": (0.40, 0.60),
}


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29 → Feb 28
        return d.replace(year=d.year + years, day=28)


def _polarity_type(score: float) -> str:
    if score > 0.15:
        return "용신"
    if score < -0.15:
        return "기신"
    return "한신"


def _stem_effect(stem: Stem, useful: set[str], unfavorable: set[str]) -> LuckPolarity:
    """천간(드러남) 효과 — 표면 오행 하나로 용신/기신 판정."""
    el = str(STEM_ELEMENT[stem])
    score = 1.0 if el in useful else (-1.0 if el in unfavorable else 0.0)
    return LuckPolarity(element=el, type=_polarity_type(score), score=score)


def _branch_effect(branch: Branch, useful: set[str], unfavorable: set[str]) -> LuckPolarity:
    """지지(기반) 효과 — 지장간(정기·중기·여기) 가중 합으로 강약까지 반영."""
    score = 0.0
    parts: list[str] = []
    for hstem, _htype, weight in hidden_stems_for(branch):
        hel = str(STEM_ELEMENT[hstem])
        sign = 1.0 if hel in useful else (-1.0 if hel in unfavorable else 0.0)
        score += weight * sign
        parts.append(f"{hstem}{hel}")
    score = round(score, 4)
    return LuckPolarity(
        element=str(BRANCH_ELEMENT[branch]),  # 정기 대표 오행
        type=_polarity_type(score), score=score, detail="·".join(parts),
    )


def _relation_modifier(
    transformed: list[str], useful: set[str], unfavorable: set[str],
) -> float:
    """합 변환 오행의 용신/기신 방향만 가감(±0.2). 충/공망은 지지 동태에서 처리(이중 감산 방지)."""
    mod = 0.0
    for el in transformed:
        if el in useful:
            mod += 0.10
        elif el in unfavorable:
            mod -= 0.10
    return round(max(min(mod, 0.2), -0.2), 4)


def _branch_dynamics(
    branch_eff: LuckPolarity, branch: Branch, void: bool, relations: list[str],
    useful: set[str], unfavorable: set[str],
) -> None:
    """공망/충이 지지 용신·기신의 발현을 바꾼다(실속·사건성). branch_eff를 제자리 갱신.

    방향성(용신/기신)은 유지하고, 공망은 작동력·실속을, 충은 사건화·변동성을 조정한다.
    같은 충/공망을 _relation_modifier에서 다시 깎지 않는다(이중 감산 방지).
    """
    base = branch_eff.score
    clashes = [r for r in relations if r.startswith("충")]
    has_clash = bool(clashes)
    btype = branch_eff.type

    score, trigger, volatility, reliability = base, 0.0, 0.0, 1.0
    if void and has_clash:  # 비어 있던 것이 충으로 자극 → 사건화, 안정성 낮음
        score *= 0.65
        trigger, volatility, reliability = 1.5, 1.5, 0.5
    elif void:  # 작동력 저하·지연·실속 부족
        score *= 0.60
        volatility, reliability = 1.0, 0.6
    elif has_clash:  # 변화·충돌을 통해 발현
        score *= 0.80
        trigger, volatility, reliability = 1.0, 1.0, 0.85

    # 충 상대(원국 지지) 성격에 따른 방향성(경우 A/B).
    note = ""
    for r in clashes:
        pair = r.split(":", 1)[1].split("-")
        other = pair[1] if pair[0] == str(branch) else pair[0]
        nel = str(BRANCH_ELEMENT[Branch(other)])
        if btype == "용신" and nel in unfavorable:
            note, trigger = f" · 원국 기신({nel}) 충거(정리)", trigger + 0.5
        elif btype == "기신" and nel in useful:
            note, volatility = f" · 원국 용신({nel}) 기반 손상", volatility + 0.5

    label = ""
    if btype in ("용신", "기신"):
        kind = "용신운" if btype == "용신" else "기신운"
        if void and has_clash:
            label = f"공망충발 {kind}"
        elif void:
            label = f"공망 {kind}"
        elif has_clash:
            label = "충발 용신운" if btype == "용신" else "충동 기신운"

    branch_eff.base_score = round(base, 4)
    branch_eff.score = round(score, 4)
    branch_eff.is_void = void
    branch_eff.has_clash = has_clash
    branch_eff.branch_label = (label + note) if label else note.lstrip(" ·").strip()
    branch_eff.event_trigger = round(trigger, 2)
    branch_eff.volatility = round(volatility, 2)
    branch_eff.reliability = round(reliability, 2)


def _luck_label(stem_t: str, branch_t: str, strong_relation: bool) -> tuple[str, str, str]:
    """천간/지지 용신관계 조합 → (code, 한글 라벨, 요약)."""
    if stem_t == "용신" and branch_t == "용신":
        return ("pure_yongsin_luck", "강한 용신운",
                "천간·지지가 모두 용신 — 기회와 실제 기반이 함께 좋아지는 운")
    if stem_t == "기신" and branch_t == "기신":
        return ("pure_gisin_luck", "강한 기신운",
                "천간·지지가 모두 기신 — 현실 부담이 크고 사건화되기 쉬운 운")
    if stem_t == "용신" and branch_t == "기신":
        return ("mixed_yongsin_surface", "천간 용신·지지 기신(혼합)",
                "겉으로 기회·도움이 보이나 현실 기반은 부담이 함께 오는 운")
    if stem_t == "기신" and branch_t == "용신":
        return ("mixed_gisin_surface", "천간 기신·지지 용신(혼합)",
                "초반엔 압박이 드러나나 실제 기반은 회복되는 운")
    if "용신" in (stem_t, branch_t):
        return ("partial_yongsin", "용신운(부분)",
                "천간·지지 중 한쪽만 용신이라 작동이 부분적인 운")
    if "기신" in (stem_t, branch_t):
        return ("partial_gisin", "기신운(부분)",
                "천간·지지 중 한쪽만 기신이라 압박이 부분적인 운")
    if strong_relation:
        return ("trigger_luck", "변동·트리거운",
                "용신·기신색은 옅으나 충·합·공망 자극으로 변동이 큰 운")
    return ("neutral_luck", "평운", "용신·기신 작용이 뚜렷하지 않은 운")


def _coarse_alignment(code: str) -> str:
    """세분 라벨 → 기존 coarse 라벨(용신운/기신운/혼합/평운) 호환."""
    if code in ("pure_yongsin_luck", "partial_yongsin"):
        return "용신운"
    if code in ("pure_gisin_luck", "partial_gisin"):
        return "기신운"
    if code in ("mixed_yongsin_surface", "mixed_gisin_surface"):
        return "혼합"
    return "평운"


def _luck_effect(
    stem: Stem, branch: Branch, useful: set[str], unfavorable: set[str], period_type: str,
    relations: list[str], transformed: list[str], void: bool,
) -> dict:
    """천간·지지·관계를 분리 평가하고 가중 점수·세분 라벨을 산출.

    지지는 방향(용신/기신) 평가 후 공망·충 동태(_branch_dynamics)로 작동력·사건성을 조정한다.
    """
    stem_eff = _stem_effect(stem, useful, unfavorable)
    branch_eff = _branch_effect(branch, useful, unfavorable)
    _branch_dynamics(branch_eff, branch, void, relations, useful, unfavorable)
    rel_mod = _relation_modifier(transformed, useful, unfavorable)
    w_s, w_b = _PERIOD_WEIGHTS.get(period_type, (0.4, 0.6))
    score = round(w_s * stem_eff.score + w_b * branch_eff.score + rel_mod, 4)
    strong = branch_eff.has_clash or branch_eff.is_void
    code, label, summary = _luck_label(stem_eff.type, branch_eff.type, strong)
    if branch_eff.branch_label:  # 공망/충 동태를 요약에 덧붙임
        summary = f"{summary} · 지지 {branch_eff.branch_label}"
    return {
        "stem_effect": stem_eff, "branch_effect": branch_eff, "luck_score": score,
        "luck_label_code": code, "luck_label": label, "luck_summary": summary,
        "coarse": _coarse_alignment(code),
    }


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


def _gongmang_activation(branch: Branch, pillars: FourPillarsResult) -> list[str]:
    """운 지지가 원국 공망 지지를 자극: 전실(채움)/충(발동)/합(해소)."""
    out: list[str] = []
    for vb in pillars.gongmang_branches:
        vbranch = Branch(vb)
        if branch == vbranch:
            out.append(f"공망전실:{vb}")
            continue
        key = frozenset({branch, vbranch})
        if key in BRANCH_CLASHES:
            out.append(f"공망발동(충):{branch}-{vb}")
        elif key in SIX_COMBINATIONS:
            out.append(f"공망해소(합):{branch}-{vb}")
    return out


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
    gong = _gongmang_activation(branch, pillars)
    transformed = _transformed_elements(branch, pillars)
    void = str(branch) in set(pillars.gongmang_branches)
    eff = _luck_effect(stem, branch, useful, unfavorable, period_type, rels, transformed, void)
    return LuckPillar(
        label=label,
        period_type=period_type,
        ganji=f"{stem}{branch}",
        stem=str(stem),
        branch=str(branch),
        stem_ten_god=str(ten_god(dm, stem)),
        branch_ten_god=str(ten_god(dm, main_hidden_stem(branch))),
        twelve_unseong=twelve_unseong(dm, branch),
        raw_elements=sorted(elements),
        relations_to_chart=rels,
        gongmang_activation=gong,
        yongsin_alignment=eff["coarse"],
        stem_effect=eff["stem_effect"],
        branch_effect=eff["branch_effect"],
        luck_score=eff["luck_score"],
        luck_label=eff["luck_label"],
        luck_label_code=eff["luck_label_code"],
        luck_summary=eff["luck_summary"],
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
    for i in range(10):
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
        gong = _gongmang_activation(branch, pillars)
        void = str(branch) in set(pillars.gongmang_branches)
        eff = _luck_effect(
            stem, branch, useful_elements, unfavorable_elements, "daewoon",
            rels, transformed, void,
        )
        # 이 대운 10년의 세운(연동 표시용).
        sew_years = range(birth_date.year + age, birth_date.year + age + 10)
        sewoon = _yearly(pillars, dm, useful_elements, unfavorable_elements, sew_years)
        daewoon.append(DaewoonItem(
            index=i, start_age=age, approx_start_date=sdate, approx_end_date=edate,
            ganji=f"{stem}{branch}", stem=str(stem), branch=str(branch),
            stem_ten_god=str(ten_god(dm, stem)),
            branch_ten_god=str(ten_god(dm, main_hidden_stem(branch))),
            twelve_unseong=twelve_unseong(dm, branch),
            relations_to_chart=rels,
            gongmang_activation=gong,
            raw_elements=raw,
            transformed_elements=transformed,
            yongsin_relation=eff["coarse"],
            stem_effect=eff["stem_effect"],
            branch_effect=eff["branch_effect"],
            luck_score=eff["luck_score"],
            luck_label=eff["luck_label"],
            luck_label_code=eff["luck_label_code"],
            luck_summary=eff["luck_summary"],
            volatility_score=_volatility(rels),
            sewoon=sewoon,
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
        cycles.current_year = reference_date.year
        cycles.current_month = reference_date.month
        for item in daewoon:
            if item.start_age <= current_age < item.start_age + 10:
                cycles.current_daewoon_index = item.index
                break
        cycles.yearly_luck = _yearly(
            pillars, dm, useful_elements, unfavorable_elements,
            range(reference_date.year - 4, reference_date.year + 6),
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


def monthly_luck_for_year(
    pillars: FourPillarsResult,
    day_master: Stem,
    useful: set[str],
    unfavorable: set[str],
    year: int,
    table: SolarTermTable,
) -> list[LuckPillar]:
    """주어진 연도의 월운 12개 — 세운 선택 시 온디맨드 조회용(메인 응답엔 미포함)."""
    return _monthly(pillars, day_master, useful, unfavorable, year, table)
