"""대운 발현 진행(progression) 프로필 — 서술 전용 inert 레이어 출력 계약 (2026-07-21 데굴님 확정).

"전반 0-4년 천간 / 후반 5-9년 지지" 하드 이분 서술을 대체한다. 천간(계기·드러남)이
상대적으로 먼저 인식되고 지지(현실 기반·정착)가 누적·구체화되는 **기본 그라데이션 prior**를
전제로, 원국과의 충·형·합국·공망 발동·천간 작동성(통근/합거)이 그 순서를 뒤집는 예외를
모드로 요약한다. 근거: doc/v2_2/DAEWOON_PROGRESSION_NARRATIVE.md.

불변식(narrative_only): 사건 생성·점수·길흉·confidence·후보 수·시점을 절대 변경하지 않는다.
resolver는 luck_cycles가 이미 계산한 신호만 읽으며, 어떤 명리 판정도 재계산하지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProgressionMode = Literal[
    "default_gradient",  # 기본 prior — 계기 선인식 → 현실화 누적(경계 연차 없음)
    "branch_early_activation",  # 지지 즉시 발동 — 핵심 궁위 충·형/합국 완성/공망 충발
    "stem_persistent",  # 천간 지속 — 통근·미합거로 외부 주제가 전 기간 반복 가능
    "coactivated",  # 천간·지지 동시 발현 — 간여지동 또는 조기 발동+천간 작동
    "weak_manifestation",  # 약발현 — 천간 무근·합거 + 지지 공망 등, 명분에 머물 수 있음
    "indeterminate",  # 단정 불가 — 상충 신호, 세운·월운 발동 확인 권고
]


class DaewoonProgressionProfile(BaseModel):
    """대운 1개의 발현 진행 모드 — usage는 항상 narrative_only(점수·판정 개입 금지)."""

    daewoon_index: int
    ganji: str
    start_age: int
    mode: ProgressionMode = "default_gradient"
    # 판정 근거 코드(내부 식별·테스트용). 예: BRANCH_CLASH_DAY_PALACE, SAMHAP_COMPLETE,
    # VOID_ACTIVATED_BY_CLASH, GANYEOJIDONG, STEM_ROOTED_IN_LUCK_BRANCH, STEM_NO_ROOT,
    # STEM_COMBINED_AWAY.
    reason_codes: list[str] = Field(default_factory=list)
    usage: Literal["narrative_only"] = "narrative_only"
