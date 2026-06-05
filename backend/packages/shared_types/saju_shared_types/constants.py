"""Single source of truth for all Saju constant tables.

Every mapping needed by the deterministic engine lives here so that the rules can
be audited in one place. All formula constants are taken directly from the v2.1
spec bundle (``saju_v2_pillar_calculation_spec.md`` and friends) and have been
cross-checked against the golden fixture 1980-11-22 09:08 Seoul → 庚申·丁亥·己亥·己巳.
"""

from __future__ import annotations

from .enums import Branch, Element, HiddenStemType, Stem, TenGod, YinYang

# ---------------------------------------------------------------------------
# Ordering (indices are load-bearing: used for 60갑자 / 둔월·둔시 arithmetic)
# ---------------------------------------------------------------------------
STEMS: list[Stem] = list(Stem)  # 甲..癸 (0..9)
BRANCHES: list[Branch] = list(Branch)  # 子..亥 (0..11)

STEM_INDEX: dict[Stem, int] = {s: i for i, s in enumerate(STEMS)}
BRANCH_INDEX: dict[Branch, int] = {b: i for i, b in enumerate(BRANCHES)}

# ---------------------------------------------------------------------------
# Korean readings (for display / explanation only)
# ---------------------------------------------------------------------------
STEM_KO: dict[Stem, str] = {
    Stem.GAP: "갑", Stem.EUL: "을", Stem.BYEONG: "병", Stem.JEONG: "정", Stem.MU: "무",
    Stem.GI: "기", Stem.GYEONG: "경", Stem.SIN: "신", Stem.IM: "임", Stem.GYE: "계",
}
BRANCH_KO: dict[Branch, str] = {
    Branch.JA: "자", Branch.CHUK: "축", Branch.IN: "인", Branch.MYO: "묘",
    Branch.JIN: "진", Branch.SA: "사", Branch.O: "오", Branch.MI: "미",
    Branch.SIN: "신", Branch.YU: "유", Branch.SUL: "술", Branch.HAE: "해",
}
ELEMENT_KO: dict[Element, str] = {
    Element.WOOD: "목", Element.FIRE: "화", Element.EARTH: "토",
    Element.METAL: "금", Element.WATER: "수",
}

# 띠 (지지 동물)
BRANCH_ZODIAC: dict[Branch, str] = {
    Branch.JA: "쥐", Branch.CHUK: "소", Branch.IN: "호랑이", Branch.MYO: "토끼",
    Branch.JIN: "용", Branch.SA: "뱀", Branch.O: "말", Branch.MI: "양",
    Branch.SIN: "원숭이", Branch.YU: "닭", Branch.SUL: "개", Branch.HAE: "돼지",
}

# ---------------------------------------------------------------------------
# Stem → element / yinyang
# ---------------------------------------------------------------------------
STEM_ELEMENT: dict[Stem, Element] = {
    Stem.GAP: Element.WOOD, Stem.EUL: Element.WOOD,
    Stem.BYEONG: Element.FIRE, Stem.JEONG: Element.FIRE,
    Stem.MU: Element.EARTH, Stem.GI: Element.EARTH,
    Stem.GYEONG: Element.METAL, Stem.SIN: Element.METAL,
    Stem.IM: Element.WATER, Stem.GYE: Element.WATER,
}
STEM_YINYANG: dict[Stem, YinYang] = {
    Stem.GAP: YinYang.YANG, Stem.EUL: YinYang.YIN,
    Stem.BYEONG: YinYang.YANG, Stem.JEONG: YinYang.YIN,
    Stem.MU: YinYang.YANG, Stem.GI: YinYang.YIN,
    Stem.GYEONG: YinYang.YANG, Stem.SIN: YinYang.YIN,
    Stem.IM: YinYang.YANG, Stem.GYE: YinYang.YIN,
}

# ---------------------------------------------------------------------------
# Branch → surface element / yinyang
# ---------------------------------------------------------------------------
BRANCH_ELEMENT: dict[Branch, Element] = {
    Branch.IN: Element.WOOD, Branch.MYO: Element.WOOD,
    Branch.SA: Element.FIRE, Branch.O: Element.FIRE,
    Branch.JIN: Element.EARTH, Branch.SUL: Element.EARTH,
    Branch.CHUK: Element.EARTH, Branch.MI: Element.EARTH,
    Branch.SIN: Element.METAL, Branch.YU: Element.METAL,
    Branch.JA: Element.WATER, Branch.HAE: Element.WATER,
}
BRANCH_YINYANG: dict[Branch, YinYang] = {
    Branch.JA: YinYang.YANG, Branch.IN: YinYang.YANG, Branch.JIN: YinYang.YANG,
    Branch.O: YinYang.YANG, Branch.SIN: YinYang.YANG, Branch.SUL: YinYang.YANG,
    Branch.CHUK: YinYang.YIN, Branch.MYO: YinYang.YIN, Branch.SA: YinYang.YIN,
    Branch.MI: YinYang.YIN, Branch.YU: YinYang.YIN, Branch.HAE: YinYang.YIN,
}

