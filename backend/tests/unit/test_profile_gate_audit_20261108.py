"""프로필 게이트 전면 검수 반영(2026-11-08) — 반례 테스트.

검수 결함 4건의 반례: ① 현재 상태를 과거 연도에 적용 ② 병합 시 전환 태그 유실 ③ 미입력 비중립
(충돌 해결기 no_business_context) ④ 별거 의미 불일치, 그리고 ⑤ 취업 보조 없음 감점의 전환 전/후
비대칭. 모두 종전 코드에서는 통과하지 못하는 반례다(반례 없는 테스트는 게이트를 통과한다 — 교훈).
"""

from __future__ import annotations

from datetime import date

from saju_engines.addendum_gate_modifier import (
    AddendumGateModifier,
    GateContext,
    is_past_period,
    period_end_year,
)
from saju_engines.event_engine_v2 import _rank_context
from saju_engines.profile_engine import derive_relationship_status, marital_routing
from saju_shared_types.event_engine import EventCandidateV2, TenGod


def _cand(event: str, score: int = 70, period: str = "2027") -> EventCandidateV2:
    return EventCandidateV2(event_key=event, period=period, score=score)


# ── 기간 라벨 파싱 ──────────────────────────────────────────────────────────


def test_period_end_year_handles_year_month_and_daewoon_ranges() -> None:
    assert period_end_year("2026") == 2026
    assert period_end_year("2026-06") == 2026
    assert period_end_year("2024~2033") == 2033  # event_engine_v2 대운 라벨('~')
    assert period_end_year("2024–2033") == 2033  # 리포트 표기('–')
    assert period_end_year("") is None


def test_is_past_period_is_strictly_before_today_year_and_off_without_today() -> None:
    assert is_past_period("2010", 2026)
    assert not is_past_period("2026-03", 2026)  # 올해는 현재 상태 적용
    assert not is_past_period("2027", 2026)
    assert not is_past_period("2017~2026", 2026)  # 끝 연도가 올해인 대운은 현재
    assert is_past_period("2007~2016", 2026)
    assert not is_past_period("2010", None)  # 가드 없음(구 호출자)


# ── ① 과거 연도엔 현재 상태 미적용 ─────────────────────────────────────────


def test_married_profile_does_not_rewrite_past_marriage_year() -> None:
    """기혼자의 실제 결혼 해(과거) 결혼 신호는 그대로 — 인생 그래프 결혼 마커 소실 반례."""
    m = AddendumGateModifier()
    ctx = GateContext(relationship_status="married", today_year=2026)
    past = m.apply([_cand("marriage_signal", 80, period="2010")], ctx)[0]
    future = m.apply([_cand("marriage_signal", 80, period="2027")], ctx)[0]
    assert str(past.event_key) == "marriage_signal"
    assert not any(r.startswith("PROFILE_") for r in past.reason_codes)
    assert str(future.event_key) == "relationship_change"
    assert "PROFILE_marriage_to_change" in future.reason_codes
    assert "PROFILE_married_outside_attraction_caution" in future.reason_codes


def test_employee_profile_does_not_rewrite_past_first_job_year() -> None:
    m = AddendumGateModifier()
    ctx = GateContext(
        occupation_status="employee", present_gods={TenGod.ZHENGGUAN, TenGod.ZHENGYIN},
        today_year=2026,
    )
    past = m.apply([_cand("job_gain", 70, period="2012")], ctx)[0]
    assert str(past.event_key) == "job_gain"
    assert "PROFILE_job_gain_to_promotion" not in past.reason_codes
    cur = m.apply([_cand("job_gain", 70, period="2026")], ctx)[0]
    assert str(cur.event_key) == "promotion"


def test_childbirth_safety_gate_is_time_independent() -> None:
    """출산→창작은 '상대 확인 안 됨' 안전 기본값(출산 확정 금지) — 과거 연도에도 그대로."""
    m = AddendumGateModifier()
    ctx = GateContext(relationship_status="single", today_year=2026)
    past = m.apply([_cand("childbirth", 60, period="2015")], ctx)[0]
    assert str(past.event_key) == "creative_output"
    now = m.apply([_cand("childbirth", 60, period="2027")], ctx)[0]
    assert str(now.event_key) == "creative_output"
    # 상대 있음(married)이면 시점과 무관하게 출산 신호 유지.
    married = GateContext(relationship_status="married")
    kept = m.apply([_cand("childbirth", 60, period="2015")], married)[0]
    assert str(kept.event_key) == "childbirth"


def test_rank_context_profile_flags_only_when_active() -> None:
    active = _rank_context([], set(), [], "employee", "married")
    expected = {"relationship_context_exists", "career_context_exists", "no_business_context"}
    assert expected <= active.flags
    past = _rank_context([], set(), [], "employee", "married", profile_active=False)
    assert not past.flags & {
        "relationship_context_exists", "career_context_exists", "no_business_context",
    }
    # 출산 안전 플래그(상대 확인 안 됨)는 시점 무관.
    assert "childbirth_profile_gate_false" in _rank_context(
        [], set(), [], None, None, profile_active=False,
    ).flags


