"""Phase 8.5 사용자 프로필 & 페르소나 검증 (T8.5.1~T8.5.11 — docs/11 전체 규격)."""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.persona import PersonaEngine
from saju_engines.prediction import PredictionEngines
from saju_engines.profile_engine import (
    JustInTimeTracker,
    OccupationTaxonomy,
    apply_extracted_updates,
    approx_hour_candidates,
    basic_to_birth_input,
    chart_variant_state,
    children_registration_suggestions,
    delete_extended_field,
    marital_routing,
    render_twin_notice,
    twin_adjusted_hour_pillar,
)
from saju_shared_types.events import EventKey
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.profile import (
    BasicProfile,
    BirthPlace,
    ChildItem,
    Children,
    ExtendedProfile,
    MultipleBirth,
    Occupation,
    PersonaConfig,
    SpeechConfig,
    UserHonorific,
)

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def _basic(**over) -> BasicProfile:
    base = dict(
        birth_date="1980-11-22", birth_time="09:08",
        birth_place=BirthPlace(city="서울"), gender="M", display_name="홍길동",
    )
    base.update(over)
    return BasicProfile(**base)


# ── T8.5.1 — 1단계 변환(만세력 보정 재사용) ──────────────────────


def test_basic_profile_to_birth_input_and_calculate() -> None:
    """BasicProfile → BirthInput → 기존 엔진 계산(보정 재구현 금지)."""
    bi = basic_to_birth_input(_basic())
    assert bi.birth_place_name == "서울" and bi.gender == "male"
    result = calculate(bi)
    assert result.pillars is not None and result.pillars.hour is not None


def test_time_unknown_three_pillar_mode() -> None:
    """시간 모름 → 3주 모드(시주 None) — 차단 아님(A13)."""
    bi = basic_to_birth_input(_basic(birth_time=None, birth_time_unknown=True))
    result = calculate(bi)
    assert result.pillars is not None and result.pillars.hour is None


def test_birth_time_approx_candidates() -> None:
    """대략 시간대 → 시주 후보 2~3개 병기(단일 확정 금지)."""
    assert 2 <= len(approx_hour_candidates("저녁")) <= 3
    assert len(approx_hour_candidates("새벽")) == 3


# ── T8.5.10/11 — 쌍둥이 시주 조정(2-2 규격) ──────────────────────


def test_twin_second_advances_one_step() -> None:
    """문서 예시: 乙丑(축시) 기준 둘째 → 丙寅, 셋째 → 丁卯."""
    # 乙丑시 → 일간은 시두법 역산: 丑(idx1)에서 乙(idx1) → 子시 천간 甲 → 甲/己일.
    assert twin_adjusted_hour_pillar("乙", "丑", "甲", 2) == ("丙", "寅", False)
    assert twin_adjusted_hour_pillar("乙", "丑", "甲", 3) == ("丁", "卯", False)


def test_twin_first_unchanged() -> None:
    stem, branch, wrapped = twin_adjusted_hour_pillar("乙", "丑", "甲", 1)
    assert (stem, branch, wrapped) == ("乙", "丑", False)


def test_twin_wrap_keeps_day_and_uses_sidubeop() -> None:
    """亥→子 wrap: 시주 1기둥만 조정 — 천간은 원 일간 기준 시두법."""
    # 甲일 亥시 = 乙亥. 둘째 → 子시 wrap → 甲일 시두법 子시 천간 = 甲 → 甲子.
    stem, branch, wrapped = twin_adjusted_hour_pillar("乙", "亥", "甲", 2)
    assert wrapped is True
    assert (stem, branch) == ("甲", "子")  # 일주·년주·월주는 호출 측에서 불변 유지


def test_chart_variant_state() -> None:
    """order=1: original만 / order≥2: 둘 다 + 기본 active=twin_adjusted."""
    single = chart_variant_state(1)
    assert single.available == ["original"] and single.twin_shift == 0
    twin = chart_variant_state(2)
    assert set(twin.available) == {"original", "twin_adjusted"}
    assert twin.active == "twin_adjusted" and twin.twin_shift == 1


def test_twin_notice_fixed_template() -> None:
    """안내 문구는 고정 템플릿 치환만(즉석 작문 금지) + 양방향."""
    adjusted = render_twin_notice(2, "丙寅", "乙丑", "twin_adjusted")
    assert "둘째" in adjusted and "丙寅" in adjusted and "乙丑" in adjusted
    assert "말년·자녀·아랫사람·내면" in adjusted
    original = render_twin_notice(2, "丙寅", "乙丑", "original")
    assert "조정된 시주" in original  # 반대 방향 문구


def test_multiple_birth_order_validation() -> None:
    with pytest.raises(ValueError):
        MultipleBirth(total=2, order=3)


# ── T8.5.3 — occupation 분류·E3/E6 연동 ──────────────────────────


