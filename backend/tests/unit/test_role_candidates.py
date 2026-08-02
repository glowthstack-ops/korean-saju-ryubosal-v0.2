"""경계 명식 역할 후보 보존 회귀 (CAL-ROLE-BORDERLINE-01b, 2026-08-02).

01a 가 보인 것은 "어느 역할표가 맞다" 가 아니라 **runner-up 을 버리면 P3 결과 방향이 실제로
뒤집힐 수 있다** 는 사실이다. 그래서 후보를 보존하되 canonical 은 흔들지 않는다.

`requires_validation` 은 경계 판정에 쓰지 않는다 — 26 명식 전건 True 라 판별력이 없다(01a).
"""

from __future__ import annotations

import dataclasses
import inspect
from decimal import Decimal

import pytest

from saju_engines import role_candidates as mod
from saju_engines.role_activation_projection import CanonicalRole
from saju_engines.role_candidates import (
    MAX_ALTERNATE_CANDIDATES,
    ROLE_CLOSE_MARGIN_V1,
    ROLE_COMPETITION_POLICY_VERSION,
    CanonicalRoleMap,
    RoleCompetitionBand,
    RoleMapDifferenceKind,
    RoleModelCandidate,
    build_role_candidate_set,
    role_map_differences,
)

#: 사례 A — 0A 에서 고정한 두 후보.
_EOKBU = CanonicalRoleMap(yong="土", hui="金", gi="木", gu="火", han="水")
_PATTERN = CanonicalRoleMap(yong="水", hui="金", gi="土", gu="火", han="木")


def _cand(role_map, score, model="eokbu", rank=1):
    return RoleModelCandidate(
        model_id=model, model_version="v1", score=Decimal(str(score)), rank=rank,
        role_map=role_map, selection_reason_codes=("axis_top_score",))


def _case_a(primary_score="0.1508", alternate_score="0.1400"):
    return build_role_candidate_set(
        primary=_cand(_EOKBU, primary_score),
        alternate=_cand(_PATTERN, alternate_score, model="pattern", rank=2),
        score_model_version="yongsin.v2",
    )


# ── 완전 보존 ────────────────────────────────────────────────────────────


def test_both_role_maps_are_preserved_in_full() -> None:
    """부분 diff 만 저장하면 역할 규칙이 바뀔 때 원본 후보를 복원할 수 없다."""
    s = _case_a()
    assert s.primary.role_map == _EOKBU
    assert s.alternate is not None and s.alternate.role_map == _PATTERN
    for role_map in (s.primary.role_map, s.alternate.role_map):
        assert len(role_map.elements()) == 5
        assert len(set(role_map.elements())) == 5


def test_difference_kinds_are_derived_not_a_substitute() -> None:
    """`difference_kinds` 는 파생값이다 — 이것만으로 후보를 대체하지 않는다."""
    s = _case_a()
    assert s.difference_kinds
    # 파생값을 지워도 원본 역할표로 다시 만들 수 있다.
    rebuilt = role_map_differences(s.primary.role_map, s.alternate.role_map)
    assert rebuilt == s.difference_kinds


def test_scores_and_margins_are_preserved() -> None:
    s = _case_a()
    assert s.primary.score == Decimal("0.1508")
    assert s.alternate is not None and s.alternate.score == Decimal("0.1400")
    assert s.absolute_margin == Decimal("0.0108")
    assert s.relative_margin is not None      # 진단용으로 보존
    assert s.score_model_version == "yongsin.v2"


def test_model_versions_and_policy_version_are_recorded() -> None:
    s = _case_a()
    assert s.policy_version == ROLE_COMPETITION_POLICY_VERSION
    assert s.primary.model_version and s.alternate is not None
    assert s.primary.selection_reason_codes


# ── 경쟁 대역 ────────────────────────────────────────────────────────────


def test_case_a_is_close_and_sensitivity_eligible() -> None:
    s = _case_a()
    assert s.competition_band is RoleCompetitionBand.CLOSE
    assert s.sensitivity_eligible is True


@pytest.mark.parametrize(
    ("alt_score", "expected"),
    [("0.1309", RoleCompetitionBand.CLOSE),    # margin 0.0199
     ("0.1308", RoleCompetitionBand.CLEAR)],   # margin 0.0200
)
def test_threshold_is_strict_less_than(alt_score, expected) -> None:
    """0.0200 은 CLEAR 다 — 비교가 `<` 임을 경계값으로 고정한다."""
    s = _case_a(alternate_score=alt_score)
    assert s.competition_band is expected
    assert s.sensitivity_eligible is (expected is RoleCompetitionBand.CLOSE)


