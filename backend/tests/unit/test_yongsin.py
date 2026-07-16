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


# ── 2015-03-01 03:34 균시차 미적용판(乙未 戊寅 丙子 庚寅) — 감수 케이스 ─────────
# 감수(2026-07-13, 데굴님 확정): 병=월주 偏印奪食(월간 戊식신 vs 월지 본기 甲편인),
# 치료=火통관(化印·扶身·通關·生食)으로 木→火→土→金 식신생재 경로 복원, 金은 制印·成財의
# 희신(필요성 높음·원국 작동성 낮음 — 무근·봄철 실령·피극). 최종 기대 판정 = 용신 火·희신 金.
# required_diagnostics: ①壬/癸 조후 기능 구분 ②寅中丙(잠재 火)≠노출 火 ③偏印奪食 감지
# ④식신생재 천간 경로 감지 ⑤乙庚합 이원 평가(병 완화 vs 작동력 감소).

_GYEONGIN_SPEC = (
    (Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
    (Stem.BYEONG, Branch.JA), (Stem.GYEONG, Branch.IN), Stem.BYEONG,
)
_GICHUK_SPEC = (
    (Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
    (Stem.BYEONG, Branch.JA), (Stem.GI, Branch.CHUK), Stem.BYEONG,
)


def test_2015_gyeongin_raw_structure_signals(make_pillars) -> None:
    # 영구 원시 신호 — 판정 로직과 무관하게 항상 참이어야 하는 구조 사실.
    pillars = make_pillars(*_GYEONGIN_SPEC)
    # 월주 내 偏印奪食 접촉: 월간 식신 투간 + 월지 본기 편인.
    assert pillars.month.stem_ten_god == "식신"        # 월간 戊
    assert pillars.month.branch_main_ten_god == "편인"  # 월지 寅 본기 甲
    # 식신생재 천간 경로(食透+財透): 월간 戊 → 시간 庚.
    assert pillars.hour is not None
    assert pillars.hour.stem_ten_god == "편재"          # 시간 庚
    # 庚 투간 무근: 지지 지장간 어디에도 金이 없다.
    all_hidden = [
        h for p in (pillars.year, pillars.month, pillars.day, pillars.hour)
        for h in p.hidden_stems
    ]
    assert all(h.element != "金" for h in all_hidden)
    # 지지 火는 잠재 상태로만 존재: 본기 火 지지(巳·午) 없음, 寅中丙은 중기.
    fire_hidden = [h for h in all_hidden if h.element == "火"]
    assert fire_hidden and all(h.type != "main" for h in fire_hidden)
    # 子中癸(본기)가 인성 木을 재생하는 관인상생 경로 존재.
    assert any(
        h.stem == "癸" and h.type == "main" for h in pillars.day.hidden_stems
    )


def test_2015_gyeongin_engine_raw_signals(make_pillars) -> None:
    # 엔진 산출 원시 신호 — 밴드 라벨(태신강 등)은 지장간 통근 평가 개선 시 변할 수 있어
    # 고정하지 않고, 己丑판 대비 '상대 증가'만 고정한다.
    r_in = analyze_chart(make_pillars(*_GYEONGIN_SPEC))
    r_chuk = analyze_chart(make_pillars(*_GICHUK_SPEC))
    groups_in = r_in.force.ten_gods.groups
    groups_chuk = r_chuk.force.ten_gods.groups
    assert groups_in["resource"] > groups_chuk["resource"]  # 인성 기여 증가
    assert r_in.force.strength.score > r_chuk.force.strength.score  # 신강 이동
    # 庚 무근: rooting 에 金 계열 근이 없다.
    assert all(it.hidden_stem not in ("庚", "辛") for it in r_in.force.rooting.roots)
    # 乙庚 원거리 합이 상호작용으로 감지된다(이원 평가 P3의 입력 신호).
    assert any(
        i.relation_type == "stem_combination" and set(i.members) == {"乙", "庚"}
        for i in r_in.structure.interactions
    )


def test_2015_gyeongin_final_fire_metal(make_pillars) -> None:
    # 감수 확정 기대값(火/金) — P1(재성 단독 완성도 게이트)+P2(偏印奪食 감지·화인통관
    # 치료 중재)로 도달. 선택 모델은 특수형(pyeonin_talsik)이어야 한다.
    y = analyze_chart(make_pillars(*_GYEONGIN_SPEC)).yongsin
    f = y.final
    assert f["selected_model"] == "food_rescue:pyeonin_talsik"
    assert f["yongsin"] == "火"   # 化印·扶身·通關·生食
    assert f["heesin"] == "金"   # 制印·成財 (필요성 높음·원국 작동성 낮음)
    assert f["gisin"] == "木"    # 인성 과다 = 구조적 병
    assert f["gusin"] == "水"    # 官印相生으로 병 재생
    assert f["hansin"] == "土"   # 보호 대상 식신 — operational 주석으로 보존
    # 財損印은 삭제되지 않고 감점 경쟁 후보로 존속(金 필요성 보존).
    types = {m.model_type for m in y.candidate_models}
    assert "wealth_breaks_resource" in types
    # 土(한신)는 중립이 아니라 protected_output 주석을 가진다.
    op_by_el = {r.element: r for r in (y.operational_roles or [])}
    assert "protected_output" in (op_by_el["土"].note or "")
    assert "필요성 높음" in (op_by_el["金"].note or "")
    # P3: 乙庚합 이원 평가 — 설명 전용(점수·역할 불변)으로 구속 이득/자기 묶임 병기.
    gold = op_by_el["金"]
    assert any("beneficial_binding" in s for s in gold.positive_when)
    assert any("remedy_operability" in s for s in gold.negative_when)


def test_1965_climate_emergency_water_yongsin_preserved(make_pillars) -> None:
    # 1965-05-15 (乙巳 辛巳 己巳 庚午, 극신강 己土·조열 巳월·水 전무) — 감수 확정(2026-07-13):
    # ①mediator veto: 극신강 비겁(土) mediator 승격 금지(신강 악화·건토 심화·金 매몰)
    # ②climate_need_preservation: 조후 필요신(水) 부재는 결핍의 증거 — canonical 필요도
    #   감점 금지, 무근 감점은 작동성(operability) 계층에만.
    # ③P4(궁통보감 사전): 巳월 己 → 최우선 癸 부재+오행 전무 → 조후가 주모델
    #   (감수 이상형 climate_dryness_correction) → 용=水·희=金(생용신).
    pillars = make_pillars(
        (Stem.EUL, Branch.SA), (Stem.SIN, Branch.SA),
        (Stem.GI, Branch.SA), (Stem.GYEONG, Branch.O), Stem.GI,
    )
    y = analyze_chart(pillars).yongsin
    f = y.final
    assert f["selected_model"] == "johu"
    assert f["yongsin"] == "水"   # 조후 윤조 — 부재가 필요도를 낮추지 못한다
    assert f["heesin"] == "金"   # 설기·생수(감수 이상형)
    assert not any(
        m.model_type.startswith("food_rescue") for m in y.candidate_models
    )  # 비겁 土 mediator 승격 차단
    assert any("mediator 승격 차단" in w for w in (y.warnings or []))
    # 財損印(水)은 감점-존속 경쟁 후보로 남아 조후 결론을 보강한다.
    assert any(m.model_type == "wealth_breaks_resource" for m in y.candidate_models)
    # 무근·부재 감점은 작동성 계층에 남는다(canonical 순위는 불변).
    water = next(r for r in (y.operational_roles or []) if r.element == "水")
    assert water.operability is not None and water.operability < 1.0
    assert "no_root" in water.operability_factors


def test_1959_non_climate_primary_no_emergency_boost(make_pillars) -> None:
    # 1959-11-15 (己亥 乙亥 辛丑 甲午, 亥월 辛): 궁통보감 1순위 壬은 한(寒) 축의 직접
    # 교정 오행(火)이 아니다 — 감수 ②: 억부·구조 목적 천간은 조후 emergency 가산 금지.
    # johu 후보는 base 신뢰도로만 제시되고 최종은 억부가 결정한다.
    y = analyze_chart(make_pillars(
        (Stem.GI, Branch.HAE), (Stem.EUL, Branch.HAE),
        (Stem.SIN, Branch.CHUK), (Stem.GAP, Branch.O), Stem.SIN,
    )).yongsin
    johu = next(m for m in y.candidate_models if m.model_type == "johu")
    assert johu.yongsin == "水"          # 궁통보감 canonical need(壬)
    assert johu.confidence == 0.4        # 극단월 base — emergency 가산 없음
    assert y.final["selected_model"] != "johu"


def test_1953_tied_heesin_semantic_tiebreak(make_pillars) -> None:
    # 1953-01-15 (壬辰 癸丑 丙寅 甲午, bridge 용신 金·희신 폴백 동점 火/木) — 감수 ③:
    # 동점만 의미론 정렬(한월 丑 → 火가 기후 축 직접 교정 → 火 우선), 사유 기록.
    # 점수·confidence·역할 구조는 불변(독립 정렬 레이어).
    y = analyze_chart(make_pillars(
        (Stem.IM, Branch.JIN), (Stem.GYE, Branch.CHUK),
        (Stem.BYEONG, Branch.IN), (Stem.GAP, Branch.O), Stem.BYEONG,
    )).yongsin
    f = y.final
    assert f["selected_model"] == "bridge_tonggwan"
    assert f["heesin"] == "火" and f["hansin"] == "木"
    assert any("타이브레이크" in w and "dominant_need" in w for w in (y.warnings or []))


def test_food_rescue_not_generated_guards(make_pillars) -> None:
    # 화인통관(food_rescue) 미생성 가드 — 감수 골든 유형(2026-07-13):
    # ①노출 통관 화력 충분(시간 丙 비견): 승격 억제 ②식신 미투간 인성과다: 미발동
    # ③상관 투간(식신 아님): 동일 규칙 자동 적용 금지.
    guards = [
        ((Stem.EUL, Branch.MI), (Stem.MU, Branch.IN),
         (Stem.BYEONG, Branch.JA), (Stem.BYEONG, Branch.IN), Stem.BYEONG),
        ((Stem.EUL, Branch.MI), (Stem.GAP, Branch.IN),
         (Stem.BYEONG, Branch.JA), (Stem.GYEONG, Branch.IN), Stem.BYEONG),
        ((Stem.EUL, Branch.MI), (Stem.GI, Branch.MYO),
         (Stem.BYEONG, Branch.JA), (Stem.GYEONG, Branch.IN), Stem.BYEONG),
    ]
    for spec in guards:
        y = analyze_chart(make_pillars(*spec)).yongsin
        assert not any(
            m.model_type.startswith("food_rescue") for m in y.candidate_models
        )


def test_1980_strong_earth_wealth_yongsin_canonical_roles(make_pillars) -> None:
    # 1980-02-15 10:30(庚申 戊寅 戊午 丁巳, 戊·신강): 편인도식 병약 → 재성 용신 水.
    # 申 지장간 壬水로 재성이 통근해 용광로(炎上)가 아니므로 水를 용신으로 쓴다.
    # 역할은 용신 기준 생극 순환을 따른다: 土克水의 土가 기신, 과다 인성 火는 구신(생기신),
    # 水生木의 木이 한신 — 용신을 극하는 土가 한신으로 새던 모순을 바로잡는다.
    pillars = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.MU, Branch.IN),
        (Stem.MU, Branch.O), (Stem.JEONG, Branch.SA), Stem.MU,
    )
    f = analyze_chart(pillars).yongsin.final
    assert f["yongsin"] == "水"
    assert f["heesin"] == "金"   # 生용신
    assert f["gisin"] == "土"    # 克용신 (土克水)
    assert f["gusin"] == "火"    # 生기신 (火生土)
    assert f["hansin"] == "木"   # 용신생 (水生木)


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