# ---------------------------------------------------------------------------
# 오행 상생(generation) / 상극(control)
# ---------------------------------------------------------------------------
GENERATES: dict[Element, Element] = {
    Element.WOOD: Element.FIRE, Element.FIRE: Element.EARTH, Element.EARTH: Element.METAL,
    Element.METAL: Element.WATER, Element.WATER: Element.WOOD,
}
CONTROLS: dict[Element, Element] = {
    Element.WOOD: Element.EARTH, Element.EARTH: Element.WATER, Element.WATER: Element.FIRE,
    Element.FIRE: Element.METAL, Element.METAL: Element.WOOD,
}

# ---------------------------------------------------------------------------
# 지장간 (hidden stems): ordered residual(여기) → middle(중기) → main(정기).
# 지지 내 본/중/여 분배 비율(budget, 합=1.0) — 사용자 지정 표.
#   3지장간: 여0.20·중0.20·정0.60 / 왕지(子卯酉): 여0.30·정0.70 / 午(예외): 丙0.30·己0.20·丁0.50.
# ⚠️ 이 비율은 '지지 내부' 분배일 뿐이고, 오행/십성 비중에는 여기에 더해 자리별(위치) 가중치
#    BRANCH_POS_WEIGHT(年12·月28·日24·時16)가 분포 계층에서 곱해진다. (월률분야 일수는 미적용)
# ---------------------------------------------------------------------------
_HIDDEN: dict[Branch, list[tuple[Stem, HiddenStemType, float]]] = {
    Branch.JA: [  # 子 = 壬0.30 癸0.70
        (Stem.IM, HiddenStemType.RESIDUAL, 0.30),
        (Stem.GYE, HiddenStemType.MAIN, 0.70),
    ],
    Branch.CHUK: [  # 丑 = 癸0.20 辛0.20 己0.60
        (Stem.GYE, HiddenStemType.RESIDUAL, 0.20),
        (Stem.SIN, HiddenStemType.MIDDLE, 0.20),
        (Stem.GI, HiddenStemType.MAIN, 0.60),
    ],
    Branch.IN: [  # 寅 = 戊0.20 丙0.20 甲0.60
        (Stem.MU, HiddenStemType.RESIDUAL, 0.20),
        (Stem.BYEONG, HiddenStemType.MIDDLE, 0.20),
        (Stem.GAP, HiddenStemType.MAIN, 0.60),
    ],
    Branch.MYO: [  # 卯 = 甲0.30 乙0.70
        (Stem.GAP, HiddenStemType.RESIDUAL, 0.30),
        (Stem.EUL, HiddenStemType.MAIN, 0.70),
    ],
    Branch.JIN: [  # 辰 = 乙0.20 癸0.20 戊0.60
        (Stem.EUL, HiddenStemType.RESIDUAL, 0.20),
        (Stem.GYE, HiddenStemType.MIDDLE, 0.20),
        (Stem.MU, HiddenStemType.MAIN, 0.60),
    ],
    Branch.SA: [  # 巳 = 戊0.20 庚0.20 丙0.60
        (Stem.MU, HiddenStemType.RESIDUAL, 0.20),
        (Stem.GYEONG, HiddenStemType.MIDDLE, 0.20),
        (Stem.BYEONG, HiddenStemType.MAIN, 0.60),
    ],
    Branch.O: [  # 午(예외) = 丙0.30 己0.20 丁0.50
        (Stem.BYEONG, HiddenStemType.RESIDUAL, 0.30),
        (Stem.GI, HiddenStemType.MIDDLE, 0.20),
        (Stem.JEONG, HiddenStemType.MAIN, 0.50),
    ],
    Branch.MI: [  # 未 = 丁0.20 乙0.20 己0.60
        (Stem.JEONG, HiddenStemType.RESIDUAL, 0.20),
        (Stem.EUL, HiddenStemType.MIDDLE, 0.20),
        (Stem.GI, HiddenStemType.MAIN, 0.60),
    ],
    Branch.SIN: [  # 申 = 戊0.20 壬0.20 庚0.60
        (Stem.MU, HiddenStemType.RESIDUAL, 0.20),
        (Stem.IM, HiddenStemType.MIDDLE, 0.20),
        (Stem.GYEONG, HiddenStemType.MAIN, 0.60),
    ],
    Branch.YU: [  # 酉 = 庚0.30 辛0.70
        (Stem.GYEONG, HiddenStemType.RESIDUAL, 0.30),
        (Stem.SIN, HiddenStemType.MAIN, 0.70),
    ],
    Branch.SUL: [  # 戌 = 辛0.20 丁0.20 戊0.60
        (Stem.SIN, HiddenStemType.RESIDUAL, 0.20),
        (Stem.JEONG, HiddenStemType.MIDDLE, 0.20),
        (Stem.MU, HiddenStemType.MAIN, 0.60),
    ],
    Branch.HAE: [  # 亥 = 戊0.20 甲0.20 壬0.60
        (Stem.MU, HiddenStemType.RESIDUAL, 0.20),
        (Stem.GAP, HiddenStemType.MIDDLE, 0.20),
        (Stem.IM, HiddenStemType.MAIN, 0.60),
    ],
}


