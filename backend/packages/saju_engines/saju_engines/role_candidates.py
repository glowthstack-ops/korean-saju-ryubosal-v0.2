"""경계 명식 역할 후보 보존 (CAL-ROLE-BORDERLINE-01b, 2026-08-02).

01a 측정이 보인 것은 "어느 역할표가 맞다" 가 아니라 **runner-up 을 버리면 P3 결과 방향이
실제로 뒤집힐 수 있다** 는 사실이다(사례 A: 유리↔불리 반전 3건이 전부 `FULLY_OPERABLE`).
그래서 지금 구조축 tie-break 로 하나를 억지로 고르지 않고 후보를 보존한다.

    canonical      기존 primary 선택을 그대로 유지한다
    alternate      완전한 역할표로 보존한다
    합산·평균      금지 — 두 후보를 섞으면 어느 쪽도 아닌 해석이 된다

**부분 diff 만 저장하지 않는다.** 다른 축으로 가는 오행만 잘라 두면 역할 family 나 모델 규칙이
바뀌었을 때 원래 후보를 복원할 수 없고, "변하지 않은 역할" 도 후보 해석의 일부라는 사실을
잃는다. `difference_kinds` 는 SSOT 가 아니라 빠른 감사를 위한 파생값이며 최종 근거는 두 개의
완전한 역할표다.

기간별 축은 `role_map + P2 evaluation` 으로 결정적으로 다시 만들 수 있으므로 저장하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .role_activation_projection import CanonicalRole

#: 경쟁 임계값. **명리적 진실의 임계값이 아니다** — 현재 후보 점수 체계에서 두 모델의 경쟁이
#: 가깝다고 보는 서비스 정책 v1 이다. 점수 스케일이나 모델 버전이 바뀌면 다시 감사한다.
ROLE_CLOSE_MARGIN_V1 = Decimal("0.0200")
ROLE_COMPETITION_POLICY_VERSION = "role-competition.v1"

#: v1 은 primary 1 + 비동등 runner-up 1 만 보존한다. 전체 후보 목록은 감사 실행에서만 쓴다.
MAX_ALTERNATE_CANDIDATES = 1

_FAVORABLE = frozenset({CanonicalRole.YONG, CanonicalRole.HUI})
_ADVERSE = frozenset({CanonicalRole.GI, CanonicalRole.GU})


class RoleMapDifferenceKind(StrEnum):
    """역할 family 전환과 polarity 반전을 구분한다."""

    SAME_POLARITY_ROLE_CHANGE = "same_polarity_role_change"
    FAVORABLE_NEUTRAL_SHIFT = "favorable_neutral_shift"
    ADVERSE_NEUTRAL_SHIFT = "adverse_neutral_shift"
    FAVORABLE_ADVERSE_FLIP = "favorable_adverse_flip"


class RoleCompetitionBand(StrEnum):
    """후보 경쟁 구간. `requires_validation` 은 쓰지 않는다 — 전건 True 라 판별력이 없다."""

    CLOSE = "close"
    CLEAR = "clear"
    EQUIVALENT = "equivalent"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CanonicalRoleMap:
    """5오행 역할표 전체. 부분 저장하지 않는다."""

    yong: str
    hui: str
    gi: str
    gu: str
    han: str

    def role_of(self, element: str) -> CanonicalRole | None:
        for role, value in (
            (CanonicalRole.YONG, self.yong), (CanonicalRole.HUI, self.hui),
            (CanonicalRole.GI, self.gi), (CanonicalRole.GU, self.gu),
            (CanonicalRole.HAN, self.han),
        ):
            if value == element:
                return role
        return None

    def elements(self) -> tuple[str, ...]:
        return (self.yong, self.hui, self.gi, self.gu, self.han)


@dataclass(frozen=True)
class RoleModelCandidate:
    """후보 하나. 점수·모델 버전·선택 사유를 함께 남긴다."""

    model_id: str
    model_version: str
    score: Decimal
    rank: int
    role_map: CanonicalRoleMap
    selection_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleCandidateSet:
    """primary + 비동등 runner-up 1개. **기간별 projection 은 담지 않는다.**"""

    primary: RoleModelCandidate
    alternate: RoleModelCandidate | None
    absolute_margin: Decimal | None
    #: 진단용으로 보존하되 v1 게이트에는 쓰지 않는다 — 26 표본으로 두 번째 임계값을 세우면
    #: 근거 없는 조건이 하나 더 생긴다.
    relative_margin: Decimal | None
    role_map_equivalent: bool
    difference_kinds: tuple[RoleMapDifferenceKind, ...]
    has_polarity_flip: bool
    competition_band: RoleCompetitionBand
    sensitivity_eligible: bool
    policy_version: str = ROLE_COMPETITION_POLICY_VERSION
    score_model_version: str = ""


def _classify(primary: CanonicalRole, alternate: CanonicalRole) -> RoleMapDifferenceKind:
    p_fav, a_fav = primary in _FAVORABLE, alternate in _FAVORABLE
    p_adv, a_adv = primary in _ADVERSE, alternate in _ADVERSE
    if (p_fav and a_fav) or (p_adv and a_adv):
        return RoleMapDifferenceKind.SAME_POLARITY_ROLE_CHANGE
    if (p_fav and a_adv) or (p_adv and a_fav):
        return RoleMapDifferenceKind.FAVORABLE_ADVERSE_FLIP
    if p_fav or a_fav:
        return RoleMapDifferenceKind.FAVORABLE_NEUTRAL_SHIFT
    return RoleMapDifferenceKind.ADVERSE_NEUTRAL_SHIFT


def role_map_differences(
    primary: CanonicalRoleMap, alternate: CanonicalRoleMap,
) -> tuple[RoleMapDifferenceKind, ...]:
    """두 역할표의 차이 종류. **파생값이며 SSOT 가 아니다.**"""
    kinds: list[RoleMapDifferenceKind] = []
    for element in sorted(set(primary.elements()) | set(alternate.elements())):
        p, a = primary.role_of(element), alternate.role_of(element)
        if p is None or a is None or p is a:
            continue
        kinds.append(_classify(p, a))
    return tuple(sorted(set(kinds), key=lambda k: k.value))


def build_role_candidate_set(
    *,
    primary: RoleModelCandidate,
    alternate: RoleModelCandidate | None,
    score_model_version: str = "",
) -> RoleCandidateSet:
    """후보 집합을 만든다. **보존과 실행을 분리한다.**

        보존   유효한 비동등 runner-up 이 있으면 margin 과 무관하게 남긴다
        실행   `sensitivity_eligible` 은 CLOSE 구간에서만 True

    임계값을 나중에 0.015·0.025 로 바꿔도 원본 후보를 잃지 않고 재측정할 수 있어야 한다.

    Args:
        primary: 엔진이 선택한 후보. canonical 은 이것이며 여기서 바뀌지 않는다.
        alternate: 최고 점수의 비동등 runner-up (없으면 None).
        score_model_version: 점수 체계 버전. 임계값 재감사의 기준이다.

    Returns:
        후보 집합. 두 후보를 평균하거나 합산하는 경로는 없다.
    """
    if alternate is None:
        return RoleCandidateSet(
            primary=primary, alternate=None, absolute_margin=None,
            relative_margin=None, role_map_equivalent=False,
            difference_kinds=(), has_polarity_flip=False,
            competition_band=RoleCompetitionBand.UNAVAILABLE,
            sensitivity_eligible=False, score_model_version=score_model_version,
        )

    equivalent = primary.role_map == alternate.role_map
    kinds = () if equivalent else role_map_differences(
        primary.role_map, alternate.role_map)
    absolute = primary.score - alternate.score
    relative = (absolute / primary.score) if primary.score else None

    if equivalent:
        band = RoleCompetitionBand.EQUIVALENT
    elif absolute < ROLE_CLOSE_MARGIN_V1:
        band = RoleCompetitionBand.CLOSE
    else:
        band = RoleCompetitionBand.CLEAR

    return RoleCandidateSet(
        primary=primary, alternate=alternate, absolute_margin=absolute,
        relative_margin=relative, role_map_equivalent=equivalent,
        difference_kinds=kinds,
        has_polarity_flip=RoleMapDifferenceKind.FAVORABLE_ADVERSE_FLIP in kinds,
        competition_band=band,
        # polarity flip 이 있다는 이유만으로 shadow 를 켜지 않는다 — 점수 차가 명확한데
        # 반전을 근거로 실행하면 후보 점수 시스템 자체가 무효가 된다.
        sensitivity_eligible=band is RoleCompetitionBand.CLOSE,
        score_model_version=score_model_version,
    )
