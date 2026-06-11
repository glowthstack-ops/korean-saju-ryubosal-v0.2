"""대화 스레드 상태 저장소 (v2.2 Phase 4 T4.1 — PostgreSQL, saju-v2-db 전용 인스턴스)."""

from __future__ import annotations

from pathlib import Path

import psycopg

from saju_shared_types.conversation import ConversationState

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "003_conversation.sql"


class ConversationStore:
    """conversation_threads 테이블 저장소 — 동기 psycopg, 호출당 단기 커넥션."""

    def __init__(self, dsn: str | None = None) -> None:
        """dsn 미지정 시 SAJU_V2_DATABASE_URL 사용."""
        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError("DB 접속 문자열 필요 — 인자 또는 SAJU_V2_DATABASE_URL")
        self._dsn = resolved

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def migrate(self) -> None:
        """마이그레이션 적용(멱등)."""
        with self._connect() as conn:
            conn.execute(_MIGRATION.read_text(encoding="utf-8"))

    def save(self, state: ConversationState, owner_id: str = "default") -> None:
        """스레드 상태 저장/갱신."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_threads (thread_id, owner_id, state)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (thread_id) DO UPDATE
                SET state = EXCLUDED.state, updated_at = now()
                """,
                (state.thread_id, owner_id, state.model_dump_json()),
            )

    def load(self, thread_id: str) -> ConversationState | None:
        """스레드 상태 복원(없으면 None — 새 스레드)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state FROM conversation_threads WHERE thread_id=%s",
                (thread_id,),
            ).fetchone()
        return ConversationState.model_validate(row[0]) if row else None

    def delete(self, thread_id: str) -> None:
        """스레드 삭제."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM conversation_threads WHERE thread_id=%s", (thread_id,)
            )
