"""용신 작동역할 — 과다·병 기반 조건부 라벨 (Phase 1).

조건부 라벨(조건부 희신/병·조건부 제살보조)은 model_map 채택 케이스에만, 과다 신호로 부여.
조후(조후보조신)·_climate_harmful 연결은 Phase 2. operational 은 생성·노출만(scoring 미연결).
규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.operational_role_config import (
    CONDITION_TEMPLATES,
    OPERATIONAL_ROLE_CLASS,
)

from saju_shared_types.enums import Branch, Stem
from saju_shared_types.yongsin import ElementRole

_CONDITIONAL = {"조건부 희신/병", "조건부 제살보조"}


def _by_element(y) -> dict[str, ElementRole]:
    return {r.element: r for r in y.operational_roles}


def _standard(make_pillars):
    # 표준사례 丁巳/壬子/丁未/癸卯 (官殺 태왕 신약, 살인상생 resource_as_yongsin).
    return analyze_chart(make_pillars(
        (Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG,
    )).yongsin


def test_overloaded_officer_water_becomes_conditional(make_pillars) -> None:
    # 희신 과다 교정(2026-07-12) 후 canonical 은 모델맵(한신=水) — 과다 병 水는
    # 중립 한신이 아니라 '조건부 한신/병'(중첩 유입 시 기신성)으로 강등 표기.
    er = _by_element(_standard(make_pillars))["水"]
    assert er.canonical_role == "한신"
    assert er.operational_role == "조건부 한신/병"  # 과다·병 합성 라벨
    assert er.negative_when and any("과다" in s for s in er.negative_when)
    assert er.positive_when  # 비어있지 않음
    # note 에 합성 출처(원래 역할들)를 남긴다.
    assert er.note is not None
    assert "base_model_role=한신" in er.note
    assert "canonical_role=한신" in er.note
    assert "synthesized_by=overload_condition" in er.note


def test_controller_earth_becomes_conditional_remedy(make_pillars) -> None:
    er = _by_element(_standard(make_pillars))["土"]
    assert er.canonical_role == "구신"
    assert er.operational_role == "조건부 제살보조"
    assert er.negative_when  # 설기/훼손 위험 명시


def test_conditional_label_is_not_favorable_class() -> None:
    # "조건부 희신/병" 은 favorable 이 아니라 conditional(향후 scoring 은 이 mapper 만 경유).
    assert OPERATIONAL_ROLE_CLASS["조건부 희신/병"] == "conditional"
    assert OPERATIONAL_ROLE_CLASS["희신"] == "favorable"
    assert _CONDITIONAL <= set(CONDITION_TEMPLATES)  # 과다 조건부 라벨 템플릿 존재


def test_no_overload_chart_has_no_overload_labels(make_pillars) -> None:
    # 1980 신약 己(model_map 채택, 과다 없음): 과다 조건부 라벨 미부여.
    # (亥월 한습이라 火 가 Phase 2 조후보조신이 될 수는 있으나, 과다 합성은 일어나지 않는다.)
    y = analyze_chart(make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )).yongsin
    labels = {r.operational_role for r in y.operational_roles}
    assert labels & _CONDITIONAL == set()  # 과다 라벨 없음
    for r in y.operational_roles:
        assert not (r.note and "overload_condition" in r.note)  # 과다 합성 출처 없음


@pytest.mark.parametrize("pillars_args", [
    # 2015 bridge_tonggwan
    ((Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
     (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG),
    # 1980 戊 disease_remedy
    ((Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.IN),
     (Stem.MU, Branch.O), (Stem.JEONG, Branch.SA), Stem.MU),
    # 1985 丁 support 특수분기
    ((Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
     (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG),
])
def test_conditional_labels_do_not_leak_to_fallback(make_pillars, pillars_args) -> None:
    # fallback/부분맵·특수분기: 조건부 라벨이 새지 않고 operational == canonical 유지.
    y = analyze_chart(make_pillars(*pillars_args)).yongsin
    labels = {r.operational_role for r in y.operational_roles}
    assert labels & _CONDITIONAL == set()
    canon = {r.element: r.canonical_role for r in y.operational_roles}
    oper = {r.element: r.operational_role for r in y.operational_roles}
    assert canon == oper


def test_operational_role_enum_rejects_unknown_label() -> None:
    with pytest.raises(ValidationError):
        ElementRole(element="木", canonical_role="용신", operational_role="존재안함")


def test_element_role_roundtrip_serialization(make_pillars) -> None:
    from saju_shared_types.yongsin import AggregatedYongsinResult

    y = _standard(make_pillars)
    restored = AggregatedYongsinResult.model_validate(y.model_dump())
    assert [r.model_dump() for r in restored.operational_roles] == \
        [r.model_dump() for r in y.operational_roles]


def test_final_and_canonical_unchanged_by_conditions(make_pillars) -> None:
    # 조건부 라벨 부여가 final(점수화 SSOT)·canonical_roles 를 바꾸지 않음을 재확인.
    # (희신 과다 교정으로 final 자체는 모델맵: 희신=火·한신=水 — 2026-07-12 확정.)
    y = _standard(make_pillars)
    assert y.final["heesin"] == "火" and y.final["hansin"] == "水"
    assert y.canonical_roles == {
        k: y.final[k]
        for k in ("yongsin", "heesin", "gisin", "gusin", "hansin")
    }
