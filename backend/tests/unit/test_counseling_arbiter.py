"""상담 결론 arbiter(P1) — truth table·outcome 규칙·도메인 캡·불변식(INV-B/D/F/G).

승인 픽스처(2026-08-21): F1 활성高+과정마찰+결과유리 → 과정 진행 유지 /
F2 활성高+결정불리 → 기회·과정 진행, 결정 조건부 / F3 활성低+결과유리 → 기회 진행(수용형)
/ F5 배경저점 단독 → HOLD 없음(INV-B) / F6 배경호운+국소불리 → 조건부(호운이 캡 해제 못 함).
"""

from __future__ import annotations

from datetime import date

from saju_engines import counseling_arbiter as ca
from saju_shared_types.llm_input import LlmEventCandidate, MonthOverviewRow


def _cand(**kw) -> LlmEventCandidate:
    base = dict(
        event_key="job_gain", event_ko="구직·채용 국면", period="2026-12", ganji="庚子",
        daewoon_context="", score=80, confidence="medium", polarity="neutral",
    )
    base.update(kw)
    return LlmEventCandidate(**base)


def _row(period: str, grade: str) -> MonthOverviewRow:
    return MonthOverviewRow(period=period, ganji="庚子", luck_grade=grade)


# ── outcome_outlook 규칙 (INV-D: 무근거 → unknown, mixed/neutral 자동 폴백 금지) ──


def test_outcome_unknown_not_mixed_when_no_evidence() -> None:
    sem = ca.build_counseling(_cand(activation=80.0, favorability=0.0))
    assert sem.outcome_outlook == "unknown"


def test_outcome_bands() -> None:
    assert ca.build_counseling(_cand(favorability=0.7)).outcome_outlook == "favorable"
    assert ca.build_counseling(
        _cand(favorability=0.7, result_nuance="leak")).outcome_outlook == "workable"
    assert ca.build_counseling(_cand(favorability=-0.7)).outcome_outlook == "adverse"
    assert ca.build_counseling(
        _cand(favorability=0.0, result_nuance="unfavorable")).outcome_outlook == "weak"
    assert ca.build_counseling(
        _cand(favorability=0.0, quality="mixed")).outcome_outlook == "mixed"
    assert ca.build_counseling(
        _cand(favorability=0.0, evidence_path=["EXAM_FAIL_pattern"])
    ).outcome_outlook == "adverse"


# ── truth table ──────────────────────────────────────────────────────────────


def test_friction_does_not_demote_proceed() -> None:
    # INV-G / T6: 압박·지연 마찰만으로는 PROCEED 가 깎이지 않는다(F1의 골자).
    sem = ca.build_counseling(_cand(
        activation=90.0, favorability=0.7, quality="pressure",
        evidence_path=["VOID_delay"],
    ))
    assert sem.stage_action_policy["process"] == "proceed"
    assert sem.stage_action_policy["opportunity"] == "proceed"
    assert sem.summary_stance == "PROCEED"
    kinds = {m.kind.value for a in sem.stages for m in a.frictions}
    assert {"pressure", "delay"} <= kinds  # 마찰은 별도 축으로 보존


def test_f2_decision_conditional_when_nuance_unfavorable() -> None:
    # F2: 기회·과정은 진행, 결정만 조건부 — 단일 PWC 가 아니라 단계 분해가 정본(INV-A).
    sem = ca.build_counseling(_cand(
        activation=90.0, favorability=0.0, result_nuance="unfavorable", review_month=True,
    ))
    assert sem.stage_action_policy["opportunity"] == "proceed"
    assert sem.stage_action_policy["decision"] == "conditional"
    assert sem.summary_stance == "PROCEED_WITH_CONDITIONS"


def test_f3_low_activation_favorable_outcome() -> None:
    sem = ca.build_counseling(_cand(activation=30.0, favorability=0.5))
    assert sem.activation_band == "low"
    assert sem.outcome_outlook == "favorable"
    assert sem.stage_action_policy["opportunity"] == "proceed"  # 수용형은 밴드+계약으로 표현


def test_t3_hold_requires_blocking_evidence() -> None:
    # INV-F: 비차단 불리는 CONDITIONAL, 차단형 게이트가 있어야 HOLD.
    soft = ca.build_counseling(_cand(favorability=-0.7))
    assert soft.stage_action_policy["decision"] == "conditional"
    hard = ca.build_counseling(_cand(
        event_key="business_start", favorability=-0.7,
        evidence_path=["GATE_business_start_no_wealth"],
    ))
    assert hard.stage_action_policy["decision"] == "hold"
    assert hard.summary_stance == "HOLD"


# ── INV-B: 배경 운 비거부권 (F5·F6) ─────────────────────────────────────────


def test_f5_low_luck_backdrop_never_creates_hold() -> None:
    sem = ca.build_counseling(
        _cand(activation=80.0, favorability=0.5),
        [_row("2026-12", "강한 기신운")],
    )
    assert "hold" not in sem.stage_action_policy.values()
    assert sem.summary_stance == "PROCEED"
    assert "배경 저점" in sem.luck_backdrop  # 주석으로만 실린다


