"""v2.2 분석 엔진군 (오케스트레이터·이벤트·Graph RAG 등).

만세력 엔진(`saju_manse_*`)을 수정하지 않고 그 출력을 신규 엔진이 소비한다.
Phase 0: 어댑터·간지달력 생성기 / Phase 1: 사전 스키마·lint /
Phase 2: Event Graph 빌더·검색 + Event Scoring.
"""

from __future__ import annotations

from .adapter import adapt_manse_chart
from .event_engine_v2 import EventEngineV2, to_legacy_candidate
from .event_scoring import favorability_map, filter_year_candidates
from .ganji_calendar import (
    calendar_entries_from_result,
    relation_hits,
    to_calendar_entry,
)
from .graph_builder import build_event_graph, load_event_graph, save_event_graph
from .graph_retrieval import GraphIndex
from .risk_engine import RawPeriodFacts, RelationFact, RiskEngine, build_raw_period_facts

__all__ = [
    "EventEngineV2",
    "GraphIndex",
    "RawPeriodFacts",
    "RelationFact",
    "RiskEngine",
    "adapt_manse_chart",
    "build_event_graph",
    "build_raw_period_facts",
    "calendar_entries_from_result",
    "favorability_map",
    "filter_year_candidates",
    "load_event_graph",
    "relation_hits",
    "save_event_graph",
    "to_calendar_entry",
    "to_legacy_candidate",
]
