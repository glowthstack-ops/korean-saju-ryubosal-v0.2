"""도화(桃花) 구조 판정 결과 — 원국 기준 (2026-10-13 데굴님 확정 정비 기준).

정비 원칙: **글자 보유와 도화 성립을 구분하고, 검증된 판정만 풀이에 연결한다.**

- 사정지(가도화): 子午卯酉 글자 보유 표지. 개성·자기주장 성향으로만 설명하며 도화 성립이나
  이성적 매력의 직접 근거로 쓰지 않는다(내부 명칭 '사정지' 유지).
- 진도화: 연지·일지 삼합국 기준 상대 12신살 년살이 원국 자리에 성립. 기준 지지와 성립
  자리를 함께 기록.
- 월담도화: 시지에 진도화가 성립한 경우(진도화의 위치 하위 유형 — 별도 매력 가산 금지).
  시주 미상이면 미확정.
- 나체도화: 제시 목록의 근거가 통일되지 않아 **판정 보류**(이 모델에 필드를 두지 않는다).
- 십성 조합: 도화가 성립한 지지의 본기를 일간 기준 십성으로 계산해 5군으로 분류, 자리마다 기록.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DohwaTenGodGroup(StrEnum):
    """도화 성립 지지 본기의 십성군. 표기는 '{군}도화'(관성도화·인성도화 등)."""

    PEER = "비겁"
    OUTPUT = "식상"
    WEALTH = "재성"
    OFFICER = "관성"
    RESOURCE = "인성"


PillarSlot = Literal["year", "month", "day", "hour"]


class DohwaBase(BaseModel):
    """진도화의 기준 지지 — 어느 자리(연지/일지)의 어떤 글자 삼합국에서 나왔는가."""

    slot: Literal["year", "day"]
    branch: str  # 기준 지지(한자)
    trine: str  # 삼합국 라벨('申子辰')


class DohwaEstablishment(BaseModel):
    """진도화 성립 1건 — 원국의 한 자리."""

    position: PillarSlot
    branch: str  # 도화가 성립한 지지(子午卯酉 중 하나)
    bases: list[DohwaBase] = Field(min_length=1)  # 두 기준이 겹치면 둘 다
    ten_god: str  # 성립 지지 본기의 십성(일간 기준)
    group: DohwaTenGodGroup
    wolldam: bool = False  # 시지 성립 = 월담도화(하위 유형 표시일 뿐 별도 가산 없음)

    @property
    def group_label(self) -> str:
        """'식상도화'·'관성도화' 형태 표기."""
        return f"{self.group.value}도화"


class SajeongMarker(BaseModel):
    """사정지(가도화) — 子午卯酉 보유 표지 1건. 도화 성립 아님."""

    position: PillarSlot
    branch: str


class DohwaProfile(BaseModel):
    """원국 도화 구조(운 미반영)."""

    established: list[DohwaEstablishment] = Field(default_factory=list)
    sajeong_markers: list[SajeongMarker] = Field(default_factory=list)
    # 월담도화 — 시지 진도화. 시주 미상이면 undetermined(없음으로 단정하지 않는다).
    wolldam_status: Literal["established", "not_established", "undetermined"] = "not_established"
    hour_known: bool = True

    @property
    def has_established(self) -> bool:
        """진도화가 원국 어느 자리에든 성립했는가."""
        return bool(self.established)