def hidden_stems_for(branch: Branch) -> list[tuple[Stem, HiddenStemType, float]]:
    """Return ``(stem, type, budget)`` — 지지 내 본/중/여 분배 비율(합=1.0)."""
    return list(_HIDDEN[branch])


def main_hidden_stem(branch: Branch) -> Stem:
    """본기 (main hidden stem) of *branch* — used for the branch's representative ten god."""
    for stem, kind, _w in _HIDDEN[branch]:
        if kind is HiddenStemType.MAIN:
            return stem
    raise KeyError(branch)  # pragma: no cover


# ---------------------------------------------------------------------------
# 둔월법 (五虎遁): year stem → stem of 寅月 (the first solar month).
# ---------------------------------------------------------------------------
MONTH_STEM_START: dict[Stem, Stem] = {
    Stem.GAP: Stem.BYEONG, Stem.GI: Stem.BYEONG,
    Stem.EUL: Stem.MU, Stem.GYEONG: Stem.MU,
    Stem.BYEONG: Stem.GYEONG, Stem.SIN: Stem.GYEONG,
    Stem.JEONG: Stem.IM, Stem.IM: Stem.IM,
    Stem.MU: Stem.GAP, Stem.GYE: Stem.GAP,
}

# 둔시법 (五鼠遁): day stem → stem of 子時.
HOUR_STEM_START: dict[Stem, Stem] = {
    Stem.GAP: Stem.GAP, Stem.GI: Stem.GAP,
    Stem.EUL: Stem.BYEONG, Stem.GYEONG: Stem.BYEONG,
    Stem.BYEONG: Stem.MU, Stem.SIN: Stem.MU,
    Stem.JEONG: Stem.GYEONG, Stem.IM: Stem.GYEONG,
    Stem.MU: Stem.IM, Stem.GYE: Stem.IM,
}

# Solar months run 寅,卯,…,丑 (offsets from 寅 in 둔월법 順行).
MONTH_BRANCH_ORDER: list[Branch] = [
    Branch.IN, Branch.MYO, Branch.JIN, Branch.SA, Branch.O, Branch.MI,
    Branch.SIN, Branch.YU, Branch.SUL, Branch.HAE, Branch.JA, Branch.CHUK,
]

# ---------------------------------------------------------------------------
# 십이운성 (Twelve Life Stages): 장생 starting branch + direction per day stem.
# 양간 順行(+1), 음간 逆行(-1).
# ---------------------------------------------------------------------------
TWELVE_STAGES: list[str] = [
    "장생", "목욕", "관대", "건록", "제왕", "쇠",
    "병", "사", "묘", "절", "태", "양",
]
JANGSAENG_BRANCH: dict[Stem, Branch] = {
    Stem.GAP: Branch.HAE, Stem.EUL: Branch.O,
    Stem.BYEONG: Branch.IN, Stem.JEONG: Branch.YU,
    Stem.MU: Branch.IN, Stem.GI: Branch.YU,
    Stem.GYEONG: Branch.SA, Stem.SIN: Branch.JA,
    Stem.IM: Branch.SIN, Stem.GYE: Branch.MYO,
}

