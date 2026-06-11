"""Phase 2.5 상호작용 탐지기 검증 (T2.5.1·T2.5.2 — docs/09 2장 규격).

소스 혼합 다자합·반합(왕지 플래그)·부분형·원진·천간충·자형·구조 플래그(공망/복음/반음)를
고정한다. 탐지 글자쌍은 relations.json(사전)이 단일 소스다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saju_engines.interactions import (
    InteractionDetector,
    PoolEntry,
    clash_pair_sets,
    natal_structure_flags,
    structure_flags,
)
from saju_shared_types.precompute import InteractionKind
from saju_shared_types.precompute import InteractionSource as S

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def detector() -> InteractionDetector:
    """사전 기반 탐지기(모듈 1회 로드)."""
    return InteractionDetector(_DICTS / "relations.json")


def _kinds(hits) -> set[InteractionKind]:
    return {h.kind for h in hits}


# ── 다자합: 소스 혼합 성립 (docs/09 2-4 핵심) ────────────────────


def test_mixed_source_three_harmony_full(detector: InteractionDetector) -> None:
    """원국 申 + 세운 子 + 일운 辰 = 申子辰 삼합(소스 혼합, partial=False)."""
    pool = [
        PoolEntry(S.NATAL_YEAR, "庚", "申"),
        PoolEntry(S.YEAR, "丙", "子"),
        PoolEntry(S.DAY, "戊", "辰"),
    ]
    hits = [h for h in detector.detect(pool) if h.kind is InteractionKind.BRANCH_THREE_COMBINE]
    assert len(hits) == 1
    hit = hits[0]
    assert not hit.partial
    sources = {p.source for p in hit.participants}
    assert sources == {S.NATAL_YEAR, S.YEAR, S.DAY}  # 참여 소스 기록(누락 금지)


def test_half_harmony_with_royal_flag(detector: InteractionDetector) -> None:
    """申+子 반합 — partial=True, 왕지(子) 포함 → royal_included=True."""
    pool = [PoolEntry(S.NATAL_DAY, "庚", "申"), PoolEntry(S.YEAR, "丙", "子")]
    hits = [h for h in detector.detect(pool) if h.kind is InteractionKind.BRANCH_THREE_COMBINE]
    assert len(hits) == 1 and hits[0].partial and hits[0].royal_included is True


def test_half_harmony_without_royal(detector: InteractionDetector) -> None:
    """申+辰 반합 — 왕지(子) 미포함 → royal_included=False."""
    pool = [PoolEntry(S.NATAL_DAY, "庚", "申"), PoolEntry(S.MONTH, "戊", "辰")]
    hits = [h for h in detector.detect(pool) if h.kind is InteractionKind.BRANCH_THREE_COMBINE]
    assert len(hits) == 1 and hits[0].partial and hits[0].royal_included is False


def test_partial_punishment_triple(detector: InteractionDetector) -> None:
    """寅+巳 부분형(인사신 2자) — partial=True."""
    pool = [PoolEntry(S.NATAL_DAY, "甲", "寅"), PoolEntry(S.YEAR, "丁", "巳")]
    punish = [h for h in detector.detect(pool) if h.kind is InteractionKind.BRANCH_PUNISH]
    assert any(h.partial for h in punish)


# ── 신규 관계: 천간충·원진 (docs/09 2-1·2-2) ─────────────────────


def test_stem_clash_detected(detector: InteractionDetector) -> None:
    """甲庚충 — 천간충 4종이 사전 기반으로 탐지된다."""
    pool = [PoolEntry(S.NATAL_DAY, "甲", "寅"), PoolEntry(S.YEAR, "庚", "戌")]
    assert InteractionKind.STEM_CLASH in _kinds(detector.detect(pool))


def test_wonjin_detected(detector: InteractionDetector) -> None:
    """子未 원진 — 기본 활성."""
    pool = [PoolEntry(S.NATAL_DAY, "丙", "子"), PoolEntry(S.MONTH, "己", "未")]
    assert InteractionKind.WONJIN in _kinds(detector.detect(pool))


def test_amhap_disabled_by_default(detector: InteractionDetector) -> None:
    """암합은 enabled:false — 어떤 풀에서도 탐지되지 않는다."""
    pool = [PoolEntry(S.NATAL_DAY, "戊", "子"), PoolEntry(S.YEAR, "癸", "巳")]
    assert all("암합" not in h.relation_id for h in detector.detect(pool))


def test_self_punishment_cross_source(detector: InteractionDetector) -> None:
    """원국 亥 + 운 亥 = 자형(소스 혼합 2자리)."""
    pool = [PoolEntry(S.NATAL_DAY, "己", "亥"), PoolEntry(S.YEAR, "乙", "亥")]
    selfs = [h for h in detector.detect(pool) if h.kind is InteractionKind.SELF_PUNISH]
    assert len(selfs) == 1 and len(selfs[0].participants) == 2


# ── 구조 플래그 (docs/09 2-3) ────────────────────────────────────


@pytest.fixture(scope="module")
def clash_sets():
    """사전에서 (천간충, 지지충, 육합) 쌍 집합 로드."""
    return clash_pair_sets(_DICTS / "relations.json")


def test_structure_flag_bokeum(clash_sets) -> None:
    """운 간지 == 원국 기둥 간지 → 복음."""
    sc, bc, six = clash_sets
    flags = structure_flags("己", "亥", [("己", "亥")], [], sc, bc, six)
    assert any(f.startswith("복음:") for f in flags)


def test_structure_flag_baneum(clash_sets) -> None:
    """천극지충(천간충+지지충 동시) → 반음. 甲寅 운 vs 庚申 원국."""
    sc, bc, six = clash_sets
    flags = structure_flags("甲", "寅", [("庚", "申")], [], sc, bc, six)
    assert any(f.startswith("반음:") for f in flags)


def test_structure_flag_void(clash_sets) -> None:
    """공망지 전실/충발 플래그."""
    sc, bc, six = clash_sets
    fill = structure_flags("壬", "辰", [("己", "亥")], ["辰", "巳"], sc, bc, six)
    assert any("공망전실" in f for f in fill)
    clash = structure_flags("壬", "戌", [("己", "亥")], ["辰", "巳"], sc, bc, six)
    assert any("공망발동" in f for f in clash)


def test_natal_byeongjon_adjacent_only() -> None:
    """병존은 인접 기둥 동일 간지일 때만."""
    assert natal_structure_flags([("己", "亥"), ("己", "亥"), ("庚", "申")]) == ["병존:己亥"]
    assert natal_structure_flags([("己", "亥"), ("庚", "申"), ("己", "亥")]) == []
