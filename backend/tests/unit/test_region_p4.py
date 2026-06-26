"""지역 오행 엔진 P4-A(서비스 연결부) + P4-B(스텁) 검증 — docs/12 §6·§7·§9.

P4-1 의도별 가중 치환, P4-2 evidence/fit_summary/missing_layers, P4-3 오케스트레이션 payload,
P4-4 택일 bridge, P4-5 풍수/방향성 스텁(available=False, 감점 금지).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.region_element_engine import RegionElementEngine
from saju_engines.region_geo_stubs import DirectionalFeatureAdapter, FengshuiFormAdapter
from saju_engines.region_recommendation_orchestrator import (
    RegionRecommendationOrchestrator,
    resolve_intent_mode,
    to_taekil_context,
)
from saju_shared_types.region_element import (
    IntentMode,
    RegionRecommendationQuery,
    RegionResolution,
    TargetElements,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_PROFILES = _BACKEND / "compiled" / "region_element_profiles_v1.json"
_ADMIN = _BACKEND / "compiled" / "region_admin_units_v1.json"

_needs_snapshot = pytest.mark.skipif(
    not (_PROFILES.exists() and _ADMIN.exists()), reason="스냅샷 미빌드"
)


def _engine() -> RegionElementEngine:
    return RegionElementEngine(_DICTS, _PROFILES, _ADMIN)


# ── P4-1 의도별 가중 치환 ────────────────────────────────────────


def test_intent_weights_differ_and_renormalize() -> None:
    """의도별 preset이 다르고, 미공급 레이어는 제외 후 재정규화(합 1)·phonetic cap 유지."""
    eng = RegionElementEngine(_DICTS)
    avail = {"hanja_place_name", "phonetic_reading", "relative_direction"}
    reloc, miss_r = eng.resolve_intent_weights(IntentMode.RELOCATION, avail)
    healing, _ = eng.resolve_intent_weights(IntentMode.HEALING, avail)
    _, miss_c = eng.resolve_intent_weights(IntentMode.CAREER, avail)
    assert abs(sum(reloc.values()) - 1.0) < 1e-6
    assert reloc["phonetic_reading"] == 0.03  # cap 유지
    assert reloc["relative_direction"] > healing["relative_direction"]  # 이사(0.15)>치유(0.07)
    # career는 modern_activity/transport_access가 missing.
    assert "modern_activity" in miss_c and "transport_access" in miss_c
    assert "fengshui_form" in miss_r


def test_intent_weights_missing_not_penalized() -> None:
    """미공급 레이어가 있어도 가중 합은 1 — 0점 감점이 아니라 재정규화(절대원칙 11)."""
    eng = RegionElementEngine(_DICTS)
    weights, missing = eng.resolve_intent_weights(
        IntentMode.HEALING, {"hanja_place_name", "phonetic_reading"}
    )
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert set(missing) >= {"physical_geography", "landcover_hydro_forest", "fengshui_form"}


def test_resolve_intent_mode_aliases() -> None:
    """파서 라벨 → IntentMode(별칭·미상 GENERAL)."""
    assert resolve_intent_mode("이사") is IntentMode.RELOCATION
    assert resolve_intent_mode("work_business") is IntentMode.CAREER
    assert resolve_intent_mode("휴식") is IntentMode.HEALING
    assert resolve_intent_mode(None) is IntentMode.GENERAL
    assert resolve_intent_mode("뜬금없는라벨") is IntentMode.GENERAL


# ── P4-2 evidence/fit_summary/missing_layers ─────────────────────


@_needs_snapshot
def test_explanation_fit_summary_and_missing() -> None:
    """기신 강한 지역은 negative, 용신 지역은 positive — missing_layers는 score 미감점."""
    eng = _engine()
    res = eng.recommend(RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["水"], gisin=["土"]),
        candidate_regions=["서울특별시 마포구", "서울특별시 중구"],
        resolution=RegionResolution.SIGUNGU, intent_mode=IntentMode.RELOCATION,
    ))
    by_name = {ex.full_name_ko: ex for ex in res.explanations}
    mapo = by_name["서울특별시 마포구"]
    junggu = by_name["서울특별시 중구"]
    assert any(f.role == "용신" for f in mapo.fit_summary.positive)  # 水 용신
    assert any(f.role == "기신" for f in junggu.fit_summary.negative)  # 土 기신
    # 미공급 레이어가 표시되지만 match_score는 P2와 동일(감점 아님).
    assert mapo.match_score == 92 and junggu.match_score == 0
    assert any(m.layer == "physical_geography" for m in mapo.missing_layers)
    assert mapo.evidence  # 레이어 근거 존재


@_needs_snapshot
def test_profile_vector_unchanged_by_intent() -> None:
    """intent는 explanation/missing에만 영향 — 고정 프로필 벡터·dominant는 불변(criteria 1)."""
    eng = _engine()
    p = eng.get_profile("11440")  # 서울 마포구
    assert p is not None
    base = p.element_vector.as_map()
    for im in (IntentMode.RELOCATION, IntentMode.CAREER, IntentMode.HEALING):
        res = eng.recommend(RegionRecommendationQuery(
            target_elements=TargetElements(yongsin=["水"]),
            candidate_regions=["서울특별시 마포구"],
            resolution=RegionResolution.SIGUNGU, intent_mode=im,
        ))
        assert res.explanations[0].element_vector.as_map() == base


# ── P4-3 오케스트레이션 payload ──────────────────────────────────


@_needs_snapshot
def test_orchestrator_payload_has_evidence_and_missing() -> None:
    """payload에 regions·fit_summary·missing_layers·directive 포함, LLM 계산 금지 지침."""
    orch = RegionRecommendationOrchestrator(_engine())
    q = orch.build_query(
        intent_mode=resolve_intent_mode("이사"),
        roles={"yongsin": ["水"], "gisin": ["土"]},
        base_location="서울특별시 강남구",
        candidate_scope="제주", resolution=RegionResolution.SIGUNGU, top_n=3,
    )
    payload = orch.recommend_payload(q)
    assert payload["intent"] == "relocation"
    assert "계산" in payload["directive"]  # 계산 금지 지침
    assert payload["regions"]
    first = payload["regions"][0]
    assert "fit_summary" in first and "missing_layers" in first
    assert "element_vector" in first and "match_score" in first


# ── P4-4 택일 bridge ─────────────────────────────────────────────


@_needs_snapshot
def test_taekil_bridge_serializes_candidate() -> None:
    """추천 1건 → RegionTaekilContext(지역=어디, 택일=언제 역할 분리). 방위 오행 채움."""
    eng = _engine()
    res = eng.recommend(RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["水"]),
        base_location="서울특별시 강남구",
        candidate_regions=["서울특별시 마포구"], resolution=RegionResolution.SIGUNGU,
    ))
    item = res.recommended_regions[0]
    ctx = to_taekil_context(
        item, region_code="11440", event_type="relocation",
        date_range={"start": "2026-07-01", "end": "2026-09-30"},
    )
    assert ctx.event_type == "relocation"
    assert ctx.target_region.region_code == "11440"
    assert ctx.target_region.match_score == item.match_score
    assert ctx.date_range["start"] == "2026-07-01"
    if item.direction:  # 방위 있으면 구성 오행 채움
        assert ctx.target_region.direction_elements


# ── P4-5 풍수/방향성 스텁 ────────────────────────────────────────


def test_fengshui_stub_unavailable_not_penalized() -> None:
    """DEM 미공급 → available=False·confidence 0(감점 아님, missing 표시용)."""
    res = FengshuiFormAdapter().evaluate("11110101")
    assert res.available is False and res.confidence == 0.0 and res.signals == []
    assert "미공급" in res.reason


def test_directional_stub_unavailable_when_no_data() -> None:
    """external_feature/region_feature_direction 부재·0행 → available=False(graceful)."""
    # sqlite 경로 미지정 → 비활성.
    res = DirectionalFeatureAdapter().evaluate("11110101")
    assert res.available is False and res.features == []
    # 실제 sqlite(0행) 지정해도 available=False여야 한다.
    sqlite_path = _BACKEND.parent / "doc" / "gis" / "region_spatial_engine_p0_20230729.sqlite"
    if sqlite_path.exists():
        res2 = DirectionalFeatureAdapter(sqlite_path).evaluate("11110101")
        assert res2.available is False  # region_feature_direction 0행
