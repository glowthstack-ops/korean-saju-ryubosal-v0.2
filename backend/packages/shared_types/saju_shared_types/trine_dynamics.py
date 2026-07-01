"""삼합국 관계 역학 결과 schema (Trine Dynamics, P1, 2026-07-01, shadow-only).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §5. 두 사람의 **년지(띠) 삼합국** 오행을 생극으로 비교한
관계 역학이다. **위/아래·승패·서열이 아니라 오행 생극 경향**으로만 쓴다. v1은 **shadow-only** —
결과만 생성하고 chat/report 렌더 연결·점수 반영은 하지 않는다(검증 후 v2에서 승급 검토).
"""

from __future__ import annotations

from pydantic import BaseModel


class TrineDynamics(BaseModel):
    """두 사람 삼합국(년지 기준)의 오행 생극 관계 역학 1건(shadow).

    Attributes:
        base_group / target_group: 삼합국 표시명(예: '亥卯未').
        base_element / target_element: 삼합국 오행(木/火/土/金/水 — 삼합은 木火金水만).
        relation: 생극 관계 — same_group | generates_target(내가 상대 生) |
            generated_by_target(상대가 나 生) | controls_target(내가 상대 克) |
            controlled_by_target(상대가 나 克).
        dynamics_label: 관계 역학 라벨(편안/지원/끌림·받음/주도/부담·긴장).
        reading: 중립 관계 역학 문구.
        exposure: 노출 등급 — v1은 항상 'shadow'(렌더 미연결).
    """

    base_group: str
    base_element: str
    target_group: str
    target_element: str
    relation: str
    dynamics_label: str
    reading: str
    exposure: str = "shadow"
