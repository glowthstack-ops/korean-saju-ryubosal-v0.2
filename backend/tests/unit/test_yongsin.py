"""용신 후보 산출: group mapping, model selection, candidate aggregation."""

from __future__ import annotations

from saju_manse_analysis import analyze_chart

from saju_shared_types.constants import group_elements
from saju_shared_types.enums import Branch, Element, Stem


def test_group_elements_for_earth_day_master() -> None:
    g = group_elements(Element.EARTH)  # 己/戊
    assert g["peer"] is Element.EARTH
    assert g["resource"] is Element.FIRE  # 火生土
    assert g["output"] is Element.METAL  # 土生金
    assert g["wealth"] is Element.WATER  # 土克水
    assert g["officer"] is Element.WOOD  # 木克土


def test_weak_chart_yields_support_model_matching_v1(make_pillars) -> None:
    # 1980 fixture (신약 己): v1 용신 토·희신 화·기신 목·구신 수 재현.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    assert y.status == "candidate"  # 검증 전 확정 금지
    assert y.requires_validation is True
    assert y.final["selected_model"] == "support_day_master"
    assert y.final["yongsin"] == "土"
    assert y.final["heesin"] == "火"
    assert y.final["gisin"] == "木"
    assert y.final["gusin"] == "水"
    useful = {c.element for c in y.useful_candidates}
    assert useful == {"土", "火"}
    # 경쟁 모델(부일간 + 인성용신)이 동시에 제시된다.
    assert {m.model_type for m in y.candidate_models} >= {
        "support_day_master",
        "resource_as_yongsin",
    }


def test_deficient_element_not_auto_yongsin(make_pillars) -> None:
    # 목은 raw 표면 부족이지만 자동 용신이 아니라 기신(관살)으로 분류된다.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    assert "木" not in {c.element for c in y.useful_candidates}
    assert "木" in {c.element for c in y.unfavorable_candidates}


def test_candidate_provenance_populated(make_pillars) -> None:
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    for c in y.useful_candidates + y.unfavorable_candidates:
        assert c.model  # 후보를 낸 모델 출처가 채워진다
        assert c.reason in ("yongsin", "heesin", "gisin", "gusin")
    top = y.useful_candidates[0]
    assert top.element == "土" and top.model == "support_day_master"


def test_no_special_structure_on_fixture(make_pillars) -> None:
    # 격국 특수구조(종격/전왕/화격)는 미감지. 단, 土↔水 근접으로 bridge_required(통관)는
    # 정보성으로 감지될 수 있어 구조형만 검사한다.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    checks = analyze_chart(pillars).yongsin.special_case_checks
    for key in ("transformation_structure", "dominant_one_element", "follow_structure"):
        assert not checks[key].detected, key


def test_multi_axis_weights_and_ranking(make_pillars) -> None:
    # 1980 신약: 억부 축이 우세(eokbu 0.45) → 용신 土 유지, 축 가중치/기여 노출.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    aw = y.axis_weights
    assert set(aw) == {"eokbu", "johu", "pattern", "disease", "special"}
    assert aw["eokbu"] == 0.45  # 신약 → 억부 우선
    assert y.final["yongsin"] == "土"
    # 축 기여는 점수 내림차순으로 정렬되어 있고 억부가 최상위.
    scores = [a["score"] for a in y.axes]
    assert scores == sorted(scores, reverse=True)
    assert y.axes[0]["axis"] == "eokbu"


def test_axis_weight_sets_by_situation() -> None:
    # 상황별 동적 축 가중치(사용자 §10) 단위 검증.
    from saju_manse_analysis.yongsin.candidates import _select_axis_weights

    from saju_shared_types.structure import GeokgukResult

    def gk(final_weight: float, active: int) -> GeokgukResult:
        ev = {
            "pattern_confidence": 0.5, "confidence_grade": "C", "success_failure_score": 0.0,
            "success_failure_grade": "mixed", "success_failure_label": "x",
            "damage_types": [], "failures": [], "total_active": active, "total_rescued": 0,
            "clarity_level": "unclear", "clarity_policy": "", "final_weight": final_weight,
            "final_weight_interpretation": "", "social_expression": "",
        }
        return GeokgukResult(
            main_structure="정관격", basis={}, exposure={}, formation_level="성",
            stability={}, evaluation=ev,
        )

    # 특수격 → special 1.0
    w = _select_axis_weights("중화", Branch.JIN, gk(0.30, 0), special=True)
    assert w["special"] == 1.0
    # 신약 → 억부 우선
    assert _select_axis_weights("신약", Branch.JIN, gk(0.40, 0), special=False)["eokbu"] == 0.45
    # 중화 + 파격 뚜렷 → 병약 우선
    assert _select_axis_weights("중화", Branch.JIN, gk(0.20, 2), special=False)["disease"] == 0.35
    # 중화 + 한습월(亥) → 조후 우선
    assert _select_axis_weights("중화", Branch.HAE, gk(0.20, 0), special=False)["johu"] == 0.40
    # 중화 + 격국 선명 → 격국 우선
    assert _select_axis_weights("중화", Branch.JIN, gk(0.40, 0), special=False)["pattern"] == 0.40