def test_occupation_taxonomy_full_18() -> None:
    """O01~O18 닫힌 분류 전체 + 물상 매핑 존재."""
    tax = OccupationTaxonomy(_DICTS)
    for i in range(1, 19):
        assert tax.category(f"O{i:02d}") is not None
    o14 = tax.category("O14")
    assert o14 is not None and o14["imagery"] == ["역마", "편재"]


def test_occupation_form_bias_o14_relocation() -> None:
    """역마+O14 → '출장·파견' 가중(docs/11 용도 1)."""
    tax = OccupationTaxonomy(_DICTS)
    assert tax.form_bias("O14", "relocation") == "출장·파견"
    assert tax.form_bias("O01", "relocation") is None


def test_occupation_context_feeds_manifestation() -> None:
    """occupation → reality_context → E6 modifier(±10 한도, 미입력 보정 0)."""
    tax = OccupationTaxonomy(_DICTS)
    extended = ExtendedProfile(occupation=Occupation(category_id="O14"))
    ctx = tax.reality_context(extended)
    # 운송/여행 직군 → relocation 보정(21키 이관으로 travel이 relocation에 병합, 클램프 ≤10).
    assert ctx["relocation"] >= 8 and all(-10 <= v <= 10 for v in ctx.values())
    assert tax.reality_context(None) == {}  # 미입력 → 보정 0(차단 금지)

    # E6 실연동.
    chart = calculate(basic_to_birth_input(_basic(), None).model_copy(
        update={"reference_date": __import__("datetime").date(2026, 6, 11)}
    ))
    engines = PredictionEngines(_DICTS)
    from saju_engines import EventEngineV2

    cands = EventEngineV2(_DICTS).score_legacy(chart, levels={GanjiLevel.YEAR})
    reloc = next((c for c in cands if c.event_key is EventKey.RELOCATION), None)
    if reloc is not None:
        profile = engines.self_profile(chart)
        m = engines.manifestation(reloc, profile, reality_context=ctx)
        assert m.context_modifier == 8 and m.confidence == "medium_high"


# ── T8.5.4 — 결혼 상태/자녀 분기 ─────────────────────────────────


def test_marital_routing_rules() -> None:
    """기혼 연애운 → 배우자 관계 우선+확인 / 이혼·사별 → 재혼 / 미입력 → 가정 금지."""
    married = marital_routing("기혼", "relationship")
    assert married["module"] == "M02" and married["needs_confirmation"]
    divorced = marital_routing("이혼", "relationship")
    assert divorced["module"] == "M02_REMARRIAGE"
    unknown = marital_routing(None, "relationship")
    assert unknown["needs_confirmation"]  # '미혼' 가정하지 않음
    other = marital_routing(None, "career")
    assert not other["needs_confirmation"]


def test_children_registration_suggested_not_forced() -> None:
    children = Children(count=2, items=[
        ChildItem(label="첫째", birth_date="2015-03-02"),
        ChildItem(label="둘째"),  # 출생 정보 없음 → 제안 대상 아님
    ])
    assert children_registration_suggestions(children) == ["첫째"]
    assert children_registration_suggestions(None) == []


# ── T8.5.2/9 — Just-in-time + 미입력 영향표 ──────────────────────


def test_jit_request_once_and_no_retry_after_decline() -> None:
    """필드별 1회 요청, 거절 시 같은 세션 재요청 금지 + 한계 고지."""
    jit = JustInTimeTracker()
    assert jit.should_request("residence_region") is True
    assert jit.should_request("residence_region") is False  # 재요청 금지
    notice = jit.mark_declined("occupation")
    assert "일반형" in notice
    assert jit.should_request("occupation") is False


def test_missing_fields_never_block() -> None:
    """T8.5.9: 2단계 전부 미입력이어도 엔진 동작 + 한계 고지만(4장 영향표)."""
    tax = OccupationTaxonomy(_DICTS)
    empty = ExtendedProfile()
    assert tax.reality_context(empty) == {}
    routing = marital_routing(None, "relationship")
    assert "module" in routing  # 오류 없이 분기
    jit = JustInTimeTracker()
    for field in ("birth_time", "occupation", "residence_region",
                  "living_room_facing", "marital_status", "children"):
        assert jit.limitation_notice(field)  # 전 필드 고지 문구 존재


def test_delete_field_invalidates_cache() -> None:
    """개별 삭제 → 관련 캐시 무효화 신호(1장 원칙 4)."""
    extended = ExtendedProfile(occupation=Occupation(category_id="O09"))
    updated, invalidations = delete_extended_field(extended, "occupation")
    assert updated.occupation is None
    assert "reality_context" in invalidations


# ── T8.5.8 — 대화 추출 → 확인 → 갱신(F9) ─────────────────────────