def test_threshold_constant_is_explicit() -> None:
    assert ROLE_CLOSE_MARGIN_V1 == Decimal("0.0200")


def test_equivalent_role_maps_are_not_sensitivity_targets() -> None:
    s = build_role_candidate_set(
        primary=_cand(_EOKBU, "0.1508"),
        alternate=_cand(_EOKBU, "0.1507", model="pattern", rank=2))
    assert s.role_map_equivalent is True
    assert s.competition_band is RoleCompetitionBand.EQUIVALENT
    assert s.sensitivity_eligible is False
    assert s.difference_kinds == ()


def test_missing_alternate_is_unavailable() -> None:
    s = build_role_candidate_set(primary=_cand(_EOKBU, "0.1508"), alternate=None)
    assert s.competition_band is RoleCompetitionBand.UNAVAILABLE
    assert s.sensitivity_eligible is False
    assert s.absolute_margin is None


# ── 보존과 실행의 분리 ───────────────────────────────────────────────────


def test_non_equivalent_alternate_is_preserved_regardless_of_margin() -> None:
    """임계값을 나중에 바꿔도 원본 후보를 잃지 않아야 한다."""
    wide = _case_a(alternate_score="0.0500")     # margin 0.1008 — CLEAR
    assert wide.competition_band is RoleCompetitionBand.CLEAR
    assert wide.sensitivity_eligible is False
    assert wide.alternate is not None            # **보존은 된다**
    assert wide.alternate.role_map == _PATTERN


def test_polarity_flip_alone_does_not_enable_shadow() -> None:
    """점수 차가 명확한데 반전을 근거로 실행하면 후보 점수 시스템이 무효가 된다."""
    wide = _case_a(alternate_score="0.0500")
    assert wide.has_polarity_flip is True
    assert wide.sensitivity_eligible is False


def test_case_a_difference_kinds_match_the_measured_shape() -> None:
    """01a 측정과 같은 세 유형이 나와야 한다."""
    kinds = set(_case_a().difference_kinds)
    assert RoleMapDifferenceKind.FAVORABLE_ADVERSE_FLIP in kinds      # 土
    assert RoleMapDifferenceKind.FAVORABLE_NEUTRAL_SHIFT in kinds     # 水
    assert RoleMapDifferenceKind.ADVERSE_NEUTRAL_SHIFT in kinds       # 木


def test_at_most_one_alternate_is_carried() -> None:
    assert MAX_ALTERNATE_CANDIDATES == 1
    fields = {f.name for f in dataclasses.fields(_case_a())}
    assert "alternates" not in fields and "candidates" not in fields


# ── canonical 불변 ───────────────────────────────────────────────────────


def test_alternate_never_changes_the_canonical_role_map() -> None:
    s = _case_a()
    assert s.primary.role_map == _EOKBU
    assert s.primary.role_map.role_of("土") is CanonicalRole.YONG
    assert s.alternate is not None
    assert s.alternate.role_map.role_of("土") is CanonicalRole.GI
    # 후보가 있어도 canonical 은 primary 그대로다.
    assert s.primary.role_map.yong == "土"


def test_no_blending_path_exists() -> None:
    """두 역할표를 평균·합산하는 인터페이스를 두지 않는다."""
    banned = ("blend", "merge", "average", "mean", "combine", "sum", "mix")
    for name in (n for n in dir(mod) if not n.startswith("_")):
        assert not any(w in name.lower() for w in banned), name


def test_requires_validation_is_not_part_of_the_contract() -> None:
    """26 명식 전건 True 라 판별력이 없다 — 경계 판정 입력에서 배제한다."""
    source = inspect.getsource(mod.build_role_candidate_set)
    assert "requires_validation" not in source
    params = inspect.signature(build_role_candidate_set).parameters
    assert "requires_validation" not in params


def test_no_period_projection_is_stored() -> None:
    """기간별 축은 role_map + P2 evaluation 으로 다시 만들 수 있다."""
    fields = {f.name for f in dataclasses.fields(_case_a())}
    for banned in ("activation", "favorable", "adverse", "operability", "period"):
        assert not any(banned in f for f in fields), banned


def test_candidate_set_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _case_a().sensitivity_eligible = False    # type: ignore[misc]
