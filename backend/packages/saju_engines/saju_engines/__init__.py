"""v2.2 분석 엔진군 (오케스트레이터·이벤트·Graph RAG 등).

만세력 엔진(`saju_manse_*`)을 수정하지 않고 그 출력을 신규 엔진이 소비할 수 있도록
어댑터·간지달력 생성기를 제공한다. Phase 0(T0.3·T0.4) 범위.
"""

from __future__ import annotations

from .adapter import adapt_manse_chart
from .ganji_calendar import (
    calendar_entries_from_result,
    relation_hits,
    to_calendar_entry,
)

__all__ = [
    "adapt_manse_chart",
    "calendar_entries_from_result",
    "relation_hits",
    "to_calendar_entry",
]
