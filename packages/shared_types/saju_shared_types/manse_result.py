"""Top-level engine result (greenfield index §9, codex §16.1).

The full field set is fixed now so the schema is stable; layers not yet
implemented (force/structure/geokguk/yongsin/luck/calibration) are returned as
``None`` placeholders and filled in later phases.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .analysis import ForceAnalysis
from .luck import LuckCycles
from .pillars import FourPillarsResult
from .structure import GeokgukResult, StructureAnalysis
from .time_correction import SolarTermBasis, TimeCorrectionResult
from .yongsin import AggregatedYongsinResult


class EngineMetadata(BaseModel):
    engine_version: str
    ruleset_version: str
    tzdata_version: str | None = None
    solar_terms_version: str | None = None


class ManseV2Result(BaseModel):
    chart_id: str
    input_summary: dict[str, Any] = Field(default_factory=dict)
    time_correction: TimeCorrectionResult | None = None
    solar_term_basis: SolarTermBasis | None = None
    pillars: FourPillarsResult | None = None

    force_analysis: ForceAnalysis | None = None
    structure_analysis: StructureAnalysis | None = None
    geokguk: GeokgukResult | None = None
    yongsin_analysis: AggregatedYongsinResult | None = None
    luck_cycles: LuckCycles | None = None

    # Filled in later phases — schema slots reserved now.
    calibration: dict[str, Any] | None = None
    traditional_extras: dict[str, Any] | None = None

    metadata: EngineMetadata
    trace: dict[str, Any] = Field(default_factory=dict)
