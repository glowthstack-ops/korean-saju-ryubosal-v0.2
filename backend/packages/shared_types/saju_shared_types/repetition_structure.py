"""반복 구조(천간 반복·지지 반복·자형·같은 간지 기둥) 타입 — 2026-10-27 데굴님 승인.

존재 판정(같은 글자 여부)·설명용 구조 강도·운 활성화를 분리해 담는다. 점수·사건 후보·오행 세력에는
관여하지 않는다(서술 전용). 위치 가중·그룹 강도는 검증 전 가설값이라 설명에만 쓴다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RepetitionKind = Literal["stem", "branch", "pillar"]
ActivationKind = Literal["natal_group_active", "period_new", "luck_luck", "clash_group"]


class RepetitionPair(BaseModel):
    """같은 글자 두 자리의 관계 쌍 — 그룹 안에 전부 보존한다(3개면 3쌍, 4개면 6쌍)."""

    a: str  # 'month'
    b: str  # 'day'
    distance: int  # 기둥 간격(1=인접)
    weight: float  # 위치 가중(인접 1.00·한 칸 건너 0.70·두 칸 건너 0.50 — 가설값)


class RepetitionGroup(BaseModel):
    """원국 반복 그룹 1건 — 같은 글자 n개를 한 그룹으로 묶는다(쌍마다 사건을 세지 않는다)."""

    kind: RepetitionKind
    char: str  # '亥' · '己' · '己巳'
    positions: list[str]  # 원국 자리(year/month/day/hour), 기둥 순
    count: int
    pairs: list[RepetitionPair] = Field(default_factory=list)
    adjacent: bool = False
    is_self_punishment: bool = False  # 辰辰·午午·酉酉·亥亥(지지 반복의 부분 집합)
    structural_strength: float = 0.0  # max(w) + min(0.25, 0.10·(n−2)) — 설명용, 사건 확률 아님
    ten_god: str = ""  # 반복 글자의 일간 기준 십성(지지는 본기)
    element: str = ""
    role: str = ""  # 그 오행의 용희기구한(엔진 판정, 없으면 빈 값)


class RepetitionActivation(BaseModel):
    """운 기둥이 반복 구조를 건드린 기록 1건 — 새 사건이 아니라 구조의 기간 활성화다."""

    kind: ActivationKind
    char: str  # 반복(또는 충 대상) 글자
    luck_char: str  # 운에서 들어온 글자
    layer: str  # 대상 운 층위(daewoon/year/month)
    natal_positions: list[str] = Field(default_factory=list)
    luck_layers: list[str] = Field(default_factory=list)  # luck_luck 일 때 함께 반복된 상위 층위
    is_self_punishment: bool = False
    relation: Literal["same", "clash"] = "same"


__all__ = [
    "ActivationKind",
    "RepetitionActivation",
    "RepetitionGroup",
    "RepetitionKind",
    "RepetitionPair",
]
