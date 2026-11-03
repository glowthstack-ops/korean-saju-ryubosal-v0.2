"""오늘의 운세 이번 달 층·조언 줄 (docs/17 §24, 2026-11-01 데굴님 승인).

오늘 카드 바깥의 '이번 달 흐름'(천간 공통·일주별)과 카드 안의 '조언' 한 줄을 조립한다.
일주 60버킷이라 용신을 모르므로 길흉 등급을 쓰지 않고, 십성군 쌍이 주는 생활의 결만
서술한다. 사건·확률·Top5·로또·행운의 장소에 관여하지 않는다(판정 불변, 문체 전용).

사전 키 `month_layer` 가 없는 계약(dict.v1.15 이하·베타 풀)에서는 아무것도 붙지 않는다 —
과거 날짜와 동결 풀의 바이트 불변을 키 유무로 지킨다. 새 문장은 사전 원문을 그대로 쓰며
LLM 교정 대상이 아니다.
"""

from __future__ import annotations

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
    DayGanjiContext,
)
from saju_shared_types.enums import Branch, Stem

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
    """일주별 흐름 — 월운 천간의 일지 12운성 문장 + (있으면) 관계 문장.

    12운성은 같은 일간 6일주가 전부 달라 60일주를 빠짐없이 가른다(지지 관계만으로는 연평균
    19.2/60). 관계는 일지와 월운 지지, 연말 구간은 내년 세운 지지까지 본다.
    """
    month_stem, month_branch = Stem(ctx.month_stem), Branch(ctx.month_branch)
    year_branch = Branch(ctx.year_branch)
    # dict.v1.16(11/2 보드)은 12운성 풀이 없다 — 재생성해도 그날 계약대로 관계 문장만 낸다.
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


def month_flow(ctx: DayGanjiContext, layer: dict[str, Any]) -> list[DailyMonthStemFlow]:
    """10일간의 이번 달 흐름 — 천간 공통 1문단 + 6일주 전부의 일주별 문장."""
    flows: list[DailyMonthStemFlow] = []
    for stem in Stem:
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
) -> str:
    """조언 줄 — 내 일주의 날 > 천간합 > 십성군 쌍 + (있으면) 어제·내일 연결 문장.

    같은 일간 6일주가 같은 쌍을 공유하므로 변주를 일지로도 돌려 탭 안 반복을 줄인다.
    """
    day_stem, day_branch = Stem(ctx.day_stem), Branch(ctx.day_branch)
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
    return " ".join(parts)


def attach_month_layer(
    board: DailyFortuneBoard,
    ctx: DayGanjiContext,
    layer: dict[str, Any],
    bands: dict[str, str],
    yesterday: dict[str, str],
    tomorrow: dict[str, str],
) -> None:
    """보드에 이번 달 흐름·절기 띠·조언을 채운다(제자리 수정).

    Args:
        board: `compute_board` 가 만든 직후의 보드.
        ctx: 오늘 일진·월운·세운 간지.
        layer: 사전의 `month_layer`.
        bands: 일주 → 오늘 밴드. yesterday·tomorrow 는 전날·다음 날 밴드.
    """
    board.season_band = season_band(ctx, layer)
    board.month_flow = month_flow(ctx, layer)
    for fortune in board.fortunes:
        ilju = fortune.ilju
        fortune.advice = day_advice(
            Stem(ilju[0]), Branch(ilju[1]), ctx, layer,
            yesterday.get(ilju), bands[ilju], tomorrow.get(ilju),
        )
