"""지역 추천 golden case 회귀(P4, docs/12 §6·§7).

reviewed:false 가중이므로 **상대 순위·역할 분류·구조 불변식**만 고정한다(절대값 미고정 — 이벤트
golden 스탠스와 동일). 결정론 candidate_regions 기반이라 가중 튜닝 시에도 순위 의미가 유지되는지
회귀로 잡는다. 20 케이스: 5오행 용신 최상위·용희한 순위·기신 risk·구신 avoid·약신뢰 cap·강>약·
방위·모호/미등재·scope·읍면동 계산/시군구 surface.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.region_element_engine import RegionElementEngine
from saju_engines.region_recommendation_orchestrator import (
    RegionRecommendationOrchestrator,
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
_CASES = _BACKEND / "tests" / "fixtures" / "region_recommendation_cases.jsonl"

pytestmark = pytest.mark.skipif(
    not (_PROFILES.exists() and _ADMIN.exists()), reason="지역 스냅샷 미빌드"
)


def _load_cases() -> list[dict]:
    return [json.loads(ln) for ln in _CASES.read_text("utf-8").splitlines() if ln.strip()]


def _query(case: dict) -> RegionRecommendationQuery:
    t = case["target"]
    return RegionRecommendationQuery(
        target_elements=TargetElements(
            yongsin=t.get("yongsin", []), huisin=t.get("huisin", []),
            gisin=t.get("gisin", []), gusin=t.get("gusin", []), boost=t.get("boost", []),
        ),
        base_location=case.get("base_location"),
        candidate_regions=case.get("candidate_regions"),
        candidate_scope=case.get("candidate_scope"),
        resolution=RegionResolution(case.get("resolution", "sigungu")),
        intent_mode=IntentMode.RELOCATION,
        top_n=case.get("top_n", 20),
    )


def _engine() -> RegionElementEngine:
    return RegionElementEngine(_DICTS, _PROFILES, _ADMIN)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_region_recommendation_golden(case: dict) -> None:
    """케이스별 불변식 검증(상대 순위·역할·구조). 절대 점수는 고정하지 않는다."""
    eng = _engine()
    query = _query(case)
    result = eng.recommend(query)
    items = result.recommended_regions
    by_name = {it.region_name: it for it in items}
    exp = case["expect"]

    if exp.get("recommended_empty"):
        assert items == [], f"{case['id']}: 추천이 비어야 함"
    if "note_contains" in exp:
        assert any(exp["note_contains"] in n for n in result.notes), (
            f"{case['id']}: 노트에 '{exp['note_contains']}' 필요 — {result.notes}"
        )
    if "top" in exp:
        got = items[0].region_name if items else None
        assert items and items[0].region_name == exp["top"], (
            f"{case['id']}: 최상위 {exp['top']} 기대, 실제 {got}"
        )
    if "order" in exp:
        scores = [by_name[n].match_score for n in exp["order"] if n in by_name]
        assert len(scores) == len(exp["order"]), f"{case['id']}: 순위 지역 누락"
        assert scores == sorted(scores, reverse=True), (
            f"{case['id']}: 순위 {exp['order']} 점수 비단조 — {scores}"
        )
    if "gisin_strong" in exp:
        it = by_name.get(exp["gisin_strong"])
        flags = it.risk_flags if it else None
        assert it is not None and "gisin_strong" in it.risk_flags, (
            f"{case['id']}: {exp['gisin_strong']} gisin_strong 기대 — {flags}"
        )
    if "avoid_ge" in exp:
        it = by_name.get(exp["avoid_ge"]["region"])
        assert it is not None and it.avoid_score >= exp["avoid_ge"]["ge"], (
            f"{case['id']}: avoid_score≥{exp['avoid_ge']['ge']} 기대"
        )
    if "max_score_le" in exp:
        it = by_name.get(exp["max_score_le"]["region"])
        assert it is not None and it.match_score <= exp["max_score_le"]["le"], (
            f"{case['id']}: {exp['max_score_le']['region']} 점수 ≤{exp['max_score_le']['le']} 기대 "
            f"— 실제 {it.match_score if it else None}"
        )
    if exp.get("direction_present_top"):
        assert items and items[0].direction != "", f"{case['id']}: 최상위 방위 필요"
    if exp.get("no_direction_top"):
        assert items and items[0].direction == "", f"{case['id']}: 방위 미산출 기대"
    if "all_contain" in exp:
        assert items and all(exp["all_contain"] in it.region_name for it in items), (
            f"{case['id']}: 전 결과가 '{exp['all_contain']}' 포함이어야 함"
        )
    if "all_contain_any" in exp:
        toks = exp["all_contain_any"]
        assert items and all(any(t in it.region_name for t in toks) for it in items), (
            f"{case['id']}: 전 결과가 {toks} 중 하나 포함이어야 함"
        )

    # payload 구조 불변식(emd 계산/sig surface/무데이터 가드).
    if any(k in exp for k in ("computed_level", "surface_level", "terrain_unavailable",
                              "surface_emd_detail")):
        payload = RegionRecommendationOrchestrator(eng).recommend_payload(query)
        if "computed_level" in exp:
            assert payload["computed_level"] == exp["computed_level"]
        if "surface_level" in exp:
            assert payload["surface_level"] == exp["surface_level"]
        if exp.get("terrain_unavailable"):
            assert payload["terrain_data_available"] is False
        if exp.get("surface_emd_detail"):
            assert payload.get("surface"), "시군구 surface 필요"
            cand = payload["surface"][0]["top_emd_candidates"][0]
            assert len(cand["full_name_ko"].split()) >= 3  # 읍면동 세부


def test_golden_case_count_and_terrain_guard() -> None:
    """golden 20케이스 + 모든 케이스에서 외부 지형 미연결(terrain_data_available False)."""
    cases = _load_cases()
    assert len(cases) >= 20
    eng = _engine()
    orch = RegionRecommendationOrchestrator(eng)
    sampled = orch.recommend_payload(_query(cases[0]))
    assert sampled["terrain_data_available"] is False  # 외부 데이터 미연결 상태 고정


def test_consolidated_city_districts_use_own_hanja() -> None:
    """통합시 자치구는 도시 한자 폴백이 아니라 자체 한자로 산출된다(2026-06-26 데굴님 지적).

    마산합포구(馬山合浦)는 浦=水라 水 우세여야 하고, 성산구(城山)는 土라야 한다 — 둘이 같은
    창원시(昌原=原 土)로 뭉뚱그려져 동일 土로 나오던 폴백 결함의 회귀 가드.
    """
    eng = _engine()

    def dom(name: str) -> str:
        code, _ = eng.resolve_region(name)
        assert code is not None, f"{name} 미해소"
        p = eng.get_profile(code)
        assert p is not None and p.dominant_elements
        return p.dominant_elements[0]

    assert dom("마산합포구") == "水"  # 浦(물가·항구) 반영
    assert dom("창원 성산구") == "土"  # 城山
    assert dom("마산합포구") != dom("창원 성산구")  # 도시 폴백 collapse 아님
    assert dom("용인 수지구") == "水"  # 水枝
    assert dom("고양 덕양구") == "火"  # 德陽
