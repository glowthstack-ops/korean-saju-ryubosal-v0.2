"""부(富)/귀(貴) 지향 — 사주가 재물 쪽인가 명예·조직 쪽인가 (v2.2).

'사주가 부로 가느냐 귀로 가느냐'는 사주 풀이의 기본 축이다. 격국 격신 그룹(재격·식상생재→부,
관격·관인상생→귀)과 재성/관성 분포로 **지향(lean)**을 도출한다. 우열·단정이 아니라 '어느 결로
풀리기 쉬운가'이며, 운·선택에 따라 달라질 수 있다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WealthStatusLean(BaseModel):
    """부/귀 지향 축(원국 구조). 우열이 아니라 결의 방향."""

    lean: str  # 부 / 귀 / 부귀겸전 / 뚜렷하지 않음
    geokguk_name: str = ""  # 주격(격국명)
    geokguk_group: str = ""  # 격신 그룹(wealth/officer/output/resource/peer)
    wealth_pct: float = 0.0  # 재성 세력 비중
    officer_pct: float = 0.0  # 관성 세력 비중
    note: str = ""  # 명리 통설 해석(부=실리·전문, 귀=조직·명예) — 단정 아님
    flags: list[str] = Field(default_factory=list)
