"""의미 해소 resolver 회귀 — CAREER_TRANSITION_SYSTEM §13-1 fixture 전수.

`ResolvedEventSemantics`(§11-4) 자체를 검증한다. 수치·명리 매핑의 정답이 아니라
**의미·소유권 불변식**이 대상이다(§13 작성 원칙).
"""

from __future__ import annotations

import pytest

from saju_engines.event_semantics_resolver import (
    is_semantics_stale,
    resolve_event_semantics,
)
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.event_semantics import (
    CANONICAL_EVENT_SEMANTICS,
    SEMANTICS_CONTRACT_VERSION,
    CalibrationCapKey,
    ResolutionSource,
    TransitionFamily,
)

# ── §13-1 fixture 표 ────────────────────────────────────────────────────────


def test_career_change_canonical() -> None:
    """career_change → domain=career, family=move, cap=career_transition."""
    r = resolve_event_semantics(EventKeyV2.CAREER_CHANGE)
    assert r.event_domain == "career"
    assert r.transition_family is TransitionFamily.MOVE
    assert r.calibration_domain == "career"
    assert r.calibration_cap_key is CalibrationCapKey.CAREER_TRANSITION
    assert r.resolution_source is ResolutionSource.CANONICAL
    assert r.is_consumable


def test_relocation_not_folded_into_career() -> None:
    """relocation → domain=relocation, family=move, cap=relocation.

    신규 의미에서는 이사를 career로 접지 않는다(legacy move→career fold는 별개로 불변).
    """
    r = resolve_event_semantics(EventKeyV2.RELOCATION)
    assert r.event_domain == "relocation"
    assert r.transition_family is TransitionFamily.MOVE
    assert r.calibration_domain == "relocation"
    assert r.calibration_cap_key is CalibrationCapKey.RELOCATION


def test_job_gain_has_no_transition_family() -> None:
    """job_gain → family=None(형제 발현 대상 아님), cap=employment_entry."""
    r = resolve_event_semantics(EventKeyV2.JOB_GAIN)
    assert r.event_domain == "career"
    assert r.transition_family is None
    assert r.calibration_cap_key is CalibrationCapKey.EMPLOYMENT_ENTRY


def test_promotion_has_no_transition_family() -> None:
    """promotion → family=None, cap=promotion(이직과 다른 cap 슬롯)."""
    r = resolve_event_semantics(EventKeyV2.PROMOTION)
    assert r.transition_family is None
    assert r.calibration_cap_key is CalibrationCapKey.PROMOTION


def test_legacy_resignation_normalizes_to_career_change() -> None:
    """legacy resignation → canonical career_change로 정규화 후 동일 의미."""
    r = resolve_event_semantics("resignation")
    canonical = resolve_event_semantics(EventKeyV2.CAREER_CHANGE)
    assert r.event_domain == canonical.event_domain
    assert r.transition_family == canonical.transition_family
    assert r.calibration_cap_key == canonical.calibration_cap_key


def test_legacy_travel_is_not_pulled_into_move_family() -> None:
    """legacy travel(category=move)이 이직↔이사 형제 분기에 들어가지 않는다.

    canonical EventKeyV2에 travel이 없으므로 legacy 보조로 넘어가 fail-closed 된다 —
    legacy `move`라는 이유만으로 family를 얻지 못한다(§11-5).
    """
    r = resolve_event_semantics("travel", legacy_category="move")
    assert r.transition_family is None
    assert not r.is_consumable
    assert r.resolution_source is ResolutionSource.LEGACY_AMBIGUOUS


def test_explicit_fields_matching_canonical_are_validated() -> None:
    """전달본이 canonical과 일치하면 EXPLICIT_VALIDATED."""
    r = resolve_event_semantics(
        EventKeyV2.CAREER_CHANGE,
        explicit_event_domain="career",
        explicit_transition_family=TransitionFamily.MOVE,
        explicit_calibration_domain="career",
    )
    assert r.resolution_source is ResolutionSource.EXPLICIT_VALIDATED
    assert r.is_consumable


