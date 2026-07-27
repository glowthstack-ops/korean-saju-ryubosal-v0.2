"""관계 → 길흉 부호 분류 SSOT (P3 — 2026-07-27 데굴님 확정).

**P1 렌더 축과 P3 점수 부호가 같은 함수를 쓴다.** 분류기를 둘로 나누면 화면 설명과
점수가 서로 다른 규칙으로 갈라진다(drift) — 이번 사건이 정확히 그 유형이었다.

부호는 **관계 자체의 결과**에서 도출한다. 운주(간지) 단일 라벨에서 상속받지 않는다.
그 상속이 乙未를 통째로 '기신'으로 만들어 未土(용신)의 지원을 지운 원인이었다.

이번 릴리즈의 경계(데굴님 확정):
  - 혼재 관계(boon+harm 공존)에 단일 부호를 강제하지 않는다. 대상별 magnitude 근거가
    없으므로 signed score에는 반영하지 않고 혼재 신호로만 보존한다.
  - 충·형·파·해·원진은 길흉을 판정하지 않는다(변동성만).
  - ENGINE_CONFLICT는 점수·변동성·서술 모두에서 제외한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from saju_shared_types.luck_hierarchy import (
    HierarchyInteraction,
    SemanticResolutionStatus,
)
from saju_shared_types.relation_semantics import (
    BindingState,
    EffectFavorability,
    EffectKind,
    PolarityState,
)

#: 강화 계열 효과 — 결과 오행의 역할이 부호를 정한다.
_STRENGTHEN_KINDS = frozenset(
    {EffectKind.STRENGTHENED, EffectKind.PARTIALLY_STRENGTHENED}
)


class ScoreExclusionReason(StrEnum):
    """점수에서 빠진 이유. coverage 계산이 정상 제외를 '파생 실패'로 세지 않게 한다.

    丙壬沖(길흉 규칙 미정)과 亥未(성립 미확정)와 丁壬 쟁합(배분 근거 없음)은 모두
    score_eligible=False지만 성격이 전혀 다르다. DERIVATION_UNAVAILABLE만이
    'V2 파생 실패'이며, 나머지는 정책상 정상 제외다(2026-07-27 데굴님 확정).
    """

    NONE = "NONE"  # 점수 대상
    STRUCTURAL_ONLY = "STRUCTURAL_ONLY"  # 충·형·파·해 — 길흉 규칙 미정(변동성은 반영)
    ENGINE_CONFLICT = "ENGINE_CONFLICT"  # 성립 자체가 미확정
    MIXED_UNALLOCATED = "MIXED_UNALLOCATED"  # 혼재 — 대상별 배분 근거 없음
    UNKNOWN_ROLE = "UNKNOWN_ROLE"  # 역할 미상
    DERIVATION_UNAVAILABLE = "DERIVATION_UNAVAILABLE"  # 원본 부족 — 유일한 coverage 실패

    @property
    def is_coverage_failure(self) -> bool:
        """coverage 실패로 세야 하는가 — 원래 계산해야 했는데 못한 경우만."""
        return self is ScoreExclusionReason.DERIVATION_UNAVAILABLE


class RelationPolarityResult(BaseModel):
    """관계 1건의 분류 결과.

    P1과 P3가 **같은 함수**를 쓰되 **다른 필드**를 소비한다.
      - P1 렌더  : narrative_axis (+ P0 canonical semantics)
      - P3 점수  : polarity_state / score_polarity / score_eligible
    점수 대상이 아니라는 이유로 P1 서술에서 사라지면 안 된다(丙壬沖이 그 예).
    """

    narrative_axis: str
    polarity_state: PolarityState
    score_polarity: int = 0
    score_eligible: bool = False
    volatility_eligible: bool = False
    exclusion_reason: ScoreExclusionReason = ScoreExclusionReason.NONE


def _binding_polarity(inter: HierarchyInteraction) -> RelationPolarityResult:
    """합반·합거 — 관계 이름이나 결과 오행이 아니라 effects[]로 판정한다.

    진리표(P1 렌더 축과 동일 SSOT):
        boon O / harm X → POSITIVE  (MITIGATION)
        boon X / harm O → NEGATIVE  (LOSS)
        boon O / harm O → MIXED     (MIXED_BINDING · 점수 보류)
        boon X / harm X → NEUTRAL   (NEUTRAL_ACTIVATION)
    """
    favs = {e.favorability for e in inter.effects if e.effect is EffectKind.SUPPRESSED}
    boon = EffectFavorability.BENEFICIAL in favs
    harm = EffectFavorability.ADVERSE in favs
    if boon and harm:
        # 대상별 magnitude를 나눌 근거가 엔진에 없다. 임의 배분(50:50)은 새 규칙이므로
        # 부호를 주지 않고 혼재 신호로만 남긴다. coverage 실패가 아니라 정책상 보류다.
        return RelationPolarityResult(
            narrative_axis="mixed_binding",
            polarity_state=PolarityState.MIXED,
            volatility_eligible=True,
            exclusion_reason=ScoreExclusionReason.MIXED_UNALLOCATED,
        )
    if boon:
        return RelationPolarityResult(
            narrative_axis="mitigation", polarity_state=PolarityState.POSITIVE,
            score_polarity=1, score_eligible=True, volatility_eligible=True,
        )
    if harm:
        return RelationPolarityResult(
            narrative_axis="loss", polarity_state=PolarityState.NEGATIVE,
            score_polarity=-1, score_eligible=True, volatility_eligible=True,
        )
    return RelationPolarityResult(
        narrative_axis="neutral_activation", polarity_state=PolarityState.NEUTRAL,
        score_eligible=True, volatility_eligible=True,
    )


def classify_relation_polarity(inter: HierarchyInteraction) -> RelationPolarityResult:
    """관계 1건의 분류. P1 렌더와 P3 점수가 공유하는 유일한 판정 경로.

    Args:
        inter: 계층형 grounding의 관계(의미는 P0가 확정한 값).

    Returns:
        서술 축과 점수 정책을 함께 담은 RelationPolarityResult.
    """
    status = inter.semantic_resolution_status
    if status is SemanticResolutionStatus.ENGINE_CONFLICT:
        # 성립 자체가 미확정 — 점수·변동성·서술 모두 제외.
        return RelationPolarityResult(
            narrative_axis="neutral_activation",
            polarity_state=PolarityState.UNRESOLVED,
            exclusion_reason=ScoreExclusionReason.ENGINE_CONFLICT,
        )
    if status is SemanticResolutionStatus.STRUCTURAL_ONLY:
        # 충·형·파·해·원진 — 성립은 확정이나 길흉 규칙이 미정.
        # **서술에는 남는다**(층간 긴장). 점수만 제외하고 변동성은 반영 대상이다.
        return RelationPolarityResult(
            narrative_axis="structural_tension",
            polarity_state=PolarityState.UNRESOLVED,
            volatility_eligible=True,
            exclusion_reason=ScoreExclusionReason.STRUCTURAL_ONLY,
        )
    if inter.binding_state in (BindingState.BOUND, BindingState.REMOVED):
        return _binding_polarity(inter)

    # 합·국·부분 강화 — 결과 오행의 용희기구한 역할이 부호를 정한다.
    # relation family 이름(rel_寅卯辰方合)이 아니라 result_element·effect·성립 상태에서
    # 도출한다. 부분 성립은 표시에서 '부분'으로 남고 완성으로 승격되지 않는다.
    for eff in inter.effects:
        if eff.target != inter.result_element or eff.effect not in _STRENGTHEN_KINDS:
            continue
        if eff.favorability is EffectFavorability.BENEFICIAL:
            return RelationPolarityResult(
                narrative_axis="favorable_activation",
                polarity_state=PolarityState.POSITIVE,
                score_polarity=1, score_eligible=True, volatility_eligible=True,
            )
        if eff.favorability is EffectFavorability.ADVERSE:
            return RelationPolarityResult(
                narrative_axis="adverse_activation",
                polarity_state=PolarityState.NEGATIVE,
                score_polarity=-1, score_eligible=True, volatility_eligible=True,
            )
        # 한신(조건부) — 사전이 'conditional'이라 방향을 단정하지 않는다.
        return RelationPolarityResult(
            narrative_axis="neutral_activation",
            polarity_state=PolarityState.NEUTRAL,
            score_eligible=True, volatility_eligible=True,
        )
    # 역할 미상 — 임의 추정하지 않는다(coverage 실패는 아니다).
    return RelationPolarityResult(
        narrative_axis="neutral_activation",
        polarity_state=PolarityState.UNRESOLVED,
        volatility_eligible=True,
        exclusion_reason=ScoreExclusionReason.UNKNOWN_ROLE,
    )
