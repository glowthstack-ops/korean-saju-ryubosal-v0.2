"""V2 파생 coverage · 역할 맵 fingerprint · 신호 정체성 (P3 — 2026-07-27 데굴님 확정).

세 가지를 담당한다.

1. **coverage 분리** — 정책상 제외(STRUCTURAL_ONLY·ENGINE_CONFLICT·MIXED_UNALLOCATED)와
   실제 파생 실패(UNKNOWN_ROLE·DERIVATION_UNAVAILABLE)를 구분한다. 이를 섞으면 丁壬
   쟁합 하나 때문에 해당 기간이 영구히 V1에 머문다.
2. **역할 맵 fingerprint** — 규칙 버전이 같아도 그 명식의 용희기구한 배정이 바뀌면
   저장된 polarity는 무효다(같은 火 관계라도 喜→閑이면 부호가 달라진다).
3. **신호 정체성** — exact duplicate는 관계 ID가 아니라 **계산 정체성**으로 판정한다.
   巳午未방합과 寅午반합은 같은 火 클러스터지만 서로 다른 관계이므로 둘 다 남는다.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel

from .signal_polarity import RelationPolarityResult, ScoreExclusionReason

#: 규칙 버전 4종 — 코드·사전 변경을 감지한다.
SIGNAL_SEMANTICS_VERSION = "signal_semantics_v1"
POLARITY_VERSION = "interaction_owned_v1"
FAVORABILITY_RULES_VERSION = "1.0.0"  # favorability_rules.json version 필드
STRUCTURAL_WEIGHT_VERSION = "relations_base_score_v1"

#: 역할 순서 — fingerprint 입력을 결정론적으로 만든다.
_ROLE_ORDER = ("용신", "희신", "기신", "구신", "한신")


def favorability_fingerprint(
    favorability: dict[str, str], yongsin_model_version: str = ""
) -> str:
    """그 명식의 실제 용희기구한 배정 지문.

    규칙 버전만으로는 '같은 火 관계인데 이 사람에게는 喜에서 閑으로 바뀐' 경우를
    잡지 못한다. 저장된 polarity를 재사용해도 되는지 판단하는 기준이다.

    Args:
        favorability: 오행(한자) → 역할.
        yongsin_model_version: 역할 판정 모델 버전(있으면 함께 지문화).

    Returns:
        16자 hex 지문.
    """
    by_role: dict[str, list[str]] = {r: [] for r in _ROLE_ORDER}
    for element, role in favorability.items():
        by_role.setdefault(role, []).append(element)
    parts = [
        f"{role}={''.join(sorted(by_role.get(role, [])))}" for role in _ROLE_ORDER
    ]
    parts.append(f"model={yongsin_model_version}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def v2_semantics_fingerprint(
    favorability: dict[str, str], yongsin_model_version: str = ""
) -> str:
    """규칙 버전 4종 + 역할 맵을 합친 통합 지문 — 비교 실수를 줄인다."""
    parts = [
        SIGNAL_SEMANTICS_VERSION,
        POLARITY_VERSION,
        FAVORABILITY_RULES_VERSION,
        STRUCTURAL_WEIGHT_VERSION,
        favorability_fingerprint(favorability, yongsin_model_version),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def signal_identity(
    *,
    relation_id: str,
    occurrence_ids: set[str],
    effect_identity: str,
    domain: str,
    source_period: str,
    magnitude_path: str,
    polarity_source: str,
) -> str:
    """신호 1건의 계산 정체성 — 이 값이 완전히 같을 때만 exact duplicate다.

    관계 ID만으로 묶으면 서로 다른 도메인·발생에서 각각 유효한 신호가 사라진다.
    """
    parts = [
        relation_id, "|".join(sorted(occurrence_ids)), effect_identity,
        domain, source_period, magnitude_path, polarity_source,
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


class V2Coverage(BaseModel):
    """기간 단위 V2 파생 coverage.

    `v2_coverage_complete`는 '모든 관계에 부호가 있는가'가 아니라 **원래 계산해야 하는
    신호를 계산하지 못한 것이 없는가**를 뜻한다.
    """

    required_signal_count: int = 0
    derived_signal_count: int = 0
    unavailable_signal_count: int = 0
    # 정책상 제외(파생 실패 아님) — 별도 계측.
    structural_only_count: int = 0
    engine_conflict_count: int = 0
    mixed_unallocated_count: int = 0
    neutral_count: int = 0
    unavailable_signal_ids: list[str] = []
    unavailable_reasons: list[str] = []

    @property
    def complete(self) -> bool:
        """부분 V2 노출을 막는 게이트 — 파생 실패가 하나도 없어야 한다."""
        return self.unavailable_signal_count == 0


def accumulate_coverage(
    coverage: V2Coverage, signal_id: str, result: RelationPolarityResult
) -> V2Coverage:
    """분류 결과 1건을 coverage에 반영한다(정책 제외와 파생 실패를 구분).

    Args:
        coverage: 누적 중인 coverage.
        signal_id: 신호 식별자(실패 시 telemetry에 남는다).
        result: 관계 분류 결과.

    Returns:
        갱신된 coverage(같은 객체를 수정해 반환).
    """
    reason = result.exclusion_reason
    if reason is ScoreExclusionReason.STRUCTURAL_ONLY:
        coverage.structural_only_count += 1
        return coverage
    if reason is ScoreExclusionReason.ENGINE_CONFLICT:
        coverage.engine_conflict_count += 1
        return coverage
    if reason is ScoreExclusionReason.MIXED_UNALLOCATED:
        coverage.mixed_unallocated_count += 1
        return coverage

    # 여기부터는 '원래 점수에 들어가야 하는' 신호다.
    coverage.required_signal_count += 1
    if reason in (
        ScoreExclusionReason.UNKNOWN_ROLE,
        ScoreExclusionReason.DERIVATION_UNAVAILABLE,
    ):
        coverage.unavailable_signal_count += 1
        coverage.unavailable_signal_ids.append(signal_id)
        coverage.unavailable_reasons.append(reason.value)
        return coverage
    coverage.derived_signal_count += 1
    if result.score_polarity == 0:
        coverage.neutral_count += 1
    return coverage
