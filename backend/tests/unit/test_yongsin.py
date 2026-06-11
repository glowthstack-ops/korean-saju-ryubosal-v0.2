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


def test_weak_chart_yields_support_model(make_pillars) -> None:
    # 1980 진태양시(신약 己): 억부 우선 → 부일간형 용 土(비겁)·희 火(인성)·기 木(관)·구 水(재).
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


def test_yongsin_roles_form_partition(make_pillars) -> None:
    # 용·희·기·구·한은 5오행의 분할(중복·누락 없음)이어야 한다.
    pillars = make_pillars(
        (Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
        (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG,
    )
    f = analyze_chart(pillars).yongsin.final
    roles = [f["yongsin"], f["heesin"], f["gisin"], f["gusin"], f["hansin"]]
    assert set(roles) == {"木", "火", "土", "金", "水"}  # 정확히 5오행 1:1


def test_2015_excess_resource_is_gisin(make_pillars) -> None:
    # 2015-03-01 03:34 진태양시(乙未 戊寅 丙子 己丑, 丙·신강): 인성 木 과다가 기신.
    # 木→火→土 통관 구조가 뚜렷해 통관용신 火를 우선하고, 金은 희신으로 둔다.
    pillars = make_pillars(
        (Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
        (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG,
    )
    f = analyze_chart(pillars).yongsin.final
    assert f["yongsin"] == "火"
    assert f["heesin"] == "金"
    assert f["gisin"] == "木"    # 인성 과다 = 구조적 병
    assert f["hansin"] == "水"


def test_1985_weak_resource_yongsin(make_pillars) -> None:
    # 1985-04-18 16:00 (乙丑 庚辰 丁亥 戊申, 丁·태신약): 비겁이 전무해 직접 보강 火 우선.
    # 희신=인성 木, 한신=관성 水.
    pillars = make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
        (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG,
    )
    f = analyze_chart(pillars).yongsin.final
    assert f["yongsin"] == "火"
    assert f["heesin"] == "木"
    assert f["hansin"] == "水"


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
    # 1980 신약(亥월 한습): 억부 가중치 0.45 + 정상 신뢰도 → 억부축 최상위, 용신 土.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.MU, Branch.JIN), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    aw = y.axis_weights
    assert set(aw) == {"eokbu", "johu", "pattern", "disease", "bridge", "special"}
    assert aw["eokbu"] == 0.45  # 신약 → 억부 가중치 우선
    assert y.final["yongsin"] == "土"
    # 축 기여는 점수 내림차순으로 정렬되어 있고 억부가 최상위.
    scores = [a["score"] for a in y.axes]
    assert scores == sorted(scores, reverse=True)
    assert y.axes[0]["axis"] == "eokbu"


def test_jongsal_follow_overrides(make_pillars) -> None:
    # 진종(眞從) 종살격: 甲 무근 + 관성(金) 압도 → 종격이 special 축 단독 주도, 용신=金(관).
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.GYEONG, Branch.SIN),
        (Stem.GAP, Branch.SIN), (Stem.GYEONG, Branch.O), Stem.GAP,
    )
    y = analyze_chart(pillars).yongsin
    fs = y.special_case_checks["follow_structure"]
    assert fs.detected
    assert fs.detail is not None and fs.detail.startswith("real:officer")
    assert y.final["selected_model"] == "follow_structure"
    assert y.final["yongsin"] == "金"
    labels = {m.label for m in y.candidate_models}
    assert "종살격(從殺格)" in labels


def test_jongjae_and_jongah_naming(make_pillars) -> None:
    # 종재격: 甲 무근 + 재성(土) 압도 → 용신 土.
    jae = analyze_chart(make_pillars(
        (Stem.MU, Branch.SUL), (Stem.MU, Branch.SUL),
        (Stem.GAP, Branch.SUL), (Stem.MU, Branch.JIN), Stem.GAP,
    )).yongsin
    assert jae.final["yongsin"] == "土"
    assert "종재격(從財格)" in {m.label for m in jae.candidate_models}
    # 종아격: 丙 무근 + 식상(土) 압도 → 용신 土.
    ah = analyze_chart(make_pillars(
        (Stem.MU, Branch.JIN), (Stem.MU, Branch.JIN),
        (Stem.BYEONG, Branch.JIN), (Stem.MU, Branch.SUL), Stem.BYEONG,
    )).yongsin
    assert ah.final["yongsin"] == "土"
    assert "종아격(從兒格)" in {m.label for m in ah.candidate_models}


def test_pseudo_follow_keeps_eokbu_and_flags(make_pillars) -> None:
    # 사천(乙丑 庚辰 丁亥 戊申, 丁 일간): 비겁 무근이나 인성(木) 잔존 → 가종아.
    # 비겁이 전무하므로 1차 용신은 직접 보강 火, 종아(土)는 병기, 검증 경고.
    pillars = make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
        (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG,
    )
    y = analyze_chart(pillars).yongsin
    fc = y.special_case_checks["follow_structure"]
    assert fc.detected and fc.detail is not None and fc.detail.startswith("pseudo:output")
    # 직접 보강이 1차 용신으로 유지된다(종격이 강탈하지 않음).
    assert y.final["yongsin"] == "火"
    assert y.final["selected_model"] == "support_day_master"
    # 가종아격이 후보 목록에 병기된다.
    assert "가종격(假從)·종아격(從兒格)" in {m.label for m in y.candidate_models}
    assert any("가종" in w for w in y.warnings)


def test_candidate_model_types_are_unique_for_calibration(make_pillars) -> None:
    # 병약 후보가 여러 개 생겨도 model_type이 고유해야 검증 질문/피드백에서 덮어쓰지 않는다.
    pillars = make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.GYEONG, Branch.JIN),
        (Stem.JEONG, Branch.HAE), (Stem.MU, Branch.SIN), Stem.JEONG,
    )
    y = analyze_chart(pillars).yongsin
    model_types = [m.model_type for m in y.candidate_models]
    assert len(model_types) == len(set(model_types))
    assert {
        "disease_remedy:shangguan_attacks_officer",
        "disease_remedy:pyeonin_dosik",
    } <= set(model_types)


def test_tonggwan_model_emitted(make_pillars) -> None:
    # 木(25%+)과 土(25%+)가 상극·통관 오행 火가 약함 → 통관용신형(火) 후보 생성.
    pillars = make_pillars(
        (Stem.GAP, Branch.IN), (Stem.MU, Branch.JIN),
        (Stem.GAP, Branch.IN), (Stem.MU, Branch.SUL), Stem.MU,
    )
    y = analyze_chart(pillars).yongsin
    assert y.special_case_checks["bridge_required"].detected
    assert "통관용신=火" in (y.special_case_checks["bridge_required"].detail or "")
    tg = [m for m in y.candidate_models if m.model_type == "bridge_tonggwan"]
    assert tg and tg[0].yongsin == "火"


def test_flow_circulation_present(make_pillars) -> None:
    # 1980 신약(오행 5개 전부 + 상생 5고리) → 유통 양호.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.GI, Branch.SA), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    flow = y.flow_circulation
    assert flow is not None
    assert flow["all_five_present"] is True
    assert flow["sheng_links"] == 5 and flow["smooth"] is True
    assert any("유통 양호" in w for w in y.warnings)
    # 유통은 정보성 — 용신 선택은 기존대로 억부 土.
    assert y.final["yongsin"] == "土"


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
