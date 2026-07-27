"""V2 점수 dual-run (P3-b — 2026-07-27 데굴님 확정).

V1과 **같은 raw DomainSignal**을 읽되 원본을 변경하지 않는다. V2는 읽기 전용 복사
뷰에서만 exact duplicate를 제거하고, 부호는 운주 라벨이 아니라 관계 결과에서 온다.

실패 시 계약: V2 결과만 폐기하고 V1 점수를 유지한다. 사용자 요청은 절대 실패시키지
않으며, P1·P2 계층 설명은 그대로 남는다. 넓은 except로 P1·P2나 V1 오류까지 삼키지
않도록 V2 전용 예외(V2ScoringError)와 구조 감사 실패만 포착한다.

polarity 조인은 `relation_id` 기준이다. P0가 관계 라벨당 하나의 semantics를 확정하므로
같은 관계의 여러 발생(월지 亥/일지 亥의 寅亥合)은 부호가 동일하다. 발생 구분이 필요한
곳은 dedupe이며, 그쪽은 신호 자신의 participant_occurrence_ids를 쓴다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from saju_shared_types.luck_hierarchy import LuckHierarchy
from saju_shared_types.period_role_summary import (
    SlotStatusResult,
    SlotStatusSource,
)
from saju_shared_types.precompute import LuckComposite
from saju_shared_types.relation_semantics import PolarityState

from .period_role_summary import derive_slot_status
from .period_v2_config import LOCAL_ADVERSE_ONLY_ENABLED
from .signal_magnitude import v2_contribution
from .signal_occurrence import canonical_identity_key
from .signal_polarity import (
    RelationPolarityResult,
    ScoreExclusionReason,
    classify_relation_polarity,
)
from .topic_builder import _DOMAIN_TO_CATEGORY
from .v2_coverage import V2Coverage, accumulate_coverage, signal_identity


class V2ScoringError(Exception):
    """V2 계산 전용 예외 — 이 예외만 V1 폴백으로 잡는다."""


class V2ActivationStatus(StrEnum):
    """V2 결과를 사용자에게 노출할 수 있는가.

    판정 우선순위는 DISABLED → INVARIANT_FAILED → INCOMPLETE_COVERAGE → ACTIVE다.
    구조 감사 실패를 coverage보다 먼저 두는 이유는, 계산 결과 자체가 비정상인데
    이를 단순 데이터 부족으로 숨기지 않기 위해서다(데굴님 확정).
    """

    ACTIVE = "ACTIVE"
    INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
    INVARIANT_FAILED = "INVARIANT_FAILED"
    DISABLED = "DISABLED"


class V2CategoryTotals(BaseModel):
    """카테고리 1개의 부호별 합계. 양쪽 모두 0 이상 magnitude로 유지한다."""

    positive_total: float = 0.0
    negative_total: float = 0.0  # 크기(양수)로 누적 — 음수를 더하지 않는다
    signed_signal_count: int = 0
    neutral_signal_count: int = 0
    volatility_signal_count: int = 0
    mixed_unallocated_signal_count: int = 0
    #: 층위별 긍정 기여 — 상위 지지 판정의 근거. 최종 라벨(FAVORABLE/MIXED)이
    #: 아니라 **그 카테고리에 실제 긍정 기여가 있었는지**로 본다. 대운이 MIXED여도
    #: 해당 카테고리에 긍정 기여가 있으면 상위 지지로 인정한다.
    positive_by_level: dict[str, float] = Field(default_factory=dict)
    #: 층위별 부정 기여 — 부정 방향 shadow 판정 근거(대칭 구조).
    negative_by_level: dict[str, float] = Field(default_factory=dict)

    @property
    def upper_negative_support(self) -> bool:
        """대운·세운에 같은 카테고리 부정 기여가 있는가."""
        return any(
            self.negative_by_level.get(level, 0.0) > 0
            for level in ("daewoon", "year")
        )

    @property
    def upper_positive_support(self) -> bool:
        """대운·세운에 같은 카테고리 긍정 기여가 있는가."""
        return any(
            self.positive_by_level.get(level, 0.0) > 0
            for level in ("daewoon", "year")
        )

    @property
    def net_raw(self) -> float:
        """순합 — 음수가 정상 상태다(ADVERSE_DOMINANT)."""
        return round(self.positive_total - self.negative_total, 6)


class V2ScoringResult(BaseModel):
    """dual-run 결과 — 노출 여부와 진단 정보를 함께 담는다."""

    activation_status: V2ActivationStatus
    totals: dict[str, V2CategoryTotals] = Field(default_factory=dict)
    slot_status: dict[str, SlotStatusResult] = Field(default_factory=dict)
    coverage: V2Coverage = Field(default_factory=V2Coverage)
    raw_signal_count: int = 0
    deduplicated_signal_count: int = 0
    duplicate_removed_count: int = 0
    invariant_failure_codes: list[str] = Field(default_factory=list)
    fallback_reason: str = ""

    @property
    def narrative_eligible(self) -> bool:
        """사용자에게 V2 점수·slot_status를 보여도 되는가."""
        return self.activation_status is V2ActivationStatus.ACTIVE


def _polarity_source(result: RelationPolarityResult) -> str:
    """의미 근거 라벨 — 계산 정체성 구성요소(파생 출처가 아니다)."""
    if result.exclusion_reason is ScoreExclusionReason.STRUCTURAL_ONLY:
        return "STRUCTURAL_ONLY"
    if result.narrative_axis in ("mitigation", "loss", "mixed_binding"):
        return "AFFECTED_TARGET_EFFECT"
    return "RESULT_ELEMENT_ROLE"


def _effect_identity(hierarchy: LuckHierarchy, relation_id: str) -> str:
    """관계 효과의 정체성 — 대상·역할까지 포함해 서로 다른 효과를 구분한다."""
    inter = hierarchy.by_id(relation_id)
    if inter is None:
        return ""
    parts = sorted(
        f"{e.effect.value}:{e.target}:{e.role or '-'}:{e.ten_god or '-'}"
        for e in inter.effects
    )
    return "|".join(parts)


def _polarity_index(
    hierarchy: LuckHierarchy,
) -> dict[str, RelationPolarityResult]:
    """relation_id → 분류 결과. 같은 관계의 여러 발생은 부호가 같다."""
    index: dict[str, RelationPolarityResult] = {}
    for inter in hierarchy.interactions:
        index.setdefault(inter.interaction_id, classify_relation_polarity(inter))
    return index


def _audit(result: V2ScoringResult) -> list[str]:
    """구조 불변식 감사. net_raw<0과 display_clamped=True는 정상이라 차단하지 않는다."""
    codes: list[str] = []
    for category, totals in result.totals.items():
        if totals.positive_total < 0 or totals.negative_total < 0:
            codes.append(f"NEGATIVE_TOTAL:{category}")
        for value in (totals.positive_total, totals.negative_total):
            if value != value or value in (float("inf"), float("-inf")):  # NaN/inf
                codes.append(f"NON_FINITE_TOTAL:{category}")
    for category, status in result.slot_status.items():
        counts = (
            status.signed_signal_count + status.neutral_signal_count
            + status.volatility_signal_count + status.mixed_unallocated_signal_count
        )
        if status.status.value == "NO_SIGNAL" and counts > 0:
            codes.append(f"NO_SIGNAL_WITH_SIGNALS:{category}")
        if (
            status.status.value == "DIRECTION_UNRESOLVED"
            and status.mixed_unallocated_signal_count == 0
        ):
            codes.append(f"DIRECTION_UNRESOLVED_WITHOUT_MIXED:{category}")
        if status.status.value == "VOLATILITY_ONLY" and (
            status.positive_total > 0 or status.negative_total > 0
        ):
            codes.append(f"VOLATILITY_ONLY_WITH_SIGNED:{category}")
    return codes


def build_v2_scoring(
    composites: list[LuckComposite],
    hierarchy: LuckHierarchy,
    *,
    enabled: bool,
) -> V2ScoringResult:
    """V2 점수를 계산한다(V1 원본 불변).

    Args:
        composites: V1이 쓰는 것과 **같은** 기간 범위 composite 목록.
        hierarchy: P1 계층 SSOT(관계 의미·부호의 출처).
        enabled: PILLAR_POLARITY_V2 플래그.

    Returns:
        노출 가능 여부와 진단 정보를 담은 결과.

    Raises:
        V2ScoringError: V2 계산 자체가 불가능한 경우(호출부가 V1로 폴백).
    """
    if not enabled:
        return V2ScoringResult(
            activation_status=V2ActivationStatus.DISABLED,
            fallback_reason="pillar_polarity_v2_disabled",
        )
    try:
        polarity_by_relation = _polarity_index(hierarchy)
        coverage = V2Coverage()
        totals: dict[str, V2CategoryTotals] = {}
        seen: set[str] = set()
        raw_count = 0
        deduped_count = 0

        for comp in composites:
            for signal in comp.domain_signals:  # 읽기 전용 — 원본을 바꾸지 않는다
                raw_count += 1
                verdict = polarity_by_relation.get(signal.source_interaction)
                if verdict is None:
                    # 계층에 없는 관계 — 이번 기간 스택 밖이므로 점수 대상이 아니다.
                    continue
                identity = signal_identity(
                    relation_id=signal.source_interaction,
                    occurrence_ids=set(
                        canonical_identity_key(signal.participant_occurrence_ids)
                    ),
                    effect_identity=_effect_identity(
                        hierarchy, signal.source_interaction
                    ),
                    domain=signal.domain,
                    source_period=comp.period_key,
                    magnitude_path=signal.magnitude_formula_id,
                    polarity_source=_polarity_source(verdict),
                )
                if identity in seen:
                    continue  # occurrence·effect까지 같은 실제 중복만 제거
                seen.add(identity)
                deduped_count += 1

                accumulate_coverage(coverage, identity, verdict)
                category = _DOMAIN_TO_CATEGORY.get(signal.domain, "decision")
                bucket = totals.setdefault(category, V2CategoryTotals())
                if verdict.exclusion_reason is ScoreExclusionReason.MIXED_UNALLOCATED:
                    bucket.mixed_unallocated_signal_count += 1
                    continue
                if verdict.exclusion_reason is ScoreExclusionReason.STRUCTURAL_ONLY:
                    bucket.volatility_signal_count += 1
                    continue
                if not verdict.score_eligible:
                    continue
                if signal.unsigned_magnitude_v2 is None:
                    raise V2ScoringError(
                        f"unsigned_magnitude_v2 누락: {signal.source_interaction}"
                    )
                if verdict.polarity_state is PolarityState.NEUTRAL:
                    bucket.neutral_signal_count += 1
                    continue
                contribution = v2_contribution(
                    signal.unsigned_magnitude_v2, verdict.score_polarity
                )
                bucket.signed_signal_count += 1
                if contribution >= 0:
                    bucket.positive_total = round(
                        bucket.positive_total + contribution, 6
                    )
                    level_key = comp.level.value
                    bucket.positive_by_level[level_key] = round(
                        bucket.positive_by_level.get(level_key, 0.0) + contribution, 6
                    )
                else:
                    bucket.negative_total = round(
                        bucket.negative_total + abs(contribution), 6
                    )
                    level_key = comp.level.value
                    bucket.negative_by_level[level_key] = round(
                        bucket.negative_by_level.get(level_key, 0.0)
                        + abs(contribution), 6
                    )

        slot_status = {
            category: derive_slot_status(
                positive_total=t.positive_total,
                negative_total=t.negative_total,
                neutral_signal_count=t.neutral_signal_count,
                volatility_signal_count=t.volatility_signal_count,
                mixed_unallocated_signal_count=t.mixed_unallocated_signal_count,
                signed_signal_count=t.signed_signal_count,
                upper_positive_support=t.upper_positive_support,
                upper_negative_support=t.upper_negative_support,
                local_adverse_cap_enabled=LOCAL_ADVERSE_ONLY_ENABLED,
                source=SlotStatusSource.POLARITY_V2,
            )
            for category, t in totals.items()
        }
        result = V2ScoringResult(
            activation_status=V2ActivationStatus.ACTIVE,
            totals=totals, slot_status=slot_status, coverage=coverage,
            raw_signal_count=raw_count,
            deduplicated_signal_count=deduped_count,
            duplicate_removed_count=raw_count - deduped_count,
        )
    except V2ScoringError:
        raise
    except Exception as exc:  # noqa: BLE001 — V2 계산 실패를 전용 예외로 좁힌다
        raise V2ScoringError(f"V2 계산 실패: {exc}") from exc

    # 우선순위: 구조 감사 실패 > coverage 부족 > ACTIVE.
    codes = _audit(result)
    if codes:
        result.activation_status = V2ActivationStatus.INVARIANT_FAILED
        result.invariant_failure_codes = codes
        result.fallback_reason = "invariant_failed"
    elif not coverage.complete:
        result.activation_status = V2ActivationStatus.INCOMPLETE_COVERAGE
        result.fallback_reason = "incomplete_coverage"
    return result
