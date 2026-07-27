"""P3 coverage 분리·fingerprint·신호 정체성 불변식 (2026-07-27 데굴님 확정).

핵심: 정책상 제외(충·엔진충돌·혼재)를 'V2 파생 실패'로 세면 안 된다.
"""

from __future__ import annotations

from saju_engines.signal_polarity import RelationPolarityResult, ScoreExclusionReason
from saju_engines.v2_coverage import (
    V2Coverage,
    accumulate_coverage,
    favorability_fingerprint,
    signal_identity,
    v2_semantics_fingerprint,
)
from saju_shared_types.relation_semantics import PolarityState

_FAV = {"土": "용신", "火": "희신", "木": "기신", "水": "구신", "金": "한신"}


def _result(reason: ScoreExclusionReason, polarity: int = 0) -> RelationPolarityResult:
    return RelationPolarityResult(
        narrative_axis="x",
        polarity_state=PolarityState.UNRESOLVED if reason is not
        ScoreExclusionReason.NONE else PolarityState.POSITIVE,
        score_polarity=polarity,
        score_eligible=reason is ScoreExclusionReason.NONE,
        exclusion_reason=reason,
    )


def test_policy_exclusions_are_not_coverage_failures():
    """충·엔진충돌·혼재는 정상 제외 — coverage는 여전히 complete."""
    cov = V2Coverage()
    for reason in (
        ScoreExclusionReason.STRUCTURAL_ONLY,
        ScoreExclusionReason.ENGINE_CONFLICT,
        ScoreExclusionReason.MIXED_UNALLOCATED,
    ):
        accumulate_coverage(cov, f"s:{reason.value}", _result(reason))
    assert cov.required_signal_count == 0
    assert cov.unavailable_signal_count == 0
    assert cov.complete is True
    assert cov.structural_only_count == 1
    assert cov.engine_conflict_count == 1
    assert cov.mixed_unallocated_count == 1


def test_derivation_failure_breaks_coverage():
    """역할 미상·원본 부족만 coverage 실패로 센다."""
    cov = V2Coverage()
    accumulate_coverage(cov, "s:ok", _result(ScoreExclusionReason.NONE, 1))
    accumulate_coverage(cov, "s:bad", _result(ScoreExclusionReason.UNKNOWN_ROLE))
    assert cov.required_signal_count == 2
    assert cov.derived_signal_count == 1
    assert cov.unavailable_signal_count == 1
    assert cov.complete is False
    assert cov.unavailable_signal_ids == ["s:bad"]
    assert cov.unavailable_reasons == ["UNKNOWN_ROLE"]


def test_neutral_counts_as_derived():
    """NEUTRAL은 정상 파생(기여 0)이지 실패가 아니다."""
    cov = V2Coverage()
    accumulate_coverage(cov, "s:n", _result(ScoreExclusionReason.NONE, 0))
    assert cov.derived_signal_count == 1
    assert cov.neutral_count == 1
    assert cov.complete is True


def test_fingerprint_changes_when_role_assignment_changes():
    """규칙 버전이 같아도 그 명식의 역할 배정이 바뀌면 지문이 달라진다."""
    base = favorability_fingerprint(_FAV)
    shifted = favorability_fingerprint({**_FAV, "火": "한신"})  # 喜 → 閑
    assert base != shifted
    assert v2_semantics_fingerprint(_FAV) != v2_semantics_fingerprint(
        {**_FAV, "火": "한신"}
    )


def test_fingerprint_is_stable_across_dict_order():
    """입력 순서가 달라도 지문은 같다."""
    reordered = dict(reversed(list(_FAV.items())))
    assert favorability_fingerprint(_FAV) == favorability_fingerprint(reordered)


def test_signal_identity_distinguishes_occurrence_and_domain():
    """관계 ID가 같아도 발생·도메인이 다르면 별개 신호다."""
    common = {
        "relation_id": "rel_寅亥合", "effect_identity": "SUPPRESSED:壬",
        "domain": "career", "source_period": "2026-07-27",
        "magnitude_path": "base", "polarity_source": "binding",
    }
    month = signal_identity(occurrence_ids={"natal_month:亥", "daily:寅"}, **common)
    day = signal_identity(occurrence_ids={"natal_day:亥", "daily:寅"}, **common)
    other_domain = signal_identity(
        occurrence_ids={"natal_month:亥", "daily:寅"},
        **{**common, "domain": "wealth"},
    )
    assert len({month, day, other_domain}) == 3
    # 완전히 같은 계산 정체성만 중복이다.
    assert month == signal_identity(
        occurrence_ids={"daily:寅", "natal_month:亥"}, **common
    )
