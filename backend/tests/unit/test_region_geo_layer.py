"""지형 레이어 어댑터(P3) 검증 — docs/12 §3-C·§4-1.

외부 지형 데이터 공급 시 physical_geography/landcover_hydro_forest 레이어가 활성화되고, 미공급 시
P1 동작(지형 제외)이 그대로 유지되는지 확인한다. 핵심: 산 지형성(mountain_score)=土,
산림 피복(forest_area_ratio)=木 분리(§4-1).
"""

from __future__ import annotations

from pathlib import Path

from saju_engines.region_element_engine import RegionElementEngine
from saju_shared_types.region_element import (
    DominanceType,
    RegionGeoFeature,
    RegionLevel,
    RegionUnitInput,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _engine() -> RegionElementEngine:
    return RegionElementEngine(_DICTS)


def _emd(code: str = "4011010100", parent: str = "40110") -> RegionUnitInput:
    return RegionUnitInput(
        region_code=code, region_level=RegionLevel.EMD, parent_code=parent,
        full_name_ko="가상시 가상읍", region_name_ko="가상읍",
        anchor_lat=37.5, anchor_lon=127.0,
    )


def _parent_earth(eng: RegionElementEngine) -> object:
    """土 우세 부모 시군구(상속 비교 기준)."""
    sig = RegionUnitInput(
        region_code="40110", region_level=RegionLevel.SIG, parent_code="40",
        full_name_ko="가상시", region_name_ko="가상시", hanja="中區", fallback_elements=["土"],
    )
    return eng.build_profile(sig, None, "v1")


def test_no_geo_keeps_p1_behavior() -> None:
    """지형 미공급이면 부모 상속(P1) 그대로 — 지형 레이어 없음."""
    eng = _engine()
    parent = _parent_earth(eng)
    p = eng.build_profile(_emd(), parent, "v1")  # geo=None
    assert "parent_inheritance" in p.source_layers
    assert "physical_geography" not in p.source_layers
    assert p.element_vector.normalized().as_map()["土"] >= 0.9


def test_geo_activates_layers_and_shifts_vector() -> None:
    """산림·수계 지형 → 木·水로 벡터 이동 + 지형 레이어 활성 + 신뢰도 상승."""
    eng = _engine()
    parent = _parent_earth(eng)
    geo = RegionGeoFeature(
        region_id="4011010100", forest_area_ratio=0.7, water_area_ratio=0.4,
        river_length_density=2.0, source_version="test",
    )
    p = eng.build_profile(_emd(), parent, "v1", geo)
    vec = p.element_vector.normalized().as_map()
    assert "landcover_hydro_forest" in p.source_layers
    assert vec["木"] > 0.2 and vec["水"] > 0.1  # 산림→木, 수계→水
    assert p.confidence > 0.5 and p.dominant_type in (
        DominanceType.SINGLE, DominanceType.COMPOSITE,
    )


def test_geo_blocks_parent_inheritance() -> None:
    """자체 지형 신호가 있으면 부모 상속을 하지 않는다(own_signal 게이트)."""
    eng = _engine()
    parent = _parent_earth(eng)
    geo = RegionGeoFeature(region_id="4011010100", forest_area_ratio=0.8, source_version="t")
    p = eng.build_profile(_emd(), parent, "v1", geo)
    assert "parent_inheritance" not in p.source_layers


def test_mountain_score_is_earth_not_wood() -> None:
    """산 지형성(mountain_score)은 土 — 산림이 아닌 한 木으로 보지 않는다(§4-1 핵심)."""
    eng = _engine()
    geo = RegionGeoFeature(region_id="x", mountain_score=0.8, source_version="t")
    p = eng.build_profile(_emd(), None, "v1", geo)
    vec = p.element_vector.normalized().as_map()
    assert vec["土"] > vec["木"]  # 土 우세(alt 木은 보조)
    assert "physical_geography" in p.source_layers


def test_signal_normalization_bool_and_density() -> None:
    """bool(coast_touch)·density(river) 정규화 — 과대 density도 1.0로 클램프."""
    eng = _engine()
    geo = RegionGeoFeature(
        region_id="x", coast_touch_yn=True, river_length_density=999.0, source_version="t",
    )
    p = eng.build_profile(_emd(), None, "v1", geo)
    vec = p.element_vector.normalized().as_map()
    assert vec["水"] > 0.9  # 해안+하천 → 水 압도


def test_hanja_context_alt_activates_with_geo() -> None:
    """한자 문맥규칙 alt.when — 山은 평소 土, 산림 신호(forest_high) 충족 시 木 보조 가산."""
    eng = _engine()
    base = eng._hanja_layer("山", [], set())  # 지형 신호 없음
    assert base is not None and base.vector.get("木", 0.0) == 0.0  # 土만
    with_forest = eng._hanja_layer("山", [], {"forest_area_ratio_high"})
    assert with_forest is not None and with_forest.vector.get("木", 0.0) > 0.0  # 木 보조


def test_context_alt_active_detects_conditions() -> None:
    """_context_alt_active가 지형 feature로 alt.when 조건을 평가한다."""
    eng = _engine()
    geo = RegionGeoFeature(
        region_id="x", forest_area_ratio=0.6, industrial_ratio=0.3,
        coast_touch_yn=True, source_version="t",
    )
    active = eng._context_alt_active(geo)
    assert "forest_area_ratio_high" in active  # 0.6 >= 0.5
    assert "mineral_or_industrial" in active  # 0.3 >= 0.2
    assert "harbor_industrial" in active  # industrial>=0.1 AND coast
    # 미충족: mountainous(mountain_score 없음)
    assert "mountainous" not in active


def test_build_profiles_with_geo_by_code() -> None:
    """build_profiles가 geo_by_code로 특정 단위만 지형 활성화한다."""
    eng = _engine()
    units = [
        RegionUnitInput(region_code="40", region_level=RegionLevel.CTPRVN,
                        full_name_ko="가상도", region_name_ko="가상도"),
        RegionUnitInput(region_code="40110", region_level=RegionLevel.SIG, parent_code="40",
                        full_name_ko="가상도 가상시", region_name_ko="가상시",
                        hanja="中區", fallback_elements=["土"]),
        _emd(),
    ]
    geo = {"4011010100": RegionGeoFeature(region_id="4011010100", water_area_ratio=0.9,
                                          source_version="t")}
    profiles = {p.region_code: p for p in eng.build_profiles(units, "v1", geo)}
    emd = profiles["4011010100"]
    assert "landcover_hydro_forest" in emd.source_layers
    assert emd.element_vector.normalized().as_map()["水"] > 0.8
