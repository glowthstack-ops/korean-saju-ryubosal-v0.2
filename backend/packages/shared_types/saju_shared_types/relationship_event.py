"""관계 사건 시스템 3층 타입 — P0-B2 (RELATIONSHIP_EVENT_SYSTEM §3·부록 C-2).

3층 분리(혼동 금지):
- E4 발현 단계(awareness→exploration→action→decision→completion) = 일반 사건의 발현 과정
- `RelationshipStage` = 관계 자체의 진행 단계(상태 머신 어휘)
- `RelationshipCondition` = 관계 품질 상태(같은 DATING이라도 GROWING/FRICTION은 다른 사건)

원칙(부록 C-2):
- 기존 `MarriageStage`는 수정하지 않는다 — 신규 enum + 손실 명시 어댑터로만 연결.
- `SEPARATED`는 stage를 자동 NONE으로 바꾸는 값이 아니다(별거 부부 = MARRIED+SEPARATED).
  단계·상태는 독립 축이며 결합 검증으로 서로를 제약하지 않는다.
- **E4 단계에서 관계 단계를 자동 추론하는 매핑은 금지** — E4 `decision`은 연애 시작·결혼
  진행·이별 중 무엇의 결정인지 알 수 없다. episode 합성(P4)은 사건 키+증거 계약을 동반해야
  하며, 본 모듈은 그런 매핑 함수를 제공하지 않는다(의도적 부재).
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from .marriage_timing import MarriageStage


class RelationshipStage(StrEnum):
    """관계 진행 단계 (§2-1 / §3-1) — canonical 7단계."""

    NONE = "none"                    # 특정 대상·관계 접점 없음
    AWARENESS = "awareness"          # 관심을 받거나 특정 대상이 눈에 들어옴
    CONTACT = "contact"              # 소개·연락·만남·재접촉
    DATING = "dating"                # 상호 관계가 연애로 성립
    COMMITMENT = "commitment"        # 독점성·장래·동거·가족 소개 논의
    FORMALIZATION = "formalization"  # 약혼·혼인 준비·구체적 절차
    MARRIED = "married"              # 혼인 또는 사실상 부부 관계


class RelationshipCondition(StrEnum):
    """관계 품질 상태 (§2-2 / §3-2) — stage와 독립 축."""

    QUIET = "quiet"
    GROWING = "growing"
    AMBIGUOUS = "ambiguous"
    STABLE = "stable"
    FRICTION = "friction"
    DISTANCING = "distancing"
    SEPARATED = "separated"      # stage를 NONE으로 만들지 않는다(예: MARRIED+SEPARATED=별거)
    RECONCILING = "reconciling"


class StageAdaptation(NamedTuple):
    """MarriageStage→RelationshipStage 변환 결과 — 손실 정보를 facets로 보존."""

    stage: RelationshipStage
    facets: tuple[str, ...]  # 단계 축에 담기지 않는 의미(예: family_expansion 사건)


# 기존 MarriageStage(6) → 신규 RelationshipStage(7). relationship→DATING 명칭 정렬,
# family_expansion은 관계 단계가 아니라 혼인 이후 가족 사건 → MARRIED + facet 분리.
_MARRIAGE_TO_RELATIONSHIP: dict[MarriageStage, StageAdaptation] = {
    MarriageStage.AWARENESS: StageAdaptation(RelationshipStage.AWARENESS, ()),
    MarriageStage.CONTACT: StageAdaptation(RelationshipStage.CONTACT, ()),
    MarriageStage.RELATIONSHIP: StageAdaptation(RelationshipStage.DATING, ()),
    MarriageStage.COMMITMENT: StageAdaptation(RelationshipStage.COMMITMENT, ()),
    MarriageStage.FORMALIZATION: StageAdaptation(RelationshipStage.FORMALIZATION, ()),
    MarriageStage.FAMILY_EXPANSION: StageAdaptation(
        RelationshipStage.MARRIED, ("family_expansion",)
    ),
}


def relationship_stage_from_marriage_stage(stage: MarriageStage) -> StageAdaptation:
    """기존 MarriageStage → 신규 RelationshipStage **손실 변환**(이름에 방향 명시).

    `family_expansion`은 MARRIED로 낮춰 담고 원 의미를 facets로 보존한다. 따라서
    **역방향 round-trip은 보장되지 않으며**(MARRIED만으로 family_expansion 복원 불가)
    역변환 함수는 의도적으로 제공하지 않는다(부록 C-2).

    Args:
        stage: 기존 MT 계열 단계.

    Returns:
        StageAdaptation(stage=신규 단계, facets=손실 보존 정보).
    """
    return _MARRIAGE_TO_RELATIONSHIP[stage]
