"""커리어 shadow 상태 저장소 — P4-1b (CAREER_TRANSITION_SYSTEM §12·§16).

**재생 가능한 최소 원장(`career_journal`)만 저장**하고 파생 상태(episodes·frontier·
observed_stages·고용 컨텍스트)는 load 후 `replay()`로 재구성한다 — 저장 상태와 journal이
어긋날 여지를 만들지 않기 위함.

**절대 경계**: `ConversationState` 권위 필드 미추가 · 기존 `user_facts` 미병합 ·
EventCandidate·점수·랭킹 미변경 · LLM 응답문 미저장 · forecast 미저장 ·
`OBSERVABLE_HARD_FACT`만 reducer를 거쳐 저장 · 저장 실패 시 기존 chat 경로 유지.

동시성은 **optimistic revision**만 둔다(자동 merge 없음) — 조용한 lost update만 막는다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_transition import CareerEpisodeStore
from saju_shared_types.event_semantics import SEMANTICS_CONTRACT_VERSION

_MIGRATION_016 = (
    Path(__file__).resolve().parents[3] / "migrations" / "016_career_shadow_state.sql"
)


def _deserialize_journal(raw) -> tuple:
    """저장된 journal JSON → 통합 journal 항목 tuple."""
    from saju_shared_types.career_transition import (
        AcceptedEpisodeSwitchedJournalItem,
        EmploymentContextRolledJournalItem,
        EntryScopeDeclaredJournalItem,
        EpisodeClosedJournalItem,
        EpisodeCreatedJournalItem,
        EpisodeReopenedJournalItem,
        JournalItemKind,
        StageHistoryItem,
    )

    by_kind: dict[JournalItemKind, type[BaseModel]] = {
        JournalItemKind.EPISODE_CREATED: EpisodeCreatedJournalItem,
        JournalItemKind.EPISODE_CLOSED: EpisodeClosedJournalItem,
        JournalItemKind.EPISODE_REOPENED: EpisodeReopenedJournalItem,
        JournalItemKind.CAREER_FACT: StageHistoryItem,
        JournalItemKind.ACCEPTED_EPISODE_SWITCHED: AcceptedEpisodeSwitchedJournalItem,
        JournalItemKind.EMPLOYMENT_CONTEXT_ROLLED: EmploymentContextRolledJournalItem,
        JournalItemKind.ENTRY_SCOPE_DECLARED: EntryScopeDeclaredJournalItem,
    }
    items = []
    for entry in raw or ():
        model = by_kind[JournalItemKind(entry["kind"])]
        items.append(model.model_validate(entry))
    return tuple(items)


class ShadowWriteOutcome(BaseModel):
    """저장 결과 — 실패 사유를 telemetry로 남긴다."""

    model_config = ConfigDict(frozen=True)

    saved: bool = False
    revision: int = 0
    reason: str | None = None   # STALE_SHADOW_WRITE / SAVE_FAILED / ...


class LoadedShadowState(BaseModel):
    """load 결과 — `store`는 journal replay 산물이다."""

    model_config = ConfigDict(frozen=True)

    store: CareerEpisodeStore
    revision: int = 0
    semantics_contract_version: str = SEMANTICS_CONTRACT_VERSION
    contract_mismatch: bool = False


def journal_digest(store: CareerEpisodeStore) -> str:
    """journal 다이제스트 — 프로세스 해시를 쓰지 않는다(결정론)."""
    payload = [i.model_dump(mode="json") for i in store.career_journal]
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scope_key(thread_id: str, subject_id: str) -> str:
    """thread + subject 격리 키 — 다른 thread·subject 와 상태가 섞이지 않는다."""
    return f"{thread_id}:{subject_id}"


class CareerShadowStateRepository(Protocol):
    """shadow 원장 저장소 인터페이스."""

    def load(self, thread_id: str, subject_id: str) -> LoadedShadowState:
        """journal을 읽어 replay한 store를 돌려준다(없으면 빈 store)."""
        ...

    def save(
        self,
        thread_id: str,
        subject_id: str,
        store: CareerEpisodeStore,
        *,
        expected_revision: int,
        producer_build_sha: str = "",
    ) -> ShadowWriteOutcome:
        """journal만 저장한다. `expected_revision` 불일치면 덮어쓰지 않는다."""
        ...


class InMemoryCareerShadowRepository:
    """프로세스 로컬 구현 — 테스트·단일 프로세스 canary용.

    DB 구현과 동일한 계약(격리 키·optimistic revision·journal only)을 지킨다.
    """

    class _Row(BaseModel):
        model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

        journal: tuple = ()
        digest: str = ""
        revision: int = 0
        semantics_contract_version: str = SEMANTICS_CONTRACT_VERSION
        producer_build_sha: str = ""

    def __init__(self) -> None:
        self._rows: dict[str, InMemoryCareerShadowRepository._Row] = {}

    def load(self, thread_id: str, subject_id: str) -> LoadedShadowState:
        from .career_transition_reducer import replay

        row = self._rows.get(scope_key(thread_id, subject_id))
        if row is None:
            return LoadedShadowState(store=CareerEpisodeStore())
        mismatch = row.semantics_contract_version != SEMANTICS_CONTRACT_VERSION
        return LoadedShadowState(
            store=replay(row.journal),
            revision=row.revision,
            semantics_contract_version=row.semantics_contract_version,
            contract_mismatch=mismatch,
        )

    def save(
        self,
        thread_id: str,
        subject_id: str,
        store: CareerEpisodeStore,
        *,
        expected_revision: int,
        producer_build_sha: str = "",
    ) -> ShadowWriteOutcome:
        key = scope_key(thread_id, subject_id)
        row = self._rows.get(key)
        current = row.revision if row else 0
        if current != expected_revision:
            # 조용한 lost update 방지 — 덮어쓰지 않고 호출자가 신규 블록을 억제한다.
            return ShadowWriteOutcome(
                saved=False, revision=current, reason="STALE_SHADOW_WRITE"
            )
        revision = current + 1
        self._rows[key] = InMemoryCareerShadowRepository._Row(
            journal=store.career_journal,
            digest=journal_digest(store),
            revision=revision,
            producer_build_sha=producer_build_sha,
        )
        return ShadowWriteOutcome(saved=True, revision=revision)


__all__ = [
    "CareerShadowStateRepository",
    "InMemoryCareerShadowRepository",
    "PostgresCareerShadowStateRepository",
    "build_career_shadow_repository",
    "LoadedShadowState",
    "ShadowWriteOutcome",
    "journal_digest",
    "scope_key",
]


class PostgresCareerShadowStateRepository:
    """`career_shadow_state`(migration 016) 저장소 — 동기 psycopg, 호출당 단기 커넥션.

    **자동 in-memory fallback을 두지 않는다.** DB 오류 시 상태 없는 신규 Episode 로
    진행하면 worker 마다 다른 임시 상태가 생겨 더 큰 혼선이 된다 — 호출자가 이번 turn
    노출을 억제하고 기존 경로를 유지한다.
    """

    def __init__(self, dsn: str | None = None) -> None:
        """dsn 미지정 시 `SAJU_V2_DATABASE_URL` 사용."""
        from .precompute_store import default_dsn

        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError("DB 접속 문자열 필요 — 인자 또는 SAJU_V2_DATABASE_URL")
        self._dsn = resolved

    def _connect(self):
        import psycopg

        return psycopg.connect(self._dsn)

    def migrate(self) -> None:
        """마이그레이션 적용(멱등)."""
        with self._connect() as conn:
            conn.execute(_MIGRATION_016.read_text(encoding="utf-8"))

    def load(self, thread_id: str, subject_id: str) -> LoadedShadowState:
        """journal 을 읽어 replay 한다. digest 불일치면 소비하지 않는다."""
        from .career_transition_reducer import replay

        with self._connect() as conn:
            row = conn.execute(
                "SELECT career_journal, journal_digest, revision,"
                " semantics_contract_version FROM career_shadow_state"
                " WHERE thread_id = %s AND subject_id = %s",
                (thread_id, subject_id),
            ).fetchone()
        if row is None:
            return LoadedShadowState(store=CareerEpisodeStore())
        raw_journal, digest, revision, contract_version = row
        store = CareerEpisodeStore(career_journal=_deserialize_journal(raw_journal))
        if journal_digest(store) != digest:
            # 저장 손상 — 과거 projection 을 소비하지 않는다.
            return LoadedShadowState(
                store=CareerEpisodeStore(), revision=int(revision),
                semantics_contract_version=contract_version, contract_mismatch=True,
            )
        replayed = replay(store.career_journal)
        return LoadedShadowState(
            store=replayed,
            revision=int(revision),
            semantics_contract_version=contract_version,
            contract_mismatch=contract_version != SEMANTICS_CONTRACT_VERSION,
        )

    def save(
        self,
        thread_id: str,
        subject_id: str,
        store: CareerEpisodeStore,
        *,
        expected_revision: int,
        producer_build_sha: str = "",
    ) -> ShadowWriteOutcome:
        """CAS 저장 — revision 이 어긋나면 덮어쓰지 않는다."""
        payload = json.dumps(
            [i.model_dump(mode="json") for i in store.career_journal], ensure_ascii=False
        )
        digest = journal_digest(store)
        with self._connect() as conn:
            if expected_revision == 0:
                # 최초 생성은 unique key 로 원자적으로 처리한다(동시 생성 중복 0).
                created = conn.execute(
                    "INSERT INTO career_shadow_state (shadow_state_id, thread_id,"
                    " subject_id, career_journal, journal_digest, revision,"
                    " semantics_contract_version, producer_build_sha)"
                    " VALUES (%s, %s, %s, %s::jsonb, %s, 1, %s, %s)"
                    " ON CONFLICT (thread_id, subject_id) DO NOTHING"
                    " RETURNING revision",
                    (
                        scope_key(thread_id, subject_id), thread_id, subject_id,
                        payload, digest, SEMANTICS_CONTRACT_VERSION, producer_build_sha,
                    ),
                ).fetchone()
                if created is not None:
                    return ShadowWriteOutcome(saved=True, revision=int(created[0]))
                # 다른 요청이 먼저 만들었다 — 덮어쓰지 않는다.
                return ShadowWriteOutcome(saved=False, reason="STALE_SHADOW_WRITE")
            updated = conn.execute(
                "UPDATE career_shadow_state SET career_journal = %s::jsonb,"
                " journal_digest = %s, revision = revision + 1,"
                " semantics_contract_version = %s, producer_build_sha = %s,"
                " updated_at = now()"
                " WHERE thread_id = %s AND subject_id = %s AND revision = %s"
                " RETURNING revision",
                (
                    payload, digest, SEMANTICS_CONTRACT_VERSION, producer_build_sha,
                    thread_id, subject_id, expected_revision,
                ),
            ).fetchone()
        if updated is None:
            return ShadowWriteOutcome(saved=False, reason="STALE_SHADOW_WRITE")
        return ShadowWriteOutcome(saved=True, revision=int(updated[0]))


def build_career_shadow_repository(kind: str | None = None):
    """환경에 따른 저장소 선택 — 테스터 환경은 `postgres` 로 고정한다.

    `memory` 는 개발·단위 테스트 전용이며, **DB 오류 시 자동 fallback 하지 않는다.**
    """
    import os

    raw = kind or os.getenv("CAREER_SHADOW_REPOSITORY") or "postgres"
    resolved = raw.strip().lower()
    if resolved == "memory":
        return InMemoryCareerShadowRepository()
    return PostgresCareerShadowStateRepository()
