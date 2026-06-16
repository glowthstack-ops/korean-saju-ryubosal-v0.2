"""연운 시대 기운(era energy) — 그 해 간지의 명리적 기운 캐릭터 (v2.2).

'개인 사주를 사회운 흐름 안에서 본다'는 기본 관점을 **명리 한정**으로 구현한다 — 그 해 간지의
오행·음양·계절·왕상으로 '올해는 어떤 기운의 해인가'를 개인 풀이 앞에 맥락으로 제공한다.
**경제·시장·채용 같은 시사 예측은 포함하지 않는다**(명리 밖). 키워드는 오행 통설이며 단정 아님.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EraEnergyProfile(BaseModel):
    """그 해(세운) 간지의 명리 기운 캐릭터. 개인 무관·경제 예측 무관."""

    year_ganji: str
    stem_element: str
    branch_element: str
    dominant_element: str  # 그 해 사회 기운의 중심 오행(계절 기운 = 지지 오행)
    season: str  # 봄/여름/가을/겨울/환절기
    yinyang: str  # 양/음/양→음 교차/음→양 교차
    keywords: list[str] = Field(default_factory=list)  # 오행 통설 키워드(단정 아님)
    summary: str = ""
