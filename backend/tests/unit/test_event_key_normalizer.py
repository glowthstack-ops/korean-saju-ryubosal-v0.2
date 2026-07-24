"""이벤트 키 정규화 read-adapter 검증 — B1-a (RELATIONSHIP_EVENT_SYSTEM 부록 B).

canonical 해소·general 도메인 수리·provenance 보존·미지 키 보호·계측을 고정한다.
"""

from __future__ import annotations

from saju_engines.event_key_normalizer import (
    NormalizationStats,
    normalize_domain_signal,
    normalize_domain_signals,
)
from saju_shared_types.precompute import DomainSignal


def _sig(event_key: str | None, domain: str = "general") -> DomainSignal:
    return DomainSignal(
        domain=domain, event_key=event_key, weight=0.5, source_interaction="rel_x",
    )


def test_canonical_key_domain_repaired() -> None:
    """canonical 키 + general 오분류(기존 DB 실측 결함) → 도메인 수리·provenance 없음."""
    stats = NormalizationStats()
    out = normalize_domain_signal(_sig("new_relationship", "general"), stats)
    assert out.domain == "relationship" and out.event_key == "new_relationship"
    assert out.source_event_key is None and out.source_taxonomy_version == ""
    assert stats.legacy_general_domain_repaired_count == 1


def test_canonical_key_correct_domain_untouched() -> None:
    """정상 신호는 원본 그대로(복사 없음)."""
    s = _sig("wealth_change", "wealth")
    stats = NormalizationStats()
    assert normalize_domain_signal(s, stats) is s
    assert stats.canonical_signal_count == 1
    assert stats.legacy_general_domain_repaired_count == 0


def test_legacy_key_canonicalized_with_provenance() -> None:
    """구키 → canonical 해소 + source key·taxonomy version 보존(원본 키 유실 금지)."""
    stats = NormalizationStats()
    out = normalize_domain_signal(_sig("family_change", "relationship"), stats)
    assert out.event_key == "relationship_change" and out.domain == "relationship"
    assert out.source_event_key == "family_change"
    assert out.source_taxonomy_version == "legacy"
    assert stats.legacy_event_key_read_count == 1


def test_unknown_key_preserved_and_counted() -> None:
    """미지 키 — 원본·도메인 유지(임의 배정 금지) + 계측."""
    stats = NormalizationStats()
    s = _sig("mystery_key", "general")
    out = normalize_domain_signal(s, stats)
    assert out is s
    assert stats.unknown_legacy_key_count == 1 and stats.unknown_keys == ["mystery_key"]


def test_none_event_key_passthrough() -> None:
    s = _sig(None, "career")
    assert normalize_domain_signal(s) is s


def test_batch_normalization() -> None:
    stats = NormalizationStats()
    out = normalize_domain_signals(
        [_sig("relationship_start"), _sig("health_attention", "general"), _sig("contract")],
        stats,
    )
    assert [s.event_key for s in out] == [
        "new_relationship", "health_attention", "contract_document",
    ]
    assert [s.domain for s in out] == ["relationship", "health", "career"]
    assert stats.legacy_event_key_read_count == 2  # relationship_start, contract
