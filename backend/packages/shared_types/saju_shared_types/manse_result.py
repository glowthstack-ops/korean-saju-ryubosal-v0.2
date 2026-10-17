"""Top-level engine result (greenfield index §9, codex §16.1).

The full field set is fixed now so the schema is stable; layers not yet
implemented (force/structure/geokguk/yongsin/luck/calibration) are returned as
``None`` placeholders and filled in later phases.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .analysis import ForceAnalysis
from .calibration import CalibrationQuestionSet
from .hour_unknown import HourUnknownAnalysis
from .luck import LuckCycles
from .pillars import FourPillarsResult
from .sinsal import TraditionalExtras
from .structure import GeokgukResult, StructureAnalysis
from .structure_patterns import DetectedPattern
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
    calibration: CalibrationQuestionSet | None = None
    traditional_extras: TraditionalExtras | None = None
    #: 출생시간 미상 분석(12시진 후보 비교·범위·경고) — 시간이 있으면 None(2026-10-06).
    hour_unknown: HourUnknownAnalysis | None = None
    #: 원국 구조 배합(상관생재·재다신약·재극인 등) — 만세력 화면 노출용 선별본
    #: (`select_manse_display_patterns`). 길흉 미확정 구조 라벨이며 점수에 관여하지 않는다
    #: (2026-10-17).
    structure_patterns: list[DetectedPattern] | None = None

    metadata: EngineMetadata
    trace: dict[str, Any] = Field(default_factory=dict)