def test_extracted_updates_require_confirmation() -> None:
    """확인 전 저장 금지(무단 저장 금지) → 확인 후 갱신+무효화."""
    extended = ExtendedProfile()
    same, questions, _ = apply_extracted_updates(
        extended, {"marital_status": "기혼"}, confirmed=False,
    )
    assert same is extended and questions  # 저장 안 됨 + 확인 질문
    updated, qs, invalidations = apply_extracted_updates(
        extended, {"marital_status": "기혼"}, confirmed=True,
    )
    assert updated is not None and updated.marital_status == "기혼" and not qs
    assert "m01_m02_routing" in invalidations


# ── T8.5.5 — 페르소나 조합 제약(5-2) ─────────────────────────────


@pytest.fixture(scope="module")
def persona_engine() -> PersonaEngine:
    return PersonaEngine(_DICTS)


def test_speech_combo_enforced_by_schema() -> None:
    with pytest.raises(ValueError):
        SpeechConfig(politeness="jondae", style="banmal_chae")
    with pytest.raises(ValueError):
        SpeechConfig(politeness="banmal", style="haeyo")


def test_honorific_constraints(persona_engine) -> None:
    """jondae↔neo 불가 / banmal↔gogaeknim 불가 / jane→hagae 전용."""
    bad = PersonaConfig(user_honorific=UserHonorific(preset_id="neo"))  # 기본 jondae
    assert not persona_engine.validate(bad).valid

    bad2 = PersonaConfig(
        speech=SpeechConfig(politeness="banmal", style="banmal_chae"),
        user_honorific=UserHonorific(preset_id="gogaeknim"),
    )
    assert not persona_engine.validate(bad2).valid

    jane_ok = PersonaConfig(
        speech=SpeechConfig(politeness="banmal", style="hagae"),
        user_honorific=UserHonorific(preset_id="jane"),
    )
    assert persona_engine.validate(jane_ok).valid

    jane_bad = PersonaConfig(
        speech=SpeechConfig(politeness="banmal", style="banmal_chae"),
        user_honorific=UserHonorific(preset_id="jane"),
    )
    assert not persona_engine.validate(jane_bad).valid


def test_custom_honorific_banned_words(persona_engine) -> None:
    bad = PersonaConfig(user_honorific=UserHonorific(type="custom", custom_text="바보야"))
    result = persona_engine.validate(bad)
    assert not result.valid and any("금칙어" in e for e in result.errors)


# ── T8.5.6 — 프롬프트 블록(템플릿 치환 전용) ─────────────────────


def test_persona_block_is_template_substitution(persona_engine) -> None:
    """기본 페르소나 블록 — 슬롯 치환 결과 검증(즉석 작문 금지)."""
    block = persona_engine.build_block(PersonaConfig(), "길동")
    assert block.startswith("[페르소나 — 필수 준수]")
    assert "40대 여성 사주 상담가" in block
    assert '"길동님"' in block
    assert "해요체" in block and "~예요" in block
    assert "점수·날짜·간지·판정을 바꾸는 것" in block  # 문체 전용 고지(절대 원칙 12)


def test_persona_block_rejects_invalid(persona_engine) -> None:
    bad = PersonaConfig(user_honorific=UserHonorific(preset_id="neo"))
    with pytest.raises(ValueError):
        persona_engine.build_block(bad, "길동")


# ── T8.5.7 — 준수 검사 4종(5-4) ──────────────────────────────────


def test_compliance_pass(persona_engine) -> None:
    text = "올해 흐름이 참 좋네요. 상반기에 기회가 보여요. 길동님께 잘 맞는 시기예요."
    report = persona_engine.check_compliance(text, PersonaConfig(), "길동")
    assert report.passed and report.ending_ratio >= 0.95


def test_compliance_catches_politeness_mix(persona_engine) -> None:
    """③ 존대 혼용 — 해요체 설정에 반말 어미."""
    text = "올해 흐름이 좋네요. 그런데 하반기는 조심해야 해. 결정은 미루는 게 좋겠어요."
    report = persona_engine.check_compliance(text, PersonaConfig(), "길동")
    assert not report.passed
    assert any("혼용" in v or "95%" in v for v in report.violations)


def test_compliance_easy_unexplained_terms(persona_engine) -> None:
    """④ easy 난이도 — 미해설 전문용어 0건."""
    easy = PersonaConfig(difficulty="easy")
    bad = "올해는 편관이 강해지는 해예요. 부담이 커질 수 있어요."
    report = persona_engine.check_compliance(bad, easy, "길동")
    assert not report.passed and any("편관" in v for v in report.violations)
    ok = "올해는 편관(외부에서 오는 부담의 기운)이 강해지는 해예요. 어깨가 무거워질 수 있어요."
    assert persona_engine.check_compliance(ok, easy, "길동").passed


def test_compliance_wrong_honorific(persona_engine) -> None:
    """② 허용 외 호칭 사용 검출."""
    text = "고객님, 올해 흐름이 좋네요. 기회가 보여요."
    report = persona_engine.check_compliance(text, PersonaConfig(), "길동")
    assert not report.passed and any("고객님" in v for v in report.violations)
