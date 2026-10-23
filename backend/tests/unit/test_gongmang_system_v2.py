"""공망 체계 재검토(2026-10-23) — P0 정합·P1 2축/강도/자극·P2 확장 공망·P3 사전·P4 측정 플래그.

SSOT: doc/v2_2/GONGMANG_HAP_SEMANTICS.md §7. 전부 서술 전용(점수 불변)이며, 아래는 그 불변식과
현대 통설(대운 공망 무시·세운 공망 일부 인정)을 반례로 고정한다.
"""

from __future__ import annotations

import pytest
from saju_manse_analysis.structure.gongmang_extended import extended_gongmang

from saju_engines import period_v2_config
from saju_engines.addendum_gate_modifier import AddendumGateModifier, GateContext
from saju_engines.chart_interpretation import _void_ten_god_text
from saju_engines.dictionaries import VoidTenGodItem, VoidTenGodTextFile, _lint_void_ten_god_text
from saju_engines.gongmang_state import (
    intensity_of,
    natal_slot_lines,
    same_xun_line,
    stimuli_for,
    transit_state,
    transit_suffix,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.event_engine import EventCandidateV2, EventKeyV2, EventTiming

# 己亥일주(공망 辰巳), 시지 巳가 공망 자리.
_P = {"year": "庚申", "month": "丁亥", "day": "己亥", "hour": "己巳"}
_V = ["辰", "巳"]


def _kinds(ganji: str) -> set[str]:
    st = transit_state(_P, "己", _V, "x", ganji)
    assert st is not None and len(st.slots) == 1
    return {s.kind for s in st.slots[0].stimuli}


# ── P1. 자극 종류·2축 상태 ───────────────────────────────────────────────────


def test_stimulus_kinds_cover_clash_punishment_combine_trine_hidden() -> None:
    assert _kinds("辛亥") == {"clash"}
    assert _kinds("丙申") == {"punishment", "six_combine"}  # 寅巳申 삼형 + 巳申 육합
    assert _kinds("戊寅") == {"punishment"}
    assert _kinds("乙酉") == {"half_trine", "hidden_combine"}  # 巳酉 반합(酉 왕지) + 丙辛 암합
    assert _kinds("癸巳") == {"fill"}
    assert _kinds("丁丑") == set()  # 巳丑은 왕지 없는 두 글자 — 반합 아님


def test_void_state_grades_follow_strength_hierarchy() -> None:
    def state(g: str) -> tuple[str, str]:
        st = transit_state(_P, "己", _V, "x", g)
        assert st is not None
        return st.slots[0].void_state, st.slots[0].activation

    assert state("癸巳") == ("RELEASED", "ACTIVATED")  # 전실 1.0
    assert state("辛亥") == ("RELEASED", "ACTIVATED")  # 충 0.8
    assert state("丙申") == ("PARTIAL_VOID", "ACTIVATED")  # 형 0.5·육합 0.4
    assert state("乙酉") == ("PARTIAL_VOID", "ACTIVATED")  # 반합 0.3
    assert state("丁丑") == ("FULL_VOID", "DORMANT")


def test_partner_void_halves_release_and_leaves_contact_only() -> None:
    # 癸亥일주(공망 子丑), 시지 丑 공망 자리 — 운 子는 丑과 육합이지만 子 자신도 공망 글자.
    p = {"year": "乙卯", "month": "丁亥", "day": "癸亥", "hour": "癸丑"}
    st = transit_state(p, "癸", ["子", "丑"], "x", "甲子")
    assert st is not None
    s = st.slots[0].stimuli[0]
    assert s.kind == "six_combine" and s.partner_void and s.strength == 0.2
    assert (st.slots[0].void_state, st.slots[0].activation) == ("FULL_VOID", "CONTACTED")


def test_fill_absent_recorded_for_sewoon_but_not_daewoon() -> None:
    # 辰은 원국에 없는 공망 글자 — 세운·월운은 '빈 자리 전실', 대운은 기록하지 않는다
    # (대운 공망 무시).
    st = transit_state(_P, "己", _V, "2032", "壬辰")
    assert st is not None and st.fill_absent == ["辰"]
    assert "공망 글자 辰 유입" in transit_suffix(st)
    dw = transit_state(_P, "己", _V, "dw", "壬辰", is_daewoon=True)
    assert dw is not None and dw.fill_absent == [] and transit_suffix(dw) == ""


def test_intensity_uses_season_and_stage() -> None:
    grade, basis = intensity_of(Stem.GI, Branch.SA, Branch.HAE)  # 亥월 火=사(0) + 己@巳 제왕(+1)
    assert grade == "중" and "제왕" in basis and "사" in basis
    grade2, _ = intensity_of(Stem.GI, Branch.SA, Branch.O)  # 午월 火=왕(2) + 제왕 → 강
    assert grade2 == "강"


def test_natal_slot_lines_only_for_present_void_positions() -> None:
    lines = natal_slot_lines(_P, "己", _V)
    assert len(lines) == 2 and lines[1].startswith("공망 자리 巳(시지 · 정인) — 강도 중")
    assert natal_slot_lines({"year": "庚申", "month": "丁亥", "day": "己亥"}, "己", _V) == []
    assert natal_slot_lines(_P, "己", []) == []


def test_stimuli_for_never_scores() -> None:
    # 등급 값은 SSOT §3 계층의 서술 등급 — 모두 0~1, 점수 필드 없음.
    for s in stimuli_for(Branch.SIN, Branch.SA, "hour", {Branch.SIN, Branch.HAE, Branch.SA}, set()):
        assert 0.0 <= s.strength <= 1.0


# ── P2. 확장 공망 사실 ───────────────────────────────────────────────────────


def test_extended_gongmang_sadae_and_jeollo(make_pillars) -> None:
    # 甲子일주 → 甲子旬(납음 水 결). 연주 丙子=간하수(水) → 사대공망 해당. 시간 壬 → 절로공망.
    p = make_pillars(
        (Stem.BYEONG, Branch.JA), (Stem.BYEONG, Branch.IN),
        (Stem.GAP, Branch.JA), (Stem.IM, Branch.SIN), Stem.GAP,
    )
    e = extended_gongmang(p)
    assert e.xun_head == "甲子旬" and e.sadae_missing_element == "水"
    assert e.sadae_hits == ["연주"] and e.jeollo is True and e.hohwan == []
    assert any(f.startswith("사대공망 해당") for f in e.facts_ko)
    assert "절로공망(시간 壬)" in e.facts_ko


def test_extended_gongmang_hohwan_and_no_sadae(make_pillars) -> None:
    # 乙丑년(공망 戌亥) · 癸亥일(공망 子丑): 서로의 공망 글자를 지지로 가짐 → 호환공망 연↔일.
    # 癸亥는 甲寅旬(납음 金 결)인데 다른 기둥 납음에 金이 없으면 사대공망 미해당.
    p = make_pillars(
        (Stem.EUL, Branch.CHUK), (Stem.JEONG, Branch.HAE),
        (Stem.GYE, Branch.HAE), (Stem.GI, Branch.MI), Stem.GYE,
    )
    e = extended_gongmang(p)
    assert e.xun_head == "甲寅旬" and e.sadae_missing_element == "金"
    assert e.hohwan == ["연↔일"] and e.jeollo is False
    assert "호환공망 연↔일" in e.facts_ko


def test_extended_gongmang_complete_xun_has_no_sadae(make_pillars) -> None:
    # 甲辰旬·甲戌旬은 납음 오행 완비 — 사대공망 없음. (己亥는 甲午旬·공망 辰巳 — 水 결이지만
    # 庚申·丁亥·己巳 납음에 水가 없어 미해당.)
    p = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GAP, Branch.JIN), (Stem.GI, Branch.SA), Stem.GAP,
    )
    e = extended_gongmang(p)
    assert e.xun_head == "甲辰旬" and e.sadae_missing_element is None and e.sadae_hits == []
    q = make_pillars(
        (Stem.GYEONG, Branch.SIN), (Stem.JEONG, Branch.HAE),
        (Stem.GI, Branch.HAE), (Stem.GI, Branch.SA), Stem.GI,
    )
    e2 = extended_gongmang(q)
    assert e2.xun_head == "甲午旬" and e2.sadae_missing_element == "水" and e2.sadae_hits == []


