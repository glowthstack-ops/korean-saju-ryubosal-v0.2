"""원국 횡재 그릇(natal wealth capacity) — 재물·횡재 발현의 '그릇' 구조 (v2.2 Phase 1).

운(발동)과 분리된 **원국 자체의 잠재력**만 본다. 단일 사례(로또 당첨 사주)에서 도출한 가설
구조이며, 같은 구조가 비당첨자에게도 흔하다는 전제(확증편향 차단) 아래 reviewed 전 가설로
다룬다. 실제 점수 가산은 운 발동(Phase 2 — 申子辰 완성·辰戌충 개고 등)과 결합해 회귀·캘리브
레이션으로 확정한다(절대원칙 5). 본 모델은 그 '그릇' 판정만 담는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CapacityBand = Literal["strong", "moderate", "weak"]


class WealthCapacity(BaseModel):
    """원국 횡재 그릇 판정(운 발동과 분리). 모든 플래그는 원국만으로 결정된다."""

    wealth_element: str  # 재성 오행(일간이 극하는 오행 — 戊土→水)
    body_can_hold: bool  # 身強임재 — 신강 계열 + 재성 존재(큰돈을 쥘 그릇)
    visible_wealth_stem: bool  # 재성(편재/정재) 천간 투출
    wealth_rooted: bool  # 재성이 지지 본기/지장간에 뿌리(실체성)
    hidden_output: bool  # 식상이 천간엔 없고 지장간에 잠복(식상생재 잠재 통로)
    wealth_trine_seed: bool  # 재성 오행 삼합 글자 원국 보유(재성국 씨앗)
    storage_repeat: bool  # 동일 묘고(辰戌丑未) 지지 반복(충개고 잠재)
    capacity_band: CapacityBand  # 종합 그릇 강도(strong/moderate/weak)
    flags: list[str] = Field(default_factory=list)  # 성립 플래그 한글 라벨(서술용)
