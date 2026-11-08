"""오늘의 운세 이번 달 층·조언 줄 (docs/17 §24, 2026-11-01 데굴님 승인).

오늘 카드 바깥의 '이번 달 흐름'(천간 공통·일주별)과 카드 안의 '조언' 한 줄을 조립한다.
일주 60버킷이라 용신을 모르므로 길흉 등급을 쓰지 않고, 십성군 쌍이 주는 생활의 결만
서술한다. 사건·확률·Top5·로또·행운의 장소에 관여하지 않는다(판정 불변, 문체 전용).

사전 키 `month_layer` 가 없는 계약(dict.v1.15 이하·베타 풀)에서는 아무것도 붙지 않는다 —
과거 날짜와 동결 풀의 바이트 불변을 키 유무로 지킨다. 새 문장은 사전 원문을 그대로 쓰며
LLM 교정 대상이 아니다.

12운성 방향 교정(docs/17 §25, dict.v1.18): 12운성 문장은 '일간→월운 지지'로 천간 공통 흐름에
싣고(`stem_stage`), 일주별 흐름은 일지↔월운 지지·내년 세운 지지 관계만 남긴다. `ilju_stage`
키가 있는 v1.17 계약(11/3~11/4)은 종전대로 '월운 천간→일지' 문장을 일주별로 낸다. 패널 라벨
(월 이름·기간)과 다음 달 미리보기(월운 전환 7일 전부터)도 `stem_stage` 가 있는 계약에만 붙는다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from saju_engines import daily_ilju_fortune as v1
from saju_manse_core.calendar.ganji_calendar import build_month
from saju_manse_core.calendar.sexagenary_cycle import ganzi_from_index
from saju_manse_core.pillars.twelve_unseong import twelve_unseong
from saju_shared_types.constants import (
    BRANCH_KO,
    STEM_COMBINATIONS,
    STEM_KO,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.daily_fortune import (
    DailyFortuneBoard,
    DailyMonthIljuFlow,
    DailyMonthStemFlow,
    DailyYearStemFlow,
    DayGanjiContext,
)
from saju_shared_types.enums import Branch, Stem

from . import simple_reading as _simple

#: 십성 → 십성군(`daily_ilju_fortune._SIPSEONG_GROUP` 와 같은 분류).
_GROUP = v1._SIPSEONG_GROUP
#: 연말 구간 월운 지지 — 연결 문장이 다음 달 대신 내년 준비를 말한다(입춘 전 3개월).
_YEAR_END_BRANCHES = frozenset({Branch("亥"), Branch("子"), Branch("丑")})
#: '좋은 날' 밴드(§24-3 연결 문장 판정).
_GOOD_BANDS = frozenset({"s5", "s4"})
_CAUTION_BAND = "s1"
_VARIANTS = 3


def _sipseong(day_master: Stem, target: Stem) -> str:
    """일간 기준 십성 이름 — 같은 글자는 비견."""
    return "비견" if target == day_master else ten_god(day_master, target).value


def _branch_sipseong(day_master: Stem, branch: Branch) -> str:
    """지지 본기의 십성 이름."""
    main = main_hidden_stem(branch)
    return _sipseong(day_master, Stem(getattr(main, "value", main)))


def _next_ganzi(stem: Stem, branch: Branch) -> tuple[Stem, Branch]:
    """60갑자 순서상 다음 간지 — 다음 달 월운·내년 세운은 달력 조회 없이 정해진다."""
    index = next(i for i in range(60) if ganzi_from_index(i) == (stem, branch))
    return ganzi_from_index((index + 1) % 60)


def _relation_kind(transit: Branch, ilju_branch: Branch, helpers: tuple[Branch, ...]) -> str:
    """일지와 운 지지의 관계 — 충 > 육합 > 삼합·반합, 없으면 빈 문자열.

    형·파·해는 쓰지 않는다(§24-3): 일주 카드에서 사건 없이 말하면 겁만 주기 때문이다.
    """
    hits = v1._branch_relations(transit, ilju_branch, helpers)
    if "clash" in hits:
        return "chung"
    if "six_combination" in hits:
        return "yukhap"
    if "three_harmony_complete" in hits or "half_harmony" in hits:
        return "samhap"
    return ""


def _stem_common_line(day_master: Stem, ctx: DayGanjiContext, layer: dict[str, Any]) -> str:
    """천간 공통 흐름 — 결 + 행동 + (세운 겹침) + 다음 달 또는 내년 준비."""
    month_stem, month_branch = Stem(ctx.month_stem), Branch(ctx.month_branch)
    stem_god = _sipseong(day_master, month_stem)
    branch_god = _branch_sipseong(day_master, month_branch)
    stem_group, branch_group = _GROUP[stem_god], _GROUP[branch_god]
    parts = [layer["month_tone"][f"{stem_group}+{branch_group}"], layer["month_action"][stem_god]]
    # 12운성 — 일간이 월운 지지에서 갖는 힘(통설·만세력 엔진 luck_cycles 와 같은 방향, §25).
    # 같은 일간 6일주가 같은 문장을 공유하는 것은 설계대로다(일주 차이는 관계 문장이 맡는다).
    stem_stage = layer.get("stem_stage")
    if stem_stage:
        parts.append(stem_stage[str(twelve_unseong(day_master, month_branch))])
    year_group = _GROUP[_sipseong(day_master, Stem(ctx.year_stem))]
    if year_group in (stem_group, branch_group):
        parts.append(layer["year_overlap"])
    if month_branch in _YEAR_END_BRANCHES:
        next_year_stem, _ = _next_ganzi(Stem(ctx.year_stem), Branch(ctx.year_branch))
        parts.append(layer["next_year"][_GROUP[_sipseong(day_master, next_year_stem)]])
    else:
        next_month_stem, _ = _next_ganzi(month_stem, month_branch)
        parts.append(layer["next_month"][_GROUP[_sipseong(day_master, next_month_stem)]])
    return " ".join(parts)


def _ilju_note(
    ilju_branch: Branch, ctx: DayGanjiContext, layer: dict[str, Any]
) -> str:
    """일주별 흐름 — 일지↔월운 지지(연말 구간은 내년 세운 지지) 관계 문장. 관계가 없으면 빈 문자열.

    §25 교정(dict.v1.18)부터 12운성 문장은 천간 공통 줄로 옮겨 갔다 — 통설은 같은 일간에 같은
    달 풀이를 주고 일주 차이는 巳亥충 같은 지지 관계로만 둔다(연평균 19.2/60 일주에 관계 있음).
    `ilju_stage` 키가 있는 v1.17 계약(11/3~11/4)만 종전 '월운 천간→일지' 12운성 문장을 앞에 둔다.
    """
    month_stem, month_branch = Stem(ctx.month_stem), Branch(ctx.month_branch)
    year_branch = Branch(ctx.year_branch)
    # v1.16(11/2)은 12운성 풀이 없고 v1.18 부터는 공통 줄로 옮겨 갔다 — v1.17 만 일주별 12운성.
    stage_pool = layer.get("ilju_stage")
    parts = [stage_pool[str(twelve_unseong(month_stem, ilju_branch))]] if stage_pool else []
    kind = _relation_kind(month_branch, ilju_branch, (year_branch,))
    if kind:
        parts.append(layer["ilju_note"][f"month_{kind}"])
    elif month_branch in _YEAR_END_BRANCHES:
        _, next_year_branch = _next_ganzi(Stem(ctx.year_stem), year_branch)
        kind = _relation_kind(next_year_branch, ilju_branch, ())
        if kind:
            parts.append(layer["ilju_note"][f"year_{kind}"])
    return " ".join(parts)


def month_span(ctx: DayGanjiContext) -> tuple[date, date, tuple[str, str] | None]:
    """오늘이 속한 월운 간지의 (시작일, 종료일, 다음 달 간지) — 엔진 달력(정오 기준) 그대로.

    입절 시각이 오후면 엔진의 월운 전환일이 입절일 다음 날이라 패널 기간도 그 날짜를 쓴다
    (2026 입동 11/7 18:52 → 기해월 11/8 시작). 내용과 라벨이 같은 달력을 봐야 하기 때문이다.
    """
    d = ctx.the_date
    ganji_of: dict[date, tuple[str, str]] = {}
    for offset in (-1, 0, 1):
        year, month = d.year, d.month + offset
        if month < 1:
            year, month = year - 1, 12
        elif month > 12:
            year, month = year + 1, 1
        for day in build_month(year, month)["days"]:
            ganji_of[day["date"]] = (day["month_ganji"][0], day["month_ganji"][1])
    current = ganji_of[d]
    start = end = d
    while ganji_of.get(start - timedelta(days=1)) == current:
        start -= timedelta(days=1)
    while ganji_of.get(end + timedelta(days=1)) == current:
        end += timedelta(days=1)
    return start, end, ganji_of.get(end + timedelta(days=1))


def _month_name(stem: str, branch: str) -> str:
    """월운 간지 표기 — '기해월(己亥)'."""
    return f"{STEM_KO[Stem(stem)]}{BRANCH_KO[Branch(branch)]}월({stem}{branch})"


def month_label(ctx: DayGanjiContext) -> str:
    """패널 라벨 — '기해월(己亥) 11월 8일~12월 6일'."""
    start, end, _next = month_span(ctx)
    return (
        f"{_month_name(ctx.month_stem, ctx.month_branch)} "
        f"{start.month}월 {start.day}일~{end.month}월 {end.day}일"
    )


#: 다음 달 미리보기를 켜는 전환 전 일수(§25-3 — 입절 전 주).
PREVIEW_DAYS_BEFORE = 7


def next_month_preview_context(ctx: DayGanjiContext) -> DayGanjiContext | None:
    """월운 전환이 7일 안이면 다음 달 첫날의 간지 컨텍스트, 아니면 None."""
    _start, end, _next = month_span(ctx)
    next_start = end + timedelta(days=1)
    if not 0 < (next_start - ctx.the_date).days <= PREVIEW_DAYS_BEFORE:
        return None
    return v1.build_day_context(next_start)


def next_month_label(next_ctx: DayGanjiContext) -> str:
    """미리보기 라벨 — '기해월(己亥) 11월 8일부터'."""
    d = next_ctx.the_date
    return f"{_month_name(next_ctx.month_stem, next_ctx.month_branch)} {d.month}월 {d.day}일부터"


def month_flow(
    ctx: DayGanjiContext,
    layer: dict[str, Any],
    preview_ctx: DayGanjiContext | None = None,
    simple: dict[str, Any] | None = None,
) -> list[DailyMonthStemFlow]:
    """10일간의 이번 달 흐름 — 천간 공통 1문단 + 관계가 있는 일주의 일주별 문장(+ 미리보기).

    Args:
        ctx: 오늘 일진·월운·세운 간지.
        layer: 사전의 `month_layer`.
        preview_ctx: 다음 달 첫날 컨텍스트(전환 7일 전부터). None 이면 미리보기 없음.
        simple: 사전의 `simple_layer`(docs/17 §26) — 있으면 월운 천간·지지 십성군이 같은 달에
            `same_group_note` 1문장을 채운다. None(과거 계약)이면 필드가 None 이다.
    """
    flows: list[DailyMonthStemFlow] = []
    month_stem, month_branch = Stem(ctx.month_stem), Branch(ctx.month_branch)
    for stem in Stem:
        same_note = (
            _simple.simple_reading(
                stem, month_stem, month_branch, "month", simple, layer,
            ).emphasis
            if simple else None
        )
        notes = [
            DailyMonthIljuFlow(
                ilju=f"{ilju_stem.value}{ilju_branch.value}",
                ilju_ko=f"{STEM_KO[ilju_stem]}{BRANCH_KO[ilju_branch]}",
                note=note,
            )
            for ilju_stem, ilju_branch in map(ganzi_from_index, range(60))
            if ilju_stem == stem
            # v1.16 계약은 관계 없는 일주가 빈 문자열 — 한 번 조립한 값으로 걸러낸다.
            and (note := _ilju_note(ilju_branch, ctx, layer))
        ]
        flows.append(DailyMonthStemFlow(
            day_stem_ko=STEM_KO[stem],
            common=_stem_common_line(stem, ctx, layer),
            ilju_notes=notes,
            next_preview=(
                _stem_common_line(stem, preview_ctx, layer) if preview_ctx is not None else None
            ),
            same_group_note=same_note,
        ))
    return flows


def year_span(ctx: DayGanjiContext) -> tuple[date, date]:
    """오늘이 속한 세운(입춘 기준)의 (시작일, 종료일) — 엔진 달력 그대로."""
    d = ctx.the_date
    ganji_of: dict[date, str] = {}
    for year in (d.year - 1, d.year, d.year + 1):
        for month in range(1, 13):
            for day in build_month(year, month)["days"]:
                ganji_of[day["date"]] = day["year_ganji"]
    current = ganji_of[d]
    start = end = d
    while ganji_of.get(start - timedelta(days=1)) == current:
        start -= timedelta(days=1)
    while ganji_of.get(end + timedelta(days=1)) == current:
        end += timedelta(days=1)
    return start, end


def year_label(ctx: DayGanjiContext) -> str:
    """올해의 결 패널 라벨 — '병오년(丙午) 2026년 2월 4일~2027년 2월 3일'."""
    start, end = year_span(ctx)
    stem, branch = Stem(ctx.year_stem), Branch(ctx.year_branch)
    return (
        f"{STEM_KO[stem]}{BRANCH_KO[branch]}년({stem.value}{branch.value}) "
        f"{start.year}년 {start.month}월 {start.day}일~{end.year}년 {end.month}월 {end.day}일"
    )


def year_flow(
    ctx: DayGanjiContext, simple: dict[str, Any], layer: dict[str, Any]
) -> list[DailyYearStemFlow]:
    """10일간의 올해의 결(단식, docs/17 §26) — 쌍 결·같은 결 강조·체감 포인트 3·절정 달.

    Args:
        ctx: 오늘 일진·월운·세운 간지(세운만 쓴다).
        simple: 사전의 `simple_layer`.
        layer: 사전의 `month_layer`(연 지평은 쓰지 않지만 시그니처 통일).
    """
    year_stem, year_branch = Stem(ctx.year_stem), Branch(ctx.year_branch)
    flows: list[DailyYearStemFlow] = []
    for stem in Stem:
        sr = _simple.simple_reading(stem, year_stem, year_branch, "year", simple, layer)
        flows.append(DailyYearStemFlow(
            day_stem_ko=STEM_KO[stem],
            tone=sr.tone,
            emphasis=sr.emphasis,
            points=list(sr.points),
            peak_months=_simple.peak_month_line(stem, year_stem, year_branch, simple),
        ))
    return flows


def season_band(ctx: DayGanjiContext, layer: dict[str, Any]) -> str | None:
    """절기 띠 — 12절기 입절일에만. 중기(소설·동지 등)는 사전에 없어 None."""
    d = ctx.the_date
    day = next(x for x in build_month(d.year, d.month)["days"] if x["date"] == d)
    term = day["solar_term"]
    return layer["season_band"].get(term) if term else None


def day_advice(
    ilju_stem: Stem,
    ilju_branch: Branch,
    ctx: DayGanjiContext,
    layer: dict[str, Any],
    yesterday_band: str | None,
    band: str,
    tomorrow_band: str | None,
    simple: dict[str, Any] | None = None,
) -> str:
    """조언 줄 — (단식 같은 결 강조) + 내 일주의 날 > 천간합 > 십성군 쌍 + 어제·내일 연결 문장.

    같은 일간 6일주가 같은 쌍을 공유하므로 변주를 일지로도 돌려 탭 안 반복을 줄인다.
    simple(docs/17 §26)이 있고 오늘 천간·지지 십성군이 같으면 `day_same_group` 1문장을 앞에 둔다.
    """
    day_stem, day_branch = Stem(ctx.day_stem), Branch(ctx.day_branch)
    lead: list[str] = []
    if simple:
        sr = _simple.simple_reading(ilju_stem, day_stem, day_branch, "day", simple, layer)
        if sr.emphasis:
            lead.append(sr.emphasis)
    variant = (
        ctx.the_date.toordinal()
        + list(Branch).index(ilju_branch) // 2
        + list(Stem).index(ilju_stem) % 2
    ) % _VARIANTS
    if day_stem == ilju_stem and day_branch == ilju_branch:
        parts = [layer["own_pillar"][variant]]
    elif frozenset({ilju_stem, day_stem}) in STEM_COMBINATIONS:
        parts = [layer["stem_hap"][variant]]
    else:
        stem_group = _GROUP[_sipseong(ilju_stem, day_stem)]
        branch_group = _GROUP[_branch_sipseong(ilju_stem, day_branch)]
        parts = [layer["day_scene"][f"{stem_group}+{branch_group}"][variant]]
    if yesterday_band == _CAUTION_BAND and band in _GOOD_BANDS:
        parts.append(layer["flow_relief"][variant])
    elif band == _CAUTION_BAND and tomorrow_band in _GOOD_BANDS:
        parts.append(layer["flow_defer"][variant])
    return " ".join([*lead, *parts])


def attach_month_layer(
    board: DailyFortuneBoard,
    ctx: DayGanjiContext,
    layer: dict[str, Any],
    bands: dict[str, str],
    yesterday: dict[str, str],
    tomorrow: dict[str, str],
    simple: dict[str, Any] | None = None,
) -> None:
    """보드에 이번 달 흐름·절기 띠·조언(+ 단식 결 층)을 채운다(제자리 수정).

    Args:
        board: `compute_board` 가 만든 직후의 보드.
        ctx: 오늘 일진·월운·세운 간지.
        layer: 사전의 `month_layer`.
        bands: 일주 → 오늘 밴드. yesterday·tomorrow 는 전날·다음 날 밴드.
        simple: 사전의 `simple_layer`(docs/17 §26, dict.v1.19) — 있으면 올해의 결·같은 결 강조를
            채운다. None(과거 계약)이면 새 필드가 전부 None 이고 조언 줄도 종전 그대로다.
    """
    board.season_band = season_band(ctx, layer)
    # 라벨·미리보기는 §25 계약(stem_stage)부터 — v1.16·v1.17 보드는 재생해도 필드가 None 이다.
    preview_ctx = next_month_preview_context(ctx) if layer.get("stem_stage") else None
    board.month_flow = month_flow(ctx, layer, preview_ctx, simple)
    if simple:
        board.year_flow = year_flow(ctx, simple, layer)
        board.year_label = year_label(ctx)
        board.year_direction_note = simple.get("direction_note")
    if layer.get("stem_stage"):
        board.month_label = month_label(ctx)
        board.next_month_label = (
            next_month_label(preview_ctx) if preview_ctx is not None else None
        )
    for fortune in board.fortunes:
        ilju = fortune.ilju
        fortune.advice = day_advice(
            Stem(ilju[0]), Branch(ilju[1]), ctx, layer,
            yesterday.get(ilju), bands[ilju], tomorrow.get(ilju), simple,
        )
