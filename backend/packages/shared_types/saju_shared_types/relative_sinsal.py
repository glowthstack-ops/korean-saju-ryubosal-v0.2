"""12신살 상대위치 결과 schema (Relative Sinsal, P2, 2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §4. 기준 지지(년지=사회 / 일지=친밀)를 삼합국 기준으로 삼아
상대 지지가 어느 12신살 위치에 놓이는지 계산한 결과다. **단일 글자살·일반 신살 카탈로그와 구분**
하며, 관계 역학 경향(설명)으로만 쓰고 점수·판정을 변경하지 않는다(explanation-first).
"""

from __future__ import annotations

from pydantic import BaseModel


class RelativeSinsalResult(BaseModel):
    """기준 지지 대비 상대 지지의 12신살 상대위치 1건.

    Attributes:
        base_branch: 기준 지지(예: '亥').
        target_branch: 상대 지지(예: '卯').
        sinsal: 12신살명(겁살/재살/천살/지살/연살/월살/망신/장성/반안/역마/육해/화개 계열).
        tier: 노출 등급 — 'expose'(노출) | 'movement'(이동계 노출) | 'internal'(약노출·내부).
        relationship_reading: 중립 관계 역학 문구(internal이면 빈 문자열).
        confidence: 신뢰도 라벨('medium' 기본).
    """

    base_branch: str
    target_branch: str
    sinsal: str
    tier: str
    relationship_reading: str = ""
    confidence: str = "medium"
