"""P4-1b shadow 상태 영속 회귀 — CAREER_TRANSITION_SYSTEM §12·§16.

journal만 저장하고 load 시 replay로 재구성한다. thread·subject 격리, optimistic
revision, 계약 버전 불일치 억제를 검증한다.
"""

from __future__ import annotations

from saju_engines.career_shadow_repository import (
    InMemoryCareerShadowRepository,
    scope_key,
)
from saju_engines.career_state_shadow import PersistenceStatus, process_career_turn
from saju_engines.career_transition_reducer import reduce_career_command, replay
from saju_shared_types.career_commands import CareerFactSource, CreateEpisodeCommand
from saju_shared_types.career_transition import CareerEpisodeStore

UC = CareerFactSource.USER_CONFIRMED
_N = 0


def _turn(repo, text, *, thread="t1", subject="s1", episode=None):
    global _N
    _N += 1
    return process_career_turn(
        repo, thread_id=thread, subject_id=subject, conversation_text=text,
        command_id=f"c{_N}", source_fact_id=f"sf{_N}", recorded_at=f"ts{_N}",
        target_episode_id=episode,
    )


def _seed_episode(repo, *, thread="t1", subject="s1", eid="ep-a"):
    """Episode 생성은 명령 경로로 만들고 저장소에 넣는다."""
    loaded = repo.load(thread, subject)
    store = reduce_career_command(
        loaded.store,
        CreateEpisodeCommand(
            command_id=f"mk-{thread}-{subject}-{eid}", episode_id=eid,
            recorded_at="t0", source_kind=UC,
        ),
    ).store
    out = repo.save(thread, subject, store, expected_revision=loaded.revision)
    assert out.saved
    return out.revision


# ── 1~2. turn 간 상태 유지·해소 ────────────────────────────────────────────


def test_state_survives_across_turns() -> None:
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)
    r1 = _turn(repo, "A사 지원서를 냈다", episode="ep-a")
    assert r1.run is not None and r1.run.applied
    reloaded = repo.load("t1", "s1")
    assert "ep-a" in reloaded.store.by_id
    assert len(reloaded.store.fact_journal) == 1


def test_next_turn_resolves_to_same_episode() -> None:
    """다음 turn의 '면접 봤어'가 유일한 열린 Episode로 해소된다."""
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)
    _turn(repo, "지원서를 냈다", episode="ep-a")
    r2 = _turn(repo, "면접 봤어")
    assert r2.run is not None and r2.run.applied
    stages = {
        o.stage.stage.value
        for o in r2.store.by_id["ep-a"].opportunity.observed_stages
    }
    assert stages == {"application", "interview"}


# ── 3~4. 격리 ──────────────────────────────────────────────────────────────


def test_no_cross_thread_bleed() -> None:
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo, thread="t1")
    _seed_episode(repo, thread="t2")
    _turn(repo, "지원서를 냈다", thread="t1", episode="ep-a")
    other = repo.load("t2", "s1")
    assert other.store.fact_journal == ()


def test_no_cross_subject_bleed() -> None:
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo, subject="s1")
    _seed_episode(repo, subject="s2")
    _turn(repo, "지원서를 냈다", subject="s1", episode="ep-a")
    other = repo.load("t1", "s2")
    assert other.store.fact_journal == ()
    assert scope_key("t1", "s1") != scope_key("t1", "s2")


# ── 5. 추측은 저장 0 ───────────────────────────────────────────────────────


def test_speculation_does_not_grow_journal() -> None:
    repo = InMemoryCareerShadowRepository()
    rev = _seed_episode(repo)
    before = repo.load("t1", "s1")
    r = _turn(repo, "곧 오퍼가 올 것 같아")
    assert r.run is not None and not r.run.applied
    after = repo.load("t1", "s1")
    assert after.store.fact_journal == before.store.fact_journal
    assert after.revision == rev          # revision 증가 없음


# ── 6~7. 저장 실패·stale ───────────────────────────────────────────────────


def test_save_failure_keeps_chat_and_suppresses_block() -> None:
    """저장 실패 시 신규 블록을 억제하고 기존 경로를 유지한다."""

    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)   # seed 는 정상 저장, 이후 저장만 실패시킨다

    from saju_engines.career_shadow_repository import ShadowWriteOutcome

    def failing_save(*a, **k):
        return ShadowWriteOutcome(saved=False, reason="SAVE_FAILED")

    repo.save = failing_save  # type: ignore[method-assign]
    r = _turn(repo, "지원서를 냈다", episode="ep-a")
    assert not r.consumable
    assert r.persistence_status is PersistenceStatus.SAVE_FAILED


def test_stale_revision_does_not_overwrite() -> None:
    """revision 이 뒤바뀐 상태에서 덮어쓰지 않는다."""
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)
    loaded = repo.load("t1", "s1")
    # 다른 writer 가 먼저 저장해 revision 을 올린 상황
    repo.save("t1", "s1", loaded.store, expected_revision=loaded.revision)
    out = repo.save("t1", "s1", loaded.store, expected_revision=loaded.revision)
    assert not out.saved
    assert out.reason == "STALE_SHADOW_WRITE"


# ── 8. 계약 버전 불일치 ────────────────────────────────────────────────────


def test_contract_version_mismatch_suppresses_consumption() -> None:
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)
    key = scope_key("t1", "s1")
    row = repo._rows[key]
    repo._rows[key] = row.model_copy(update={"semantics_contract_version": "old.v0"})
    r = _turn(repo, "지원서를 냈다", episode="ep-a")
    assert not r.consumable
    assert r.persistence_status is PersistenceStatus.CONTRACT_MISMATCH
    assert r.run is None                   # reducer 자체를 돌리지 않는다


