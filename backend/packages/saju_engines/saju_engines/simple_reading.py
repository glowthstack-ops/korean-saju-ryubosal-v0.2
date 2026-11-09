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
from functools import lru_cache
from typing import Any

from saju_shared_types.constants import BRANCH_KO, STEM_KO, main_hidden_stem, ten_god
from saju_shared_types.enums import Branch, Stem

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
        f"{simple['strong_month_lead'].format(months='·'.join(str(m) for m in ms) + '월')} "
        f"{simple['strong_month'][group]}"
        for group, ms in by_group.items()
    ]
    return "\n".join(lines)


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
) -> str:
    """채팅·테마사주 참고 문단(§26-3) — 용어 허용 경로. 호출자는 이 문단을 **그대로** 싣는다.

    - year: "간단히 봤을 때, 丙午년은 무(戊) 일간에게 인성(편인·정인)의 해예요. {year_tone}"
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
    parts.append(_REFERENCE_SUFFIX)
    return " ".join(p for p in parts if p)


def ganji_ko(stem: Stem, branch: Branch) -> str:
    """간지 한글 표기(예: 병오)."""
    return f"{STEM_KO[stem]}{BRANCH_KO[branch]}"
