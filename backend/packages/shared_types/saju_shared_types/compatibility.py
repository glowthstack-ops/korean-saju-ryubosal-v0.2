"""두 명식 궁합(宮合) 결과 타입 — 관계운 상대(궁합) 모드.

엔진(compatibility_engine)이 원국A↔원국B의 명리 신호(일주 상호작용·십성 관계·용신
상호보완)를 계산해 채운다. LLM은 이 사실을 솔직하게 서술만 한다(CLAUDE.md 1조 — 계산 금지).
방향(보완/마찰/중립) 배정과 전반 톤은 reviewed:false 초안(전문가 감수 전 미보장).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CompatSignalKind(StrEnum):
    """궁합 신호 종류 — 확정 세트(일주 상호작용 / 십성 관계 / 용신 상호보완)."""

    DAY_STEM_COMBINE = "day_stem_combine"      # 일간 천간합
    DAY_BRANCH_SIX = "day_branch_six"          # 일지 육합
    DAY_BRANCH_CLASH = "day_branch_clash"      # 일지 충
    DAY_BRANCH_PUNISH = "day_branch_punish"    # 일지 형
    DAY_BRANCH_BREAK = "day_branch_break"      # 일지 파
    DAY_BRANCH_HARM = "day_branch_harm"        # 일지 해
    DAY_BRANCH_DUPLICATE = "day_branch_dup"    # 일지 복음(같은 글자)
    TEN_GOD_TO_PARTNER = "ten_god_to_partner"  # 본인 일간 기준 상대 일간의 십성
    TEN_GOD_TO_SELF = "ten_god_to_self"        # 상대 일간 기준 본인 일간의 십성
    TEN_GOD_COMPLEMENT = "ten_god_complement"  # 내게 약한 십성군을 상대가 채워줌(보완 끌림)
    YONGSIN_SUPPORT = "yongsin_support"        # 상대 오행이 본인 용·희신 보완
    YONGSIN_BURDEN = "yongsin_burden"          # 상대 오행이 본인 기·구신 강화
    SINSAL_CHARM = "sinsal_charm"              # 도화·홍염 끌림(보조 — 가볍게)
    SINSAL_FRICTION = "sinsal_friction"        # 원진·귀문 거슬림(보조 — 가볍게)


class CompatDirection(StrEnum):
    """신호가 관계에 작용하는 방향(reviewed:false 배정)."""

    HARMONY = "보완"
    FRICTION = "마찰"
    NEUTRAL = "중립"


class CompatSignal(BaseModel):
    """궁합 신호 1개 — 엔진 계산 사실 + 방향 태그."""

    kind: CompatSignalKind
    label: str  # 한글 신호명(예: '일지 육합')
    detail: str  # 글자 단위 설명(예: '본인 일지 亥 ↔ 상대 일지 寅 육합(化木)')
    direction: CompatDirection
    # 보조 신호(신살 교차 등) — 보완/마찰 카운트·전반 톤에 반영하지 않고 가볍게만 언급.
    auxiliary: bool = False


class CompatibilityReport(BaseModel):
    """두 명식 궁합 분석 결과(원국A↔원국B). 관계운 RP-04·RP-05·RP-08 입력."""

    self_label: str
    partner_label: str
    self_day: str  # 본인 일주 간지(예: '己亥')
    partner_day: str  # 상대 일주 간지
    signals: list[CompatSignal] = Field(default_factory=list)
    harmony_count: int = 0
    friction_count: int = 0
    summary: str = ""  # 전반 톤(보완/마찰 카운트 기반 — reviewed:false 휴리스틱)
    # 끌림(자극) 채널 — 안정(보완/마찰)과 분리. 충·형·도화·홍염·천간합 등 '스파크/매력'의 세기.
    # 궁합 자료: "충·살이 많아도 확 끌릴 수 있다" — 끌림(activation) ≠ 좋은 궁합(안정). 강/중/약.
    attraction_score: int = 0
    attraction_band: str = ""  # 강/중/약 — 빈 문자열이면 미산정
