"""풍수 형국 · 방향성 지형 어댑터 스텁 (v2.2 P4-5, docs/12 §4-4·§4-5).

외부 지형 원천(산/하천/호수/해안/DEM)이 아직 공급되지 않았다(doc/gis README 한계 — sqlite의
external_feature·region_feature_direction는 0행). 따라서 본 어댑터는 계약(스키마)과 비활성 처리만
제공한다. 핵심 원칙:

- 데이터 0행이면 available=False — 0점 감점이 아니라 missing_layers에만 표시한다(절대원칙 11).
- 방위 오행은 지역 고정 프로필에 저장하지 않는다(§4-4) — 추천 시점 계산하거나 외부 feature로 채운다.
- 실제 feature 매칭(어느 방향에 산/하천)은 외부 데이터 공급 뒤 후속 단계에서 활성화한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from saju_shared_types.region_element import (
    DirectionalFeature,
    DirectionalFeatureResult,
    ElementVector,
    FengshuiFormResult,
)

_FENGSHUI_UNAVAILABLE = "DEM/외부 지형 feature 미공급 — 풍수 형국 판정 보류"
_DIRECTIONAL_UNAVAILABLE = "external_feature/region_feature_direction 0행 — 방향성 지형 보류"


class FengshuiFormAdapter:
    """풍수 형국(배산임수·분지·개활 등) 판정 — DEM 공급 전까지 항상 비활성(P4-B 스텁)."""

    def evaluate(self, region_code: str) -> FengshuiFormResult:
        """available=False만 반환(감점 금지 — missing_layers 표시용, §4-5)."""
        return FengshuiFormResult(
            region_code=region_code,
            available=False,
            reason=_FENGSHUI_UNAVAILABLE,
            signals=[],
            confidence=0.0,
        )


class DirectionalFeatureAdapter:
    """지역 anchor 기준 방향별 외부 지형(산/하천 등) 관계 — feature 데이터 공급 전까지 비활성.

    sqlite_path 지정 시 region_feature_direction 테이블을 읽되, 0행이면 available=False.
    경로 미지정·파일 부재도 graceful(available=False).
    """

    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def evaluate(self, region_code: str) -> DirectionalFeatureResult:
        """region_code의 방향성 지형 관계. 데이터 없으면 available=False(감점 금지)."""
        rows = self._fetch(region_code)
        if not rows:
            return DirectionalFeatureResult(
                region_code=region_code,
                available=False,
                reason=_DIRECTIONAL_UNAVAILABLE,
                features=[],
                directional_element_vector=ElementVector(),
            )
        features = [
            DirectionalFeature(
                feature_type=str(r["feature_type"]),
                feature_name=str(r["feature_name"] or ""),
                distance_m=float(r["distance_m"] or 0.0),
                bearing_deg=float(r["bearing_deg"] or 0.0),
                element_signal={str(r["element_signal"]): float(r["signal_weight"] or 0.0)}
                if r["element_signal"]
                else {},
            )
            for r in rows
        ]
        acc: dict[str, float] = {}
        for feat in features:
            for el, w in feat.element_signal.items():
                acc[el] = acc.get(el, 0.0) + w
        return DirectionalFeatureResult(
            region_code=region_code,
            available=True,
            features=features,
            directional_element_vector=ElementVector.from_map(acc).normalized(),
        )

    def _fetch(self, region_code: str) -> list[sqlite3.Row]:
        """region_feature_direction 조회. 경로 부재·테이블 부재·0행이면 빈 리스트."""
        if self._sqlite_path is None or not self._sqlite_path.exists():
            return []
        con = sqlite3.connect(f"file:{self._sqlite_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute(
                "SELECT feature_type, feature_name, distance_m, bearing_deg, "
                "element_signal, signal_weight FROM region_feature_direction "
                "WHERE region_code = ?",
                (region_code,),
            )
            return cur.fetchall()
        except sqlite3.Error:
            return []
        finally:
            con.close()
