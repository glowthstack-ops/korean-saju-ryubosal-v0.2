"""사고수 확장 구조 패턴(2026-07-23 승인안 A) — 역마 상대 계산·형 세분·건강 부담.

승인 조건 검증(데굴님 확대안 H장):
- 실제 역마가 아닌 寅申巳亥 충은 YEOKMA_*로 잡히지 않는다(MOVEMENT_BRANCH_CLASH 보조만).
- 연지·일지 기준 상대 역마를 삼합국으로 계산한다(글자살 판정 금지).
- 삼형 완성과 부분 삼형을 구분하고, 부분형은 미완 글자를 기록한다.
- 자형(辰午酉亥)·자묘형을 별도 감지한다.
- 전통 해석 문구(classical_note)는 비단정 프레임('해석')을 지킨다.
"""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.relationship_relative_sinsal import get_relative_sinsal
from saju_engines.structure_patterns import detect_structure_patterns, load_structure_patterns
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.enums import Branch

_NEW_IDS = {
    "YEOKMA_CLASH_ACTIVE", "YEOKMA_PUNISHMENT_ACTIVE", "MOVEMENT_BRANCH_CLASH",
    "THREE_PUNISHMENT_COMPLETE", "THREE_PUNISHMENT_PARTIAL", "SELF_PUNISHMENT",
    "ZI_MAO_PUNISHMENT", "RESOURCE_SUPPORT_WEAK", "MULTI_RELATION_STRESS",
    "ACTION_PRESSURE_EXCESS", "CONTROL_RESOURCE_DEFICIT", "SHARP_INJURY_AUXILIARY",
    "WEALTH_EXPOSURE_WITH_WEAK_CONTROL", "DOCUMENT_AUTHORITY_CONFLICT",
    "IDENTITY_AUTHORIZATION_STRESS", "ELEMENT_EXCESS_ACTIVE", "ELEMENT_DEFICIENCY_ACTIVE",
    "CLIMATE_IMBALANCE_ACTIVE", "HEAT_DRYNESS_BURDEN", "COLD_DAMP_BURDEN",
    "RECOVERY_RESOURCE_WEAK", "SAME_AREA_REPEATED_STRESS", "FLOW_STAGNATION_BURDEN",
}


def _detect(birth_date: str, birth_time: str = "12:30") -> dict[str, list[str]]:
    """대상 차트의 감지 결과를 {pattern_id: evidence} 로 요약한다."""
    result = calculate(BirthInput(
        birth_date=birth_date, birth_time=birth_time,
        birth_place_name="서울", gender="male",
    ))
    return {p.pattern_id: p.evidence for p in detect_structure_patterns(result)}


# ── 사전 무결성 ─────────────────────────────────────────────────────────

def test_new_patterns_registered_with_classical_note() -> None:
    dic = load_structure_patterns()
    by_id = {p.pattern_id: p for p in dic.patterns}
    for pid in _NEW_IDS:
        assert pid in by_id, f"{pid} 사전 미등재"
        entry = by_id[pid]
        assert entry.classical_note, f"{pid} classical_note 누락"
        assert len(entry.classical_note) <= 220
        assert "해석" in entry.classical_note, f"{pid} 비단정 프레임 누락"
        assert len(entry.llm_tag) <= 120


# ── 역마 상대 계산 (글자살 아님 — 삼합국 기준) ─────────────────────────

@pytest.mark.parametrize("base,expected", [
    ("子", "寅"),  # 申子辰 기준 역마 = 寅
    ("寅", "申"),  # 寅午戌 기준 역마 = 申
    ("卯", "巳"),  # 亥卯未 기준 역마 = 巳
    ("酉", "亥"),  # 巳酉丑 기준 역마 = 亥
])
def test_relative_yeokma_table(base: str, expected: str) -> None:
    got = [
        t for t in "子丑寅卯辰巳午未申酉戌亥"
        if get_relative_sinsal(Branch(base), Branch(t)).sinsal == "역마살"
    ]
    assert got == [expected]


def test_yeokma_clash_detected_with_reference() -> None:
    """일지 亥·월지 巳(巳亥충) — 연지 丑 기준 역마 亥가 충에 걸린 역마충."""
    hits = _detect("1985-05-12")  # 丑巳亥午
    assert "YEOKMA_CLASH_ACTIVE" in hits
    assert any("기준 역마" in e for e in hits["YEOKMA_CLASH_ACTIVE"])


def test_non_yeokma_sasaeng_clash_is_movement_only() -> None:
    """巳亥충이 있어도 연·일지 삼합국 역마가 아니면 MOVEMENT_BRANCH_CLASH만(과탐 방지)."""
    hits = _detect("1976-05-06", "22:00")  # 辰巳午亥 — 역마는 寅/申이라 巳亥 무관
    assert "MOVEMENT_BRANCH_CLASH" in hits
    assert "YEOKMA_CLASH_ACTIVE" not in hits
    assert "YEOKMA_PUNISHMENT_ACTIVE" not in hits


# ── 형 세분화 ───────────────────────────────────────────────────────────

def test_three_punishment_complete_and_yeokma_punishment() -> None:
    """寅巳申 전자 성립(일지 관여) — 삼형 완성 + 일지 기준 역마 寅 형."""
    hits = _detect("1986-05-16")  # 寅巳申午
    assert "THREE_PUNISHMENT_COMPLETE" in hits
    assert "THREE_PUNISHMENT_PARTIAL" not in hits
    assert "YEOKMA_PUNISHMENT_ACTIVE" in hits


def test_three_punishment_partial_records_missing_char() -> None:
    """丑未 2자만 성립 — 부분 삼형으로 구분하고 미완 글자(戌)를 기록한다."""
    hits = _detect("1975-01-13")  # 寅丑未午
    assert "THREE_PUNISHMENT_PARTIAL" in hits
    assert "THREE_PUNISHMENT_COMPLETE" not in hits
    assert any("戌" in e for e in hits["THREE_PUNISHMENT_PARTIAL"])


def test_self_punishment_detected() -> None:
    """午午 병존 — 자형 별도 감지."""
    hits = _detect("1975-01-12")  # 寅丑午午
    assert "SELF_PUNISHMENT" in hits


# ── 보조·건강 신호 불변식 ───────────────────────────────────────────────

def test_resource_support_weak_single_state() -> None:
    """인성 지원 약화는 세분 상태 1개만 기록한다(부재/잠복/약/피극 배타)."""
    hits = _detect("1986-05-16")
    if "RESOURCE_SUPPORT_WEAK" in hits:
        states = [e for e in hits["RESOURCE_SUPPORT_WEAK"] if e.startswith("상태:")]
        assert len(states) == 1


def test_detection_inert_and_deterministic() -> None:
    """신규 감지는 결정적이며 favorability(길흉)를 만들지 않는다(inert)."""
    result = calculate(BirthInput(
        birth_date="1986-05-16", birth_time="12:30",
        birth_place_name="서울", gender="male",
    ))
    a = detect_structure_patterns(result)
    b = detect_structure_patterns(result)
    assert [(p.pattern_id, p.strength) for p in a] == [(p.pattern_id, p.strength) for p in b]
    assert all(p.favorability is None for p in a)
