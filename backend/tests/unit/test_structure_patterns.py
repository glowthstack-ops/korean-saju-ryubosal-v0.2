"""구조 패턴 감지기(Step ②) — 사전 무결성 + 어댑터 감지 + inert 불변식.

설계: doc/v2_2/docs/13_STRUCTURE_PATTERNS.md
"""

from __future__ import annotations

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_chart_interpretation
from saju_engines.context_reducer import serialize_chart_prefix
from saju_engines.structure_patterns import (
    _FAILURE_TO_PID,
    _MAX_LLM_PATTERNS,
    detect_structure_patterns,
    load_structure_patterns,
    select_llm_patterns,
)
from saju_shared_types.birth_input import BirthInput

# EventKeyV2(21종) — domain_hints 정렬 검증용.
_EVENT_KEYS = {
    "career_change", "job_gain", "promotion", "business_start", "business_expansion",
    "wealth_change", "windfall", "contract_document", "education_admission",
    "education_completion", "relationship_change", "new_relationship", "marriage_signal",
    "childbirth", "relocation", "legal_conflict", "health_attention", "social_conflict",
    "preparation_delay", "creative_output", "public_exposure",
}
_POLARITY_MODES = {"favorable", "unfavorable", "depends_on_yonggi_and_control", "context_only"}
_SCOPES = {"natal", "luck", "natal_luck"}


@pytest.fixture(scope="module")
def result():
    return calculate(BirthInput(
        birth_date="1980-11-22", birth_time="09:08",
        birth_place_name="서울", gender="male",
    ))


# ── 사전 무결성 ─────────────────────────────────────────────────────────

def test_dictionary_loads_and_no_dup() -> None:
    dic = load_structure_patterns()
    ids = [p.pattern_id for p in dic.patterns]
    assert len(ids) == len(set(ids)), "중복 pattern_id"
    assert len(ids) == 35, "P0 전체 35종"


def test_dictionary_fields_valid() -> None:
    dic = load_structure_patterns()
    for p in dic.patterns:
        assert p.polarity_mode in _POLARITY_MODES
        assert set(p.domain_hints) <= _EVENT_KEYS, f"{p.pattern_id} domain_hints 미정렬"
        assert len(p.llm_tag) <= 120, f"{p.pattern_id} llm_tag 초과"
        assert p.llm_usage == "explanation_tag_only"


# ── 감지 결과 불변식 ────────────────────────────────────────────────────

def test_detected_patterns_wellformed(result) -> None:
    dic = load_structure_patterns()
    valid_ids = {p.pattern_id for p in dic.patterns}
    detected = detect_structure_patterns(result)
    assert detected, "실제 명식에서 구조 패턴이 하나도 감지되지 않음"
    seen = set()
    for d in detected:
        assert d.pattern_id in valid_ids, f"사전에 없는 pattern_id: {d.pattern_id}"
        assert d.pattern_id not in seen, f"중복 감지: {d.pattern_id}"
        seen.add(d.pattern_id)
        assert 0.0 <= d.strength <= 1.0
        assert d.scope in _SCOPES
        assert d.polarity_mode in _POLARITY_MODES
        assert set(d.domain_hints) <= _EVENT_KEYS
        assert d.favorability is None, "P0: 길흉 미확정(favorability None)"


def test_sorted_by_strength_desc(result) -> None:
    detected = detect_structure_patterns(result)
    strengths = [d.strength for d in detected]
    assert strengths == sorted(strengths, reverse=True)


def test_deterministic(result) -> None:
    a = detect_structure_patterns(result)
    b = detect_structure_patterns(result)
    assert [d.pattern_id for d in a] == [d.pattern_id for d in b]


# ── 어댑터 정합성: 활성 파격 → 대응 pattern_id 감지 ──────────────────────

def test_active_failures_map_to_patterns(result) -> None:
    assert result.geokguk is not None and result.geokguk.evaluation is not None
    detected_ids = {d.pattern_id for d in detect_structure_patterns(result)}
    for f in result.geokguk.evaluation.failures:
        if f.get("active") and f.get("type") in _FAILURE_TO_PID:
            assert _FAILURE_TO_PID[f["type"]] in detected_ids, (
                f"활성 파격 {f['type']} → {_FAILURE_TO_PID[f['type']]} 미감지"
            )


def test_geguk_main_structure_detected(result) -> None:
    """주격이 P0 사전에 있으면 해당 격국 패턴이 감지된다."""
    assert result.geokguk is not None
    detected_ids = {d.pattern_id for d in detect_structure_patterns(result)}
    from saju_engines.structure_patterns import _GEOK_NAME_TO_PID

    pid = _GEOK_NAME_TO_PID.get(result.geokguk.main_structure or "")
    if pid is not None:
        assert pid in detected_ids


# ── Step ④: LLM 입력 배선(캐시 프리픽스, 상한, inert) ─────────────────────

def test_select_llm_patterns_capped_and_ranked(result) -> None:
    detected = detect_structure_patterns(result)
    top = select_llm_patterns(detected)
    assert len(top) <= _MAX_LLM_PATTERNS
    assert [d.pattern_id for d in top] == [d.pattern_id for d in detected[:_MAX_LLM_PATTERNS]]


def test_select_llm_patterns_domain_priority() -> None:
    """domain 지정 시 domain_hints 매칭이 앞으로(비캐시 경로용). strength 내부순서 안정."""
    dic = load_structure_patterns()
    from saju_shared_types.structure_patterns import DetectedPattern

    def mk(pid: str, strength: float, hints: list[str]) -> DetectedPattern:
        return DetectedPattern(
            pattern_id=pid, name_ko=pid, strength=strength,
            polarity_mode="context_only", domain_hints=hints,
        )

    pats = [mk("A", 0.9, ["wealth_change"]), mk("B", 0.8, ["career_change"])]
    assert dic is not None
    # domain=None: strength desc
    assert [d.pattern_id for d in select_llm_patterns(pats)] == ["A", "B"]
    # domain=career_change: B(매칭) 우선
    ordered = select_llm_patterns(pats, domain="career_change")
    assert ordered[0].pattern_id == "B"


def test_chart_interpretation_carries_patterns(result) -> None:
    ci = build_chart_interpretation(result)
    assert ci is not None
    assert len(ci.detected_patterns) <= _MAX_LLM_PATTERNS
    # 결정적: 두 번 빌드해도 동일(캐시 프리픽스 계약).
    ci2 = build_chart_interpretation(result)
    assert ci2 is not None
    assert [p.pattern_id for p in ci.detected_patterns] == [
        p.pattern_id for p in ci2.detected_patterns
    ]


def test_prefix_serialization_deterministic_and_present(result) -> None:
    from saju_engines.context_reducer import build_birth_summary

    ci = build_chart_interpretation(result)
    summary = build_birth_summary(result)
    a = serialize_chart_prefix(summary, ci)
    b = serialize_chart_prefix(summary, ci)
    assert a == b, "고정 프리픽스는 결정적이어야 한다(캐시)"
    if ci is not None and ci.detected_patterns:
        assert any("구조 패턴" in line for line in a), "구조 패턴 블록 누락"
