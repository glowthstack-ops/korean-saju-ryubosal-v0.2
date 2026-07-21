"""결혼·자산 자원 구조 분석 단위 테스트 (v2.2).

실사례(둘 다 丙火 여성, 60대 = 1961-09-30, 같은 년월일·다른 시주):
- 午시(甲午): 시주 인성·비겁 → 부모 혜택·보호 구조(parental).
- 卯시(辛卯): 시주 정재 → 결혼 후·결과 자리 재성(시댁 재력 잠재 = spouse_family) + 卯酉충 발동.

핵심 검증 = **시주 하나가 자산 출처 경향을 가른다**(구조 신호, 예측 아님). 여성 명식에서 관성이
드러나지 않아도(투간·본기 기준) 재성 환경이 강하면 spouse_family 잠재가 잡힌다.
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.marriage_resource import analyze_marriage_resource
from saju_shared_types.birth_input import BirthInput


def _profile(time_: str, gender: str = "female"):
    return analyze_marriage_resource(
        calculate(
            BirthInput(
                calendar_type="solar", birth_date="1961-09-30", birth_time=time_,
                birth_place_name="서울", gender=gender,
            )
        )
    )


# 배우자성 성별 인지 — 헤더가 성별 기준(남=재성·여=관성)으로 분기(2026-06-22 데굴님 지적 교정).
def test_marriage_lines_header_gender_aware() -> None:
    from saju_engines.structural_context import marriage_resource_lines
    male = " ".join(marriage_resource_lines(_profile("12:00", "male")))
    female = " ".join(marriage_resource_lines(_profile("12:00", "female")))
    # 남성: 재성=배우자(처), '관성=배우자' 여성 기준 문구 없음.
    assert "재성=배우자(처)" in male
    assert "관성=배우자," not in male and "관성=배우자(남편)" not in male
    # 여성: 관성=배우자(남편).
    assert "관성=배우자(남편)" in female


def test_spouse_star_directive_gender() -> None:
    from saju_engines.structural_context import spouse_star_directive
    male = spouse_star_directive("male")
    female = spouse_star_directive("female")
    assert "남성의 배우자(아내)는 재성" in male and "배우자가 아니다" in male
    assert "여성의 배우자(남편)는 관성" in female
    # 미상은 단정 금지 안내.
    assert "단정하지" in spouse_star_directive(None)


def test_hour_pillar_splits_wealth_source() -> None:
    """같은 년월일·다른 시주 → 자산 출처 경향이 갈린다(午시=parental만, 卯시=+spouse_family)."""
    left = _profile("12:00")   # 甲午시 — 시주 인성
    right = _profile("06:00")  # 辛卯시 — 시주 정재
    assert left.wealth_element == "金"  # 丙火 → 재성 金
    # 왼쪽: 재성 시주 없음 → spouse_family 미성립, 시주 자원=보호(인성).
    assert not left.wealth_in_result_palace
    assert "spouse_family" not in left.wealth_source_leans
    assert "parental" in left.wealth_source_leans
    assert "인성" in left.hour_resource_role
    # 오른쪽: 재성 시주 있음 → spouse_family 성립, 시주 자원=재물, 재성궁 충.
    assert right.wealth_in_result_palace
    assert "spouse_family" in right.wealth_source_leans
    assert "재물" in right.hour_resource_role
    assert right.wealth_palace_clash  # 卯酉충


def test_visible_officer_absent_but_spouse_family_present() -> None:
    """여성 명식 — 관성이 투간/본기로 드러나지 않아도 재성 환경(시댁 재력 잠재)은 잡힌다."""
    right = _profile("06:00")
    assert right.gender == "female" and right.spouse_star == "관성"
    assert right.spouse_star_present is False  # 水 관성 투간·본기 부재(지장간 癸는 제외)
    assert "spouse_family" in right.wealth_source_leans  # 그래도 재성 환경 강


# E3 배우자 인연 결(중립·비낙인) — 도화/홍염·배우자 별 과다/미투출(궁합 자료 ⑤⑥).
def test_charm_and_spouse_star_fields() -> None:
    prof = _profile("12:00")  # 1961-09-30 여성 — 酉월(사정지) → 도화 성립
    assert isinstance(prof.spouse_star_excess, bool)
    assert isinstance(prof.charm_present, bool)
    # 酉(사정지) 포함 → 도화 끌림 경향.
    assert prof.charm_present is True
    # 미투출 플래그는 존재 플래그의 보수적 반대(일관성).
    assert prof.spouse_star_absent == (not prof.spouse_star_present)


def test_neutral_labels_no_stigma() -> None:
    # '바람둥이/과부상' 류 낙인 표현이 flags에 절대 들어가지 않는다(중립 가드).
    for time_ in ("12:00", "06:00"):
        prof = _profile(time_)
        joined = " ".join(prof.flags)
        for banned in ("바람둥이", "과부", "팔자", "사주가 나쁨"):
            assert banned not in joined


# E3 렌더 — marriage_resource_lines가 새 배우자 인연 결 신호를 실제로 출력(chat·report 공용).
def test_lines_render_bond_signals() -> None:
    from saju_engines.structural_context import marriage_resource_lines
    mr = _profile("12:00")  # 酉(도화) 포함
    text = " ".join(marriage_resource_lines(mr))
    assert "배우자 인연 결" in text  # 새 신호 줄이 실제 렌더됨(이전엔 누락)
    assert "도화" in text
    # 낙인 표현 절대 금지(중립 가드).
    for banned in ("바람둥이", "과부"):
        assert banned not in text


# Task 1 — 일지 3분류 배우자궁 기질(왕지/생지/고지, 도화·역마·화개).
def test_day_branch_temperament_classification() -> None:
    """일지 지지가 왕지/생지/고지 중 하나로 일관되게 분류된다(비단정 라벨)."""
    from saju_manse_analysis.sinsal.sinsal_catalog import SAGO, SAJEONG, SASAENG

    from saju_engines.marriage_resource import _day_branch_temperament
    from saju_shared_types.enums import Branch

    expected = {"wangji": SAJEONG, "saengji": SASAENG, "goji": SAGO}
    seen: set[str] = set()
    for branch in Branch:
        group, tendency = _day_branch_temperament(branch)
        assert group in expected and tendency  # 12지지 전부 분류·라벨 존재
        assert branch in expected[group]  # 분류가 사정/사생/사고 집합과 일치
        seen.add(group)
    assert seen == {"wangji", "saengji", "goji"}  # 세 그룹 모두 커버


def test_day_branch_temperament_on_profile() -> None:
    """실사례 1961-09-30(일지 寅) → 생지(역마형)로 분류·라벨 노출."""
    mr = _profile("12:00")  # 丙寅 일주
    assert mr.day_branch_group == "saengji"
    assert "생지" in mr.day_branch_tendency and "역마" in mr.day_branch_tendency


def test_day_branch_temperament_rendered_neutral() -> None:
    """배우자궁 기질이 marriage_resource_lines에 렌더되며 기질 라벨에 단정·낙인이 없다."""
    from saju_engines.structural_context import marriage_resource_lines
    mr = _profile("12:00")
    text = " ".join(marriage_resource_lines(mr))
    assert "배우자궁(일지) 기질" in text
    # 기질 라벨 자체는 단정·낙인 어휘를 쓰지 않는다(헤더의 '금지' 안내문은 검사 대상 아님).
    for banned in ("반드시", "바람둥이", "과부", "이혼한다"):
        assert banned not in mr.day_branch_tendency


# ── 영상 1+2 보강: A 일지 십성 이상형 (2026-07-21 음양 세분+마찰 결 확장) ──
def test_ideal_type_mapping_all_groups() -> None:
    from saju_engines.marriage_resource import _ideal_type
    cases = {
        "비견": "peer", "겁재": "peer", "식신": "output", "상관": "output",
        "정재": "wealth", "편재": "wealth", "정관": "officer", "편관": "officer",
        "정인": "resource", "편인": "resource",
    }
    for god, grp in cases.items():
        group, label, friction = _ideal_type(god)
        assert group == grp and label and friction
    assert _ideal_type(None) == ("", "", "")
    assert _ideal_type("없음") == ("", "", "")


def test_ideal_type_yin_yang_refinement() -> None:
    """재성·관성·인성은 정/편 세분 라벨, 비겁·식상은 군 라벨(영상 자료 음양 분화)."""
    from saju_engines.marriage_resource import _ideal_type

    assert "단정" in _ideal_type("정재")[1] and "뚜렷" in _ideal_type("편재")[1]
    assert _ideal_type("정재")[1] != _ideal_type("편재")[1]
    assert "균형" in _ideal_type("정관")[1] and "엣지" in _ideal_type("편관")[1]
    assert "인정" in _ideal_type("정인")[1] and "전문성" in _ideal_type("편인")[1]
    # 비겁·식상은 군 라벨 유지(자료도 군 단위 설명).
    assert _ideal_type("비견")[1] == _ideal_type("겁재")[1]
    assert _ideal_type("식신")[1] == _ideal_type("상관")[1]
    # 마찰 결은 군 단위 공통.
    assert _ideal_type("정재")[2] == _ideal_type("편재")[2]


def test_ideal_type_on_profile() -> None:
    # 일지 본기 십성 기준 이상형 그룹이 채워진다(성별 무관 — 일지 십성은 동일).
    mr = _profile("12:00")
    assert mr.day_branch_ten_god_group in ("peer", "output", "wealth", "officer", "resource")
    assert mr.ideal_type_tendency


# ── E 배우자별 하나·튼튼 ──
def test_spouse_quality_fields_present() -> None:
    mr = _profile("06:00")
    assert isinstance(mr.spouse_star_clean, bool)
    assert isinstance(mr.spouse_star_rooted, bool)
    # clean이면 반드시 배우자성 존재·과다 아님.
    if mr.spouse_star_clean:
        assert mr.spouse_star_present and not mr.spouse_star_excess


# ── F 배우자궁(일지) 안정도: 충/형/원진/파/해 ──
def test_spouse_palace_afflictions_detection() -> None:
    from saju_engines.marriage_resource import _spouse_palace_afflictions
    from saju_shared_types.enums import Branch
    assert "충" in _spouse_palace_afflictions(Branch.JA, [Branch.O])  # 子午충
    assert "원진" in _spouse_palace_afflictions(Branch.JA, [Branch.MI])  # 子未 원진
    assert _spouse_palace_afflictions(Branch.JA, [Branch.CHUK]) == []  # 子丑 육합(살 아님)


def test_spouse_palace_stable_consistency() -> None:
    mr = _profile("12:00")
    # stable은 afflictions 비어있음과 정확히 일치.
    assert mr.spouse_palace_stable == (not mr.spouse_palace_afflictions)


# ── G 배우자성=용신 → 배우자 덕 ──
def test_spouse_is_yongsin_cross() -> None:
    from saju_shared_types.llm_input import UsefulGods
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    ))
    mr0 = analyze_marriage_resource(r)  # useful 미입력 → graceful False
    assert mr0.spouse_is_yongsin is False
    # 남성 배우자성=재성. 재성 오행을 용신으로 주면 True.
    useful = UsefulGods(yongsin=[mr0.wealth_element])
    mr1 = analyze_marriage_resource(r, useful)
    assert mr1.spouse_is_yongsin is True
    # 재성 오행이 기신이면 False.
    useful2 = UsefulGods(gisin=[mr0.wealth_element])
    assert analyze_marriage_resource(r, useful2).spouse_is_yongsin is False


# ── 직렬화: 새 축(이상형·배우자복 품질)이 렌더된다(chat·report 공용) ──
def test_lines_render_new_axes() -> None:
    from saju_engines.structural_context import marriage_resource_lines
    text = " ".join(marriage_resource_lines(_profile("12:00")))
    assert "배우자 취향(이상형" in text
    assert "배우자복 품질" in text
    # 이혼 단정 금지 가드(F 손상 케이스 라벨에 포함될 때).
    assert "이혼한다" not in text


# ── B 생애 단계별 연애 대상(연/월/시지 십성) ──
def test_life_stage_ideals_helper() -> None:
    from saju_engines.marriage_resource import _life_stage_ideals
    out = _life_stage_ideals("정재", "정관", "정인")  # wealth/officer/resource
    assert any("어릴 때" in x and "현실 매력형" in x for x in out)
    assert any("원숙기" in x and "조건·태도형" in x for x in out)
    assert any("말년" in x and "보살핌형" in x for x in out)
    # 미상 십성은 스킵.
    assert _life_stage_ideals(None, "없음", None) == []


def test_life_stage_ideals_on_profile_and_render() -> None:
    from saju_engines.structural_context import marriage_resource_lines
    mr = _profile("12:00")
    assert mr.life_stage_ideals  # 연/월/시지 본기 십성 → 단계 라벨
    text = " ".join(marriage_resource_lines(mr))
    assert "생애 단계 연애 대상" in text
    assert "시기 단정 아님" in text  # 단정 가드 동반


# ── 관계 친화·돌봄 성향(식신 케어/식상생재/인성/비겁/신약+비겁약) ──
def _pil(stem_tg: str | None, branch_tg: str):
    from types import SimpleNamespace
    return SimpleNamespace(stem_ten_god=stem_tg, branch_main_ten_god=branch_tg)


def _fa_stub(groups: dict, band: str):
    from types import SimpleNamespace
    return SimpleNamespace(
        ten_gods=SimpleNamespace(groups=groups), strength=SimpleNamespace(band=band),
    )


def test_relationship_affinity_signals() -> None:
    from types import SimpleNamespace

    from saju_engines.marriage_resource import _relationship_affinity

    # 식신(월·일지) + 비겁 → 케어 + 당당.
    p = SimpleNamespace(
        year=_pil("비견", "비견"), month=_pil("식신", "식신"),
        day=_pil("정재", "식신"), hour=None,
    )
    aff = _relationship_affinity(p, _fa_stub({"output": 20, "wealth": 5, "peer": 25}, "신강"))
    assert any("식신" in x and "케어" in x for x in aff)
    assert any("비겁" in x and "당당" in x for x in aff)

    # 신약 + 비겁 약 + 식상·재성 → 회피 주의.
    p2 = SimpleNamespace(
        year=None, month=_pil("정재", "정재"), day=_pil("정재", "정재"), hour=None,
    )
    aff2 = _relationship_affinity(p2, _fa_stub({"output": 15, "wealth": 30, "peer": 5}, "신약"))
    assert any("회피" in x or "물러" in x for x in aff2)

    # 인성 과다 → 단점 경향.
    p3 = SimpleNamespace(
        year=_pil("정인", "정인"), month=_pil("편인", "정인"),
        day=_pil("정인", "편인"), hour=None,
    )
    aff3 = _relationship_affinity(p3, _fa_stub({"resource": 40, "peer": 10}, "신강"))
    assert any("인성 과다" in x for x in aff3)


def test_relationship_affinity_rendered_neutral() -> None:
    from saju_engines.structural_context import marriage_resource_lines
    mr = _profile("12:00")
    text = " ".join(marriage_resource_lines(mr))
    if mr.relationship_affinity:
        assert "관계 친화·돌봄 성향" in text
    for banned in ("반드시", "확실히", "최악"):
        assert all(banned not in x for x in mr.relationship_affinity)


# ── 재성 위치 정밀 표기(2026-07-21 데굴님 실로그) — '년월(집안 기반)' 뭉뚱그림 라벨이
# LLM의 '재성이 연주와 월주에 드러남' 오독(연주 庚申=상관·상관)을 만들던 결함 회귀 ──
def _degool_male():
    # 실로그 동일 조건: 1980-11-22 09:00 서울 남 · 진태양시 미적용 → 庚申 丁亥 己亥 己巳.
    return analyze_marriage_resource(
        calculate(
            BirthInput(
                calendar_type="solar", birth_date="1980-11-22", birth_time="09:00",
                birth_place_name="서울", gender="male",
                time_options={"apply_true_solar_time": False},
            )
        )
    )


def test_wealth_positions_exact_pillars() -> None:
    mr = _degool_male()
    # 일간 己 → 재성=水: 월지 亥·일지 亥 정재만 드러남(연주 庚申=상관·상관, 재성 아님).
    assert mr.wealth_positions == ["월지 정재", "일지 정재"]
    assert not any(pos.startswith("년") for pos in mr.wealth_positions)


def test_wealth_line_renders_exact_positions_with_guard() -> None:
    from saju_engines.structural_context import marriage_resource_lines

    text = " ".join(marriage_resource_lines(_degool_male()))
    assert "월지 정재·일지 정재" in text
    assert "옮겨 말하지" in text  # 재성 없는 주(柱)로의 오독 방지 가드
    assert "년월(집안 기반)" not in text  # 뭉뚱그림 라벨 제거


def test_friction_rendered_with_non_stigma_guard() -> None:
    """P1 — 잘 안 맞기 쉬운 결이 렌더되고 낙인·이별 단정 금지 가드를 동반한다."""
    from saju_engines.structural_context import marriage_resource_lines

    mr = _degool_male()  # 일지 亥 본기 壬=정재(wealth군)
    assert mr.ideal_type_friction and "조건·명분만으로" in mr.ideal_type_friction
    text = " ".join(marriage_resource_lines(mr))
    assert "잘 안 맞기 쉬운 결" in text
    assert "낙인·이별 단정 아님" in text


def test_degool_day_branch_jeongjae_refined_label() -> None:
    """실로그 명식(일지 정재) — 세분 라벨 '정재(현실 매력형·단정)'이 적용된다."""
    mr = _degool_male()
    assert "정재(현실 매력형·단정)" in mr.ideal_type_tendency


def test_love_marriage_unified_directive_content() -> None:
    """P2 — 연애운·결혼운 이원 구도 교정 디렉티브(속설 채택 금지·반박 없이 정리)."""
    from saju_engines.structural_context import LOVE_MARRIAGE_UNIFIED_DIRECTIVE

    assert "이원 구도로 답하지 말 것" in LOVE_MARRIAGE_UNIFIED_DIRECTIVE
    assert "일지(배우자궁)" in LOVE_MARRIAGE_UNIFIED_DIRECTIVE
    assert "반박·훈계 없이" in LOVE_MARRIAGE_UNIFIED_DIRECTIVE
