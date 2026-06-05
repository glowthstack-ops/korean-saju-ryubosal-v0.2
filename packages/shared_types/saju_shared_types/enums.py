"""Core enumerations for the deterministic Saju engine.

Canonical representation uses Hanja single characters for stems/branches/elements
(matching the v2.1 spec, e.g. ``庚申``). Korean readings are provided via
``constants.py`` lookup tables, not on the enums themselves.
"""

from __future__ import annotations

from enum import StrEnum


class Element(StrEnum):
    """오행 (Five Elements)."""

    WOOD = "木"
    FIRE = "火"
    EARTH = "土"
    METAL = "金"
    WATER = "水"


class YinYang(StrEnum):
    """음양."""

    YANG = "陽"
    YIN = "陰"


class Stem(StrEnum):
    """천간 (Heavenly Stems), in canonical order 甲→癸."""

    GAP = "甲"
    EUL = "乙"
    BYEONG = "丙"
    JEONG = "丁"
    MU = "戊"
    GI = "己"
    GYEONG = "庚"
    SIN = "辛"
    IM = "壬"
    GYE = "癸"


class Branch(StrEnum):
    """지지 (Earthly Branches), in canonical order 子→亥."""

    JA = "子"
    CHUK = "丑"
    IN = "寅"
    MYO = "卯"
    JIN = "辰"
    SA = "巳"
    O = "午"  # noqa: E741 - traditional single-char branch label
    MI = "未"
    SIN = "申"
    YU = "酉"
    SUL = "戌"
    HAE = "亥"


class TenGod(StrEnum):
    """십성 (Ten Gods)."""

    BIGYEON = "비견"
    GEOMJAE = "겁재"
    SIKSIN = "식신"
    SANGGWAN = "상관"
    PYEONJAE = "편재"
    JEONGJAE = "정재"
    PYEONGWAN = "편관"
    JEONGGWAN = "정관"
    PYEONIN = "편인"
    JEONGIN = "정인"
    ILGAN = "일간"  # the day master itself


class HiddenStemType(StrEnum):
    """지장간 구분: 본기/중기/여기."""

    MAIN = "main"  # 본기 (정기)
    MIDDLE = "middle"  # 중기
    RESIDUAL = "residual"  # 여기 (잔기)


class Palace(StrEnum):
    """궁성 (Palace) — life-domain mapping per pillar position."""

    YEAR = "뿌리·가족궁"
    MONTH = "직업·환경궁"
    DAY = "배우자·현실궁"
    HOUR = "자녀·결과궁"


class StrengthBand(StrEnum):
    """신강/신약 9단계 (defined now; populated in a later phase)."""

    EXTREME_WEAK = "극신약"
    VERY_WEAK = "태신약"
    WEAK = "신약"
    NEUTRAL_WEAK = "중화신약"
    NEUTRAL = "중화"
    NEUTRAL_STRONG = "중화신강"
    STRONG = "신강"
    VERY_STRONG = "태신강"
    EXTREME_STRONG = "극신강"


class CalendarType(StrEnum):
    SOLAR = "solar"
    LUNAR = "lunar"


class PillarPosition(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
