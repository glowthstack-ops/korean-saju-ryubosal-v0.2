"""AI채팅상담 대화 전문 저장소 (v2.2 — saju-v2-db 전용).

ConversationStore(오케스트레이터 상태)와 별개로, 사용자가 열람·이어가기 할 수 있도록 질문/답변
전문을 스레드별로 보관한다. 턴마다 자동 저장되며 스레드 단위로 삭제한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg

from .precompute_store import default_dsn

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_MIGRATION_FILES = (
    "007_chat_history.sql", "011_chat_message_status.sql", "021_chat_thread_subject.sql",
)
_TITLE_MAX = 60


class ChatHistoryStore:
    """chat_threads / chat_messages 저장소 — 동기 psycopg, 호출당 단기 커넥션."""

    def __init__(self, dsn: str | None = None) -> None:
        """dsn 미지정 시 SAJU_V2_DATABASE_URL 사용."""
        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError("DB 접속 문자열 필요 — 인자 또는 SAJU_V2_DATABASE_URL")
        self._dsn = resolved

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def migrate(self) -> None:
        """마이그레이션 적용(멱등) — 스키마(007) + 상태/열람 컬럼(011) + 명식 바인딩(021)."""
        with self._connect() as conn:
            for name in _MIGRATION_FILES:
                conn.execute((_MIGRATIONS_DIR / name).read_text(encoding="utf-8"))

    def record_turn(
        self,
        owner_id: str,
        thread_id: str,
        subject_label: str | None,
        user_text: str,
        assistant_text: str,
        meta: dict | None = None,
        user_meta: dict | None = None,
        subject_id: str | None = None,
    ) -> None:
        """한 턴(질문+답변)을 저장한다. 스레드가 없으면 생성(title=첫 질문).

        user_meta: 질문(user) 메시지에 붙일 메타(예: 첨부 동반자 {"partner": {...}}).
        subject_id: 이 턴의 기준 명식 — 스레드 최초 바인딩(이미 묶인 스레드는 유지, 021).
        """
        title = user_text.strip().replace("\n", " ")[:_TITLE_MAX]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_threads (thread_id, owner_id, subject_label, title, subject_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE SET updated_at = now(),
                  subject_id = COALESCE(chat_threads.subject_id, EXCLUDED.subject_id)
                """,
                (thread_id, owner_id, subject_label, title, subject_id),
            )
            conn.execute(
                "INSERT INTO chat_messages (thread_id, role, text, meta) "
                "VALUES (%s, 'user', %s, %s::jsonb)",
                (thread_id, user_text, json.dumps(user_meta or {}, ensure_ascii=False)),
            )
            conn.execute(
                "INSERT INTO chat_messages (thread_id, role, text, meta) "
                "VALUES (%s, 'assistant', %s, %s::jsonb)",
                (thread_id, assistant_text, json.dumps(meta or {}, ensure_ascii=False)),
            )

    def start_turn(
        self,
        owner_id: str,
        thread_id: str,
        subject_label: str | None,
        user_text: str,
        meta: dict | None = None,
        user_meta: dict | None = None,
        subject_id: str | None = None,
    ) -> int:
        """질문을 저장하고 어시스턴트 답변을 pending(미열람)으로 예약한다.

        백그라운드 생성 직전에 호출. 반환된 message_id를 백그라운드 태스크가 받아
        생성 완료 시 :meth:`complete_turn`으로 본문을 채운다. 클라이언트가 이탈해도
        답변은 서버에서 끝까지 생성·영속되며, 재진입 시 폴링으로 복구된다.
        user_meta: 질문(user) 메시지에 붙일 메타(예: 첨부 동반자 {"partner": {...}}).
        subject_id: 이 턴의 기준 명식 — 스레드 최초 바인딩(이미 묶인 스레드는 유지, 021).
        """
        title = user_text.strip().replace("\n", " ")[:_TITLE_MAX]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_threads (thread_id, owner_id, subject_label, title, subject_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE SET updated_at = now(),
                  subject_id = COALESCE(chat_threads.subject_id, EXCLUDED.subject_id)
                """,
                (thread_id, owner_id, subject_label, title, subject_id),
            )
            conn.execute(
                "INSERT INTO chat_messages (thread_id, role, text, meta) "
                "VALUES (%s, 'user', %s, %s::jsonb)",
                (thread_id, user_text, json.dumps(user_meta or {}, ensure_ascii=False)),
            )
            row = conn.execute(
                "INSERT INTO chat_messages (thread_id, role, text, meta, status, seen) "
                "VALUES (%s, 'assistant', '', %s::jsonb, 'pending', false) RETURNING id",
                (thread_id, json.dumps(meta or {}, ensure_ascii=False)),
            ).fetchone()
        assert row is not None
        return int(row[0])

    def complete_turn(
        self,
        message_id: int,
        assistant_text: str,
        status: str = "done",
        meta: dict | None = None,
    ) -> None:
        """예약된 pending 답변(message_id)에 본문·상태를 채운다.

        status: 'done'(정상) | 'error'(생성 실패 — text에 사용자 안내문). meta가 주어지면
        기존 meta에 병합한다. 스레드 updated_at도 갱신한다.
        """
        with self._connect() as conn:
            if meta is not None:
                conn.execute(
                    "UPDATE chat_messages SET text=%s, status=%s, "
                    "meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb "
                    "WHERE id=%s AND role='assistant'",
                    (assistant_text, status, json.dumps(meta, ensure_ascii=False), message_id),
                )
            else:
                conn.execute(
                    "UPDATE chat_messages SET text=%s, status=%s "
                    "WHERE id=%s AND role='assistant'",
                    (assistant_text, status, message_id),
                )
            conn.execute(
                "UPDATE chat_threads SET updated_at = now() WHERE thread_id = "
                "(SELECT thread_id FROM chat_messages WHERE id=%s)",
                (message_id,),
            )

    def mark_seen(self, thread_id: str) -> None:
        """스레드의 완료 답변을 열람 처리(뱃지 해제)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_messages SET seen=true "
                "WHERE thread_id=%s AND role='assistant' AND seen=false AND status='done'",
                (thread_id,),
            )

    def unseen_count(self, owner_id: str) -> int:
        """소유자의 미열람 완료 답변이 있는 스레드 수(이탈 후 복구 뱃지용)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count(DISTINCT m.thread_id) "
                "FROM chat_messages m JOIN chat_threads t ON t.thread_id = m.thread_id "
                "WHERE t.owner_id=%s AND m.role='assistant' "
                "AND m.status='done' AND m.seen=false",
                (owner_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def list_threads(self, owner_id: str) -> list[dict]:
        """소유자의 대화 스레드 목록(최신순) — 메시지 수 포함."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.thread_id, t.subject_label, t.title, t.updated_at,
                       t.subject_id,
                       (SELECT count(*) FROM chat_messages m WHERE m.thread_id = t.thread_id),
                       EXISTS(SELECT 1 FROM chat_messages m WHERE m.thread_id = t.thread_id
                              AND m.role='assistant' AND m.status='done' AND m.seen=false),
                       EXISTS(SELECT 1 FROM chat_messages m WHERE m.thread_id = t.thread_id
                              AND m.role='assistant' AND m.status='pending')
                FROM chat_threads t
                WHERE t.owner_id = %s
                ORDER BY t.updated_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [
            {
                "thread_id": r[0],
                "subject_label": r[1],
                "title": r[2],
                "updated_at": r[3].isoformat() if r[3] else None,
                "subject_id": r[4],
                "message_count": r[5],
                "has_unseen": bool(r[6]),
                "pending": bool(r[7]),
            }
            for r in rows
        ]

    def owner_of(self, thread_id: str) -> str | None:
        """스레드 소유자(없으면 None) — 접근 검증용."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_id FROM chat_threads WHERE thread_id=%s", (thread_id,)
            ).fetchone()
        return row[0] if row else None

    def thread_info(self, thread_id: str) -> dict | None:
        """스레드 소유자·바인딩 명식(없으면 None) — POST /chat 접근·명식 정합 검증용(S2·S4)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_id, subject_id FROM chat_threads WHERE thread_id=%s", (thread_id,)
            ).fetchone()
        return {"owner_id": row[0], "subject_id": row[1]} if row else None

    def get_messages(self, thread_id: str) -> list[dict]:
        """스레드의 메시지 전문(시간순). `id`는 평가·후속 질문(delayed outcome)의 키."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, text, meta, created_at, status, seen, id FROM chat_messages "
                "WHERE thread_id=%s ORDER BY id",
                (thread_id,),
            ).fetchall()
        return [
            {
                "role": r[0],
                "text": r[1],
                "meta": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "status": r[4],
                "seen": bool(r[5]),
                "id": int(r[6]),
            }
            for r in rows
        ]

    def message_thread(self, message_id: int) -> str | None:
        """메시지가 속한 스레드 id(없으면 None) — 메시지 단위 쓰기 전 소유 검증용."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT thread_id FROM chat_messages WHERE id=%s", (message_id,)
            ).fetchone()
        return row[0] if row else None

    def merge_message_meta(self, message_id: int, patch: dict) -> None:
        """메시지 meta 에 patch 를 병합한다(평가·후속 답 기록)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE chat_messages SET meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb "
                "WHERE id=%s",
                (json.dumps(patch, ensure_ascii=False), message_id),
            )

    def followup_messages(self, owner_id: str, subject_id: str, limit: int = 30) -> list[dict]:
        """후속 확인(delayed outcome) 후보를 가진 완료 답변 — 소유자·명식 한정, 미응답만."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.id, m.thread_id, m.meta, m.created_at, t.title
                FROM chat_messages m JOIN chat_threads t ON t.thread_id = m.thread_id
                WHERE t.owner_id = %s AND m.role = 'assistant' AND m.status = 'done'
                  AND m.meta ? 'followup' AND NOT (m.meta ? 'followup_answered')
                  AND m.meta->>'subject_id' = %s
                ORDER BY m.id DESC LIMIT %s
                """,
                (owner_id, subject_id, limit),
            ).fetchall()
        return [
            {
                "id": int(r[0]), "thread_id": r[1], "meta": r[2] or {},
                "created_at": r[3].isoformat() if r[3] else None, "title": r[4],
            }
            for r in rows
        ]

    def delete_thread(self, thread_id: str) -> None:
        """스레드 + 메시지(CASCADE) 삭제."""
        with self._connect() as conn:
            conn.execute("DELETE FROM chat_threads WHERE thread_id=%s", (thread_id,))