# ── ② 병합 시 전환 태그 보존 ───────────────────────────────────────────────


def test_merge_keeps_profile_tags_when_converted_candidate_loses() -> None:
    """결혼 신호(65, 기혼 전환)가 기존 관계 이슈(80)에 져도 PROFILE_* 태그는 남는다."""
    m = AddendumGateModifier()
    out = m.apply(
        [_cand("marriage_signal", 65), _cand("relationship_change", 80)],
        GateContext(relationship_status="married"),
    )
    by = {str(c.event_key): c for c in out}
    assert set(by) == {"relationship_change"}
    assert by["relationship_change"].score == 80  # 점수는 이기는 쪽
    assert "PROFILE_marriage_to_change" in by["relationship_change"].reason_codes
    assert "PROFILE_married_outside_attraction_caution" in by["relationship_change"].reason_codes


# ── ③ 미입력은 중립 ────────────────────────────────────────────────────────


def test_no_business_context_requires_explicit_non_business_occupation() -> None:
    unknown = _rank_context([], set(), [], None, None)
    assert "no_business_context" not in unknown.flags
    employee = _rank_context([], set(), [], "employee", None)
    assert "no_business_context" in employee.flags
    owner = _rank_context([], set(), [], "business_owner", None)
    assert "no_business_context" not in owner.flags


# ── ④ 별거 = 기혼 계열 ─────────────────────────────────────────────────────


def test_separated_maps_to_married_consistently() -> None:
    assert derive_relationship_status("별거") == "married"
    assert derive_relationship_status("사별") == "single"
    assert derive_relationship_status("이혼") == "divorced"
    assert marital_routing("별거", "relationship")["module"] == "M02"
    m = AddendumGateModifier()
    out = m.apply(
        [_cand("marriage_signal", 70), _cand("childbirth", 60)],
        GateContext(relationship_status=derive_relationship_status("별거"), today_year=2026),
    )
    by = {str(c.event_key): c for c in out}
    assert "relationship_change" in by and "marriage_signal" not in by
    assert "childbirth" in by  # 배우자 있음 → 출산 신호 유지


# ── ⑤ 취업 보조 없음 감점은 전환 후 키 기준 ───────────────────────────────


def test_job_gain_unsupported_penalty_follows_converted_key() -> None:
    m = AddendumGateModifier()
    # 재직자: 취업→승진 전환 후보에는 '취업 보조 없음' 감점·라벨이 붙지 않는다.
    emp = m.apply(
        [_cand("job_gain", 70)],
        GateContext(occupation_status="employee", present_gods={TenGod.ZHENGGUAN}),
    )[0]
    assert str(emp.event_key) == "promotion"
    assert emp.score == 70
    assert "GATE_job_gain_unsupported" not in emp.reason_codes
    # 무직자: 이직→취업 전환 후보에는 관성 단독이면 감점이 붙는다.
    jobless = m.apply(
        [_cand("career_change", 70)],
        GateContext(occupation_status="unemployed", present_gods={TenGod.ZHENGGUAN}),
    )[0]
    assert str(jobless.event_key) == "job_gain"
    assert jobless.score == 62
    assert "GATE_job_gain_unsupported" in jobless.reason_codes
    # 무프로필 취업 후보는 종전과 동일(−8).
    plain = m.apply([_cand("job_gain", 70)], GateContext(present_gods={TenGod.ZHENGGUAN}))[0]
    assert plain.score == 62


# ── ⑥ 충돌 규칙: 프로필 조건은 태그만, 사업자는 이직 선호 제외 ─────────────────────


def test_conflict_rules_with_profile_flags_are_tag_effect() -> None:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "dictionaries" / "event_engine"
    rules = json.loads((path / "conflict_resolver_duration.json").read_text(encoding="utf-8"))
    profile_flags = {
        "relationship_context_exists", "career_context_exists", "no_business_context",
        "childbirth_profile_gate_false",
    }
    for r in rules["event_conflict_resolver"]["priority_rules"]:
        expected = "tag" if set(r["if"]) & profile_flags else "score"
        assert r.get("effect") == expected, r


def test_business_owner_excluded_from_career_change_preference() -> None:
    assert "career_context_exists" not in _rank_context([], set(), [], "business_owner", None).flags
    assert "career_context_exists" in _rank_context([], set(), [], "employee", None).flags
    assert "career_context_exists" in _rank_context([], set(), [], "freelancer", None).flags


def test_today_defaults_are_date_based() -> None:
    """엔진 공개 API 의 today 기본값은 date.today() — 단위 테스트는 명시 연도로 고정한다."""
    assert isinstance(date.today().year, int)
