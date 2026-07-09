"""능동 제안 판정 엔진 (Phase B, docs/15) — 합성 facts 평가 + 실차트 통합 검증."""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.direction_suggestion import (
    DEFICIENT_PCT,
    EXCESS_PCT,
    _group_percents,
    build_direction_facts,
    detect_direction_suggestions,
    evaluate_direction_suggestions,
    load_direction_suggestions,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.direction_suggestions import DirectionFacts
from saju_shared_types.enums import StrengthBand
from saju_shared_types.event_engine import TenGod as TenGodRoman

_GROUPS = {"peer", "output", "wealth", "authority", "resource"}
_STATES = {
    "natal_excess",
    "luck_excess_onset",
    "excess_intensified",
    "natal_deficient",
    "deficient_persistent",
    "luck_replenished",
    "luck_inflow",
}


def _facts(**overrides: object) -> DirectionFacts:
    """합성 facts — 재성 과다 x 상관 작동(원형 사례) 기본형."""
    base: dict[str, object] = {
        "group_states": {"wealth": ["natal_excess"]},
        "ten_god_present": ["SHANGGUAN", "ZHENGCAI"],
        "ten_god_active": ["SHANGGUAN", "ZHENGCAI"],
        "yongsin_roles": {},
        "strength_band": "중화",
        "pattern_ids": [],
        "group_conflicts": {},
    }
    base.update(overrides)
    return DirectionFacts.model_validate(base)


def _only(suggestions: list, suggestion_id: str) -> object:
    """특정 룰의 제안 1건을 꺼낸다(없으면 실패)."""
    hits = [s for s in suggestions if s.suggestion_id == suggestion_id]
    assert len(hits) == 1, f"{suggestion_id} 제안 {len(hits)}건"
    return hits[0]


# ── 합성 facts 평가 (원형 사례: 정재 과다 + 상관 작동) ──────────────────


def test_prototype_recommend_mode() -> None:
    """재성 과다 + 상관 작동(식신 비작동) + guard 없음 → recommend·부업형 채널."""
    s = _only(evaluate_direction_suggestions(_facts()), "WEALTH_EXCESS")
    assert s.mode == "recommend"
    assert s.channel_id == "sanggwan_side_income"
    assert "본업" in s.headline
    assert s.cautions == [] and s.matched_guards == []
    assert s.group_state == "natal_excess"


def test_guard_flips_to_caution_not_blocks() -> None:
    """신약 guard 매칭 → 제안이 사라지지 않고 caution 모드로 반전(설계 §1-3)."""
    s = _only(evaluate_direction_suggestions(_facts(strength_band="신약")), "WEALTH_EXCESS")
    assert s.mode == "caution"
    assert "정리" in s.headline  # caution_headline로 교체
    assert "weak_self" in s.matched_guards
    assert any("감당" in c for c in s.cautions)
    assert s.actions, "caution 모드에서도 방향 재료(actions)는 유지"


def test_multiple_guards_accumulate() -> None:
    """복수 guard(신약+재성충파+편재동반) → note가 전부 cautions로 누적."""
    s = _only(
        evaluate_direction_suggestions(
            _facts(
                strength_band="신약",
                ten_god_present=["SHANGGUAN", "ZHENGCAI", "PIANCAI"],
                group_conflicts={"wealth": ["충"]},
            )
        ),
        "WEALTH_EXCESS",
    )
    assert set(s.matched_guards) >= {"weak_self", "pyeonjae_accompany", "wealth_conflict"}
    assert len(s.cautions) == len(s.matched_guards)


def test_supports_raise_strength() -> None:
    """support 3건(생재 패턴+신강+재성 용신) 매칭 → strength 0.5+0.15x3=0.95."""
    plain = _only(evaluate_direction_suggestions(_facts()), "WEALTH_EXCESS")
    boosted = _only(
        evaluate_direction_suggestions(
            _facts(
                strength_band="신강",
                pattern_ids=["SANGGWAN_SAENGJAE"],
                yongsin_roles={"wealth": "용신"},
            )
        ),
        "WEALTH_EXCESS",
    )
    assert plain.strength == 0.5
    assert boosted.strength == 0.95
    assert len(boosted.matched_supports) == 3


def test_channel_priority_first_match_wins() -> None:
    """식신도 작동하면 상관 채널(식신 비작동 요구)은 탈락 → siksin_steady 채택."""
    s = _only(
        evaluate_direction_suggestions(
            _facts(
                ten_god_present=["SHANGGUAN", "SHISHEN"],
                ten_god_active=["SHANGGUAN", "SHISHEN"],
            )
        ),
        "WEALTH_EXCESS",
    )
    assert s.channel_id == "siksin_steady"


def test_no_channel_no_suggestion() -> None:
    """트리거 성립해도 성립 채널이 없으면 제안 없음(억지 제안 금지)."""
    suggestions = evaluate_direction_suggestions(
        _facts(ten_god_present=["ZHENGCAI"], ten_god_active=["ZHENGCAI"])
    )
    assert all(s.suggestion_id != "WEALTH_EXCESS" for s in suggestions)


def test_replenish_window_gated_by_yongsin_role() -> None:
    """부족+운보충이라도 해당 군이 기신이면 '기회 창' 서술 금지(길흉=용신/기신)."""
    base = {
        "group_states": {"wealth": ["natal_deficient", "luck_replenished", "luck_inflow"]},
        "ten_god_present": [],
        "ten_god_active": [],
    }
    blocked = evaluate_direction_suggestions(_facts(**base, yongsin_roles={"wealth": "기신"}))
    assert all(s.suggestion_id != "WEALTH_DEFICIT" for s in blocked)
    allowed = _only(
        evaluate_direction_suggestions(_facts(**base, yongsin_roles={"wealth": "희신"})),
        "WEALTH_DEFICIT",
    )
    assert allowed.channel_id == "replenish_window"
    assert allowed.group_state == "luck_replenished"


def test_evidence_records_channel_and_conditions() -> None:
    """근거 경로에 트리거·채널·조건 라벨이 남는다."""
    s = _only(evaluate_direction_suggestions(_facts()), "WEALTH_EXCESS")
    assert any(e.startswith("군상태:wealth") for e in s.evidence)
    assert "채널:sanggwan_side_income" in s.evidence


def test_sorted_by_strength_then_id() -> None:
    """복수 제안은 strength 내림차순, 동률은 id 순 — 결정적 출력."""
    facts = _facts(
        group_states={
            "wealth": ["natal_excess"],
            "resource": ["natal_excess"],
        },
        ten_god_present=["SHANGGUAN", "ZHENGCAI"],
        ten_god_active=["SHANGGUAN", "ZHENGCAI"],
        yongsin_roles={"wealth": "용신"},
    )
    suggestions = evaluate_direction_suggestions(facts)
    assert len(suggestions) >= 2
    strengths = [s.strength for s in suggestions]
    assert strengths == sorted(strengths, reverse=True)


# ── 실차트 통합 (facts 조립 어댑터) ──────────────────────────────────────


@pytest.fixture(scope="module")
def result():
    # reference_date 지정 시 현재 대운·세운이 채워져 운 합산 경로까지 검증된다.
    return calculate(
        BirthInput(
            birth_date="1980-11-22",
            birth_time="09:08",
            birth_place_name="서울",
            gender="male",
            reference_date=date(2026, 7, 9),
        )
    )


def test_facts_wellformed(result) -> None:
    """실차트 facts — 군/상태/십성/밴드/충파 값이 전부 유효 도메인."""
    facts = build_direction_facts(result)
    romans = {t.value for t in TenGodRoman}
    bands = {b.value for b in StrengthBand}
    assert set(facts.group_states) == _GROUPS
    for states in facts.group_states.values():
        assert set(states) <= _STATES
    assert set(facts.ten_god_present) <= romans
    assert set(facts.ten_god_active) <= set(facts.ten_god_present)
    assert facts.strength_band in bands
    for group, kinds in facts.group_conflicts.items():
        assert group in _GROUPS and set(kinds) <= {"충", "형", "파", "해"}


def test_group_percents_normalized(result) -> None:
    """합산 분포율은 원국 단독/운 합산 모두 총합 100%(부동소수 오차 허용)."""
    natal = _group_percents(result.pillars, [])
    assert abs(sum(natal.values()) - 100.0) < 0.1
    facts = build_direction_facts(result)
    assert facts.group_states  # 상태 산출 자체가 분포 기반


def test_states_consistent_with_thresholds(result) -> None:
    """원국 과다/부족 상태가 분포율 임계와 일치한다."""
    natal = _group_percents(result.pillars, [])
    facts = build_direction_facts(result)
    for group, pct in natal.items():
        states = facts.group_states[group]
        assert ("natal_excess" in states) == (pct >= EXCESS_PCT)
        assert ("natal_deficient" in states) == (pct < DEFICIENT_PCT)


def test_luck_path_exercised(result) -> None:
    """reference_date 지정 차트에서는 운 유입 상태와 용신 역할 전개가 산출된다."""
    facts = build_direction_facts(result)
    assert any("luck_inflow" in states for states in facts.group_states.values())
    assert set(facts.yongsin_roles.values()) <= {"용신", "희신", "기신", "구신", "한신"}
    assert facts.yongsin_roles, "canonical_roles(역할→오행) 역전개가 비어 있으면 회귀"


def test_detect_runs_deterministic(result) -> None:
    """실차트 판정이 결정적이며 출력 계약(mode/strength/근거)을 지킨다."""
    first = detect_direction_suggestions(result)
    second = detect_direction_suggestions(result)
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]
    for s in first:
        assert s.mode in {"recommend", "caution"}
        assert 0.0 <= s.strength <= 1.0
        assert s.evidence and s.headline and s.actions
        if s.mode == "caution":
            assert s.cautions and s.matched_guards


def test_loader_prefers_snapshot() -> None:
    """로더가 컴파일 스냅샷(v1.0.0)을 로드하고 시드 10종을 보존한다."""
    d = load_direction_suggestions()
    assert len(d.rules) == 10
