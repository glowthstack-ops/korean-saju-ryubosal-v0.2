"""단식(單式) 결 층 — 일간 × 운 십성군 체감 서술 (docs/17 §26, 2026-11-08 데굴님 승인).

외부 '올해 단식' 풀이의 로직을 그대로 옮긴다: **일간 기준 운 천간 십성군 + 운 지지 본기
십성군** 만으로 "일·돈·사람·몸·연애" 체감을 말하고 길흉은 가르지 않는다. 우리 판정 원칙
(길흉=용기신 / 사건 종류=십성)의 '종류' 축만 떼어 쓴 것이라 용신을 모르는 일주 60버킷과 맞고,
개인화 경로(채팅·테마사주)에서는 "간단히 봤을 때," 참고 줄로만 싣는다.

순수 함수다. 십성·지지 관계 판정은 기존 엔진(`ten_god`·`main_hidden_stem`·
`daily_ilju_fortune._branch_relations`)만 쓰며 새 명리 규칙을 두지 않는다. 점수·사건 선발·
확률에 관여하지 않는다(판정 불변, 문체 전용). 문장은 사전(`daily_phrase_templates.json`
`simple_layer`·`month_layer`) 원문 그대로다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_KO,
    PUNISHMENT_MUTUAL,
    PUNISHMENT_TRIPLES,
    SELF_PUNISHMENT,
    STEM_ELEMENT,
    STEM_KO,
    THREE_HARMONY,
    main_hidden_stem,
    ten_god,
)
from saju_shared_types.enums import Branch, Element, Stem

#: 십성군 5종(사전 키와 같은 표기).
GROUPS: tuple[str, ...] = ("비겁", "식상", "재성", "관성", "인성")
#: 체감 축 5종.
AXES: tuple[str, ...] = ("일", "돈", "사람", "몸", "연애")
#: 지평 — 사전 `{horizon}_same_group` 키와 같다.
HORIZONS: tuple[str, ...] = ("year", "month", "day")
_UNIT_KO: dict[str, str] = {"year": "년", "month": "월", "day": "일"}
_NOUN_KO: dict[str, str] = {"year": "해", "month": "달", "day": "날"}
#: 십성 → 십성군(`daily_ilju_fortune._SIPSEONG_GROUP` 와 같은 분류 — 순환 import 회피용 사본).
_GROUP_OF: dict[str, str] = {
    "비견": "비겁", "겁재": "비겁", "식신": "식상", "상관": "식상",
    "편재": "재성", "정재": "재성", "편관": "관성", "정관": "관성",
    "편인": "인성", "정인": "인성",
}
#: 십성군 상생 — 세운 군이 생(生)하는 군(인성→비겁→식상→재성→관성→인성). 그 군의 달은 세운
#: 기운이 흘러나가 실제로 드러나는 달이라 절정 점수 +1(2026-11-08 데굴님 "비겁뿐 아니라 다른
#: 십성도" → 상생으로 일반화). 예: 인성 세운(戊 일간 2026)은 비겁(土) 달, 관성 세운(庚)은
#: 인성(土) 달, 재성 세운(壬)은 관성(土) 달.
_GENERATES: dict[str, str] = {
    "인성": "비겁", "비겁": "식상", "식상": "재성", "재성": "관성", "관성": "인성",
}
#: 세운 지지와 월운 지지의 합(삼합 완성·반합·육합) — 월 절정 점수 2점.
_HAP_KEYS: frozenset[str] = frozenset({"six_combination", "half_harmony", "three_harmony_complete"})
#: 월 절정 — 최고점 하한·동점 표기 상한.
PEAK_MIN_SCORE = 2
PEAK_MAX_MONTHS = 3
#: 채팅·테마 참고 줄 말머리(데굴님 지정).
REFERENCE_PREFIX = "간단히 봤을 때,"
_REFERENCE_SUFFIX = "(일간과 운의 십성만 본 단식 풀이라 참고용이에요.)"
#: 채팅 월 참고 문단의 간지동 달 첫 문장(용어 허용 경로) — 데굴님 지정(2026-11-09): "이 달은
#: 천간과 지지 모두 (해당 십성)로 들어와 강하게 영향을 받을 수 있는 달입니다". `{label}{ro}` =
#: 같은 십성이면 "겁재로", 십성군만 같으면 "인성(정인·편인)으로". 오늘의 운세 패널은 사전
#: `strong_month_lead`(쉬운 말, "{months}에는 … 같은 성격의 글자")를 쓴다.
STRONG_MONTH_CHAT_LEAD = (
    "이 달은 천간과 지지 모두 {label}{ro} 들어와 강하게 영향을 받을 수 있는 달이에요."
)
#: 채팅 참고 문단의 기간 지칭 — 강조 문장은 패널과 같은 사전 문장이라 '이번 달은·오늘은'으로
#: 시작하지만, 채팅은 지난달·다음 달·내일처럼 **다른 기간**도 묻는다. 문단 첫 문장이 그 기간을
#: 간지로 밝히므로 지시어로 받는다(2026-11-09 최종안 보완).
_CHAT_SCOPE: dict[str, tuple[str, str]] = {
    "year": ("올해는", "이 해는"),
    "month": ("이번 달은", "이 달은"),
    "day": ("오늘은", "이 날은"),
}


@dataclass(frozen=True)
class SimpleReading:
    """한 지평(연·월·일)의 단식 결."""

    stem_god: str  # 운 천간 십성(일간 기준)
    branch_god: str  # 운 지지 본기 십성
    stem_group: str
    branch_group: str
    same_group: bool  # 두 군이 같은가 — 단식이 또렷한 해·달·날
    tone: str  # 쌍 결 문장(사전 원문)
    emphasis: str | None  # same_group 일 때만
    points: tuple[str, ...]  # 체감 포인트 3줄


def ten_god_name(day_master: Stem, target: Stem) -> str:
    """일간 기준 십성 이름 — 같은 글자는 비견."""
    return "비견" if target == day_master else ten_god(day_master, target).value


def branch_god_name(day_master: Stem, branch: Branch) -> str:
    """지지 본기의 십성 이름."""
    main = main_hidden_stem(branch)
    return ten_god_name(day_master, Stem(getattr(main, "value", main)))


def group_of(ten_god_name_ko: str) -> str:
    """십성 이름 → 십성군."""
    return _GROUP_OF[ten_god_name_ko]


def simple_reading(
    day_master: Stem,
    stem: Stem,
    branch: Branch,
    horizon: str,
    simple: dict[str, Any],
    month_layer: dict[str, Any] | None = None,
) -> SimpleReading:
    """일간 × 운 간지 → 단식 결(§26-1).

    Args:
        day_master: 일간.
        stem / branch: 운 천간·지지(세운·월운·일진 중 하나).
        horizon: 'year' | 'month' | 'day'.
        simple: 사전 `simple_layer`.
        month_layer: 사전 `month_layer` — 월·일 지평의 쌍 결 문장(`month_tone`·`day_scene`)을 여기서
            가져온다. 연 지평만 쓰면 None 가능.

    Raises:
        ValueError: 지평이 셋 중 하나가 아닐 때.
    """
    if horizon not in HORIZONS:
        raise ValueError(f"unknown horizon: {horizon}")
    stem_god = ten_god_name(day_master, stem)
    branch_god = branch_god_name(day_master, branch)
    sg, bg = _GROUP_OF[stem_god], _GROUP_OF[branch_god]
    pair = f"{sg}+{bg}"
    if horizon == "year":
        tone = simple["year_tone"][pair]
    elif horizon == "month":
        tone = (month_layer or {}).get("month_tone", {}).get(pair, "")
    else:
        scenes = (month_layer or {}).get("day_scene", {}).get(pair, [])
        tone = scenes[0] if scenes else ""
    same = sg == bg
    emphasis = simple[f"{horizon}_same_group"][sg] if same else None
    points = god_points(stem_god, branch_god, simple)
    return SimpleReading(
        stem_god=stem_god, branch_god=branch_god, stem_group=sg, branch_group=bg,
        same_group=same, tone=tone, emphasis=emphasis, points=points,
    )


def god_points(stem_god: str, branch_god: str, simple: dict[str, Any]) -> tuple[str, ...]:
    """체감 포인트 3줄 — 운 천간 십성 장면 2 + 운 지지 십성 장면 1(§27, dict.v1.20).

    `god_scene`(10십성×5영역)이 있으면 십성 단위라 비견·겁재(식신·상관 …)가 다른 문장을 받는다
    (데굴님 "묶으면 두 달씩 같은 내용"). 지지 장면의 영역은 천간이 쓴 두 영역과 겹치지 않는 첫 축.
    v1.19 사전(`group_scene`)은 종전 군 단위로 폴백한다.
    """
    scene = simple.get("god_scene")
    if scene:
        axes_s = list(simple["god_axes"][stem_god])
        axes_b = [a for a in simple["god_axes"][branch_god] if a not in axes_s[:2]]
        third = axes_b[0] if axes_b else simple["god_axes"][branch_god][0]
        return (scene[stem_god][axes_s[0]], scene[stem_god][axes_s[1]], scene[branch_god][third])
    sg, bg = _GROUP_OF[stem_god], _GROUP_OF[branch_god]
    axes_s = list(simple["group_axes"][sg])
    gscene = simple["group_scene"]
    if sg == bg:
        return tuple(gscene[sg][a] for a in axes_s[:3])
    axes_b = list(simple["group_axes"][bg])
    return (gscene[sg][axes_s[0]], gscene[sg][axes_s[1]], gscene[bg][axes_b[0]])


def month_ganji_of_year(year_stem: Stem) -> list[tuple[Stem, Branch, int]]:
    """세운 천간이 정하는 열두 월운 간지(월건법) — (천간, 지지, 양력 월 번호).

    寅월 천간: 甲己→丙, 乙庚→戊, 丙辛→庚, 丁壬→壬, 戊癸→甲. 지지는 寅부터 丑까지. 월 번호는 절기월이
    대부분 걸치는 양력 달(寅=2월 … 子=12월, 丑=1월).
    """
    stems = list(Stem)
    branches = list(Branch)
    start = (2 * (stems.index(year_stem) % 5) + 2) % 10
    out: list[tuple[Stem, Branch, int]] = []
    for k in range(12):
        b_idx = (2 + k) % 12  # 寅 = 2
        month_no = 12 if b_idx == 0 else b_idx
        out.append((stems[(start + k) % 10], branches[b_idx], month_no))
    return out


def peak_month_entries(
    day_master: Stem, year_stem: Stem, year_branch: Branch,
) -> list[tuple[int, Branch]]:
    """올해 흐름이 가장 강해지는 달 — (양력 월 번호, 월운 지지) 목록. 규칙은 `peak_months` 참조."""
    from saju_engines.daily_ilju_fortune import _branch_relations  # 지연 import — 순환 회피

    year_group = _GROUP_OF[ten_god_name(day_master, year_stem)]
    amplifiers = {year_group, _GENERATES[year_group]}  # 같은 군(중첩) + 생하는 군(출구)
    scored: list[tuple[int, int, Branch]] = []
    for m_stem, m_branch, month_no in month_ganji_of_year(year_stem):
        score = 0
        hits = set(_branch_relations(m_branch, year_branch, ()))
        if m_branch != year_branch and _HAP_KEYS & hits:
            score += 2
        if _GROUP_OF[ten_god_name(day_master, m_stem)] in amplifiers:
            score += 1
        if _GROUP_OF[branch_god_name(day_master, m_branch)] in amplifiers:
            score += 1
        scored.append((score, month_no, m_branch))
    best = max((s for s, _, _ in scored), default=0)
    if best < PEAK_MIN_SCORE:
        return []
    return [(m, b) for s, m, b in scored if s == best][:PEAK_MAX_MONTHS]


def peak_months(day_master: Stem, year_stem: Stem, year_branch: Branch) -> list[int]:
    """올해 흐름이 가장 강해지는 달(양력 월 번호) — §26-1 점수식.

    월운별 점수 = 세운 지지와 월운 지지의 합(삼합 완성·반합·육합) 2점
    + 월운 천간/지지 본기 십성군이 세운 천간군과 **같으면** 각 1점(중첩)
    + 월운 천간/지지 본기 십성군이 세운 천간군이 **생하는 군**이면 각 1점(출구 — `_GENERATES`).
    최고점이 `PEAK_MIN_SCORE` 이상인 달만, 동점은 절기 연도 순으로 최대 `PEAK_MAX_MONTHS` 개.
    2026 丙午 戊 일간(인성 세운): 戌월 = 午戌 반합 2 + 戊戌 천간·지지 비겁(인성→비겁 출구) 2 = 4 로
    단독 최고(원문 '10월'). 未월 = 육합 2 + 未 己 겁재 1 = 3, 寅월 = 반합 2.
    """
    return [m for m, _ in peak_month_entries(day_master, year_stem, year_branch)]


def strong_months(day_master: Stem, year_stem: Stem) -> list[tuple[int, str]]:
    """그 해의 간여지동 달 — (양력 월 번호, 십성군), 절기 연도 순(寅월 → 丑월).

    간여지동 = 월운 천간과 지지(본기)의 오행이 같음 = 일간 기준 같은 십성군(2026-11-09 데굴님
    "그해 간여지동으로 들어오는 월의 내용을 풀이"). 세운 지지와의 합·출구 점수(`peak_months`)는
    쓰지 않는다. 60갑자 전수: 1개 36년 · 2개 12년 · 7개 12년(戊·癸년 — 甲寅월 시작).
    """
    out: list[tuple[int, str]] = []
    for m_stem, m_branch, month_no in month_ganji_of_year(year_stem):
        sg = _GROUP_OF[ten_god_name(day_master, m_stem)]
        if sg == _GROUP_OF[branch_god_name(day_master, m_branch)]:
            out.append((month_no, sg))
    return out


def peak_month_line(
    day_master: Stem, year_stem: Stem, year_branch: Branch, simple: dict[str, Any]
) -> str | None:
    """오늘의 운세 패널 간여지동 달 문장 — 십성군별로 묶어 한 줄씩(줄바꿈 구분, 최대 5줄).

    **2026-11-10 패널에서 제거**(데굴님 "불필요해보여", docs/17 §30) — 지금은 호출처가 없다. 함수와
    사전 `strong_month_lead` 는 남겨 두었다(되살릴 때 그대로 쓴다). 채팅 월 문단은
    `strong_month_chat_line` 을 쓰며 영향이 없다.

    줄 = 사전 `strong_month_lead`("{months}에는 천간과 지지가 모두 같은 성격의 글자로 …") + 사전
    `strong_month[그 달 십성군]`("이 영향은 … 해보세요"). 내용은 **그 달**의 십성군이다(세운 군
    아님 — 2026-11-09 데굴님 "올해 흐름과 어떤 관계인지 알 수가 없어"). 간여지동 달이 없으면 None.
    필드 이름(`peak_months`)은 보드 계약 호환으로 유지한다.

    v1.19 계약(`peak_month[군]` 에 `{months}`)은 종전 절정 점수식(`peak_months`) 문장을 그대로 쓴다.
    """
    legacy = simple.get("peak_month")
    if "strong_month" not in simple and legacy:
        months = peak_months(day_master, year_stem, year_branch)
        if not months:
            return None
        group = _GROUP_OF[ten_god_name(day_master, year_stem)]
        return str(legacy[group]).format(months="·".join(f"{m}월" for m in months))
    by_group: dict[str, list[int]] = {}
    for month_no, group in strong_months(day_master, year_stem):
        by_group.setdefault(group, []).append(month_no)
    if not by_group:
        return None
    lines = [
        f"{simple['strong_month_lead'].format(months=months_label(ms))} "
        f"{simple['strong_month'][group]}"
        for group, ms in by_group.items()
    ]
    return "\n".join(lines)


def months_label(months: list[int]) -> str:
    """간여지동 달 표기 — '2·3월' / '다음 해 1월' / '12월·다음 해 1월'.

    세운은 寅월(양력 2월)에 시작해 丑월(양력 1월)에 끝나므로, 월 번호 1 은 그 세운의 **마지막 달 =
    다음 해 1월**이다. '1월'로만 적으면 그 해 1월(전년도 세운의 丑월 — 간지가 다르다)로 읽힌다
    (2026-11-10 점검: 乙·庚년의 己丑월, 데굴님 "다음해 1월로 표기하자").
    """
    this_year = [m for m in months if m != 1]
    parts: list[str] = []
    if this_year:
        parts.append("·".join(str(m) for m in this_year) + "월")
    if 1 in months:
        parts.append("다음 해 1월")
    return "·".join(parts)


def _ro(word: str) -> str:
    """조사 '로/으로' — 받침 없거나 ㄹ 받침이면 '로'. 괄호로 끝나면 괄호 앞 글자 기준."""
    ch = word.rstrip(")").rsplit("·", 1)[-1][-1] if word.endswith(")") else word[-1]
    code = ord(ch) - 0xAC00
    if not 0 <= code < 11172:
        return "로"
    final = code % 28
    return "로" if final in (0, 8) else "으로"


def strong_month_chat_line(
    day_master: Stem, stem: Stem, branch: Branch, simple: dict[str, Any]
) -> str | None:
    """채팅 월 참고 문단의 간여지동 달 문장 — 그 달이 간여지동일 때만(세운과 무관), 아니면 None.

    `STRONG_MONTH_CHAT_LEAD`(같은 십성 "겁재로" / 같은 군 "인성(정인·편인)으로") + 사전
    `strong_month[그 달 십성군]`. v1.20 이전 사전(`strong_month` 없음)은 None.
    """
    if "strong_month" not in simple:
        return None
    sg_name, bg_name = ten_god_name(day_master, stem), branch_god_name(day_master, branch)
    group = _GROUP_OF[sg_name]
    if group != _GROUP_OF[bg_name]:
        return None
    label = sg_name if sg_name == bg_name else f"{group}({sg_name}·{bg_name})"
    lead = STRONG_MONTH_CHAT_LEAD.format(label=label, ro=_ro(label))
    return f"{lead} {simple['strong_month'][group]}"


def chat_scoped(sentence: str, horizon: str) -> str:
    """패널용 강조 문장의 기간 지칭('이번 달은' 등)을 채팅 지시어('이 달은' 등)로 바꾼다."""
    panel, chat = _CHAT_SCOPE[horizon]
    return chat + sentence[len(panel):] if sentence.startswith(panel) else sentence


# ── 연 지평 확장(docs/17 §31, dict.v1.21, 2026-11-11 데굴님 승인) ─────────────────────────────
# 외부 '내년 단식' 글(2027 丁未)의 읽는 법을 옮긴다: 한 해를 통으로 보지 않고 ① 그 해 안에서 흐름이
# 가장 강한 구간과 전환 시점("7월까지 / 8월부터") ② 여러 해에 걸친 흐름("임인년부터 …") ③ 일지와
# 세운 지지의 관계 ④ 명식 조건(신약·과다·필요한 기운)이 있을 때의 차이. 전부 서술 전용이다(점수·판정
# 불관여). 십성군은 본기 기준 그대로 두고(연 쌍 문장), 구간만 지지 계절(방합)로 묶는다.

#: 지지 계절(방합) — (계절 오행, 지지 3, 양력 월 번호 3). 절기 연도 순(寅월 → 丑월). 월 번호는
#: `month_ganji_of_year` 와 같다(丑월 = 다음 해 1월).
_SEASONS: tuple[tuple[Element, tuple[Branch, ...], tuple[int, ...]], ...] = (
    (Element.WOOD, (Branch("寅"), Branch("卯"), Branch("辰")), (2, 3, 4)),
    (Element.FIRE, (Branch("巳"), Branch("午"), Branch("未")), (5, 6, 7)),
    (Element.METAL, (Branch("申"), Branch("酉"), Branch("戌")), (8, 9, 10)),
    (Element.WATER, (Branch("亥"), Branch("子"), Branch("丑")), (11, 12, 1)),
)
#: 오행 → 그 오행의 대표 천간(십성군 판정용 — 음양은 군에 영향이 없다).
_ELEMENT_STEM: dict[Element, Stem] = {
    Element.WOOD: Stem("甲"), Element.FIRE: Stem("丙"), Element.EARTH: Stem("戊"),
    Element.METAL: Stem("庚"), Element.WATER: Stem("壬"),
}
#: 오행의 쉬운 표기(조건 줄 — 사용자가 자기 명식과 맞춰 보는 말이라 오행 이름을 그대로 쓴다).
_ELEMENT_PLAIN: dict[Element, str] = {
    Element.WOOD: "목(나무)", Element.FIRE: "화(불)", Element.EARTH: "토(흙)",
    Element.METAL: "금(쇠)", Element.WATER: "수(물)",
}
#: 여러 해 흐름의 한 묶음 = 세운 지지 계절 3년(寅卯辰·巳午未·申酉戌·亥子丑).
SPAN_YEARS = 3
#: 기간 지칭 — 패널은 '올해', 채팅·테마는 다른 해(내년·작년)도 물으므로 '이 해'.
PANEL_YEAR_SCOPE = "올해"
CHAT_YEAR_SCOPE = "이 해"
#: 힘을 쓰는 군(일간이 生·剋 하거나 剋 받는 군) — 신약에는 부담, 신강에는 쓸 곳.
_DRAIN_GROUPS: frozenset[str] = frozenset({"식상", "재성", "관성"})
#: 조건 줄 신강약 판정 — 양끝 두 단계씩만(중화 3단계는 어느 쪽도 싣지 않는다).
_WEAK_BANDS: frozenset[str] = frozenset({"태신약", "신약"})
_STRONG_BANDS: frozenset[str] = frozenset({"신강", "태신강"})
_FAVORABLE_ROLES: frozenset[str] = frozenset({"용신", "희신"})
_ADVERSE_ROLES: frozenset[str] = frozenset({"기신", "구신"})


def element_group(day_master: Stem, element: Element) -> str:
    """일간 기준 그 오행의 십성군."""
    return _GROUP_OF[ten_god_name(day_master, _ELEMENT_STEM[element])]


@dataclass(frozen=True)
class YearPhase:
    """한 해 안의 구간 — 흐름이 가장 강한 계절과 그 다음 계절(전환)."""

    year_group: str  # 세운 천간 십성군
    peak_months: tuple[int, ...]  # 가장 강한 구간(양력 월 번호 3)
    turn_month: int | None  # 전환이 시작되는 달 — 水 세운(겨울이 절정)은 그 해 안에 전환이 없다
    turn_group: str | None  # 전환 뒤 계절의 십성군


def _peak_season_index(year_stem: Stem) -> int | None:
    """세운 천간 오행과 같은 계절의 순번 — 土 세운(戊·己)은 같은 계절이 없어 None."""
    element = STEM_ELEMENT[year_stem]
    return next((i for i, (e, _b, _m) in enumerate(_SEASONS) if e == element), None)


def year_phase(day_master: Stem, year_stem: Stem) -> YearPhase | None:
    """연내 구간(§31-1) — 세운 천간 오행과 같은 계절 석 달이 가장 강한 때, 다음 계절이 전환.

    丙·丁년 = 5~7월 절정·8월 전환, 甲·乙년 = 2~4월·5월, 庚·辛년 = 8~10월·11월, 壬·癸년 = 11월~
    다음 해 1월(전환 없음). 戊·己년은 같은 계절이 없어 None — 규칙을 정하지 않았다(2028년부터
    해당, 보류).
    """
    idx = _peak_season_index(year_stem)
    if idx is None:
        return None
    turn = _SEASONS[idx + 1] if idx + 1 < len(_SEASONS) else None
    return YearPhase(
        year_group=_GROUP_OF[ten_god_name(day_master, year_stem)],
        peak_months=_SEASONS[idx][2],
        turn_month=turn[2][0] if turn else None,
        turn_group=element_group(day_master, turn[0]) if turn else None,
    )


def phase_months_label(months: tuple[int, ...]) -> str:
    """구간 표기 — '5~7월' / '11월~다음 해 1월'(丑월은 그 세운의 마지막 달 = 다음 해 1월)."""
    if months[-1] < months[0]:
        return f"{months[0]}월~다음 해 {months[-1]}월"
    return f"{months[0]}~{months[-1]}월"


def phase_peak_passed(year_stem: Stem, month_branch: Branch) -> bool:
    """그 세운 안에서 오늘 월운 지지가 가장 강한 구간을 지났는가(절기 기준 — 양력 달 아님)."""
    idx = _peak_season_index(year_stem)
    if idx is None:
        return False
    order = [b for _e, branches, _m in _SEASONS for b in branches]
    return order.index(month_branch) > idx * 3 + 2


def year_phase_passed_on(today: date, year: int, year_stem: Stem, year_branch: Branch) -> bool:
    """오늘이 그 세운 안에 있고 가장 강한 구간이 이미 지났는가 — 지났으면 그 문장만 과거형으로 쓴다.

    오늘이 다른 세운이면(내년·작년 질문) False 다 — 지난 해 전체는 호출자가 `past=True` 로 따로
    처리한다.
    """
    from saju_engines.daily_ilju_fortune import build_day_context  # 지연 import — 순환 회피

    ctx = build_day_context(today)
    if (ctx.year_stem, ctx.year_branch) != (year_stem.value, year_branch.value):
        return False
    if abs(today.year - year) > 1:  # 60년 뒤 같은 간지
        return False
    return phase_peak_passed(year_stem, Branch(ctx.month_branch))


def year_phase_lines(
    day_master: Stem,
    year_stem: Stem,
    simple: dict[str, Any],
    *,
    scope: str = PANEL_YEAR_SCOPE,
    peak_passed: bool = False,
) -> list[str]:
    """연내 구간 문장 — [가장 강한 때 1문장, 전환 뒤 흐름·조언]. 土 세운·과거 계약은 빈 목록.

    가장 강한 때 문장은 사실 서술(`year_phase_peak`)이라 구간이 지났으면 과거형('~이었어요')으로
    바꾼다. 전환 문장은 '○월부터는 … 흐름이에요'로 시제에 매이지 않는다.
    """
    turn_pool = simple.get("year_phase_turn")
    phase = year_phase(day_master, year_stem)
    if not turn_pool or phase is None:
        return []
    peak = str(simple["year_phase_peak"]).format(
        this=scope, months=phase_months_label(phase.peak_months),
    )
    if peak_passed:
        from saju_engines.speech_style import past_sentence  # 지연 import — 문체 모듈

        peak = past_sentence(peak) or peak
    lines = [peak]
    if phase.turn_group is not None:
        turn = turn_pool.get(f"{phase.year_group}>{phase.turn_group}")
        if turn:
            lines.append(str(turn).format(month=phase.turn_month))
    return lines


@dataclass(frozen=True)
class SeasonRun:
    """세운 지지 계절 3년 묶음 하나."""

    start_year: int  # 묶음 첫 해(寅·巳·申·亥년)
    position: int  # 대상 해가 묶음에서 몇 번째인가(1~3)
    element: Element  # 계절 오행
    group: str  # 일간 기준 그 계절의 십성군


def year_branch_of(year: int) -> Branch:
    """그 해 세운 지지(입춘 뒤 기준) — 서기 4년이 甲子년."""
    return list(Branch)[(year - 4) % 12]


def season_run(day_master: Stem, year: int) -> SeasonRun:
    """그 해가 속한 세운 지지 계절 3년 묶음(§31-2).

    세운 지지는 12년에 걸쳐 봄(寅卯辰)·여름(巳午未)·가을(申酉戌)·겨울(亥子丑)을 3년씩 지난다. 2027
    丁未 = 여름 3년(2025~2027)의 마지막 해, 직전 봄 3년은 2022 壬寅 ~ 2024 甲辰. 연도만으로
    정해지므로 아무리 먼 과거·미래 해도 같은 식으로 구한다.
    """
    offset = ((year - 4) % 12 - 2) % 12  # 寅 = 0
    element = _SEASONS[offset // SPAN_YEARS][0]
    position = offset % SPAN_YEARS + 1
    return SeasonRun(
        start_year=year - (position - 1), position=position, element=element,
        group=element_group(day_master, element),
    )


def season_history(day_master: Stem, year: int, spans: int = 4) -> list[SeasonRun]:
    """그 해의 묶음부터 과거로 `spans` 개 — 첫 원소가 그 해의 묶음(position = 그 해 순번).

    "언제부터 이어진 흐름인가"를 여러 묶음 거슬러 확인하는 용도다(예: 土 일간 2027 → 2025 인성 ·
    2022 관성 · 2019 재성 · 2016 식상). 과거 묶음의 position 은 3(끝난 묶음)이다.
    """
    current = season_run(day_master, year)
    out = [current]
    start = current.start_year
    for _ in range(max(spans, 1) - 1):
        start -= SPAN_YEARS
        out.append(season_run(day_master, start + SPAN_YEARS - 1))
    return out


def year_span_line(
    day_master: Stem,
    year: int,
    simple: dict[str, Any],
    *,
    scope: str = PANEL_YEAR_SCOPE,
    year_branch: Branch | None = None,
) -> str:
    """여러 해 흐름 문장 — 직전 3년 → 지금 3년(몇 번째 해) → (마지막 해면) 다음 3년.

    과거 계약(사전에 `year_span` 없음)은 빈 문자열.

    `year_branch` 를 주면 연도와 맞는지 확인하고, 어긋나면 빈 문자열이다(연도·간지가 다른 출처에서
    온 호출 방어).
    """
    pool, tone = simple.get("year_span"), simple.get("season_tone")
    if not pool or not tone:
        return ""
    if year_branch is not None and year_branch_of(year) != year_branch:
        return ""
    current = season_run(day_master, year)
    previous = season_run(day_master, current.start_year - 1)
    following = season_run(day_master, current.start_year + SPAN_YEARS)
    return str(pool[str(current.position)]).format(
        this=scope,
        prev_start=previous.start_year, prev=tone[previous.group],
        start=current.start_year, cur=tone[current.group],
        next_start=following.start_year, next=tone[following.group],
    )


def year_ilju_kind(ilju_branch: Branch, year_branch: Branch) -> str:
    """일지와 세운 지지의 관계(§31-3) — 충 > 육합 > 삼합·반합 > 형 > 같은 글자 > 없음.

    월 패널(§24-3)은 형을 쓰지 않지만 연 줄은 형(丑戌未·寅巳申·子卯·자형)을 싣는다 — 원문 단식이
    未년의 丑·戌 을 함께 짚었고, 문장은 겁주지 않게 조율·몸 관리 조언으로 쓴다. 왕지 없는 반합도
    삼합 문장으로 친다(§27 과 같다).
    """
    from saju_engines.daily_ilju_fortune import _branch_relations  # 지연 import — 순환 회피

    hits = _branch_relations(year_branch, ilju_branch, ())
    pair = frozenset({ilju_branch, year_branch})
    if "clash" in hits:
        return "chung"
    if "six_combination" in hits:
        return "yukhap"
    if (
        "three_harmony_complete" in hits or "half_harmony" in hits
        or (len(pair) == 2 and any(pair <= members for members, _e, _r in THREE_HARMONY))
    ):
        return "samhap"
    if "punishment" in hits:
        return "hyeong"
    if ilju_branch == year_branch:
        return "same"
    return "none"


def year_ilju_line(ilju_branch: Branch, year_branch: Branch, simple: dict[str, Any]) -> str | None:
    """일주별 올해 한 줄 — 60일주 전부 한 줄씩(관계 없으면 'none' 문장). 과거 계약은 None."""
    pool = simple.get("year_ilju")
    if not pool:
        return None
    return str(pool[year_ilju_kind(ilju_branch, year_branch)])


def year_elements(year_stem: Stem, year_branch: Branch) -> list[Element]:
    """그 해에 들어오는 오행 — 세운 천간 오행 + 지지 본기 오행(중복 제거, 천간 먼저)."""
    out = [STEM_ELEMENT[year_stem]]
    branch_element = STEM_ELEMENT[Stem(main_hidden_stem(year_branch))]
    if branch_element not in out:
        out.append(branch_element)
    return out


def year_clash_branches(year_branch: Branch) -> list[Branch]:
    """세운 지지와 충·형이 되는 지지 — 지지 순서(子 → 亥). 자형이면 자기 글자도 든다.

    2027 未 → 丑(충·형)·戌(형), 2026 午 → 子(충)·午(자형).
    """
    hit: set[Branch] = set()
    for pair in BRANCH_CLASHES:
        if year_branch in pair:
            hit |= pair - {year_branch}
    for triple in PUNISHMENT_TRIPLES:
        if year_branch in triple:
            hit |= triple - {year_branch}
    for pair in PUNISHMENT_MUTUAL:
        if year_branch in pair:
            hit |= pair - {year_branch}
    if year_branch in SELF_PUNISHMENT:
        hit.add(year_branch)
    return [b for b in Branch if b in hit]


def _elements_label(elements: list[Element]) -> str:
    return "·".join(_ELEMENT_PLAIN[e] for e in elements)


def _branches_label(branches: list[Branch]) -> str:
    return "·".join(f"{BRANCH_KO[b]}({b.value})" for b in branches)


def year_condition_lines(
    day_master: Stem,
    year_stem: Stem,
    year_branch: Branch,
    simple: dict[str, Any],
    *,
    scope: str = PANEL_YEAR_SCOPE,
) -> list[str]:
    """올해의 흐름 패널 조건 줄(§31-4) — 조건을 가졌는지는 사용자가 자기 명식으로 판단한다.

    일주 버킷은 원국을 모르므로 판정하지 않고 "이런 명식이면 …"만 적는다: ① 신약/신강(세운 천간
    십성군 기준) ② 올해 들어오는 기운이 용신·희신/기신·구신일 때 ③ 지지에 세운 지지와 충·형이 되는
    글자가 있을 때 ④ 올해 들어오는 기운이 이미 많을 때. 과거 계약(`year_cond` 없음)은 빈 목록.
    """
    cond = simple.get("year_cond")
    if not cond:
        return []
    group = _GROUP_OF[ten_god_name(day_master, year_stem)]
    lead, body = cond["strength_lead"], cond["strength"][group]
    elements = _elements_label(year_elements(year_stem, year_branch))
    lines = [
        f"{lead['weak']} {body['weak']} {lead['strong']} {body['strong']}",
        str(cond["need"]).format(this=scope, elements=elements),
    ]
    clash = year_clash_branches(year_branch)
    if clash:
        lines.append(str(cond["clash"]).format(this=scope, branches=_branches_label(clash)))
    lines.append(
        f"{str(cond['excess_lead']).format(elements=elements)} "
        f"{str(cond['excess']).format(this=scope)}"
    )
    return lines


def year_condition_hits(
    day_master: Stem,
    year_stem: Stem,
    year_branch: Branch,
    simple: dict[str, Any] | None = None,
    *,
    band: str = "",
    excessive_elements: list[str] | tuple[str, ...] = (),
    roles: dict[str, str] | None = None,
    scope: str = CHAT_YEAR_SCOPE,
) -> list[str]:
    """채팅·테마용 조건 줄 — 엔진이 이 명식에서 **확인한 항목만** 싣는다(§31-4).

    - 신강약: `band` 가 신약·태신약 또는 신강·태신강일 때 세운 천간 십성군의 그쪽 문장. 단 용기신
      방향과 어긋나면 싣지 않는다(부담 문장인데 그 오행이 용신·희신, 도움 문장인데 기신·구신 —
      종격처럼 강약과 용신이 반대로 가는 명식 방어. 방향 판정은
      `SIMPLE_READING_DIRECTION_RULE` 이 맡는다).
    - 과다: 그 해에 들어오는 오행(천간·지지 본기)이 엔진의 과다 오행(`excessive_elements`)에
      있을 때.
    - 필요한 기운(용희신)·지지 충형은 싣지 않는다 — 운 줄의 역할 표기와 관계 계층 블록이 이미
      엔진 확정값으로 전달하며, 같은 사실을 두 표현으로 주면 감사와 어긋난다.

    Args:
        band: 신강약 등급(`StrengthBand` 값 — '신약'·'태신강' 등).
        excessive_elements: 엔진 과다 오행(한자 — '土' 등).
        roles: 오행(한자) → 역할('용신'·'기신' 등). 없으면 방향 대조를 생략한다.
    """
    if simple is None:
        simple = _current_layers()[0]
    cond = (simple or {}).get("year_cond")
    if not cond:
        return []
    out: list[str] = []
    side = "weak" if band in _WEAK_BANDS else "strong" if band in _STRONG_BANDS else ""
    if side:
        group = _GROUP_OF[ten_god_name(day_master, year_stem)]
        burden = (side == "weak") == (group in _DRAIN_GROUPS)
        role = (roles or {}).get(STEM_ELEMENT[year_stem].value, "")
        contradicts = (burden and role in _FAVORABLE_ROLES) or (
            not burden and role in _ADVERSE_ROLES
        )
        if not contradicts:
            out.append(f"이 명식은 {band}이라 {cond['strength'][group][side]}")
    excess = [e for e in year_elements(year_stem, year_branch) if e.value in excessive_elements]
    if excess:
        out.append(
            f"이 명식은 {_elements_label(excess)} 기운이 이미 많아, "
            f"{str(cond['excess']).format(this=scope)}"
        )
    return out


@lru_cache(maxsize=1)
def _current_layers() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """채팅·테마 참고 줄용 — 현재 `DICT_VERSION` 사전의 (`simple_layer`, `month_layer`)."""
    try:
        from saju_engines.daily_ilju_fortune import load_daily_dicts

        tpl = load_daily_dicts().templates
        return tpl.get("simple_layer"), tpl.get("month_layer")
    except Exception:  # noqa: BLE001 — 사전 부재는 참고 줄 생략으로(기능 차단 금지)
        return None, None


def _copula(word: str) -> str:
    """명사 뒤 해요체 서술격 — 받침 있으면 '이에요', 없으면 '예요'(해예요·달이에요·날이에요)."""
    code = ord(word[-1]) - 0xAC00
    return "이에요" if 0 <= code < 11172 and code % 28 else "예요"


def _desc(sr: SimpleReading, noun: str) -> str:
    """'인성(편인·정인)의 해' 또는 '천간 겁재(비겁)·지지 편재(재성)이 섞인 달'."""
    if sr.same_group:
        return f"{sr.stem_group}({sr.stem_god}·{sr.branch_god})의 {noun}"
    return (
        f"천간 {sr.stem_god}({sr.stem_group})·지지 {sr.branch_god}({sr.branch_group})이 섞인 {noun}"
    )


def _parse_ganji(ganji: str | None) -> tuple[Stem, Branch] | None:
    if not ganji or len(ganji) < 2:
        return None
    try:
        return Stem(ganji[0]), Branch(ganji[1])
    except ValueError:
        return None


def simple_reference_line(
    day_master: str,
    ganji: str,
    horizon: str,
    simple: dict[str, Any] | None = None,
    month_layer: dict[str, Any] | None = None,
    *,
    year_ganji: str | None = None,
    prefix: str = REFERENCE_PREFIX,
    past: bool = False,
    year: int | None = None,
    today: date | None = None,
) -> str:
    """채팅·테마사주 참고 문단(§26-3) — 용어 허용 경로. 호출자는 이 문단을 **그대로** 싣는다.

    - year: "간단히 봤을 때, 丙午년은 무(戊) 일간에게 인성(편인·정인)의 해예요. {year_tone}"
      + 연내 구간(`year_phase_lines` — 가장 강한 때 + 전환 뒤 흐름) + `year` 가 있으면 여러 해
      흐름(`year_span_line`). §31, dict.v1.21 — 이전 사전은 종전 그대로.
    - month / day(2026-11-08 2차 실답 교정 — 데굴님 "이달 운세를 물었는데 올해 흐름을 계속 반복해
      올해 내용인지 이달 내용인지 헛갈린다"): **그 달/그 날에 집중** — 이름 1문장 + 운 천간 십성
      장면 + 운 지지 십성 장면(§27 `god_points` 1·3번째). 같은 군(간여지동)이면 — 월은
      `strong_month_chat_line`("이 달은 천간과 지지 모두 ○○로 들어와 …" + 그 달 십성군 본문),
      일은 강조 1문장(`chat_scoped` — '이 날은'). 올해 흐름 문장은 싣지 않는다(2026-11-09 데굴님
      "올해 흐름과 어떤 관계인지 알 수가 없어"). v1.19 사전(god_scene 없음)은 그 달 `tone`.
    끝에 참고 안내 1문장. 일간·간지가 비었거나 사전이 없으면 빈 문자열(호출자는 줄을 생략한다).

    Args:
        year_ganji: 호출 호환용으로 남긴 인자 — 2026-11-09 부터 문단이 세운에 의존하지 않아 쓰지
            않는다.
        past: 이미 지난 기간(지난달·어제·작년)을 묻는 질문이면 True — 문단을 과거형으로 싣는다
            (`speech_style.to_past`: 서술 '~했을 수 있어요', 간지 사실 '~달이었어요', 권유 문장
            제외. 2026-11-10 데굴님 "과거형 문단" — 지난달 답에 현재형 문단이 끼고, LLM 이
            과거형으로 바꿔 쓴 문단을 감사가 못 알아봐 같은 내용이 두 번 나갔다). 끝의 참고 안내는
            현재형 그대로.
        year: 연 지평의 대상 연도(서기) — 여러 해 흐름 문장에 쓴다. 없으면 그 문장을 생략한다.
        today: 연 지평에서 오늘 날짜 — 대상 해가 올해이고 가장 강한 구간이 지났으면 그 문장만
            과거형으로 쓴다. 없으면 현재형.
    """
    del year_ganji  # 호환 인자(미사용)
    if not day_master or horizon not in HORIZONS:
        return ""
    if simple is None or (horizon != "year" and month_layer is None):
        cur_simple, cur_month = _current_layers()
        simple = simple or cur_simple
        month_layer = month_layer or cur_month
    target = _parse_ganji(ganji)
    if simple is None or target is None:
        return ""
    try:
        dm = Stem(day_master)
    except ValueError:
        return ""
    stem, branch = target
    sr = simple_reading(dm, stem, branch, horizon, simple, month_layer)
    unit, noun = _UNIT_KO[horizon], _NOUN_KO[horizon]
    who = f"{STEM_KO[dm]}({dm.value}) 일간에게"
    parts: list[str] = [f"{prefix} {ganji}{unit}은 {who} {_desc(sr, noun)}{_copula(noun)}."]
    if horizon == "year":
        if sr.tone:
            parts.append(sr.tone)
        # 연내 구간·여러 해 흐름(§31) — 채팅은 내년·작년도 물으므로 '올해' 대신 '이 해'.
        passed = (
            not past and today is not None and year is not None
            and year_phase_passed_on(today, year, stem, branch)
        )
        parts.extend(
            year_phase_lines(dm, stem, simple, scope=CHAT_YEAR_SCOPE, peak_passed=passed)
        )
        if year is not None:
            parts.append(
                year_span_line(dm, year, simple, scope=CHAT_YEAR_SCOPE, year_branch=branch)
            )
    elif simple.get("god_scene"):
        # 그 달/그 날에 집중 — 천간 십성 장면 + 지지 십성 장면(§27). 올해 결은 싣지 않는다.
        parts.extend((sr.points[0], sr.points[2]))
        # 월: 간여지동 달이면 강조 문장 대신 "이 달은 천간과 지지 모두 ○○로 들어와 …" + 그 달
        # 십성군 본문(같은 조건이라 강조 문장과 둘 다 싣지 않는다). 올해 흐름은 언급하지 않는다.
        strong = strong_month_chat_line(dm, stem, branch, simple) if horizon == "month" else None
        if strong:
            parts.append(strong)
        elif sr.emphasis:
            parts.append(chat_scoped(sr.emphasis, horizon))
    elif sr.tone:
        parts.append(sr.tone)
    core = " ".join(p for p in parts if p)
    if past:
        from saju_engines.speech_style import to_past  # 지연 import — 문체 모듈은 이 경로에서만

        core = to_past(core)
    return f"{core} {_REFERENCE_SUFFIX}"


def ganji_ko(stem: Stem, branch: Branch) -> str:
    """간지 한글 표기(예: 병오)."""
    return f"{STEM_KO[stem]}{BRANCH_KO[branch]}"
