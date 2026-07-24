"""이벤트 키 정규화 read-adapter — B1-a (RELATIONSHIP_EVENT_SYSTEM 부록 B).

기존 DB composite에는 두 세대 결함이 섞여 있다: ①구키(relationship_start 등) 저장분
②canonical 21키인데 domain="general" 오분류 저장분(종전 쓰기 경로의 구키 도메인 매핑
결함 — P0-A 실측: new_relationship 96건·relationship_change 175건 전부 general).

이 어댑터는 읽기 시점에 `source key 보존 → canonical 해소 → domain 보정` 순으로
정규화한다(부록 B §8-1). 원본 키를 버리지 않고 `source_event_key`·
`source_taxonomy_version`으로 보존해 M02의 legacy family_change 호환 소비를 가능하게
한다(저장 alias ≠ 소비 의미 동일). 미지 키는 원 도메인 유지+계측만(§8-2 — 임의 도메인
배정 금지). 계측 카운터는 B1-b 재계산 후 어댑터 제거 시점 판단 자료다(§8-3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN, LEGACY_EVENT_KEY_MAP
from saju_shared_types.precompute import DomainSignal

logger = logging.getLogger(__name__)

_CANONICAL_DOMAIN: dict[str, str] = {str(k): v for k, v in EVENT_DOMAIN.items()}
_LEGACY_TO_CANONICAL: dict[str, str] = {k: v.value for k, v in LEGACY_EVENT_KEY_MAP.items()}


@dataclass
class NormalizationStats:
    """dual-read 계측(부록 B §8-3) — legacy 소진 후 어댑터 제거 판단용."""

    canonical_signal_count: int = 0
    legacy_event_key_read_count: int = 0
    legacy_general_domain_repaired_count: int = 0
    unknown_legacy_key_count: int = 0
    unknown_keys: list[str] = field(default_factory=list)

    def merge_log(self, context: str) -> None:
        """legacy·미지 키가 있었으면 1줄 로그(운영 관측 — 토큰·출력 무관)."""
        if self.legacy_event_key_read_count or self.unknown_legacy_key_count \
                or self.legacy_general_domain_repaired_count:
            logger.info(
                "event_key_normalize context=%s canonical=%d legacy=%d "
                "domain_repaired=%d unknown=%d unknown_keys=%s",
                context, self.canonical_signal_count, self.legacy_event_key_read_count,
                self.legacy_general_domain_repaired_count, self.unknown_legacy_key_count,
                self.unknown_keys[:5],
            )


def normalize_domain_signal(
    signal: DomainSignal, stats: NormalizationStats | None = None
) -> DomainSignal:
    """DomainSignal 1건 정규화 — canonical 해소·domain 보정·provenance 보존.

    Args:
        signal: 저장된 신호(구키·canonical 혼재 가능).
        stats: 계측 누적기(None이면 계측 생략).

    Returns:
        정규화된 신호(변경 불필요 시 원본 그대로 — 복사 최소화).
    """
    key = signal.event_key
    if key is None:
        return signal
    if key in _CANONICAL_DOMAIN:
        # canonical 키 — 종전 쓰기 결함의 general 오분류만 수리.
        if stats is not None:
            stats.canonical_signal_count += 1
        resolved = _CANONICAL_DOMAIN[key]
        if signal.domain != resolved:
            if stats is not None:
                stats.legacy_general_domain_repaired_count += 1
            return signal.model_copy(update={"domain": resolved})
        return signal
    canonical = _LEGACY_TO_CANONICAL.get(key)
    if canonical is None:
        # 미지 키 — 원본 유지(도메인 임의 배정 금지) + 계측.
        if stats is not None:
            stats.unknown_legacy_key_count += 1
            if key not in stats.unknown_keys:
                stats.unknown_keys.append(key)
        return signal
    if stats is not None:
        stats.legacy_event_key_read_count += 1
    return signal.model_copy(update={
        "event_key": canonical,
        "domain": _CANONICAL_DOMAIN.get(canonical, signal.domain),
        "source_event_key": key,
        "source_taxonomy_version": "legacy",
    })


def normalize_domain_signals(
    signals: list[DomainSignal], stats: NormalizationStats | None = None
) -> list[DomainSignal]:
    """신호 목록 정규화(읽기 전용 어댑터 — 저장 데이터 불변)."""
    return [normalize_domain_signal(s, stats) for s in signals]
