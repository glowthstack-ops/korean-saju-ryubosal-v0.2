"""Marriage Production Readiness v1 — Step 3: 결혼 출력 가드(코드 레벨) 테스트.

핵심 검증: ① marker 미구현 → 결혼 확정·논의 표현 차단(relationship 진전까지만) ② 하드 금지 표현
항상 차단 ③ marker 채우면 상위 허용 ④ detect_marriage_overclaim가 확정 단정 탐지 ⑤ directive 렌더.
"""

from __future__ import annotations

from saju_engines.marriage_output_guard import (
    compute_marriage_output_guard,
    detect_marriage_overclaim,
    has_stability_risk,
    is_relationship_stability_risk,
    marriage_guard_directive,
)


def test_relationship_stage_blocks_confirmation() -> None:
    """relationship 단계 + marker 부재 → 진전만 허용, 확정·논의 차단."""
    g = compute_marriage_output_guard("relationship")
    assert g.can_say_relationship_progress is True
    assert g.can_say_marriage_discussion is False
    assert g.can_say_marriage_confirmed is False


def test_awareness_stage_no_progress() -> None:
    g = compute_marriage_output_guard("awareness")
    assert g.can_say_relationship_progress is False
    assert g.can_say_marriage_confirmed is False


def test_empty_stage_conservative() -> None:
    """비-MT(stage='') → 진전·확정 모두 불가(보수)."""
    g = compute_marriage_output_guard("")
    assert g.can_say_relationship_progress is False
    assert g.can_say_marriage_confirmed is False


def test_commitment_marker_enables_discussion() -> None:
    g = compute_marriage_output_guard("commitment", has_commitment_marker=True)
    assert g.can_say_marriage_discussion is True
    assert g.can_say_marriage_confirmed is False  # formalization marker 별도


def test_formalization_marker_enables_confirmation() -> None:
    g = compute_marriage_output_guard(
        "formalization", has_commitment_marker=True, has_formalization_marker=True,
    )
    assert g.can_say_marriage_confirmed is True
    assert g.can_say_marriage_discussion is True


def test_hard_blocked_always_present() -> None:
    """하드 금지 표현은 단계·marker와 무관하게 항상 blocked_expressions에 있다."""
    for stage in ("", "awareness", "relationship", "formalization"):
        g = compute_marriage_output_guard(
            stage, has_commitment_marker=True, has_formalization_marker=True,
        )
        assert "거의 100%" in g.blocked_expressions
        assert "혼인 확정" in g.blocked_expressions


def test_directive_reflects_blocks() -> None:
    d = marriage_guard_directive(compute_marriage_output_guard("relationship"))
    assert "결혼 확정" in d  # 차단 안내 포함
    assert "관계 진전 가능성" in d


def test_detect_overclaim() -> None:
    assert detect_marriage_overclaim("올해 반드시 결혼합니다")
    assert detect_marriage_overclaim("거의 100% 결혼운입니다")
    assert detect_marriage_overclaim("이 사람과 결혼합니다")
    assert detect_marriage_overclaim("결혼 확정 시기입니다")


def test_detect_overclaim_clean() -> None:
    assert detect_marriage_overclaim("관계가 진전될 가능성이 있는 시기입니다") == []
    assert detect_marriage_overclaim("이미 만나는 분이 있다면 결혼 논의로 이어질 수 있습니다") == []


# ── Step 4: risk_flags 분기 ──────────────────────────────────────────


def test_has_stability_risk_detects_clash_and_risk() -> None:
    assert has_stability_risk(["MT3_DIRECTIONAL_DAY_BRANCH", "MT2_EMERGENCE_CLASHED"])
    assert has_stability_risk(["MT1_GISIN_RISK"])
    assert has_stability_risk(["MT1_COMPETITION_RISK"])
    assert not has_stability_risk(["MT3_DIRECTIONAL_DAY_BRANCH", "MT1_STAGE_AWARENESS"])


def test_stability_risk_blocks_discussion_and_branches() -> None:
    """충·쟁합·기신 동반 → 결혼 논의·확정 차단 + 관계 변화 병기 지시."""
    g = compute_marriage_output_guard(
        "relationship", has_commitment_marker=True, stability_risk=True,
    )
    assert g.stability_risk is True
    assert g.can_say_marriage_discussion is False  # risk가 marker 허용을 덮어씀
    d = marriage_guard_directive(g)
    assert "관계 변화" in d and "병기" in d


# ── B2: REL 계열 명시 분류 (RELATIONSHIP_EVENT_SYSTEM 부록 B, 2026-07-24) ─────────
# P0-A 실측: REL_CHUNG_* 기반 marriage_signal이 리스크 표기 없이 Top5 진입하던
# 방향 누수 — 충·형·파·해 REL reason을 안정성 위험으로 명시 분류해 출력 가드 연결.


def test_rel_negative_kinds_are_stability_risk() -> None:
    """충·형·파·해 REL reason은 각각 안정성 위험."""
    assert has_stability_risk(["REL_CHUNG_day_pillar"])
    assert has_stability_risk(["REL_HYEONG_day_pillar"])
    assert has_stability_risk(["REL_PA_day_pillar"])
    assert has_stability_risk(["REL_HAE_day_pillar"])


def test_rel_hap_alone_is_not_stability_risk() -> None:
    """합 단독(REL_HAP_*)은 위험 아님 — 결속·재정의 활성."""
    assert not has_stability_risk(["REL_HAP_day_pillar"])
    assert not has_stability_risk(["REL_HAP_day_pillar", "MT3_DIRECTIONAL_DAY_BRANCH"])


def test_rel_hap_with_chung_is_stability_risk() -> None:
    """합+충 복합은 위험(충 구성 코드 기준)."""
    assert has_stability_risk(["REL_HAP_day_pillar", "REL_CHUNG_day_pillar", "REL_COMPOUND"])


def test_rel_compound_alone_conservative_no_risk() -> None:
    """REL_COMPOUND 단독(구성 코드 부재 — 이론상 없음)은 보수적 미판정."""
    assert not has_stability_risk(["REL_COMPOUND"])


def test_mt2_spouse_palace_clashed_still_risk() -> None:
    """기존 MT 계열(CLASHED 포함)은 그대로 위험 — 회귀 보존."""
    assert has_stability_risk(["SPOUSE_PALACE_CLASHED"])
    assert has_stability_risk(["MT2_EMERGENCE_CLASHED", "REL_HAP_day_pillar"])


def test_is_relationship_stability_risk_explicit_classifier() -> None:
    """명시 분류기 단위 동작 — 접두사 화이트리스트만 매칭."""
    assert is_relationship_stability_risk("REL_CHUNG_year_pillar")
    assert not is_relationship_stability_risk("REL_HAP_day_pillar")
    assert not is_relationship_stability_risk("REL_BOKEUM_day_pillar")
    assert not is_relationship_stability_risk("REL_COMPOUND")


def test_chung_based_marriage_blocks_positive_claims() -> None:
    """충 기반 marriage_signal → 결혼 확정·논의 차단 + 관계 변화 병기(방향 누수 차단)."""
    risk = has_stability_risk(["REL_CHUNG_day_pillar", "REL_COMPOUND"])
    g = compute_marriage_output_guard(
        "relationship",
        has_commitment_marker=True,
        has_formalization_marker=True,
        stability_risk=risk,
    )
    assert g.can_say_marriage_confirmed is False
    assert g.can_say_marriage_discussion is False
    d = marriage_guard_directive(g)
    assert "긍정 단정 금지" in d