# ── 12. replay 정합 ────────────────────────────────────────────────────────


def test_reloaded_projection_equals_replay() -> None:
    """load 결과가 journal replay와 동일하다(저장-journal divergence 0)."""
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)
    _turn(repo, "지원서를 냈다", episode="ep-a")
    _turn(repo, "면접 봤어")
    loaded = repo.load("t1", "s1")
    assert replay(loaded.store.career_journal) == loaded.store


def test_repository_stores_journal_only() -> None:
    """파생 상태를 저장하지 않는다 — 저장 행은 journal·digest·revision 뿐."""
    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo)
    row = repo._rows[scope_key("t1", "s1")]
    assert set(type(row).model_fields) == {
        "journal", "digest", "revision", "semantics_contract_version",
        "producer_build_sha",
    }


def test_empty_scope_loads_empty_store() -> None:
    repo = InMemoryCareerShadowRepository()
    loaded = repo.load("t-none", "s-none")
    assert loaded.store == CareerEpisodeStore()
    assert loaded.revision == 0


# ── P2-3a: 요청당 1회 조회·1회 파싱 ────────────────────────────────────────


class _CountingRepository:
    """load 횟수를 세는 래퍼 — "1회 조회"를 주장이 아니라 측정으로 확인한다."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.load_calls = 0

    def load(self, thread_id, subject_id):
        self.load_calls += 1
        return self.inner.load(thread_id, subject_id)

    def save(self, *args, **kwargs):
        return self.inner.save(*args, **kwargs)


class _FailingRepository:
    """저장소 장애 — load 가 예외를 던진다(Postgres 구현은 예외를 삼키지 않는다)."""

    def load(self, thread_id, subject_id):
        raise RuntimeError("db down")

    def save(self, *args, **kwargs):  # pragma: no cover - 호출되면 안 된다
        raise AssertionError("save 는 호출되지 않아야 한다")


def test_prepared_turn_is_not_reloaded() -> None:
    """준비 결과를 넘기면 `process_career_turn` 이 다시 load 하지 않는다."""
    from saju_engines.career_state_shadow import prepare_career_turn

    repo = _CountingRepository(InMemoryCareerShadowRepository())
    _seed_episode(repo.inner, eid="ep-a")

    prepared = prepare_career_turn(
        repo, thread_id="t1", subject_id="s1", conversation_text="어제 면접 봤어요"
    )
    assert repo.load_calls == 1

    process_career_turn(
        repo, thread_id="t1", subject_id="s1", conversation_text="어제 면접 봤어요",
        command_id="c-prep", source_fact_id="sf-prep", recorded_at="ts-prep",
        prepared=prepared,
    )

    assert repo.load_calls == 1, "요청당 저장소 조회는 1회여야 한다"


def test_unprepared_turn_still_works() -> None:
    """준비 결과 없이 호출하면 기존 동작(자체 load)을 유지한다."""
    repo = _CountingRepository(InMemoryCareerShadowRepository())
    _seed_episode(repo.inner, eid="ep-a")

    result = _turn(repo, "어제 면접 봤어요")

    assert repo.load_calls >= 1
    assert result.persistence_status is PersistenceStatus.SAVED


def test_prepare_reports_load_failure_without_raising() -> None:
    """조회 실패는 예외가 아니라 상태로 전달된다."""
    from saju_engines.career_state_shadow import prepare_career_turn
    from saju_shared_types.process_fact import ProcessSourceStatus

    prepared = prepare_career_turn(
        _FailingRepository(), thread_id="t1", subject_id="s1",
        conversation_text="어제 면접 봤어요",
    )

    assert prepared.blocked
    assert prepared.persistence_status is PersistenceStatus.LOAD_FAILED
    assert prepared.source_status is ProcessSourceStatus.LOAD_FAILED
    assert prepared.store == CareerEpisodeStore()


def test_prepare_distinguishes_empty_from_failure() -> None:
    """빈 저장소는 실패가 아니다 — 커리어는 '없음'을 확정할 수 있다."""
    from saju_engines.career_state_shadow import prepare_career_turn
    from saju_shared_types.process_fact import ProcessSourceStatus

    prepared = prepare_career_turn(
        InMemoryCareerShadowRepository(), thread_id="t1", subject_id="s1",
        conversation_text="이직운 어때요",
    )

    assert not prepared.blocked
    assert prepared.source_status is ProcessSourceStatus.LOADED_EMPTY


def test_prepare_reports_facts_present() -> None:
    from saju_engines.career_state_shadow import prepare_career_turn
    from saju_shared_types.process_fact import ProcessSourceStatus

    repo = InMemoryCareerShadowRepository()
    _seed_episode(repo, eid="ep-a")

    prepared = prepare_career_turn(
        repo, thread_id="t1", subject_id="s1", conversation_text="이직운 어때요"
    )

    assert prepared.source_status is ProcessSourceStatus.LOADED_WITH_FACTS


def test_blocked_prepare_suppresses_exposure() -> None:
    """차단된 준비 결과로 turn 을 돌리면 노출이 억제되고 save 도 없다."""
    from saju_engines.career_state_shadow import prepare_career_turn

    repo = _FailingRepository()
    prepared = prepare_career_turn(
        repo, thread_id="t1", subject_id="s1", conversation_text="어제 면접 봤어요"
    )

    result = process_career_turn(
        repo, thread_id="t1", subject_id="s1", conversation_text="어제 면접 봤어요",
        command_id="c-x", source_fact_id="sf-x", recorded_at="ts-x", prepared=prepared,
    )

    assert result.suppress_exposure
    assert result.persistence_status is PersistenceStatus.LOAD_FAILED
