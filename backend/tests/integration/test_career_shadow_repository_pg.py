"""P4-1b Postgres shadow 저장소 통합 회귀 — 실제 DB 필요.

CAS·unique constraint 동시성은 mock 으로 검증할 수 없으므로 실제 PostgreSQL 을 쓴다.
DSN 미설정 환경에서는 skip 한다.
"""

from __future__ import annotations

import os

import pytest

from saju_engines.career_shadow_repository import (
    PostgresCareerShadowStateRepository,
    journal_digest,
)
from saju_engines.career_state_shadow import PersistenceStatus, process_career_turn
from saju_engines.career_transition_reducer import reduce_career_command, replay
from saju_shared_types.career_commands import CareerFactSource, CreateEpisodeCommand
from saju_shared_types.career_transition import CareerEpisodeStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAJU_V2_DATABASE_URL"), reason="SAJU_V2_DATABASE_URL 미설정"
)

_THREAD = "pgtest-thread"
_N = 0


@pytest.fixture()
def repo():
    r = PostgresCareerShadowStateRepository()
    r.migrate()
    _clear()
    yield r
    _clear()


def _clear() -> None:
    import psycopg

    with psycopg.connect(os.environ["SAJU_V2_DATABASE_URL"]) as conn:
        conn.execute("DELETE FROM career_shadow_state WHERE thread_id LIKE 'pgtest%'")


def _with_episode(store: CareerEpisodeStore, eid: str = "ep-a") -> CareerEpisodeStore:
    return reduce_career_command(
        store,
        CreateEpisodeCommand(
            command_id=f"mk-{eid}", episode_id=eid, recorded_at="t0",
            source_kind=CareerFactSource.USER_CONFIRMED,
        ),
    ).store


def _turn(repo, text, *, thread=_THREAD, subject="s1"):
    global _N
    _N += 1
    return process_career_turn(
        repo, thread_id=thread, subject_id=subject, conversation_text=text,
        command_id=f"c{_N}", source_fact_id=f"sf{_N}", recorded_at=f"ts{_N}",
    )


# ── 1~2. 재시작 내구성 ─────────────────────────────────────────────────────


def test_state_survives_new_repository_instance(repo) -> None:
    """저장 후 repository 객체를 새로 만들어도 이력이 유지된다."""
    _turn(repo, "A사 지원서를 냈다")
    fresh = PostgresCareerShadowStateRepository()
    loaded = fresh.load(_THREAD, "s1")
    assert len(loaded.store.fact_journal) == 1
    assert loaded.revision >= 1


def test_replay_matches_after_reload(repo) -> None:
    """프로세스 재시작을 모사한 새 세션에서 replay 결과가 동일하다."""
    _turn(repo, "A사 지원서를 냈다")
    _turn(repo, "어제 면접을 봤다")
    fresh = PostgresCareerShadowStateRepository()
    loaded = fresh.load(_THREAD, "s1")
    assert replay(loaded.store.career_journal) == loaded.store


# ── 3~5. 동시성 ────────────────────────────────────────────────────────────


def test_concurrent_update_only_one_wins(repo) -> None:
    """두 instance 가 같은 revision 을 갱신하면 한쪽만 성공한다."""
    _turn(repo, "A사 지원서를 냈다")
    a = PostgresCareerShadowStateRepository()
    b = PostgresCareerShadowStateRepository()
    base = a.load(_THREAD, "s1")
    store = _with_episode(base.store, "ep-b")
    first = a.save(_THREAD, "s1", store, expected_revision=base.revision)
    second = b.save(_THREAD, "s1", store, expected_revision=base.revision)
    assert first.saved is True
    assert second.saved is False
    assert second.reason == "STALE_SHADOW_WRITE"


def test_stale_writer_does_not_overwrite_journal(repo) -> None:
    """stale writer 가 최신 journal 을 덮어쓰지 않는다."""
    _turn(repo, "A사 지원서를 냈다")
    stale = repo.load(_THREAD, "s1")
    _turn(repo, "어제 면접을 봤다")            # 최신 revision 으로 이동
    latest_before = repo.load(_THREAD, "s1")
    repo.save(_THREAD, "s1", stale.store, expected_revision=stale.revision)
    latest_after = repo.load(_THREAD, "s1")
    assert latest_after.store.career_journal == latest_before.store.career_journal


def test_concurrent_first_insert_creates_one_row(repo) -> None:
    """최초 행 동시 생성 시 중복 0 — 한쪽만 성공한다."""
    a = PostgresCareerShadowStateRepository()
    b = PostgresCareerShadowStateRepository()
    store = _with_episode(CareerEpisodeStore())
    first = a.save(_THREAD, "s-new", store, expected_revision=0)
    second = b.save(_THREAD, "s-new", store, expected_revision=0)
    assert first.saved != second.saved
    loaded = a.load(_THREAD, "s-new")
    assert len([e.episode_id for e in loaded.store.episodes]) == 1


