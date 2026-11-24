"""24방위(二十四山)·8방위 기하 상수 — 방위 **표기 전용**(docs/19 §5-6, 2026-11-24 데굴님 승인).

나경(패철)의 24방위는 정북(子)에서 시계 방향으로 한 칸 15°씩 놓인다. 8방위 한 칸(45°)은 24방위
세 칸이다(북 = 壬·子·癸, 북동 = 丑·艮·寅 …). 각도는 기준점에서 정북 0°·시계 방향이다.

이 모듈은 기하(어느 칸이 어느 8방위에 속하고 몇 도인가)만 다룬다. 어느 흉방이 어느 칸을 차지하는가는
사전(`dictionaries/folk_taboo_direction.json` 의 `extent`)이 정하고, 길흉 판정은 하지 않는다.
"""

from __future__ import annotations

from typing import Literal

#: 8방위 라벨(정방 4 + 간방 4).
Direction8 = Literal["북", "북동", "동", "남동", "남", "남서", "서", "북서"]

#: 24방위 — 정북(子)에서 시계 방향. 지지 12 + 천간 8(戊·己 제외) + 사유(艮·巽·坤·乾).
MOUNTAINS_24: tuple[str, ...] = (
    "子", "癸", "丑", "艮", "寅", "甲", "卯", "乙", "辰", "巽", "巳", "丙",
    "午", "丁", "未", "坤", "申", "庚", "酉", "辛", "戌", "乾", "亥", "壬",
)

#: 8방위 — 북에서 시계 방향.
DIRECTIONS_8: tuple[Direction8, ...] = ("북", "북동", "동", "남동", "남", "남서", "서", "북서")

#: 24방위 한 칸의 폭(도).
MOUNTAIN_SPAN_DEG = 15.0


def mountain_index(mountain: str) -> int:
    """24방위 글자 → 순번(子=0, 시계 방향). 표에 없는 글자는 ValueError."""
    return MOUNTAINS_24.index(mountain)


def direction8_of(mountain: str) -> Direction8:
    """24방위 한 칸이 속한 8방위(북 = 壬·子·癸 …)."""
    return DIRECTIONS_8[((mountain_index(mountain) + 1) // 3) % 8]


def mountains_of(direction: Direction8) -> list[str]:
    """8방위 한 칸의 24방위 세 칸(시계 방향 — 북 → 壬·子·癸)."""
    first = (DIRECTIONS_8.index(direction) * 3 - 1) % 24
    return [MOUNTAINS_24[(first + k) % 24] for k in range(3)]


def arc(start: str, end: str) -> list[str]:
    """start 칸에서 end 칸까지 시계 방향으로 이은 구간(양 끝 포함)."""
    i, j = mountain_index(start), mountain_index(end)
    return [MOUNTAINS_24[(i + k) % 24] for k in range((j - i) % 24 + 1)]


def degree_range(mountains: list[str]) -> tuple[float, float]:
    """시계 방향으로 이어진 구간의 (시작 각, 끝 각) — 정북 0°. 정북을 넘으면 시작 각이 더 크다."""
    start = (mountain_index(mountains[0]) * MOUNTAIN_SPAN_DEG - MOUNTAIN_SPAN_DEG / 2) % 360
    end = (mountain_index(mountains[-1]) * MOUNTAIN_SPAN_DEG + MOUNTAIN_SPAN_DEG / 2) % 360
    return start, end


def adjacent_direction8(mountain: str) -> Direction8 | None:
    """8방위 한 칸의 가장자리 칸이 맞닿은 이웃 8방위. 가운데 칸(子·艮·卯 …)이면 None."""
    idx = mountain_index(mountain)
    position = (idx + 1) % 3  # 0 = 그 8방위의 첫 칸, 1 = 가운데, 2 = 끝 칸
    if position == 1:
        return None
    own = DIRECTIONS_8.index(direction8_of(mountain))
    return DIRECTIONS_8[(own - 1) % 8 if position == 0 else (own + 1) % 8]
