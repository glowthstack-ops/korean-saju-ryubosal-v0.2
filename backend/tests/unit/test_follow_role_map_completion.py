"""종재·종살 역할맵 완비 — 2026-10-08 데굴님 승인(같은 날 종살 정정).

종격 공통 판정기 통합(c9cc799) 뒤 코호트 명식 1983-04-17 23:40 남(丙일간, 癸亥 丙辰 丙子 戊子)이
종살격으로 잡혔는데, follow_structure 모델이 용신·기신만 가진 부분맵이라 canonical 이 정적 생극으로
폴백해 모델맵이 버려졌다(test_yongsin_decision_provenance 회귀). 완비 규칙은 생극 순환을 따른다 —
종살: 용 관살·희 재·기 식상·구 비겁·한 인성 / 종재: 용 재·희 식상·기 비겁·구 인성·한 관살.
1차안(종살 기=비겁·한=식상)은 식상이 용신을 克하는데도 운 점수의 한신 세분이 HAN_GOOD 으로 읽어
길흉이 역전됐다(데굴님 지적). 인성이 '약한 흉(HAN_BAD)'에 묶이는 강도 문제는 미해결(별도 검토).
"""

from __future__ import annotations

from datetime import date

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import PolarityRole, _han_gen_role, _period_role
from saju_engines.event_scoring import favorability_map
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.luck import LuckPillar

_ROLE_KEYS = ("yongsin", "heesin", "gisin", "gusin", "hansin")


def _result():
    return calculate(BirthInput(
        birth_date="1983-04-17", birth_time="23:40", birth_place_name="서울",
        gender="male", reference_date=date(2026, 7, 27),
    ))


def test_jongsal_model_map_is_complete_and_adopted() -> None:
    """종살격(丙일간, 관살 水 순응): 용 水·희 金(재)·기 土(식상)·구 火(비겁)·한 木(인성)."""
    y = _result().yongsin_analysis
    model = next(c for c in y.candidate_models if c.model_type == "follow_structure")
    assert model.label.startswith("종살격")
    roles = {k: getattr(model, k) for k in _ROLE_KEYS}
    assert roles == {"yongsin": "水", "heesin": "金", "gisin": "土", "gusin": "火", "hansin": "木"}
    assert any("식상 기신" in r and "인성 한신" in r for r in model.reasons)
    # 완비 모델맵이 canonical 로 승격된다(정적 폴백이 아니라 모델 자체맵).
    assert y.final["selected_model"] == "follow_structure"
    assert {k: y.final[k] for k in _ROLE_KEYS} == roles
    assert y.canonical_roles == roles


def test_jongsal_adverse_elements_do_not_flip_favorable_in_luck_polarity() -> None:
    """운 극성: 식상 土=기신(흉)·비겁 火=구신(흉)·인성 木=한신이되 生 대상이 구신이라 HAN_BAD.

    1차안에서는 식상이 한신이라 生 희신(金)을 보고 HAN_GOOD(약한 길)로 뒤집혔다. 인성이 약한 흉에
    그치는 강도는 미해결 항목이다.
    """
    r = _result()
    fav = favorability_map(r)
    assert fav["土"] == "기신" and fav["火"] == "구신" and fav["木"] == "한신"
    assert _han_gen_role("木", fav) is PolarityRole.HAN_BAD
    assert _han_gen_role("土", fav) is None  # 한신이 아니므로 세분 대상 아님(기신 직접)
    adverse = (PolarityRole.GI, PolarityRole.GI_STRONG)
    for ganji in ("戊戌", "丙午"):  # 식상(土土)·비겁(火火) 운 — 천간·지지 동일 오행이면 GI_STRONG
        p = LuckPillar(
            label="t", period_type="year", ganji=ganji, stem=ganji[0], branch=ganji[1],
            stem_ten_god="", branch_ten_god="",
        )
        assert _period_role(p, fav) in adverse, ganji