# ── 6~8. 멱등·격리 ─────────────────────────────────────────────────────────


def test_retry_of_same_turn_does_not_duplicate(repo) -> None:
    """동일 turn 재시도 시 journal·revision 중복 증가 0."""
    global _N
    _turn(repo, "A사 지원서를 냈다")
    before = repo.load(_THREAD, "s1")
    _N -= 1                                    # 동일 command_id 재사용
    _turn(repo, "A사 지원서를 냈다")
    after = repo.load(_THREAD, "s1")
    assert len(after.store.fact_journal) == len(before.store.fact_journal)
    assert after.revision == before.revision


def test_no_cross_thread_bleed(repo) -> None:
    _turn(repo, "A사 지원서를 냈다", thread=_THREAD)
    other = repo.load("pgtest-other", "s1")
    assert other.store.career_journal == ()


def test_no_cross_subject_bleed(repo) -> None:
    _turn(repo, "A사 지원서를 냈다", subject="s1")
    other = repo.load(_THREAD, "s2")
    assert other.store.career_journal == ()


# ── 9~10. 손상·버전 ────────────────────────────────────────────────────────


def test_digest_mismatch_blocks_consumption(repo) -> None:
    """digest 가 어긋나면 소비·노출하지 않는다."""
    import psycopg

    _turn(repo, "A사 지원서를 냈다")
    with psycopg.connect(os.environ["SAJU_V2_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE career_shadow_state SET journal_digest = 'tampered'"
            " WHERE thread_id = %s AND subject_id = %s", (_THREAD, "s1"),
        )
    loaded = repo.load(_THREAD, "s1")
    assert loaded.contract_mismatch is True
    assert loaded.store.career_journal == ()


def test_contract_version_mismatch_suppresses_turn(repo) -> None:
    """계약 버전 불일치면 parse·reducer·save 를 하지 않는다."""
    import psycopg

    _turn(repo, "A사 지원서를 냈다")
    with psycopg.connect(os.environ["SAJU_V2_DATABASE_URL"]) as conn:
        conn.execute(
            "UPDATE career_shadow_state SET semantics_contract_version = 'old.v0'"
            " WHERE thread_id = %s AND subject_id = %s", (_THREAD, "s1"),
        )
    result = _turn(repo, "어제 면접을 봤다")
    assert result.persistence_status is PersistenceStatus.CONTRACT_MISMATCH
    assert result.suppress_exposure is True
    assert result.run is None


# ── 11~13. 실패·연속성 ─────────────────────────────────────────────────────


def test_load_failure_suppresses_without_memory_fallback(repo) -> None:
    """DB load 실패 시 상태 없는 신규 Episode 로 진행하지 않는다."""

    def boom(*a, **k):
        raise RuntimeError("db down")

    repo.load = boom  # type: ignore[method-assign]
    result = _turn(repo, "A사 지원서를 냈다")
    assert result.persistence_status is PersistenceStatus.LOAD_FAILED
    assert result.suppress_exposure is True
    assert result.store.career_journal == ()


def test_save_failure_suppresses_exposure(repo) -> None:
    """save 실패 시 메모리상 신규 사실을 노출하지 않는다."""
    original = repo.save

    def boom(*a, **k):
        raise RuntimeError("write failed")

    repo.save = boom  # type: ignore[method-assign]
    result = _turn(repo, "A사 지원서를 냈다")
    repo.save = original  # type: ignore[method-assign]
    assert result.persistence_status is PersistenceStatus.SAVE_FAILED
    assert result.suppress_exposure is True


def test_two_workers_share_continuity(repo) -> None:
    """다중 worker 역할의 두 repository 에서 지원 → 면접 연속성이 유지된다."""
    worker_a = PostgresCareerShadowStateRepository()
    worker_b = PostgresCareerShadowStateRepository()
    _turn(worker_a, "A사 지원서를 냈다")
    _turn(worker_b, "어제 면접을 봤다")
    loaded = worker_a.load(_THREAD, "s1")
    kinds = {f.fact_type for f in loaded.store.fact_journal}
    assert kinds == {"application_submitted", "interview_completed"}


# ── 14. 부분 저장 없음 ─────────────────────────────────────────────────────


def test_digest_always_matches_stored_journal(repo) -> None:
    """저장된 journal 과 digest 가 항상 일치한다(부분 저장 0)."""
    _turn(repo, "A사 지원서를 냈다")
    _turn(repo, "어제 면접을 봤다")
    loaded = repo.load(_THREAD, "s1")
    assert journal_digest(
        CareerEpisodeStore(career_journal=loaded.store.career_journal)
    ) == journal_digest(CareerEpisodeStore(career_journal=loaded.store.career_journal))
    assert loaded.contract_mismatch is False