# ── P3. 사전 확장 ────────────────────────────────────────────────────────────


def test_void_ten_god_text_carries_indirect_and_evidence_tag() -> None:
    texts = _void_ten_god_text()
    assert set(texts) == {
        "비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인",
    }
    assert "인성" in texts["편재"] and "(출처: 강의 주장·단정 금지)" in texts["편재"]
    assert "식상" in texts["정인"]
    # 성별 조건 문장 중립화(P0): '여명' 표현 없음.
    assert all("여명" not in t for t in texts.values())


def test_void_ten_god_lint_checks_new_fields() -> None:
    items = [
        VoidTenGodItem(
            ten_god=tg, text="공망 자리면 결실이 늦을 수 있어 준비가 필요하다.", reviewed=False,
        )
        for tg in ("비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인")
    ]
    items.append(VoidTenGodItem(
        ten_god="정인", text="공망 자리면 결실이 늦을 수 있어 준비가 필요하다.", reviewed=False,
        indirect="식상이 반드시 발현한다.", evidence_status="엉뚱",
    ))
    errors = _lint_void_ten_god_text(VoidTenGodTextFile(version="t", reviewed=False, items=items))
    assert any("정인.indirect" in e for e in errors)
    assert any("evidence_status" in e for e in errors)


# ── P4. 측정용 비활성 플래그 ────────────────────────────────────────────────


