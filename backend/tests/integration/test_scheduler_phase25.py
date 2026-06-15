"""갱신 스케줄러·대상 저장소 검증 (T2.5.4 — 전용 DB saju-v2-db 필요, 미기동 시 skip).

ensure-current 방식 검증: 경계(자정/입춘/절입)를 지나면 period_key가 바뀌어 누락이
생기고, 보충 호출이 곧 T1/T2 갱신이 된다. 동일 기준일 재호출은 0건(멱등).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.precompute import CompositeBuilder
from saju_engines.precompute_scheduler import PrecomputeScheduler
from saju_engines.precompute_store import PrecomputeStore, default_dsn
from saju_engines.subject_store import SubjectStore
from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.precompute import CompositeLevel
from saju_shared_types.subject import SubjectRecord

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_DSN = default_dsn() or "postgresql://saju_v2:saju_v2@localhost:5433/saju_v2"
_SID = "subject-sched-test"


def _db_available() -> bool:
    """전용 DB 기동 여부."""
    try:
        PrecomputeStore(_DSN).migrate()
        SubjectStore(_DSN).migrate()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="saju-v2-db(5433) 미기동")


@pytest.fixture()
def subject() -> SubjectRecord:
    """테스트 대상(구독 → 활성)."""
    return SubjectRecord(
        subject_id=_SID, kind="self", label="검증 대상",
        birth=BirthInput(
            calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
            birth_place_name="서울", gender="male",
        ),
        subscribed=True,
    )


@pytest.fixture()
def scheduler() -> PrecomputeScheduler:
    """저장소 초기화 + 스케줄러 구성(만세 계산 함수 주입)."""
    store = PrecomputeStore(_DSN)
    store.migrate()
    store.invalidate_subject(_SID)
    return PrecomputeScheduler(
        store, CompositeBuilder(_DICTS), calculate, "1.0.0", table=get_table()
    )


def test_subject_store_roundtrip(subject) -> None:
    """대상 저장/조회/활성 판정/삭제."""
    store = SubjectStore(_DSN)
    store.migrate()
    store.upsert(subject)
    loaded = store.get(_SID)
    assert loaded is not None and loaded.birth.birth_date == date(1980, 11, 22)
    assert loaded.is_active(datetime.now(UTC))  # 구독 → 활성
    active = store.list_active(datetime.now(UTC))
    assert any(s.subject_id == _SID for s in active)
    store.delete(_SID)
    assert store.get(_SID) is None


def test_t0_upsert_then_ensure_current_idempotent(subject, scheduler) -> None:
    """T0 전체 재계산 후, 같은 날 ensure_current는 0건(멱등)."""
    today = date(2026, 6, 11)
    saved = scheduler.on_subject_upsert(subject, today, "2026-06-11T00:00:00+00:00")
    assert saved > 50  # natal 1 + 대운 10 + 세운/월운/일운
    assert scheduler.ensure_current(subject, today, "2026-06-11T01:00:00+00:00") == 0


def test_boundary_refresh_via_ensure_current(subject, scheduler) -> None:
    """경계 통과(다음날) → day 레코드 누락 → ensure_current가 보충(T2)."""
    scheduler.on_subject_upsert(subject, date(2026, 6, 11), "2026-06-11T00:00:00+00:00")
    saved = scheduler.ensure_current(subject, date(2026, 7, 1), "2026-07-01T00:00:00+00:00")
    assert saved > 0  # 7/1 일운(+월 경계라 월운도) 보충
    store = PrecomputeStore(_DSN)
    assert store.get(_SID, CompositeLevel.DAY, "2026-07-01", "1.0.0") is not None


def test_daily_batch_and_purge(subject, scheduler) -> None:
    """일일 배치: 활성 대상 보충 + day 보존 정리 보고.

    엔진은 기준일이 속한 달 전체 일운을 한 번에 계산하므로, 같은 달 다음날 배치는
    0건(이미 존재)이고 달이 바뀌면 보충이 일어난다.
    """
    scheduler.on_subject_upsert(subject, date(2026, 6, 11), "2026-06-11T00:00:00+00:00")
    same_month = scheduler.daily_batch(
        [subject], date(2026, 6, 12), "2026-06-12T00:00:00+00:00"
    )
    assert same_month["subjects"] == 1 and same_month["saved"] == 0  # 멱등
    next_month = scheduler.daily_batch(
        [subject], date(2026, 7, 2), "2026-07-02T00:00:00+00:00"
    )
    assert next_month["saved"] > 0 and "purged" in next_month


def test_lazy_get_computes_on_miss(subject, scheduler) -> None:
    """비활성 대상 경로: 미존재 레코드는 lazy 계산 후 반환."""
    found = scheduler.lazy_get(
        subject, CompositeLevel.YEAR, "2026", date(2026, 6, 11),
        "2026-06-11T00:00:00+00:00",
    )
    assert found is not None and found.period_key == "2026"


def test_dict_version_change_invalidates(subject, scheduler) -> None:
    """사전 버전 변경 → 구버전 레코드 무효화."""
    scheduler.on_subject_upsert(subject, date(2026, 6, 11), "2026-06-11T00:00:00+00:00")
    newer = PrecomputeScheduler(
        PrecomputeStore(_DSN), CompositeBuilder(_DICTS), calculate, "1.1.0"
    )
    removed = newer.on_dict_version_change()
    assert removed > 0
    assert PrecomputeStore(_DSN).get(_SID, CompositeLevel.NATAL, "natal", "1.0.0") is None
