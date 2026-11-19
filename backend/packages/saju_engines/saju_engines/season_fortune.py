"""계절로 보는 길흉 구간 — 태어난 계절 기준 참고 줄 (2026-11-18 데굴님 제공 규칙).

절기 달력(절기월) 기준으로 태어난 계절에 따라 한 해의 계절 구간을 좋음·나쁨으로 나눈다.
  - 봄(2~4월)·가을(8~10월)·겨울(11~1월)생: 봄 좋음 1 · 여름 좋음 2 · 가을은 추석 전 좋음 1,
    추석 뒤 나쁨 1 · 겨울 나쁨 1
  - 여름(5~7월)생: 봄·가을·겨울 좋음 1 · 여름 나쁨 1
  - 여름생·겨울생은 태어난 달(원국 월지와 같은 지지의 달)이 특히 나쁨(나쁨 2)
추석은 그 해 음력 8월 15일의 양력 날짜(만세력 음양력 변환)이고, 추석이 든 절기월은 날짜로 나눈다.

태어난 계절 하나만 보는 단순 구간이라 용신·운 판정과 엇갈릴 수 있다 — 점수·사건 후보에 쓰지
않는 서술 전용 층이며, 풀이에서는 엔진 판정이 본론이고 이 줄은 참고 한 문장이다. 출생 시각이
없어도 월주만 있으면 낸다. 간지·날짜는 엔진이 계산해 싣는다(LLM 계산 금지).
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from saju_manse_core.calendar.lunar_solar_converter import lunar_to_solar

from .employment_history import luck_month_label

SEASON_FORTUNE_HEADER = "[계절로 보는 길흉 구간 — 태어난 계절 기준, 참고]"
SEASON_FORTUNE_RULE = (
    "이 표는 태어난 계절 하나만으로 본 단순 구간이다. 엔진의 용신·사건 판정과 엇갈리면 엔진 "
    "판정이 본론이고, 이 줄은 '계절로만 보면'이라는 말머리를 붙여 한 문장 참고로만 덧붙일 것. "
    "구간을 사건 확정이나 그 기간 전체의 길흉 결론으로 말하지 말고, 표에 없는 달·날짜를 지어내지 "
    "말 것."
)
#: 절기월 라벨의 월(1~12) → 계절. 봄=寅卯辰(2~4), 여름=巳午未(5~7), 가을=申酉戌(8~10), 겨울=亥子丑.
_SEASON_BY_MONTH: dict[int, str] = {
    2: "봄", 3: "봄", 4: "봄", 5: "여름", 6: "여름", 7: "여름",
    8: "가을", 9: "가을", 10: "가을", 11: "겨울", 12: "겨울", 1: "겨울",
}
_MONTH_OF_BRANCH: dict[str, int] = {
    "寅": 2, "卯": 3, "辰": 4, "巳": 5, "午": 6, "未": 7,
    "申": 8, "酉": 9, "戌": 10, "亥": 11, "子": 12, "丑": 1,
}
_SPAN_KO = {"봄": "2~4월", "여름": "5~7월", "가을": "8~10월", "겨울": "11~1월"}
_GRADE_KO = {2: "많이 좋은 구간", 1: "좋은 구간", -1: "나쁜 구간", -2: "특히 나쁜 구간"}
#: 가을의 추석 전·후 등급(여름생 제외).
_AUTUMN_BEFORE, _AUTUMN_AFTER = 1, -1
#: 태어난 달이 특히 나쁜 계절.
_BIRTH_MONTH_PENALTY_SEASONS = frozenset({"여름", "겨울"})
_BIRTH_MONTH_GRADE = -2
SEASON_FORTUNE_MAX_YEARS = 3
SEASON_FORTUNE_MAX_MONTHS = 6


def birth_season(month_branch: str) -> str | None:
    """원국 월지 → 태어난 계절('봄'·'여름'·'가을'·'겨울'). 모르는 글자면 None."""
    month = _MONTH_OF_BRANCH.get(month_branch)
    return _SEASON_BY_MONTH[month] if month is not None else None


@lru_cache(maxsize=256)
def chuseok(year: int) -> date:
    """그 해 추석(음력 8월 15일)의 양력 날짜."""
    return lunar_to_solar(date(year, 8, 15), False)


def season_grade(born: str, season: str) -> int | None:
    """태어난 계절 × 구간 계절 → 등급(+2·+1·−1). 가을은 추석으로 갈리면 None(여름생 제외)."""
    if born == "여름":
        return -1 if season == "여름" else 1
    if season == "가을":
        return None
    return {"봄": 1, "여름": 2, "겨울": -1}[season]


def autumn_phase(label: str) -> str:
    """가을 절기월 라벨이 그 해 추석의 어느 쪽인가 — 'before'·'split'(추석이 든 달)·'after'."""
    split_label = luck_month_label(chuseok(int(label[:4])))
    if label < split_label:
        return "before"
    return "after" if label > split_label else "split"


def month_grade(natal_month_branch: str, label: str) -> tuple[int, int | None, date | None]:
    """절기월 라벨('YYYY-MM')의 등급 — (등급, 추석 뒤 등급 또는 None, 갈리는 날짜 또는 None).

    추석이 든 가을 절기월만 둘로 갈린다(여름생은 가을 전체가 한 등급). 여름생·겨울생의 태어난
    달은 계절 등급 대신 '특히 나쁨'이다.
    """
    born = birth_season(natal_month_branch)
    month = int(label[5:7])
    if born is None or month not in _SEASON_BY_MONTH:
        raise ValueError(f"계절 구간을 정할 수 없음: {natal_month_branch!r}, {label!r}")
    season = _SEASON_BY_MONTH[month]
    if born in _BIRTH_MONTH_PENALTY_SEASONS and month == _MONTH_OF_BRANCH[natal_month_branch]:
        return _BIRTH_MONTH_GRADE, None, None
    grade = season_grade(born, season)
    if grade is not None:
        return grade, None, None
    phase = autumn_phase(label)
    if phase == "before":
        return _AUTUMN_BEFORE, None, None
    if phase == "after":
        return _AUTUMN_AFTER, None, None
    return _AUTUMN_BEFORE, _AUTUMN_AFTER, chuseok(int(label[:4]))


def board_season_key(month_branch: str, on: date) -> str | None:
    """오늘의 운세 월 패널용 — 그 날이 속한 절기월의 계절 문장 키.

    'spring'·'summer'·'winter', 가을은 추석 기준 'autumn_before'·'autumn_split'·
    'autumn_after'. 일주별 콘텐츠라 태어난 달을 모르므로, 문장이 태어난 계절별 구간을 함께
    말한다(문장은 사전 `month_layer.birth_season`).
    """
    season = birth_season(month_branch)
    if season is None:
        return None
    if season != "가을":
        return {"봄": "spring", "여름": "summer", "겨울": "winter"}[season]
    return f"autumn_{autumn_phase(luck_month_label(on))}"


ENTRY_SEASON_TENURE_HEADER = "[입사 뒤 재직 기간 — 계절로 본 가능성]"
ENTRY_SEASON_TENURE_MAX_MONTHS = 3


def entry_season_tenure_line(natal_month_branch: str | None, periods: list[str]) -> str | None:
    """입사 시점 후보 달의 계절 등급 → 재직 기간 가능성 한 줄(양 끝 등급만). 없으면 None.

    2026-11-18 데굴님: "입사 자체가 길흉은 아니고, 취업 이벤트인거고 그런 점수는 해당 회사에 재직
    할 수 있는 기간" → 계절 등급은 입사 성사가 아니라 그 자리의 재직 기간 쪽으로 읽는다. 실이력
    대조(EXPERT_RULES_20261118.md §8)에서 방향이 맞은 것은 양 끝뿐이라 두 등급만 싣는다 —
    '특히 나쁜 구간'(여름생·겨울생의 태어난 달): 오래 다니지 못할 수도 있다 / '많이 좋은 구간':
    오래 다니게 될 수도 있다. 가운데 등급(좋은·나쁜 구간)과 추석으로 갈리는 달에는 재직 기간
    얘기를 붙이지 않는다. 서술 전용 — 점수·성사 달 배정·조건 등급은 바꾸지 않는다.

    Args:
        natal_month_branch: 원국 월지(없으면 None).
        periods: 입사·이직 후보 기간 라벨. 절기월 라벨('YYYY-MM')만 본다.
    """
    if birth_season(natal_month_branch or "") is None or natal_month_branch is None:
        return None
    short: list[str] = []
    long_: list[str] = []
    for label in sorted({p for p in periods if len(p) == 7}):
        grade, after, _day = month_grade(natal_month_branch, label)
        if after is not None:
            continue
        if grade == _BIRTH_MONTH_GRADE:
            short.append(label)
        elif grade == 2:
            long_.append(label)
    short = short[:ENTRY_SEASON_TENURE_MAX_MONTHS]
    long_ = long_[:ENTRY_SEASON_TENURE_MAX_MONTHS]
    if not short and not long_:
        return None
    parts: list[str] = []
    if short:
        parts.append(
            f"{', '.join(short)}(절기월)은 이 명식이 태어난 달과 같은 "
            f"{natal_month_branch}월로, 계절로 보면 특히 나쁜 구간이다. 성사 달·움직이는 달이 "
            "이 달에 들면 '이 시점의 입사는 오래 다니지 못할 수도 있다'는 가능성을 한 문장으로 "
            "덧붙일 것."
        )
    if long_:
        parts.append(
            f"{', '.join(long_)}(절기월)은 계절로 보면 많이 좋은 구간이다. 성사 달·움직이는 달이 "
            "이 달에 들면 '이 시점의 입사는 오래 다니게 될 수도 있다'는 가능성을 한 문장으로 "
            "덧붙일 것."
        )
    parts.append(
        "계절 구간은 입사가 성사되는지와는 별개다(이 구간에도 입사는 일어난다) — 그 자리에 "
        "머무는 기간 쪽의 가능성으로만 말할 것. 재직 기간을 숫자로 말하거나 확정하지 말고, 여기 "
        "없는 달의 입사에는 계절을 근거로 재직 기간 얘기를 붙이지 말 것. 위에 '용신 군 세운' "
        "재직 기간 가능성이 함께 있고 방향이 엇갈리면 두 가능성을 나란히 말할 것."
    )
    return f"{ENTRY_SEASON_TENURE_HEADER} " + " ".join(parts)


def _year_line(natal_month_branch: str, born: str, year: int) -> str:
    """한 해의 계절 구간 줄."""
    parts: list[str] = []
    for season in ("봄", "여름", "가을", "겨울"):
        grade = season_grade(born, season)
        if grade is None:
            day = chuseok(year)
            parts.append(
                f"가을({_SPAN_KO['가을']}) 추석({day.month}월 {day.day}일) 전까지 "
                f"{_GRADE_KO[_AUTUMN_BEFORE]}, 추석 뒤부터 {_GRADE_KO[_AUTUMN_AFTER]}"
            )
        else:
            parts.append(f"{season}({_SPAN_KO[season]}) {_GRADE_KO[grade]}")
    line = f"계절 구간 {year}년(절기월 기준): " + " · ".join(parts)
    if born in _BIRTH_MONTH_PENALTY_SEASONS:
        line += (
            f" · 그중 태어난 달과 같은 {natal_month_branch}월"
            f"({_MONTH_OF_BRANCH[natal_month_branch]}월 절기월)은 {_GRADE_KO[_BIRTH_MONTH_GRADE]}"
        )
    return line


def season_fortune_lines(
    natal_month_branch: str | None,
    years: list[int],
    months: list[tuple[str, str]] | None = None,
) -> list[str]:
    """계절 길흉 구간 블록(머리 줄 + 해별 줄 + 달별 줄 + 읽는 법). 낼 것이 없으면 빈 목록.

    Args:
        natal_month_branch: 원국 월지(없으면 빈 목록 — 추측하지 않는다).
        years: 구간을 보일 해(절기년). `SEASON_FORTUNE_MAX_YEARS` 를 넘으면 해별 줄을 생략한다.
        months: (절기월 라벨 'YYYY-MM', 월운 간지) — 질문이 달 단위일 때. 상한
            `SEASON_FORTUNE_MAX_MONTHS` 를 넘으면 달별 줄을 생략한다.
    """
    born = birth_season(natal_month_branch or "")
    if born is None or natal_month_branch is None:
        return []
    body: list[str] = []
    uniq_years = sorted(set(years))
    if 0 < len(uniq_years) <= SEASON_FORTUNE_MAX_YEARS:
        body += [_year_line(natal_month_branch, born, y) for y in uniq_years]
    month_rows = [m for m in (months or []) if len(m[0]) == 7]
    if 0 < len(month_rows) <= SEASON_FORTUNE_MAX_MONTHS:
        for label, ganji in month_rows:
            grade, after, day = month_grade(natal_month_branch, label)
            text = _GRADE_KO[grade]
            if after is not None and day is not None:
                text = (
                    f"추석({day.month}월 {day.day}일) 전까지 {_GRADE_KO[grade]}, "
                    f"추석 뒤부터 {_GRADE_KO[after]}"
                )
            # 줄 머리를 달 라벨로 시작하지 않는다 — 창 블록의 줄 머리 달 라벨은 요약 표 행 전용이다.
            body.append(f"계절 구간 {label}({ganji}월): {text}")
    if not body:
        return []
    return [
        f"{SEASON_FORTUNE_HEADER} 이 명식은 {born}생({natal_month_branch}월)이다.",
        *body,
        SEASON_FORTUNE_RULE,
    ]


__all__ = [
    "ENTRY_SEASON_TENURE_HEADER", "ENTRY_SEASON_TENURE_MAX_MONTHS", "SEASON_FORTUNE_HEADER",
    "SEASON_FORTUNE_MAX_MONTHS", "SEASON_FORTUNE_MAX_YEARS", "SEASON_FORTUNE_RULE",
    "autumn_phase", "birth_season", "board_season_key", "chuseok", "entry_season_tenure_line",
    "month_grade", "season_fortune_lines", "season_grade",
]