def test_explicit_mismatch_fails_closed() -> None:
    """전달본이 canonical과 충돌하면 INVALID_MISMATCH + 의미 필드 전부 None."""
    r = resolve_event_semantics(
        EventKeyV2.CAREER_CHANGE,
        explicit_event_domain="relocation",  # canonical 은 career
    )
    assert r.resolution_source is ResolutionSource.INVALID_MISMATCH
    assert not r.is_consumable
    assert r.event_domain is None
    assert r.transition_family is None
    assert r.calibration_domain is None
    assert r.calibration_cap_key is None


def test_legacy_move_alone_is_ambiguous() -> None:
    """event_key 없이 legacy move만 있으면 LEGACY_AMBIGUOUS — family 확정 금지."""
    r = resolve_event_semantics(None, legacy_category="move")
    assert r.resolution_source is ResolutionSource.LEGACY_AMBIGUOUS
    assert not r.is_consumable
    assert r.transition_family is None


def test_contract_version_mismatch_requires_reresolution() -> None:
    """계약 버전이 다르면 이전 해소 결과를 재사용하지 않는다."""
    assert is_semantics_stale("career-semantics.v0") is True
    assert is_semantics_stale(SEMANTICS_CONTRACT_VERSION) is False


# ── 속성 회귀 ──────────────────────────────────────────────────────────────


def test_canonical_key_outranks_legacy_category() -> None:
    """canonical key가 legacy category보다 우선한다 — legacy는 권위 소스가 아니다."""
    r = resolve_event_semantics(EventKeyV2.CAREER_CHANGE, legacy_category="affection")
    assert r.event_domain == "career"
    assert r.resolution_source is ResolutionSource.CANONICAL


def test_fail_closed_results_have_all_semantic_fields_none() -> None:
    """fail-closed 두 출처 모두 부분 fallback을 남기지 않는다."""
    for r in (
        resolve_event_semantics(None, legacy_category="move"),
        resolve_event_semantics(EventKeyV2.PROMOTION, explicit_event_domain="wealth"),
    ):
        assert not r.is_consumable
        assert (
            r.event_domain,
            r.transition_family,
            r.calibration_domain,
            r.calibration_cap_key,
        ) == (None, None, None, None)


def test_cap_key_is_derived_not_accepted_as_input() -> None:
    """calibration_cap_key는 호출자가 넣는 권위 필드가 아니라 파생값이다(D21)."""
    with pytest.raises(TypeError):
        resolve_event_semantics(  # type: ignore[call-arg]
            EventKeyV2.CAREER_CHANGE,
            calibration_cap_key=CalibrationCapKey.RELOCATION,
        )


def test_move_family_has_exactly_two_canonical_members() -> None:
    """형제 발현 가족은 canonical career_change ↔ relocation 2멤버만 유지된다.

    legacy move는 4멤버(+resignation·travel)이므로 legacy에서 family를 유도하면 이
    불변식이 깨진다(§11-5 근거).
    """
    members = {
        key.value
        for key, sem in CANONICAL_EVENT_SEMANTICS.items()
        if sem.transition_family is TransitionFamily.MOVE
    }
    assert members == {"career_change", "relocation"}


def test_out_of_scope_canonical_keys_get_domain_only() -> None:
    """§11-5 범위 밖 canonical 키는 domain만 해소하고 career 의미를 억지로 채우지 않는다."""
    r = resolve_event_semantics(EventKeyV2.MARRIAGE_SIGNAL)
    assert r.resolution_source is ResolutionSource.CANONICAL
    assert r.event_domain == "relationship"
    assert r.transition_family is None
    assert r.calibration_domain is None
    assert r.calibration_cap_key is None


def test_resolution_is_idempotent() -> None:
    """동일 입력 재호출은 동일 결과 — resolver는 상태를 갖지 않는다."""
    a = resolve_event_semantics(EventKeyV2.CAREER_CHANGE)
    b = resolve_event_semantics(EventKeyV2.CAREER_CHANGE)
    assert a == b
