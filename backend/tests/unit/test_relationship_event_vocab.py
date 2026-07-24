"""관계 이벤트 어휘 SSOT lint — P0-B1 (RELATIONSHIP_EVENT_SYSTEM 부록 C-5).

①파일 자체 lint(validate_vocab) ②교차 참조 lint: TopicBuilder 필터·structure pattern
domain_hints·Event Graph event node(EventKeyV2 전수)·taxonomy EVENT_DOMAIN 일치·
LEGACY_EVENT_KEY_MAP 정합 ③provenance 호환 규칙(family_change) 회귀 고정.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.relationship_event_vocab import (
    load_relationship_event_vocab,
    validate_vocab,
)
from saju_engines.topic_builder import (
    M01_EVENT_KEYS,
    M01_LEGACY_EXCLUDE_KEYS,
    M02_EVENT_KEYS,
    M02_LEGACY_COMPAT_KEYS,
    M08_EVENT_KEYS,
)
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.event_taxonomy_v2 import EVENT_DOMAIN, LEGACY_EVENT_KEY_MAP

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def vocab():
    return load_relationship_event_vocab(str(_DICTS))


def test_self_contained_lint_passes(vocab) -> None:
    """파일 자체 lint(중복·순환·충돌·owner·tombstone) 위반 0건."""
    assert validate_vocab(vocab) == []


def test_covers_all_21_canonical_keys(vocab) -> None:
    """EventKeyV2 21키 전수 등록(Event Graph event node와 동일 어휘)."""
    assert vocab.canonical_keys() == {k.value for k in EventKeyV2}


def test_family_matches_taxonomy_event_domain(vocab) -> None:
    """vocab family와 taxonomy EVENT_DOMAIN 일치(이중 저장 불일치 금지)."""
    domain = {str(k): v for k, v in EVENT_DOMAIN.items()}
    for e in vocab.items:
        assert e.family == domain[e.canonical_key], e.canonical_key


def test_aliases_match_legacy_event_key_map(vocab) -> None:
    """vocab alias 집합 == LEGACY_EVENT_KEY_MAP(항등 매핑 제외) — 누락·과잉 금지."""
    expected: dict[str, str] = {
        legacy: canon.value
        for legacy, canon in LEGACY_EVENT_KEY_MAP.items()
        if legacy != canon.value
    }
    assert vocab.alias_map() == expected


def test_topic_builder_filters_registered(vocab) -> None:
    """TopicBuilder 참조 키(M01/M02/M08 canonical) 미등록 금지."""
    canon = vocab.canonical_keys()
    assert M01_EVENT_KEYS <= canon
    assert M02_EVENT_KEYS <= canon
    assert M08_EVENT_KEYS <= canon


def test_topic_builder_legacy_compat_keys_are_aliases(vocab) -> None:
    """M01 배제·M02 호환의 legacy 키(family_change)는 alias로 등록돼 있어야 한다."""
    alias = vocab.alias_map()
    for key in M01_LEGACY_EXCLUDE_KEYS | M02_LEGACY_COMPAT_KEYS:
        assert key in alias, key


def test_family_change_provenance_rule_fixed(vocab) -> None:
    """family_change 호환 규칙 회귀 고정 — canonical은 relationship_change,
    M02 호환·M01 배제 목록에 동일하게 존재(부록 B 결정문)."""
    assert vocab.alias_map()["family_change"] == "relationship_change"
    assert "family_change" in M02_LEGACY_COMPAT_KEYS
    assert "family_change" in M01_LEGACY_EXCLUDE_KEYS
    # canonical relationship_change 자체는 M02가 소비하지 않는다.
    assert "relationship_change" not in M02_EVENT_KEYS
    assert "relationship_change" in M01_EVENT_KEYS


def test_structure_pattern_domain_hints_registered(vocab) -> None:
    """structure_patterns domain_hints의 이벤트 키 미등록 금지."""
    data = json.loads((_DICTS / "structure_patterns.json").read_text("utf-8"))
    pats = data.get("patterns", data)
    items = pats.values() if isinstance(pats, dict) else pats
    canon = vocab.canonical_keys()
    for p in items:
        for hint in p.get("domain_hints", []) or []:
            assert hint in canon, f"미등록 domain_hint: {hint}"


def test_personalized_keys_not_daily_allowed(vocab) -> None:
    """개인화 전용 키의 daily(비개인화 어휘 C) 유입 금지."""
    for e in vocab.items:
        if e.personalized_allowed:
            assert e.daily_allowed is False, e.canonical_key


def test_daily_catalog_namespace_disjoint(vocab) -> None:
    """daily 카탈로그 키와 개인화 canonical/alias namespace 혼용 금지."""
    daily = json.loads(
        (_DICTS / "daily_fortune" / "daily_event_catalog.json").read_text("utf-8")
    )
    daily_keys = set(daily["events"].keys())
    canon = vocab.canonical_keys()
    aliases = set(vocab.alias_map())
    assert daily_keys.isdisjoint(canon)
    assert daily_keys.isdisjoint(aliases)


def test_relationship_keys_owned_by_relationship_event_system(vocab) -> None:
    """relationship family 키의 owner = relationship_event_system."""
    for e in vocab.items:
        if e.family == "relationship":
            assert e.owner == "relationship_event_system", e.canonical_key
