"""Phase 2.5 LuckComposite 계산기·저장소 검증 (T2.5.3 — docs/09 1·3장).

검수 포인트(docs/07): 동일 (대상, 기간, dictVersion) → byte 동일 LuckComposite(결정성).
저장소 테스트는 전용 DB(saju-v2-db, 5433)가 떠 있을 때만 실행(없으면 skip).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.precompute import CompositeBuilder
from saju_engines.precompute_store import PrecomputeStore, default_dsn
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.precompute import CompositeLevel, InteractionSource

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_TEST_DSN = default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"


def _db_available() -> bool:
    """전용 DB 기동 여부 — 미기동 시 저장소 테스트 skip."""
    try:
        PrecomputeStore(_TEST_DSN).migrate()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def result():
    """기준 차트(1980-11-22, 기준일 2026-06-11)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def composites(result):
    """전체 레벨 LuckComposite."""
    builder = CompositeBuilder(_DICTS)
    return builder.build(result, "subject-test", "1.0.0", "2026-06-11T00:00:00+00:00")


def test_levels_present(composites) -> None:
    """natal 1 + 대운 10 + 세운/월운/일운 레코드가 모두 생성된다."""
    by_level: dict[CompositeLevel, int] = {}
    for c in composites:
        by_level[c.level] = by_level.get(c.level, 0) + 1
    assert by_level[CompositeLevel.NATAL] == 1
    assert by_level[CompositeLevel.DAEWOON] == 10
    assert by_level[CompositeLevel.YEAR] == 10  # 기준일 -4 ~ +5
    assert by_level[CompositeLevel.MONTH] == 12
    assert by_level[CompositeLevel.DAY] == 30  # 2026-06


def test_level_records_only_contain_own_source(composites) -> None:
    """레벨 레코드의 상호작용은 그 레벨 소스가 참여한 것만(P 분할 규칙)."""
    for c in composites:
        if c.level is CompositeLevel.NATAL:
            natal_sources = {
                InteractionSource.NATAL_YEAR, InteractionSource.NATAL_MONTH,
                InteractionSource.NATAL_DAY, InteractionSource.NATAL_HOUR,
            }
            for hit in c.interactions:
                assert {p.source for p in hit.participants} <= natal_sources
        else:
            own = InteractionSource(str(c.level))
            for hit in c.interactions:
                assert any(p.source == own for p in hit.participants)


def test_parent_context_attached(composites) -> None:
    """월운/일운 레코드는 상위 레벨 간지(parentContext)를 동반한다(LLM 보완용)."""
    months = [c for c in composites if c.level is CompositeLevel.MONTH]
    days = [c for c in composites if c.level is CompositeLevel.DAY]
    assert all(c.parent_context.daewoon and c.parent_context.year for c in months)
    assert all(
        c.parent_context.daewoon and c.parent_context.year and c.parent_context.month
        for c in days
    )


def test_determinism_byte_identical(result) -> None:
    """동일 (대상, 기간, dictVersion) → byte 동일 직렬화(docs/07 검수 포인트)."""
    builder = CompositeBuilder(_DICTS)
    a = builder.build(result, "s", "1.0.0", "2026-06-11T00:00:00+00:00")
    b = builder.build(result, "s", "1.0.0", "2026-06-11T00:00:00+00:00")
    assert [x.model_dump_json() for x in a] == [y.model_dump_json() for y in b]


def test_natal_uses_day_pillar_and_p01(composites, result) -> None:
    """natal 레코드: 대표 간지=일주, P01 상호작용·신살 수록."""
    natal = next(c for c in composites if c.level is CompositeLevel.NATAL)
    assert natal.ganji.stem == result.pillars.day.stem
    assert natal.ganji.branch == result.pillars.day.branch
    assert natal.period_key == "natal"
    assert natal.shinsal_active  # 엔진 신살 그대로 사용(재정의 금지)


def test_domain_signals_traceable(composites) -> None:
    """도메인 신호는 sourceInteraction으로 관계 역추적이 가능하다."""
    with_signals = [c for c in composites if c.domain_signals]
    assert with_signals
    for c in with_signals:
        ids = {h.relation_id for h in c.interactions}
        assert all(s.source_interaction in ids for s in c.domain_signals)


# ── 저장소 (전용 DB 필요 — 미기동 시 skip) ────────────────────────


@pytest.mark.skipif(not _db_available(), reason="saju-v2-db(5433) 미기동")
def test_store_roundtrip_and_invalidation(composites) -> None:
    """upsert→get 동일, 구버전 무효화, 대상 무효화, day 보존 정리."""
    store = PrecomputeStore(_TEST_DSN)
    store.migrate()
    store.invalidate_subject("subject-test")

    n = store.upsert(composites)
    assert n == len(composites)

    natal = next(c for c in composites if c.level is CompositeLevel.NATAL)
    loaded = store.get("subject-test", CompositeLevel.NATAL, "natal", "1.0.0")
    assert loaded is not None and loaded.model_dump() == natal.model_dump()

    # 멱등 upsert(동일 키 갱신) — 건수 불변.
    store.upsert([natal])
    assert len(store.list_for("subject-test", "1.0.0")) == len(composites)

    # 구버전 무효화: 다른 dict_version 레코드 삽입 후 현재 버전만 남긴다.
    old = natal.model_copy(update={"dict_version": "0.9.0"})
    store.upsert([old])
    removed = store.invalidate_other_versions("1.0.0")
    assert removed >= 1
    assert store.get("subject-test", CompositeLevel.NATAL, "natal", "0.9.0") is None

    # day 보존 정리: 2027-06-11 기준이면 2026-06 일운(과거 1년)은 90일 범위 밖.
    purged = store.purge_day_records(date(2027, 6, 11))
    assert purged >= 1

    store.invalidate_subject("subject-test")
