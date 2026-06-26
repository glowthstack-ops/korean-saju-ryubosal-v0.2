"""지역 이름 해소기 + scope(P2) 검증 — docs/12 §2·§3-A.

읍면동명 전국 중복(효자동·사직동 등) 환경에서 모호하면 추측하지 않고 후보를 반환하는지,
시도/수도권 scope 후보 열거가 맞는지, recommend()가 해소기로 배선되는지 확인한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.region_element_engine import RegionElementEngine, RegionNameResolver
from saju_shared_types.region_element import (
    RegionAdminSnapshot,
    RegionLevel,
    RegionRecommendationQuery,
    RegionResolution,
    TargetElements,
)

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries"
_PROFILES = _BACKEND / "compiled" / "region_element_profiles_v1.json"
_ADMIN = _BACKEND / "compiled" / "region_admin_units_v1.json"

_needs_admin = pytest.mark.skipif(
    not _ADMIN.exists(), reason="admin 스냅샷 미빌드 — build_region_admin.py 먼저 실행"
)


def _resolver() -> RegionNameResolver:
    admin = RegionAdminSnapshot.model_validate_json(_ADMIN.read_text("utf-8"))
    return RegionNameResolver(admin.items)


@_needs_admin
def test_resolve_exact_and_alias() -> None:
    """완전일치·약식 시도명·유일 단일명은 모두 같은 코드로 해소된다."""
    r = _resolver()
    code, amb = r.resolve("서울특별시 마포구")
    assert code == "11440" and amb == []
    assert r.resolve("서울 마포구")[0] == "11440"  # 약식 시도
    assert r.resolve("마포구")[0] == "11440"  # 유일 leaf
    assert r.resolve("서울 종로구 청운동")[0] == "11110101"


@_needs_admin
def test_resolve_ambiguous_returns_candidates_not_guess() -> None:
    """전국 중복명은 추측하지 않고 후보 목록을 반환한다(절대원칙 7)."""
    r = _resolver()
    code, candidates = r.resolve("중구")  # 6개 시 중구
    assert code is None
    assert len(candidates) >= 5 and "서울특별시 중구" in candidates
    code2, cand2 = r.resolve("효자동", RegionLevel.EMD)  # 전국 중복 읍면동
    assert code2 is None and len(cand2) >= 2


@_needs_admin
def test_resolve_unknown_is_empty() -> None:
    """미등재 지명은 (None, [])."""
    assert _resolver().resolve("없는동네 가나구") == (None, [])


@_needs_admin
def test_resolve_scope_sido_and_capital_area() -> None:
    """scope: 시도(약식 포함)·수도권·상위지역 하위 트리 열거."""
    r = _resolver()
    # 수도권 = 서울+경기+인천 시군구 합.
    capital = r.resolve_scope("수도권", RegionLevel.SIG)
    seoul = r.resolve_scope("서울", RegionLevel.SIG)
    gyeonggi = r.resolve_scope("경기", RegionLevel.SIG)
    incheon = r.resolve_scope("인천", RegionLevel.SIG)
    assert len(capital) == len(seoul) + len(gyeonggi) + len(incheon)
    # 상위 지역(시군구) → 하위 읍면동.
    emd = r.resolve_scope("서울 종로구", RegionLevel.EMD)
    assert len(emd) > 10 and all(c.startswith("11110") for c in emd)


@_needs_admin
def test_recommend_uses_resolver_for_scope_and_candidates() -> None:
    """recommend()가 해소기로 scope·후보를 처리하고 모호 후보는 노트로 surface."""
    eng = RegionElementEngine(_DICTS, _PROFILES, _ADMIN)
    # scope 추천.
    res = eng.recommend(RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["水"]),
        candidate_scope="제주", resolution=RegionResolution.SIGUNGU, top_n=3,
    ))
    assert res.recommended_regions
    assert all("제주" in it.region_name for it in res.recommended_regions)
    # 모호 후보 → 결과 제외 + 노트.
    res2 = eng.recommend(RegionRecommendationQuery(
        target_elements=TargetElements(yongsin=["水"]),
        candidate_regions=["중구"], resolution=RegionResolution.SIGUNGU,
    ))
    assert res2.recommended_regions == []
    assert any("모호" in n for n in res2.notes)


@_needs_admin
def test_admin_snapshot_counts() -> None:
    """admin registry가 시도17/시군구250/읍면동5,065를 담는다."""
    admin = RegionAdminSnapshot.model_validate_json(_ADMIN.read_text("utf-8"))
    assert admin.profile_counts == {"ctprvn": 17, "sig": 250, "emd": 5065}
    assert len(admin.items) == 5332
