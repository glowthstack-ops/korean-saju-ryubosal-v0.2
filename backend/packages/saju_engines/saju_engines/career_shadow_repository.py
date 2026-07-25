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
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from saju_shared_types.career_transition import CareerEpisodeStore
from saju_shared_types.event_semantics import SEMANTICS_CONTRACT_VERSION


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
    "LoadedShadowState",
    "ShadowWriteOutcome",
    "journal_digest",
    "scope_key",
]
