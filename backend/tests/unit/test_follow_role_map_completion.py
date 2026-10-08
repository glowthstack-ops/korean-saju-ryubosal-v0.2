"""종재·종살 역할맵 완비 — 2026-10-08 데굴님 승인.

종격 공통 판정기 통합(c9cc799) 뒤 코호트 명식 1983-04-17 23:40 남(丙일간, 癸亥 丙辰 丙子 戊子)이
종살격으로 잡혔는데, follow_structure 모델이 용신·기신만 가진 부분맵이라 canonical 이 정적 생극으로
폴백해 모델이 말한 '비겁 기신'이 식상(土)으로 바뀌었다(test_yongsin_decision_provenance 회귀).
규칙: 희신=용신을 生하는 십성군, 기신=비겁, 구신=인성, 한신=나머지. 종아격은 비겁이 용신(식상)을
生하므로 같은 규칙을 쓰지 않고 부분맵을 유지한다(결정 대기).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")


def _yongsin(birth_date: str, birth_time: str, gender: str = "male"):
    return calculate(BirthInput(
        birth_date=birth_date, birth_time=birth_time, birth_place_name="서울",
        gender=gender, reference_date=date(2026, 7, 27),
    )).yongsin_analysis


def test_jongsal_model_map_is_complete_and_adopted() -> None:
    """종살격(丙일간, 관살 水 순응): 용 水·희 金(재)·기 火(비겁)·구 木(인성)·한 土(식상)."""
    y = _yongsin("1983-04-17", "23:40")
    model = next(c for c in y.candidate_models if c.model_type == "follow_structure")
    assert model.label.startswith("종살격")
    roles = {k: getattr(model, k) for k in _ROLE_KEYS}
    assert roles == {"yongsin": "水", "heesin": "金", "gisin": "火", "gusin": "木", "hansin": "土"}
    # 완비 모델맵이 canonical 로 승격된다 — 정적 생극 폴백(기신 土)이 아니다.
    assert y.final["selected_model"] == "follow_structure"
    assert {k: y.final[k] for k in _ROLE_KEYS} == roles
    assert y.canonical_roles == roles