def test_f6_good_luck_backdrop_never_lifts_conditional() -> None:
    sem = ca.build_counseling(
        _cand(activation=80.0, favorability=0.0, result_nuance="unfavorable"),
        [_row("2026-12", "강한 용신운")],
    )
    assert sem.stage_action_policy["decision"] == "conditional"
    assert sem.summary_stance == "PROCEED_WITH_CONDITIONS"


# ── 도메인 캡 ───────────────────────────────────────────────────────────────


def test_competition_cap_withholds_decision() -> None:
    sem = ca.build_counseling(
        _cand(event_key="education_admission", favorability=0.7, activation=90.0)
    )
    assert sem.domain_cap == "competition"
    assert sem.stage_action_policy.get("decision", "withheld") != "proceed"
    assert sem.summary_stance == "PROCEED_WITH_CONDITIONS"  # PUSH 형 요약 금지


def test_health_cap_converts_hold_to_conditional() -> None:
    sem = ca.build_counseling(
        _cand(favorability=-0.7, evidence_path=["GATE_business_start_no_wealth"]),
        health=True,
    )
    assert "hold" not in sem.stage_action_policy.values()


def test_minor_produces_unavailable() -> None:
    sem = ca.build_counseling(_cand(favorability=0.7), minor=True)
    assert sem.summary_stance == "UNAVAILABLE"
    assert sem.domain_cap == "minor"
    assert ca.counseling_block_lines(sem) == []  # 블록 자체 미출력


def test_big_decision_caps_summary() -> None:
    sem = ca.build_counseling(
        _cand(event_key="marriage_signal", favorability=0.7, activation=90.0),
        big_decision=True,
    )
    assert sem.summary_stance == "PROCEED_WITH_CONDITIONS"


# ── P2-1: EVENT_STAGE_TAGS 소비 ─────────────────────────────────────────────


def test_stage_tags_vocabulary_and_relationship_cap() -> None:
    from saju_shared_types.counseling import StageScope
    from saju_shared_types.event_taxonomy_v2 import EVENT_STAGE_TAGS

    valid = {s.value for s in StageScope}
    for key, tags in EVENT_STAGE_TAGS.items():
        assert set(tags) <= valid, key
    # 관계 키는 marker 게이트 미구현 상한(기회·과정)을 넘는 태그를 갖지 않는다.
    assert "decision" not in EVENT_STAGE_TAGS[
        next(k for k in EVENT_STAGE_TAGS if str(k) == "marriage_signal")]


def test_f4_high_activation_unknown_outcome_separates_stages() -> None:
    # F4: 기회·과정은 진행하되 결과 미지 단계(실행)는 UNKNOWN — 지어내지 않는다.
    sem = ca.build_counseling(_cand(activation=90.0, favorability=0.0))
    assert sem.stage_action_policy["opportunity"] == "proceed"
    assert sem.stage_action_policy["process"] == "proceed"
    assert sem.stage_action_policy.get("realization") == "unknown"
    assert sem.summary_stance == "PROCEED"
    assert "realization" in sem.unknown_stages


def test_realization_direction_requires_outcome_evidence() -> None:
    # relocation(실행 단계 태그) — 결과 증거 없으면 unknown, 있으면 방향 부여.
    blank = ca.build_counseling(_cand(event_key="relocation", favorability=0.0))
    assert blank.stage_action_policy["realization"] == "unknown"
    fav = ca.build_counseling(_cand(event_key="relocation", favorability=0.7))
    assert fav.stage_action_policy["realization"] == "proceed"


# ── 렌더 계약 ───────────────────────────────────────────────────────────────


def test_block_lines_contract() -> None:
    sem = ca.build_counseling(_cand(
        activation=90.0, favorability=0.0, result_nuance="unfavorable", quality="pressure",
    ))
    text = "\n".join(ca.counseling_block_lines(sem))
    assert "두 축은 별개" in text            # INV-C
    assert "결과 실패로 번역하지 말고" in text  # INV-G
    assert "지어내지 말 것" in text            # 미지 단계 침묵
    assert "재판정·보충하지 말 것" in text


# ── 플래그 게이트(기본 OFF → 프롬프트 불변) ────────────────────────────────


def test_flag_off_no_block_in_prompt(monkeypatch) -> None:
    from saju_api.services import chat_service
    from saju_shared_types.birth_input import BirthInput

    birth = BirthInput(
        calendar_type="solar", birth_date="1984-08-19", birth_time="10:15",
        birth_place_name="서울", gender="male",
    )
    q = "2026년 12월 이직 운 어때?"
    monkeypatch.setattr(ca, "COUNSELING_SEMANTICS_ENABLED", False)
    off = chat_service.chat(birth, q, date(2026, 8, 21), True).prompt_preview or ""
    assert "[상담 결론" not in off
    monkeypatch.setattr(ca, "COUNSELING_SEMANTICS_ENABLED", True)
    on = chat_service.chat(birth, q, date(2026, 8, 21), True).prompt_preview or ""
    assert "[상담 결론" in on
    assert "요약 태세" in on
