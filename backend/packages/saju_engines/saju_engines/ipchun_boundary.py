"""입춘 경계 안내 — 양력 2월은 사주의 해(세운)가 바뀌는 달이다 (2026-11-21 데굴님 승인).

배경: 11월에 "2월 12일 정도 이사를 해야해"를 물었을 때 답이 해 바뀜을 다루지 못했다. 세운과 연간
민속 흉방(삼살·대장군)은 1월 1일이 아니라 입춘에 바뀌므로, 양력 2월을 묻는 질문은 입춘 전(지난 해
세운·丑월)과 입춘 뒤(새 세운·寅월)가 한 달 안에 함께 들어 있다. 데굴님 지시: "2월의 경우 해가
바뀌는 부분도 있어서 입춘 전후 모두 설명해 주는 게 맞다 … 민속 방향은 입춘 전후로 모두 풀어 준다".

이 모듈은 날짜·간지·십성을 **엔진이 계산해** 줄로 만든다(절대원칙 1 — LLM 은 간지·경계 날짜를
계산하지 않는다). 점수·후보·판정은 건드리지 않는 서술 전용 층이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from saju_manse_analysis.luck.luck_calendar import luck_month_label, sewoon_year_of

from saju_manse_core.calendar.sexagenary_cycle import year_ganzi
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.constants import (
    MONTH_BRANCH_ORDER,
    MONTH_STEM_START,
    STEM_ELEMENT,
    STEM_INDEX,
    STEMS,
    hidden_stems_for,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.intent import Granularity, TimeRange

_KST = ZoneInfo("Asia/Seoul")
#: 이보다 긴 월 단위 창(연 총운·12개월 흐름)은 달마다 따로 다루므로 경계 블록을 싣지 않는다.
_MAX_MONTH_SPAN = 3

Side = Literal["both", "before", "after"]


def lichun_date(year: int) -> date:
    """그 해 입춘의 한국 날짜(절기 테이블)."""
    return get_table().lichun_for_year(year).astimezone(_KST).date()


def sewoon_year_of_day(day: date) -> int:
    """그 날이 속한 세운 연도 — 입춘 전이면 전년(절기월 라벨 규칙과 같은 기준)."""
    year = sewoon_year_of(luck_month_label(day, get_table()))
    return year if year is not None else day.year


def sewoon_year_of_start(start: str, today: date) -> int:
    """시점 창 시작 표기의 세운 연도 — 못 읽으면 오늘 기준.

    표기는 'YYYY' | 'YYYY-MM'(절기월 라벨) | 'YYYY-MM-DD' 셋 중 하나다.
    """
    if len(start) == 10:
        try:
            return sewoon_year_of_day(date.fromisoformat(start))
        except ValueError:
            return sewoon_year_of_day(today)
    year = sewoon_year_of(start)
    return year if year is not None else sewoon_year_of_day(today)


@dataclass(frozen=True)
class IpchunBoundary:
    """질문 창에 걸린 입춘 경계.

    Attributes:
        year: 입춘이 든 양력 연도(입춘 뒤의 세운 연도).
        lichun: 입춘 날짜.
        side: 질문 창이 덮는 쪽 — 'both'(2월 전체·경계를 넘는 범위), 'before'·'after'(하루·한쪽).
        stated: 사용자가 말한 날짜(있으면) — 어느 쪽인지 밝히는 데 쓴다.
        stated_label: 그 날짜의 발화 표기('2월 12일').
    """

    year: int
    lichun: date
    side: Side
    stated: date | None = None
    stated_label: str = ""


def _month_labels(start: str, end: str) -> list[str]:
    """절기월 라벨 구간(YYYY-MM ~ YYYY-MM)의 라벨 목록(최대 `_MAX_MONTH_SPAN`+1개까지만 센다)."""
    y, m = int(start[:4]), int(start[5:7])
    out: list[str] = []
    while len(out) <= _MAX_MONTH_SPAN:
        label = f"{y}-{m:02d}"
        out.append(label)
        if label >= end:
            break
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def detect_ipchun_boundary(tr: TimeRange | None) -> IpchunBoundary | None:
    """질문 시점 창이 양력 2월(입춘이 든 달)을 짧게 짚는가.

    - 월 단위 창(3개월 이하)에 2월 라벨('YYYY-02')이 들었거나, 근사 날짜 앵커가 양력 2월이면 양쪽.
    - 일 단위 창이 양력 2월 안이면 그 날이 놓인 쪽(범위가 입춘을 넘으면 양쪽).
    연·대운·긴 월 창은 None(무소음).
    """
    if tr is None or not tr.start:
        return None
    start, end = str(tr.start), str(tr.end or tr.start)
    try:
        if tr.granularity is Granularity.MONTH and len(start) == 7 and len(end) == 7:
            stated: date | None = None
            stated_label = ""
            if tr.anchor_dates:
                stated = date.fromisoformat(tr.anchor_dates[0].date)
                stated_label = tr.anchor_dates[0].label
            labels = _month_labels(start, end)
            if len(labels) > _MAX_MONTH_SPAN:
                return None
            feb = next((lb for lb in labels if lb[5:7] == "02"), None)
            if feb is None and stated is not None and stated.month == 2:
                feb = f"{stated.year}-02"
            if feb is None:
                return None
            year = int(feb[:4])
            return IpchunBoundary(year, lichun_date(year), "both", stated, stated_label)
        if tr.granularity in (Granularity.DAY, Granularity.HOUR) and len(start) == 10:
            d1 = date.fromisoformat(start)
            d2 = date.fromisoformat(end) if len(end) == 10 else d1
            if d1.month != 2 and d2.month != 2:
                return None
            year = d1.year if d1.month == 2 else d2.year
            lichun = lichun_date(year)
            if d1 < lichun <= d2:
                return IpchunBoundary(year, lichun, "both")
            side: Side = "before" if d2 < lichun else "after"
            return IpchunBoundary(year, lichun, side, d1 if d1 == d2 else None)
    except (ValueError, KeyError):
        return None
    return None


def _month_ganji(day: date) -> tuple[Stem, Branch]:
    """그 날이 속한 절기월의 간지(둔월법 — 세운 천간이 寅월 천간을 정한다)."""
    instant = datetime(day.year, day.month, day.day, 12, 0, tzinfo=_KST)
    branch, _prev, _next = get_table().month_branch(instant)
    year_stem, _yb = year_ganzi(sewoon_year_of_day(day))
    start_stem = MONTH_STEM_START[year_stem]
    stem = STEMS[(STEM_INDEX[start_stem] + MONTH_BRANCH_ORDER.index(branch)) % 10]
    return stem, branch


def _glyph_note(day_master: str, stem: Stem, branch: Branch, fav: dict[str, str]) -> str:
    """'丙午(천간 정인·희신 / 지지 편인·희신)' — 일간 기준 십성과 용희기구한 역할."""
    dm = Stem(day_master)
    main = next(hs for hs, kind, _w in hidden_stems_for(branch) if kind.value == "main")

    def _one(s: Stem) -> str:
        role = fav.get(str(STEM_ELEMENT[s].value), "")
        return f"{ten_god(dm, s)}" + (f"·{role}" if role else "")

    return f"{stem.value}{branch.value}(천간 {_one(stem)} / 지지 {_one(main)})"


def format_ipchun_lines(
    boundary: IpchunBoundary | None, day_master: str, fav: dict[str, str]
) -> list[str]:
    """[입춘 경계] 프롬프트 줄 — 입춘 날짜·전후 세운과 월운 간지·십성. 경계가 없으면 빈 목록.

    Args:
        boundary: `detect_ipchun_boundary` 결과.
        day_master: 일간(한자). 비어 있으면 십성 표기를 생략한다.
        fav: 오행(한자) → 용희기구한 역할 맵.
    """
    if boundary is None:
        return []
    y, lc = boundary.year, boundary.lichun
    before_day = date(y, 2, 1)

    def _side(year: int, day: date) -> str:
        ys, yb = year_ganzi(year)
        ms, mb = _month_ganji(day)
        if not day_master:
            return f"세운 {ys.value}{yb.value}년 · 월운 {ms.value}{mb.value}월"
        return (
            f"세운 {_glyph_note(day_master, ys, yb, fav)}년 · "
            f"월운 {_glyph_note(day_master, ms, mb, fav)}월"
        )

    prev_line = f"- 입춘 전(2월 1일~{lc.day - 1}일): {_side(y - 1, before_day)}"
    next_line = f"- 입춘부터({lc.month}월 {lc.day}일~): {_side(y, lc)}"
    stated = ""
    if boundary.stated is not None:
        where = "입춘 전" if boundary.stated < lc else "입춘 뒤"
        label = boundary.stated_label or f"{boundary.stated.month}월 {boundary.stated.day}일"
        stated = f" 사용자가 말한 {label}은 {where}에 든다."
    if boundary.side == "both":
        head = (
            f"[입춘 경계 — 양력 {y}년 2월은 사주의 해가 바뀌는 달] 입춘은 {y}년 {lc.month}월 "
            f"{lc.day}일이다. 세운은 1월 1일이 아니라 입춘에 바뀐다.{stated} 2월 풀이는 입춘 전과 "
            "입춘 뒤를 나누어 둘 다 서술하라 — 입춘 전은 지난 해 세운의 마무리 구간이고, 입춘부터 "
            "새 세운이 시작된다. 아래 간지·십성은 엔진 값이다(다른 간지를 만들지 말 것)."
        )
        return ["", head, prev_line, next_line]
    where = "입춘 전" if boundary.side == "before" else "입춘 뒤"
    head = (
        f"[입춘 경계 — 질문한 날은 {where}] 입춘은 {y}년 {lc.month}월 {lc.day}일이다. 세운은 "
        f"1월 1일이 아니라 입춘에 바뀐다 — 질문한 날의 해는 아래 줄의 세운이다(달력 연도로 "
        "해를 정하지 말 것)."
    )
    return ["", head, prev_line if boundary.side == "before" else next_line]
