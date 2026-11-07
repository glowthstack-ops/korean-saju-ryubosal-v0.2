"""결혼운 강의 7편 대조층(2026-11-07 데굴님 "1·3 진행 / 2 ON으로 시작 / 4 통설 대조·안내 형태").

SSOT: doc/v2_2/EXTERNAL_TEXT_GAP_MARRIAGE_TIMING_LECTURES.md
P0 결혼 마커 2축(시기 ≠ 길흉) · P1 실험 4종(기본 ON) · P2 서술층 · 참고 통설 안내.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from saju_api.services import report_service
from saju_api.services.manse_service import calculate
from saju_api.services.report_service import _ReportData
from saju_engines import love_timing
from saju_engines.compatibility_engine import analyze_compatibility
from saju_engines.context_reducer import build_birth_summary
from saju_engines.life_graph import MARRIAGE_CAUTION_NOTE, MARRIAGE_FAVORABLE_NOTE
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_engines.love_period_notes import love_period_note_items
from saju_engines.love_timing import (
    LOVE_DEFAULT_ON,
    apply_month_clash_partner_tag,
    apply_partner_star_hap_confluence,
    produce_female_officer_resource_seeds,
    produce_male_peer_breaks_wealth_seeds,
    resolve_love_experiments,
)
from saju_engines.structural_context import (
    MARRIAGE_TWO_AXIS_DIRECTIVE,
    marriage_alt_views_lines,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.compatibility import CompatSignalKind
from saju_shared_types.enums import TenGod
from saju_shared_types.event_engine import (
    ConfidenceLevel,
    EventCandidateV2,
    EventKeyV2,
    LuckLayer,
    PolarityRole,
)
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.life_graph import MarkerKind
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 11, 7)


def _birth(gender: str = "male") -> BirthInput:
    return BirthInput(
        calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender=gender, reference_date="2026-11-07",
    )


def _cand(event: EventKeyV2, score: int, codes: list[str]) -> EventCandidateV2:
    return EventCandidateV2(
        event_key=event, period="2032", score=score,
        confidence_level=ConfidenceLevel.WEAK_EVENT_CANDIDATE,
        polarity_role=PolarityRole.NEUTRAL,
        source_layers=[LuckLayer.SEWOON], candidate_source_layers=["sewoon"],
        source_ten_gods=[], reason_codes=codes, contributions={"base": float(score)},
    )


# ── 실험 플래그 기본 ON ───────────────────────────────────────────────────────


def test_love_experiments_default_on_and_off_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAJU_LOVE_EXPERIMENTS", raising=False)
    monkeypatch.delenv("SAJU_LOVE_EXPERIMENTS_OFF", raising=False)
    flags = resolve_love_experiments()
    assert all(flags[k] for k in LOVE_DEFAULT_ON)
    assert not flags["female_qisha_partner"] and not flags["partner_element_daewoon"]
    # 명시 목록을 줘도 기본 ON 은 유지, off 로만 꺼진다(재생 기준선용).
    flags2 = resolve_love_experiments([], off=["partner_star_hap_confluence"])
    assert not flags2["partner_star_hap_confluence"] and flags2["female_officer_resource"]
    monkeypatch.setenv("SAJU_LOVE_EXPERIMENTS_OFF", "male_peer_breaks_wealth")
    assert not resolve_love_experiments()["male_peer_breaks_wealth"]
    with pytest.raises(ValueError):
        resolve_love_experiments(off=["no_such_rule"])


# ── P1-1 배우자성 운 × 일지 합 동반 ──────────────────────────────────────────


def test_partner_star_hap_confluence_requires_gendered_star_and_day_hap() -> None:
    male_hit = _cand(EventKeyV2.MARRIAGE_SIGNAL, 60, ["SINGLE_ZHENGCAI", "REL_HAP_day_pillar"])
    out = apply_partner_star_hap_confluence([male_hit], "male")
    assert out[0].score == 69 and "LOVE_PARTNER_HAP_CONFLUENCE" in out[0].reason_codes
    # 여성에겐 재성이 배우자성이 아니다 → 불변.
    assert apply_partner_star_hap_confluence([male_hit], "female")[0].score == 60
    # 일지 합 없음·결혼 아님·성별 미상 → 불변.
    no_hap = _cand(EventKeyV2.MARRIAGE_SIGNAL, 60, ["SINGLE_ZHENGCAI"])
    assert apply_partner_star_hap_confluence([no_hap], "male")[0].score == 60
    other = _cand(EventKeyV2.JOB_GAIN, 60, ["SINGLE_ZHENGCAI", "REL_HAP_day_pillar"])
    assert apply_partner_star_hap_confluence([other], "male")[0].score == 60
    assert apply_partner_star_hap_confluence([male_hit], "unknown")[0].score == 60
    # 멱등.
    assert apply_partner_star_hap_confluence(out, "male")[0].score == 69


# ── P1-4 월지 충 동반 태그(점수 0) ───────────────────────────────────────────


def test_month_clash_partner_tag_only_adds_reason() -> None:
    c = _cand(EventKeyV2.NEW_RELATIONSHIP, 40, ["SINGLE_ZHENGGUAN", "REL_CHUNG_month_pillar"])
    out = apply_month_clash_partner_tag([c], "female")
    assert out[0].score == 40 and "LOVE_MONTH_CLASH_ENV_SHIFT" in out[0].reason_codes
    male_out = apply_month_clash_partner_tag([c], "male")[0]
    assert "LOVE_MONTH_CLASH_ENV_SHIFT" not in male_out.reason_codes


# ── P1-2 여성 관인상생 · P1-3 남성 비겁 운 시드 ─────────────────────────────


def _signals(layer: LuckLayer, *gods: TenGod) -> list[SimpleNamespace]:
    return [SimpleNamespace(layer=layer, ten_god=g, strength=1.0) for g in gods]


def test_female_officer_resource_seeds_need_officer_without_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = calculate(_birth("female"))
    sig = _signals(LuckLayer.SEWOON, TenGod.JEONGIN)
    # 이 명식은 인성이 보여 조건 미충족 → 빈 목록.
    assert produce_female_officer_resource_seeds(
        sig, LuckLayer.SEWOON, result, "female", "2032",
    ) == []
    monkeypatch.setattr(love_timing, "_visible_gods", lambda _r: {"정관", "식신"})
    seeds = produce_female_officer_resource_seeds(sig, LuckLayer.SEWOON, result, "female", "2032")
    assert {s.event_key for s in seeds} == {EventKeyV2.MARRIAGE_SIGNAL, EventKeyV2.NEW_RELATIONSHIP}
    assert all("LOVE_FEMALE_OFFICER_RESOURCE" in s.reason_codes for s in seeds)
    # 남성·월운·인성 운 아님 → 빈 목록.
    assert produce_female_officer_resource_seeds(
        sig, LuckLayer.SEWOON, result, "male", "2032",
    ) == []
    assert produce_female_officer_resource_seeds(
        sig, LuckLayer.WOLWOON, result, "female", "2032-03",
    ) == []
    assert produce_female_officer_resource_seeds(
        _signals(LuckLayer.SEWOON, TenGod.JEONGGWAN), LuckLayer.SEWOON, result, "female", "2032",
    ) == []


def test_male_peer_breaks_wealth_seed() -> None:
    result = calculate(_birth("male"))  # 월지·일지 정재 — 재성 가시
    seeds = produce_male_peer_breaks_wealth_seeds(
        _signals(LuckLayer.SEWOON, TenGod.GEOMJAE), LuckLayer.SEWOON, result, "male", "2032",
    )
    assert len(seeds) == 1 and seeds[0].event_key is EventKeyV2.RELATIONSHIP_CHANGE
    assert seeds[0].score == 24
    assert {"LOVE_MALE_PEER_BREAKS_WEALTH", "LOVE_PEER_JIECAI"} <= set(seeds[0].reason_codes)
    assert produce_male_peer_breaks_wealth_seeds(
        _signals(LuckLayer.SEWOON, TenGod.GEOMJAE), LuckLayer.SEWOON, result, "female", "2032",
    ) == []
    assert produce_male_peer_breaks_wealth_seeds(
        _signals(LuckLayer.DAEWOON, TenGod.BIGYEON), LuckLayer.DAEWOON, result, "male", "2032",
    ) == []


# ── P0-1 결혼 마커 2축 ───────────────────────────────────────────────────────


def test_life_graph_marriage_markers_keep_caution_tone_with_two_axis_note() -> None:
    spec = ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01", end="2070-12"),
    )
    data = _ReportData(_birth("male"), spec, _TODAY)
    g = data.life_graph
    assert g is not None
    marriage = [m for m in g.markers if m.kind is MarkerKind.MARRIAGE]
    assert marriage
    for m in marriage:
        assert m.note == (MARRIAGE_CAUTION_NOTE if m.tone == "주의" else MARRIAGE_FAVORABLE_NOTE)
        assert m.age <= 70
    # 이 명식은 현재 대운에 주의 방향 결혼 신호(정재 운, 구신)가 92·93점 — 되돌림으로 다시 보인다.
    assert any(m.tone == "주의" for m in marriage)
    # 희망 창(앞으로 기대할 시기)은 여전히 길·혼합만.
    for w in g.positive_windows:
        if w.kind is MarkerKind.MARRIAGE:
            assert w.peak_score >= 55


# ── P2·참고 통설 서술층 ─────────────────────────────────────────────────────


def test_serializer_palace_hap_labels_and_experiment_codes() -> None:
    ko = reason_codes_ko([
        "REL_HAP_day_pillar", "REL_HAP_month_pillar", "REL_HAP_hour_pillar",
        "REL_BOKEUM_day_pillar", "LOVE_PARTNER_HAP_CONFLUENCE", "LOVE_MONTH_CLASH_ENV_SHIFT",
    ])
    assert any(s.startswith("배우자궁(일지) 합") for s in ko)
    assert any("부모 주선·직장" in s for s in ko) and any("자녀 자리" in s for s in ko)
    assert any("복음" in s for s in ko) and any("합류" in s for s in ko)
    assert any("월지 충 동반" in s for s in ko)
    assert "관계 발동" not in ko  # 궁위별 라벨이 일반 REL_ 라벨보다 먼저 잡힌다


def test_love_period_notes_void_clash_and_female_output() -> None:
    male = calculate(_birth("male"))
    female = calculate(_birth("female"))
    void = male.pillars.gongmang_branches[0]
    # 공망 글자 운 → 참고 통설 병기 줄.
    labels = [lbl for lbl, _ in love_period_note_items(male, f"甲{void}", None)]
    assert "공망 글자 운(참고)" in labels
    # 일지 충(巳) → 충 구절에 통설 병기.
    clash = [n for lbl, n in love_period_note_items(male, "己巳", None) if lbl == "일지 충 인연"]
    assert clash and "통설은 배우자 자리의 변동·지연" in clash[0]
    # 여성 식상 운(일간 己 → 辛 식신) → 두 갈래 병기, 남성은 기존 구절.
    f_note = dict(love_period_note_items(female, "辛酉", None)).get("식상 운 연애 결", "")
    m_note = dict(love_period_note_items(male, "辛酉", None)).get("식상 운 연애 결", "")
    assert "관성(남편 자리)을 흔들어" in f_note and "두 갈래" not in m_note


def test_same_day_pillar_compatibility_signal() -> None:
    result = calculate(_birth("male"))
    useful = build_birth_summary(result).useful_gods
    report = analyze_compatibility(result, result, useful, useful)
    assert report is not None
    kinds = [s.kind for s in report.signals]
    assert CompatSignalKind.DAY_PILLAR_SAME in kinds
    assert CompatSignalKind.DAY_BRANCH_DUPLICATE in kinds


def test_marriage_alt_views_and_two_axis_directive_in_prompts() -> None:
    result = calculate(_birth("male"))
    lines = marriage_alt_views_lines(result)
    assert lines and lines[0].startswith("[결혼 시기 참고 통설")
    assert any("신약 명식" in ln for ln in lines) and any("성사가 어려운 해" in ln for ln in lines)
    assert "하지 마라" in MARRIAGE_TWO_AXIS_DIRECTIVE and "숙고" in MARRIAGE_TWO_AXIS_DIRECTIVE
    spec = ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01", end="2070-12"),
    )
    ctx = {c.section_id: c for c in report_service.plan_report(_birth("male"), spec, _TODAY)}
    f06b = ctx["F-06b"].body_prompt
    assert "[결혼 답 2축 계약]" in f06b and "[결혼 시기 참고 통설" in f06b
    assert "운의 결 주의'는 결혼 불가가 아니라" in ctx["F-14"].body_prompt


# ── 인연 마커·배우자성 대운·실패 이력 시효 (2026-11-07 "제안대로 진행") ─────────


def test_romance_markers_partner_star_daewoon_and_failure_decay() -> None:
    from saju_engines.personal_calibration import _failure_age_decay

    spec = ReportSpec(
        product_code="RPT_FULL",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="1980-01", end="2070-12"),
    )
    data = _ReportData(_birth("male"), spec, _TODAY)
    g = data.life_graph
    assert g is not None
    romance = [m for m in g.markers if m.kind is MarkerKind.ROMANCE]
    assert romance and all(m.tone != "주의" for m in romance)  # 주의 방향 관계 변동은 제외
    assert any(w.kind is MarkerKind.ROMANCE for w in g.positive_windows)
    # 현재 대운 壬辰(정재) — 남성 배우자성 대운 라벨.
    cur = next(d for d in g.daewoons if d.status == "current")
    assert cur.partner_star_daewoon is True
    from saju_engines.life_graph import daewoon_summary_lines

    assert any("[배우자성 대운" in ln for ln in daewoon_summary_lines(g))
    ctx = {c.section_id: c for c in report_service.plan_report(_birth("male"), spec, _TODAY)}
    cur_page = next(
        c for c in ctx.values()
        if c.section_id.startswith("F-14-D") and "[배우자성 대운]" in c.body_prompt
    )
    assert "본격 거론되는 10년" in cur_page.body_prompt
    # 실패 이력 시효 — 10년 초과 0.5, 이내 1.0, 연도 미상 1.0.
    assert _failure_age_decay("2027", "2007") == 0.5
    assert _failure_age_decay("2027", "2020-05") == 1.0
    assert _failure_age_decay("2027", "") == 1.0


# ── 범용 배선(2026-11-07 "테마 리포트·AI 채팅에도 반영됐나") ──────────────────


def test_marriage_layers_apply_to_theme_report_and_chat() -> None:
    from saju_engines.life_graph import PARTNER_STAR_DAEWOON_TAG, partner_star_daewoon_tag

    # 간지 태그 — 己 일간 남성에게 壬辰(정재)은 배우자성 대운, 여성에겐 아니다.
    # 성별 미상은 빈 문자열.
    assert partner_star_daewoon_tag("己", "壬辰", "male") == PARTNER_STAR_DAEWOON_TAG
    assert partner_star_daewoon_tag("己", "壬辰", "female") == ""
    assert partner_star_daewoon_tag("己", "甲寅", "female") == PARTNER_STAR_DAEWOON_TAG  # 甲 정관
    assert partner_star_daewoon_tag("己", "壬辰", None) == ""
    # 테마 애정운 리포트(R-03·R-05) — 2축 계약·성별 서술 형태·참고 통설·배우자성 대운 라벨.
    spec = ReportSpec(
        product_code="RPT_FOCUS", topic="relationship",
        subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        period=ReportPeriod(start="2026-01", end="2030-12"),
    )
    ctx = {c.section_id: c for c in report_service.plan_report(_birth("male"), spec, _TODAY)}
    love_sections = [sid for sid in ctx if sid in ("R-03", "R-05")]
    assert love_sections
    for sid in love_sections:
        body = ctx[sid].body_prompt
        assert "[결혼 답 2축 계약]" in body and "[배우자 서술 형태 — 남성 명식]" in body
        assert "[결혼 시기 참고 통설" in body
    assert any(PARTNER_STAR_DAEWOON_TAG in c.body_prompt for c in ctx.values())


def test_profile_gate_single_no_penalty_married_converts() -> None:
    """미혼은 결혼 신호를 깎지 않고, 기혼은 새 인연·결혼 신호를 관계 이슈로 전환하며 강하면 경계
    태그(2026-11-07 데굴님: 미혼은 근거 아님 / 기혼이 떨어지는 것 / 바람 경고 가능)."""
    from saju_engines.addendum_gate_modifier import AddendumGateModifier, GateContext

    m = AddendumGateModifier()

    def cand(event: str, score: int) -> EventCandidateV2:
        return EventCandidateV2(event_key=event, period="2027", score=score)

    single = m.apply([cand("marriage_signal", 60)], GateContext(relationship_status="single"))
    assert single[0].score == 60 and str(single[0].event_key) == "marriage_signal"
    assert not any("weak" in r for r in single[0].reason_codes)
    ctx = GateContext(relationship_status="married")
    strong = m.apply([cand("marriage_signal", 70)], ctx)[0]
    assert str(strong.event_key) == "relationship_change" and strong.score == 70
    assert "PROFILE_marriage_to_change" in strong.reason_codes
    assert "PROFILE_married_outside_attraction_caution" in strong.reason_codes
    weak = m.apply([cand("new_relationship", 50)], ctx)[0]
    assert str(weak.event_key) == "relationship_change"
    assert "PROFILE_new_relationship_to_change" in weak.reason_codes
    assert "PROFILE_married_outside_attraction_caution" not in weak.reason_codes
    assert any("배우자 외 인연" in s for s in reason_codes_ko(strong.reason_codes))


def test_profile_gate_career_employee_move_and_unemployed() -> None:
    """재직자 취업+이동운 → 이직, 재직자 취업 단독 → 승진, 무직자 이직 → 취업(2026-11-07 데굴님)."""
    from saju_engines.addendum_gate_modifier import AddendumGateModifier, GateContext

    m = AddendumGateModifier()

    def cand(event: str, score: int) -> EventCandidateV2:
        return EventCandidateV2(event_key=event, period="2027", score=score)

    from saju_shared_types.event_engine import TenGod as TG

    emp = GateContext(occupation_status="employee", present_gods={TG.ZHENGGUAN, TG.ZHENGCAI})
    with_move = m.apply([cand("job_gain", 70), cand("relocation", 60)], emp)
    job = next(c for c in with_move if "PROFILE_job_gain_to_career_change_move" in c.reason_codes)
    assert str(job.event_key) == "career_change" and job.score == 70
    alone = m.apply([cand("job_gain", 70), cand("relocation", 30)], emp)
    assert str(alone[0].event_key) == "promotion"
    assert "PROFILE_job_gain_to_promotion" in alone[0].reason_codes
    jobless = m.apply([cand("career_change", 66)], GateContext(occupation_status="unemployed"))
    assert str(jobless[0].event_key) == "job_gain"
    assert "PROFILE_career_change_to_job_gain" in jobless[0].reason_codes
    assert any("이직(직장 옮김)" in s for s in reason_codes_ko(job.reason_codes))

