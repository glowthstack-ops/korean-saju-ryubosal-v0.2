"""지역 오행 엔진(P1) 검증 — 고정 프로필 빌드 + 사용자 매칭 추천(docs/12).

사용자 필수 케이스(2026-06-26):
1. 음운 cap이 0.03을 넘지 않음
2. 한자 매칭 없는 지역이 음운만으로 과확정되지 않음
3. emd 프로필이 5,000개 이상 생성됨(시군구 230 퇴행 방지)
4. emd가 부모 시군구 프로필을 상속함
5. direction이 프로필엔 없고 recommend 단계에서만 들어감(§4-4)
6. 기신 오행 강한 지역이 match_score에서 감점됨
7. 기존 relocation.region_fit() 출력 호환 유지
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.region_element_engine import RegionElementEngine, region_fit_scores
from saju_shared_types.region_element import (
    DominanceType,
    RegionLevel,
    RegionRecommendationQuery,
    RegionResolution,
    RegionUnitInput,
    TargetElements,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_SNAPSHOT = Path(__file__).resolve().parents[2] / "compiled" / "region_element_profiles_v1.json"


def _engine(with_snapshot: bool = False) -> RegionElementEngine:
    return RegionElementEngine(_DICTS, _SNAPSHOT if with_snapshot else None)


def _sig(code: str, name: str, hanja: str | None, fallback: list[str]) -> RegionUnitInput:
    return RegionUnitInput(
        region_code=code, region_level=RegionLevel.SIG, parent_code="11",
        full_name_ko=name, region_name_ko=name.split()[-1],
        hanja=hanja, fallback_elements=fallback, anchor_lat=37.5, anchor_lon=127.0,
    )


# ── 고정 프로필 빌드 ────────────────────────────────────────────


def test_phonetic_cap_not_exceeded() -> None:
    """케이스1 — 한자(token) + 음운 결합 시 음운 기여가 cap(0.03) 이하로 제한된다."""
    eng = _engine()
    # 中區=土 단일 토큰. 음운(중구: ㅈ=金)이 cap를 넘으면 金이 0.03보다 커진다.
    u = _sig("11140", "서울특별시 중구", "中區", ["土"])
    p = eng.build_profile(u, None, "v1")
    vec = p.element_vector.normalized().as_map()
    assert vec["土"] >= 0.95  # 한자 레이어가 0.97 차지
    assert vec["金"] <= 0.03 + 1e-9  # 음운 cap 이하
    assert p.dominant_type is DominanceType.SINGLE and p.dominant_elements == ["土"]


def test_unmatched_hanja_not_overasserted() -> None:
    """케이스2 — 한자 토큰 미매칭(鍾路)은 폴백(weak)까지만, 음운만으로 single 단정 금지."""
    eng = _engine()
    p = eng.build_profile(_sig("11110", "서울특별시 종로구", "鍾路區", ["金"]), None, "v1")
    assert p.dominant_type is DominanceType.WEAK  # 폴백 신뢰도 0.35 → weak(단정 아님)
    assert p.confidence < 0.55
    # 한자·폴백·부모 모두 없는 단위는 음운만 남아 unknown(과확정 금지).
    ct = RegionUnitInput(
        region_code="11", region_level=RegionLevel.CTPRVN,
        full_name_ko="서울특별시", region_name_ko="서울특별시",
    )
    p_ct = eng.build_profile(ct, None, "v1")
    assert p_ct.dominant_type is DominanceType.UNKNOWN
    assert p_ct.source_layers == ["phonetic_layer"]
    assert p_ct.confidence <= 0.25


def test_emd_inherits_parent_sig() -> None:
    """케이스4 — 한자 없는 읍면동은 부모 시군구 벡터를 상속하되 신뢰도가 낮아진다."""
    eng = _engine()
    parent = eng.build_profile(_sig("11140", "서울특별시 중구", "中區", ["土"]), None, "v1")
    emd = RegionUnitInput(
        region_code="1114010100", region_level=RegionLevel.EMD, parent_code="11140",
        full_name_ko="서울특별시 중구 회현동", region_name_ko="회현동",
        anchor_lat=37.55, anchor_lon=126.98,
    )
    child = eng.build_profile(emd, parent, "v1")
    assert "parent_inheritance" in child.source_layers
    assert child.element_vector.normalized().as_map()["土"] >= 0.9  # 부모 土 상속
    assert child.confidence < parent.confidence  # 상속은 신뢰도 감쇠


def test_profile_has_no_direction_fields() -> None:
    """케이스5(절반) — 고정 프로필에는 방위가 없다(§4-4). 좌표(anchor)는 고정 지리값."""
    eng = _engine()
    p = eng.build_profile(_sig("11140", "서울특별시 중구", "中區", ["土"]), None, "v1")
    dumped = p.model_dump()
    assert "direction" not in dumped and "direction_fit" not in dumped
    assert p.anchor_lat is not None  # 좌표는 보관(추천 시점 방위 계산용)


# ── 스냅샷(읍면동 5,065 포함) ────────────────────────────────────


def test_snapshot_emd_count_at_least_5000() -> None:
    """케이스3 — 스냅샷이 읍면동 5,000개 이상을 포함(시군구 230 퇴행 방지)."""
    if not _SNAPSHOT.exists():
        pytest.skip("스냅샷 미빌드 — build_region_profiles.py 먼저 실행")
    meta = json.loads(_SNAPSHOT.with_suffix(".json").read_text("utf-8"))["meta"]
    counts = meta["profile_counts"]
    assert counts["emd"] >= 5000
    assert counts["sig"] == 250 and counts["ctprvn"] == 17


def test_snapshot_roundtrip_and_resolution() -> None:
    """스냅샷 로드 + 해상도별 후보 선별이 동작한다."""
    if not _SNAPSHOT.exists():
        pytest.skip("스냅샷 미빌드")
    eng = _engine(with_snapshot=True)
    assert eng.get_profile("11140") is not None  # 서울 중구 시군구 코드


# ── 가변 추천 ────────────────────────────────────────────────────


def test_match_penalizes_gisin_region() -> None:
    """케이스6 — 기신 오행이 우세한 지역은 match_score가 크게 깎이고 risk_flag가 붙는다."""
    if not _SNAPSHOT.exists():
        pytest.skip("스냅샷 미빌드")
    eng = _engine(with_snapshot=True)
    # 中區는 土 단일 우세 → 土이 기신인 사용자에겐 강한 감점.
    q = RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["水"], gisin=["土"]),
        candidate_regions=["서울특별시 중구"],
        resolution=RegionResolution.SIGUNGU,
    )
    item = eng.recommend(q).recommended_regions[0]
    assert item.match_score <= 20
    assert item.avoid_score >= 50
    assert "gisin_strong" in item.risk_flags


def test_direction_only_when_base_location() -> None:
    """케이스5 — 방위는 base_location이 있을 때만 추천 단계에서 산출된다."""
    if not _SNAPSHOT.exists():
        pytest.skip("스냅샷 미빌드")
    eng = _engine(with_snapshot=True)
    target = TargetElements(yongsin=["水"], huisin=["木"])
    no_base = eng.recommend(RegionRecommendationQuery(
        target_elements=target, candidate_regions=["서울특별시 마포구"],
        resolution=RegionResolution.SIGUNGU,
    )).recommended_regions[0]
    assert no_base.direction == "" and no_base.direction_fit == ""
    with_base = eng.recommend(RegionRecommendationQuery(
        target_elements=target, base_location="서울특별시 강남구",
        candidate_regions=["서울특별시 마포구"], resolution=RegionResolution.SIGUNGU,
    )).recommended_regions[0]
    assert with_base.direction != "" and with_base.direction_fit != ""


def test_score_capped_for_low_confidence() -> None:
    """확신도가 낮은 지역(weak)은 match_score 상한(78/65)을 넘지 못한다."""
    if not _SNAPSHOT.exists():
        pytest.skip("스냅샷 미빌드")
    eng = _engine(with_snapshot=True)
    p = eng.get_profile("11110")  # 종로구(weak, conf≈0.35)
    assert p is not None and p.confidence < 0.40
    # 종로구 우세 金을 용신으로 둬도 conf<0.40 → 최대 65.
    q = RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["金"]),
        candidate_regions=["서울특별시 종로구"], resolution=RegionResolution.SIGUNGU,
    )
    assert eng.recommend(q).recommended_regions[0].match_score <= 65


# ── region_fit 승격 호환(D3) ─────────────────────────────────────


def test_region_fit_scores_legacy_compat() -> None:
    """케이스7 — 승격된 region_fit_scores가 기존 1.0/0.8/0.5 계약을 보존한다."""
    # 동일 1.0 / 용신을 생(生) 0.8 / 그 외 0.5 / 미등재 0.5.
    repr_map = {"A": "水", "B": "金", "C": "木"}
    out = region_fit_scores(repr_map, ["A", "B", "C", "Z"], {"본인": "水"})
    assert out["A"] == 1.0  # 水 == 용신 水
    assert out["B"] == 0.8  # 金 → 水 생(生)
    assert out["C"] == 0.5  # 木 무관
    assert out["Z"] == 0.5  # 미등재 중립


def test_relocation_region_fit_delegates() -> None:
    """relocation.region_fit() 래퍼가 엔진 승격본과 동일 결과를 낸다."""
    from saju_engines.relocation import RelocationResolver

    resolver = RelocationResolver(_DICTS)
    regions = resolver.known_regions()[:5]
    yong = {"본인": "土"}
    assert resolver.region_fit(regions, yong) == region_fit_scores(
        resolver._region_element, regions, yong
    )
