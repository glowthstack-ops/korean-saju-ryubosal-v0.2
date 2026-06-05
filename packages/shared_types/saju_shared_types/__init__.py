"""Shared types, enums and constant tables for the Saju v2 engine."""

from __future__ import annotations

from .analysis import (
    FiveElementAnalysis,
    ForceAnalysis,
    RootingAnalysis,
    StrengthResult,
    TenGodAnalysis,
)
from .birth_input import BirthInput, TimeCalculationOptions
from .enums import (
    Branch,
    CalendarType,
    Element,
    HiddenStemType,
    Palace,
    PillarPosition,
    Stem,
    StrengthBand,
    TenGod,
    YinYang,
)
from .manse_result import EngineMetadata, ManseV2Result
from .pillars import FourPillarsResult, HiddenStem, Pillar
from .structure import (
    GeokgukResult,
    StabilityScores,
    StructuralInteraction,
    StructureAnalysis,
    TransformationCheck,
)
from .time_correction import SolarTermBasis, TimeCorrectionResult
from .yongsin import (
    AggregatedYongsinResult,
    ElementCandidate,
    SpecialCaseCheck,
    YongsinCandidateModel,
)

__all__ = [
    "BirthInput",
    "TimeCalculationOptions",
    "Branch",
    "CalendarType",
    "Element",
    "HiddenStemType",
    "Palace",
    "PillarPosition",
    "Stem",
    "StrengthBand",
    "TenGod",
    "YinYang",
    "EngineMetadata",
    "ManseV2Result",
    "FiveElementAnalysis",
    "ForceAnalysis",
    "RootingAnalysis",
    "StrengthResult",
    "TenGodAnalysis",
    "FourPillarsResult",
    "HiddenStem",
    "Pillar",
    "SolarTermBasis",
    "TimeCorrectionResult",
    "GeokgukResult",
    "StabilityScores",
    "StructuralInteraction",
    "StructureAnalysis",
    "TransformationCheck",
    "AggregatedYongsinResult",
    "ElementCandidate",
    "SpecialCaseCheck",
    "YongsinCandidateModel",
]
