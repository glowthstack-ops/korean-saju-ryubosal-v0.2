"""풍수 형국 · 방향성 지형 어댑터 (v2.2 P4-5·P4-Data, docs/12 §4-4·§4-5).

- DirectionalFeatureAdapter: '지역 주변 어느 방향에 산/물'을 compiled 방향성 요약
  (region_directional_summary, build_region_directional_summary.py 산출)에서 읽는다. 외부 지형
  feature가 공급돼 요약이 빌드되면 available=True, 아니면 available=False(감점 금지·missing 표시).
- FengshuiFormAdapter: 배산임수·분지 등 형국은 DEM 필요(3차 고도화) → 현재 스텁(available=False).

핵심 원칙: 데이터 없으면 0점 감점이 아니라 missing 표시(절대원칙 11). 방위 오행은 지역 고정 프로필에
저장하지 않고 별도 summary로 둔다(§4-4).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from saju_shared_types.region_element import (
    DirectionalFeature,
    DirectionalFeatureResult,
    ElementVector,
    FengshuiFormResult,
    RegionDirectionalElementSummary,
    RegionDirectionalSummarySnapshot,
)

_FENGSHUI_UNAVAILABLE = "DEM/외부 지형 feature 미공급 — 풍수 형국 판정 보류"
_DIRECTIONAL_UNAVAILABLE = "방향성 지형 요약 미빌드(external_geo_feature 미공급) — 보류"
_SCORE_KEYS = (("木", "wood_score"), ("火", "fire_score"), ("土", "earth_score"),
               ("金", "metal_score"), ("水", "water_score"))


class FengshuiFormAdapter:
    """풍수 형국(배산임수·분지·개활 등) 판정 — DEM 공급 전까지 항상 비활성(스텁)."""

    def evaluate(self, region_code: str) -> FengshuiFormResult:
        """available=False만 반환(감점 금지 — missing_layers 표시용, §4-5)."""
        return FengshuiFormResult(
            region_code=region_code, available=False,
            reason=_FENGSHUI_UNAVAILABLE, signals=[], confidence=0.0,
        )


class DirectionalFeatureAdapter:
    """읍면동 주변 방향성 지형(산/하천/해안 등)을 compiled 요약에서 조회(P4-Data).

    summary_path 미지정·부재면 모든 지역 available=False(graceful). 요약 빌드 시 available=True.
    """

    def __init__(self, summary_path: Path | None = None) -> None:
        self._by_region: dict[str, list[RegionDirectionalElementSummary]] = defaultdict(list)
        if summary_path is not None and summary_path.exists():
            snap = RegionDirectionalSummarySnapshot.model_validate_json(
                summary_path.read_text("utf-8")
            )
            for s in snap.items:
                self._by_region[s.region_code].append(s)

    def by_direction(self, region_code: str) -> list[RegionDirectionalElementSummary]:
        """region_code의 방위별 요약(없으면 빈 리스트)."""
        return self._by_region.get(region_code, [])

    def evaluate(self, region_code: str) -> DirectionalFeatureResult:
        """방향성 지형 종합. 요약 없으면 available=False(감점 금지)."""
        rows = self._by_region.get(region_code)
        if not rows:
            return DirectionalFeatureResult(
                region_code=region_code, available=False,
                reason=_DIRECTIONAL_UNAVAILABLE, features=[],
                directional_element_vector=ElementVector(),
            )
        acc: dict[str, float] = defaultdict(float)
        scored: list[tuple[float, DirectionalFeature]] = []
        for row in rows:
            for hanja, key in _SCORE_KEYS:
                acc[hanja] += getattr(row, key)
            for tf in row.top_features:
                scored.append((
                    tf.influence,
                    DirectionalFeature(
                        feature_type=tf.type, feature_name=tf.name,
                        direction_code=row.direction_code, distance_m=tf.distance_m,
                    ),
                ))
        scored.sort(key=lambda t: -t[0])
        return DirectionalFeatureResult(
            region_code=region_code, available=True, reason="",
            features=[f for _, f in scored[:8]],
            directional_element_vector=ElementVector.from_map(acc).normalized(),
        )
