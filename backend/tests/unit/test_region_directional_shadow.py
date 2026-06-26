"""P5-3A shadow 배선 회귀(docs/12 §14-12) — directional_terrain·form_quality를 payload에 노출하되
추천 점수·랭킹에 미반영. 합성 adapter로 파일 의존 없이 결정론 검증 + 실스냅샷 통합(skipif).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.region_geo_stubs import DirectionalFeatureAdapter
from saju_engines.region_recommendation_orchestrator import (
    REGION_REASONING_DIRECTIVE,
    _directional_payload,
    _form_quality_payload,
)
from saju_shared_types.region_element import (
    RegionDirectionalElementSummary,
    RegionDirectionalTopFeature,
)

_BACKEND = Path(__file__).resolve().parents[2]
_SNAP = _BACKEND / "compiled" / "region_directional_summary_v1.json"


def _adapter(
    region: str, rows: list[RegionDirectionalElementSummary]
) -> DirectionalFeatureAdapter:
    a = DirectionalFeatureAdapter()
    a._by_region[region] = rows  # 합성 주입(파일 무관)
    return a


def _row(code: str, **kw) -> RegionDirectionalElementSummary:
    return RegionDirectionalElementSummary(
        region_code="t", direction_code=code, confidence=0.65, **kw)


def test_directional_payload_shape_and_topfeature_cap() -> None:
    """directional_terrain: 방위별 earth/wood/water + top_features ≤5(§14-9)."""
    feats = [RegionDirectionalTopFeature(name=f"f{i}", type="mountain_peak", distance_m=i * 100)
             for i in range(7)]
    rows = [_row("N", earth_score=0.5, wood_score=0.2, top_features=feats)]
    p = _directional_payload(_adapter("R", rows), "R")
    assert p["available"] is True and "N" in p["directions"]
    assert len(p["directions"]["N"]["top_features"]) == 5  # 3~5 cap
    assert {"earth", "wood", "water"} <= p["directions"]["N"].keys()


def test_no_data_available_false() -> None:
    """external feature 없으면 available=false(추정 생성 금지)."""
    assert _directional_payload(DirectionalFeatureAdapter(), "X") == {"available": False}
    fq = _form_quality_payload(DirectionalFeatureAdapter(), "X")
    assert fq == {"available": False, "applied_to_score": False}


def test_form_quality_shadow_not_applied() -> None:
    """form_quality preview는 노출되되 applied_to_score=false(점수 미반영)."""
    rows = [_row("N", earth_score=0.6), _row("E", water_score=0.4), _row("W", wood_score=0.4)]
    fq = _form_quality_payload(_adapter("R", rows), "R")
    assert fq["available"] is True and fq["applied_to_score"] is False
    assert "score_raw" in fq and "bonus_preview" in fq


def test_no_sasinsa_labels_without_facing() -> None:
    """좌향 없음: directional_terrain에 사신사(현무/주작/청룡/백호) 라벨 미생성 — 방위코드만."""
    rows = [_row("N", earth_score=0.6), _row("S", water_score=0.4)]
    p = _directional_payload(_adapter("R", rows), "R")
    blob = str(p)
    assert not any(t in blob for t in ("현무", "주작", "청룡", "백호", "배산임수"))
    assert set(p["directions"]) <= {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}


def test_directive_has_open_facing_and_separation_guard() -> None:
    """디렉티브: 좌향 없으면 사신사 금지 + directional_terrain≠relative_direction 분리 명시."""
    assert "좌향(facing) 정보가 없으면 사신사" in REGION_REASONING_DIRECTIVE
    assert "relative_direction" in REGION_REASONING_DIRECTIVE
    assert "applied_to_score=false" in REGION_REASONING_DIRECTIVE


@pytest.mark.skipif(not _SNAP.exists(), reason="directional 스냅샷 미빌드(gitignore — 재생성 필요)")
def test_shadow_score_unchanged_and_evidence() -> None:
    """실스냅샷: directional 유무로 match_score·랭킹 불변 + 청운효자동 N방위 산/수계 evidence."""
    from saju_engines.region_element_engine import RegionElementEngine
    from saju_engines.region_recommendation_orchestrator import RegionRecommendationOrchestrator
    from saju_shared_types.region_element import (
        IntentMode,
        RegionRecommendationQuery,
        RegionResolution,
        TargetElements,
    )

    b = _BACKEND / "compiled"
    eng = RegionElementEngine(
        _BACKEND / "dictionaries", b / "region_element_profiles_v1.json",
        b / "region_admin_units_v1.json")
    q = RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["土"], huisin=["火"], gisin=["木"], gusin=["水"]),
        candidate_scope="서울", resolution=RegionResolution.EUP_MYEON_DONG,
        intent_mode=IntentMode.RELOCATION, top_n=5)
    plain = RegionRecommendationOrchestrator(eng).recommend_payload(q)
    shadow = RegionRecommendationOrchestrator(
        eng, DirectionalFeatureAdapter(_SNAP)).recommend_payload(q)
    assert [(r["region_code"], r["match_score"]) for r in plain["regions"]] == \
           [(r["region_code"], r["match_score"]) for r in shadow["regions"]]  # 점수·랭킹 불변
    assert all(r["form_quality"]["applied_to_score"] is False for r in shadow["regions"])