# ---------------------------------------------------------------------------
# 공망 (Void): 0=甲子 … head-branch arithmetic, see gongmang.py.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 납음오행 (Naeum): 30 pairs of consecutive 60갑자 → name.
# ---------------------------------------------------------------------------
_NAEUM_PAIRS: list[str] = [
    "해중금", "노중화", "대림목", "노방토", "검봉금",
    "산두화", "간하수", "성두토", "백랍금", "양류목",
    "천중수", "옥상토", "벽력화", "송백목", "장류수",
    "사중금", "산하화", "평지목", "벽상토", "금박금",
    "복등화", "천하수", "대역토", "차천금", "상자목",
    "대계수", "사중토", "천상화", "석류목", "대해수",
]


def _build_naeum() -> dict[tuple[Stem, Branch], str]:
    table: dict[tuple[Stem, Branch], str] = {}
    for n in range(60):
        stem = STEMS[n % 10]
        branch = BRANCHES[n % 12]
        table[(stem, branch)] = _NAEUM_PAIRS[n // 2]
    return table


NAEUM: dict[tuple[Stem, Branch], str] = _build_naeum()


# ---------------------------------------------------------------------------
# Ten-god derivation (일간 기준 천간/지장간 관계)
# ---------------------------------------------------------------------------
def ten_god(day_master: Stem, target: Stem) -> TenGod:
    """Classify *target* stem relative to the *day_master* (일간)."""
    dm_el = STEM_ELEMENT[day_master]
    tg_el = STEM_ELEMENT[target]
    same_polarity = STEM_YINYANG[day_master] == STEM_YINYANG[target]

    if dm_el == tg_el:
        return TenGod.BIGYEON if same_polarity else TenGod.GEOMJAE
    if GENERATES[dm_el] == tg_el:  # 일간이 생함 → 식상
        return TenGod.SIKSIN if same_polarity else TenGod.SANGGWAN
    if CONTROLS[dm_el] == tg_el:  # 일간이 극함 → 재성
        return TenGod.PYEONJAE if same_polarity else TenGod.JEONGJAE
    if CONTROLS[tg_el] == dm_el:  # 일간을 극함 → 관성
        return TenGod.PYEONGWAN if same_polarity else TenGod.JEONGGWAN
    # 일간을 생함 → 인성
    return TenGod.PYEONIN if same_polarity else TenGod.JEONGIN


# ---------------------------------------------------------------------------
# 왕상휴수사 (seasonal state) — season element per month branch + state of any
# element relative to it. Earth months (辰戌丑未) take 土 as the season element,
# which reproduces the codex earth-day-master policy exactly.
# ---------------------------------------------------------------------------
SEASON_ELEMENT_BY_MONTH: dict[Branch, Element] = {
    Branch.IN: Element.WOOD, Branch.MYO: Element.WOOD,
    Branch.SA: Element.FIRE, Branch.O: Element.FIRE,
    Branch.SIN: Element.METAL, Branch.YU: Element.METAL,
    Branch.HAE: Element.WATER, Branch.JA: Element.WATER,
    Branch.JIN: Element.EARTH, Branch.SUL: Element.EARTH,
    Branch.CHUK: Element.EARTH, Branch.MI: Element.EARTH,
}

# state → (distribution coefficient, strength season_score)
SEASON_COEFFICIENT: dict[str, float] = {
    "wang": 1.30, "xiang": 1.15, "xiu": 1.00, "qiu": 0.80, "si": 0.65,
}
SEASON_SCORE: dict[str, int] = {
    "wang": 90, "xiang": 75, "xiu": 50, "qiu": 35, "si": 20,
}


def group_elements(day_master_element: Element) -> dict[str, Element]:
    """Map 십성 그룹 → 오행, relative to the day master's element.

    peer=일간 오행, resource=일간을 생하는 오행, output=일간이 생하는 오행,
    wealth=일간이 극하는 오행, officer=일간을 극하는 오행.
    """
    d = day_master_element
    resource = next(x for x in Element if GENERATES[x] == d)
    officer = next(x for x in Element if CONTROLS[x] == d)
    return {
        "peer": d,
        "resource": resource,
        "output": GENERATES[d],
        "wealth": CONTROLS[d],
        "officer": officer,
    }


def season_state(element: Element, month_branch: Branch) -> str:
    """왕(wang)/상(xiang)/휴(xiu)/수(qiu)/사(si) of *element* in *month_branch*."""
    season = SEASON_ELEMENT_BY_MONTH[month_branch]
    if element == season:
        return "wang"
    if GENERATES[season] == element:  # season generates element
        return "xiang"
    if GENERATES[element] == season:  # element generates season (mother)
        return "xiu"
    if CONTROLS[element] == season:  # element controls season
        return "qiu"
    return "si"  # season controls element


# ---------------------------------------------------------------------------
# 합충형파해 (relation) tables — canonical traditional sets.
# Keys/members use enums; combinations are unordered (frozenset).
# ---------------------------------------------------------------------------
# 천간합 (五合) → 합화 오행
STEM_COMBINATIONS: dict[frozenset[Stem], Element] = {
    frozenset({Stem.GAP, Stem.GI}): Element.EARTH,
    frozenset({Stem.EUL, Stem.GYEONG}): Element.METAL,
    frozenset({Stem.BYEONG, Stem.SIN}): Element.WATER,
    frozenset({Stem.JEONG, Stem.IM}): Element.WOOD,
    frozenset({Stem.MU, Stem.GYE}): Element.FIRE,
}

# 지지육합 (六合) → 합화 오행 (午未는 통설상 火/土 양설 → 火로 표기, 신뢰도 보수)
SIX_COMBINATIONS: dict[frozenset[Branch], Element] = {
    frozenset({Branch.JA, Branch.CHUK}): Element.EARTH,
    frozenset({Branch.IN, Branch.HAE}): Element.WOOD,
    frozenset({Branch.MYO, Branch.SUL}): Element.FIRE,
    frozenset({Branch.JIN, Branch.YU}): Element.METAL,
    frozenset({Branch.SA, Branch.SIN}): Element.WATER,
    frozenset({Branch.O, Branch.MI}): Element.FIRE,
}

# 삼합 (三合): (members, 합화 오행, 왕지)
THREE_HARMONY: list[tuple[frozenset[Branch], Element, Branch]] = [
    (frozenset({Branch.SIN, Branch.JA, Branch.JIN}), Element.WATER, Branch.JA),
    (frozenset({Branch.IN, Branch.O, Branch.SUL}), Element.FIRE, Branch.O),
    (frozenset({Branch.SA, Branch.YU, Branch.CHUK}), Element.METAL, Branch.YU),
    (frozenset({Branch.HAE, Branch.MYO, Branch.MI}), Element.WOOD, Branch.MYO),
]

# 방합 (方合): (members, 오행)
DIRECTIONAL_COMBINATIONS: list[tuple[frozenset[Branch], Element]] = [
    (frozenset({Branch.IN, Branch.MYO, Branch.JIN}), Element.WOOD),
    (frozenset({Branch.SA, Branch.O, Branch.MI}), Element.FIRE),
    (frozenset({Branch.SIN, Branch.YU, Branch.SUL}), Element.METAL),
    (frozenset({Branch.HAE, Branch.JA, Branch.CHUK}), Element.WATER),
]

# 지지충 (六沖)
BRANCH_CLASHES: set[frozenset[Branch]] = {
    frozenset({Branch.JA, Branch.O}),
    frozenset({Branch.CHUK, Branch.MI}),
    frozenset({Branch.IN, Branch.SIN}),
    frozenset({Branch.MYO, Branch.YU}),
    frozenset({Branch.JIN, Branch.SUL}),
    frozenset({Branch.SA, Branch.HAE}),
}

# 형 (刑): 삼형 + 상형 + 자형
PUNISHMENT_TRIPLES: list[frozenset[Branch]] = [
    frozenset({Branch.IN, Branch.SA, Branch.SIN}),  # 무은지형
    frozenset({Branch.CHUK, Branch.SUL, Branch.MI}),  # 지세지형
]
PUNISHMENT_MUTUAL: set[frozenset[Branch]] = {
    frozenset({Branch.JA, Branch.MYO}),  # 무례지형
}
SELF_PUNISHMENT: set[Branch] = {Branch.JIN, Branch.O, Branch.YU, Branch.HAE}

# 파 (六破)
BRANCH_BREAKS: set[frozenset[Branch]] = {
    frozenset({Branch.JA, Branch.YU}),
    frozenset({Branch.O, Branch.MYO}),
    frozenset({Branch.SIN, Branch.SA}),
    frozenset({Branch.IN, Branch.HAE}),
    frozenset({Branch.JIN, Branch.CHUK}),
    frozenset({Branch.SUL, Branch.MI}),
}

# 해 (六害)
BRANCH_HARMS: set[frozenset[Branch]] = {
    frozenset({Branch.JA, Branch.MI}),
    frozenset({Branch.CHUK, Branch.O}),
    frozenset({Branch.IN, Branch.SA}),
    frozenset({Branch.MYO, Branch.JIN}),
    frozenset({Branch.SIN, Branch.HAE}),
    frozenset({Branch.YU, Branch.SUL}),
}


# Engine/data versions stamped onto every result for reproducibility.
ENGINE_VERSION = "v2.1.0"
RULESET_VERSION = "pillars-2024.1"