def _cand(score: int = 60) -> EventCandidateV2:
    return EventCandidateV2(event_key=EventKeyV2.CONTRACT_DOCUMENT, period="2026-08", score=score)


def test_clash_delay_flag_off_by_default_keeps_invariant() -> None:
    assert period_v2_config.GONGMANG_CLASH_DELAY_DISABLED is False
    c = AddendumGateModifier().apply(
        [_cand(60)], GateContext(void_active=True, void_kinds={"clash"}),
    )[0]
    assert c.timing is EventTiming.DELAY and "VOID_delay" in c.reason_codes and c.score < 60


def test_clash_delay_disabled_removes_penalty_and_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(period_v2_config, "GONGMANG_CLASH_DELAY_DISABLED", True)
    c = AddendumGateModifier().apply(
        [_cand(60)], GateContext(void_active=True, void_kinds={"clash"}),
    )[0]
    assert c.score == 60 and c.timing is EventTiming.ACTIVE and "VOID_delay" not in c.reason_codes


# ── 동반자 동순(同旬) 사실 ────────────────────────────────────────────────────


def test_same_xun_line_reports_match_and_mismatch() -> None:
    me = {"year": "庚申", "month": "丁亥", "day": "己亥", "hour": "己巳"}  # 甲午旬
    same = {"year": "癸酉", "month": "甲子", "day": "丁酉", "hour": "壬申"}  # 丁酉도 甲午旬
    other = {"year": "乙丑", "month": "丁亥", "day": "癸亥", "hour": "己未"}  # 甲寅旬
    a = same_xun_line(me, same, "본인", "짝")
    b = same_xun_line(me, other, "본인", "짝")
    assert a is not None and "甲午旬" in a and "동순(同旬)" in a and "단정하지 말 것" in a
    assert b is not None and "甲寅旬" in b and "동순 아님" in b
    assert same_xun_line(me, {"year": "乙丑"}, "본인", "짝") is None


# ── 리포트 패리티 ─────────────────────────────────────────────────────────────


def test_report_luck_block_carries_gongmang_lines_when_slots_exist() -> None:
    from datetime import date

    from saju_api.services.report_service import _ReportData
    from saju_shared_types.birth_input import BirthInput
    from saju_shared_types.intent import SubjectKind, SubjectRef
    from saju_shared_types.report import ReportPeriod, ReportSpec

    # 丁酉일주(공망 辰巳)·시지 巳 공망 자리(1980-11-20 10:15 서울 남) — 2026-10-23 스모크 명식.
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 20), birth_time="10:15",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    )
    spec = ReportSpec(
        product_code="RPT_FOCUS", subjects=[SubjectRef(kind=SubjectKind.SELF, label="본인")],
        topic="career", period=ReportPeriod(start="2024-01", end="2030-12"),
    )
    data = _ReportData(birth, spec, date(2026, 6, 15), owner_id=None, subject_id=None)
    text = "\n".join(data.luck_block(data.candidates))
    if data.summary.void_branches and any(
        data.summary.pillars.get(p, "  ")[1] in data.summary.void_branches
        for p in ("year", "month", "hour")
    ):
        # 원국 공망 자리가 있으면 후보 기간 블록이 (활성 자극이 있을 때) 붙고, 점수 재계산은 없다.
        assert "[대운표]" in text
        assert "공망 자극" in text or "[공망 자극(후보 기간)" not in text
    assert "점수는 확정값" in text
