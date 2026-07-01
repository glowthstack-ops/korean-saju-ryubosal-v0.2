"""궁위 관계망 schemas (Palace Relationship Network, P3, 2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §3. 연·월·일·시 궁위 간 합충형파해원진과 궁위 공망을
**설명 context 레이어**로 표현한다. 점수·confidence·후보를 변경하지 않으며(inert), 구체 발현
(조부모 육아·공공사업 등)은 질문 intent가 맞을 때만 조건부로 노출한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PalacePairRelation(BaseModel):
    """두 궁위 사이의 관계 1건 — 관계질 라벨(P4) 키와 한글 관계명·해당 지지쌍.

    Attributes:
        palace_a / palace_b: 궁위 코드('year'|'month'|'day'|'hour').
        role_a / role_b: 궁위 역할 한글 라벨.
        relation: 관계질 라벨 키('hap'|'chung'|'hyeong'|'pa'|'hae'|'wonjin').
        relation_ko: 한글 관계명('육합'|'반합'|'충'|'형'|'파'|'해'|'원진').
        branches: 지지쌍 표시(예: '卯↔酉').
    """

    palace_a: str
    palace_b: str
    role_a: str
    role_b: str
    relation: str
    relation_ko: str
    branches: str


class PalaceNetwork(BaseModel):
    """궁위 관계망 종합 — 궁위 쌍 관계 + 공망 궁위(운 미반영, 원국 구조)."""

    pairs: list[PalacePairRelation] = Field(default_factory=list)
    gongmang_palaces: list[str] = Field(default_factory=list)  # 공망인 궁위 코드
