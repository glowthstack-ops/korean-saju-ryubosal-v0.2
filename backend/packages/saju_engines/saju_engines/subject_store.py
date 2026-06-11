"""대상(self/동반자) PostgreSQL 저장소 (v2.2 Phase 2.5 — saju-v2-db 전용 인스턴스).

`PrecomputeStore`와 같은 DSN(`SAJU_V2_DATABASE_URL`)을 쓴다. 출생정보 수정은 사전계산
무효화와 한 동작이어야 하므로 스케줄러(`precompute_scheduler`)를 통해 갱신하는 것을
권장한다(직접 upsert 시 무효화는 호출자 책임).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import psycopg

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.subject import SubjectRecord

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "002_subjects.sql"


class SubjectStore:
    """subjects 테이블 저장소 — 동기 psycopg, 호출당 단기 커넥션."""

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

    def upsert(self, record: SubjectRecord) -> None:
        """대상 저장/갱신(updated_at 자동)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subjects
                  (subject_id, owner_id, kind, label, aliases, relation_to_user,
                   birth, gender, is_minor, subscribed, last_interaction_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s,%s,%s)
                ON CONFLICT (subject_id) DO UPDATE SET
                  owner_id=EXCLUDED.owner_id, kind=EXCLUDED.kind, label=EXCLUDED.label,
                  aliases=EXCLUDED.aliases, relation_to_user=EXCLUDED.relation_to_user,
                  birth=EXCLUDED.birth, gender=EXCLUDED.gender,
                  is_minor=EXCLUDED.is_minor, subscribed=EXCLUDED.subscribed,
                  last_interaction_at=EXCLUDED.last_interaction_at, updated_at=now()
                """,
                (
                    record.subject_id, record.owner_id, record.kind, record.label,
                    json.dumps(record.aliases, ensure_ascii=False),
                    record.relation_to_user,
                    record.birth.model_dump_json(), record.gender,
                    record.is_minor, record.subscribed, record.last_interaction_at,
                ),
            )

    def get(self, subject_id: str) -> SubjectRecord | None:
        """단건 조회."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT subject_id, owner_id, kind, label, aliases, relation_to_user,
                       birth, gender, is_minor, subscribed, last_interaction_at
                FROM subjects WHERE subject_id=%s
                """,
                (subject_id,),
            ).fetchone()
        return self._to_record(row) if row else None

    def list_all(self, owner_id: str = "default") -> list[SubjectRecord]:
        """소유자의 전체 대상."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT subject_id, owner_id, kind, label, aliases, relation_to_user,
                       birth, gender, is_minor, subscribed, last_interaction_at
                FROM subjects WHERE owner_id=%s ORDER BY subject_id
                """,
                (owner_id,),
            ).fetchall()
        return [self._to_record(r) for r in rows]

    def list_active(self, now: datetime, owner_id: str = "default") -> list[SubjectRecord]:
        """활성 대상(docs/09 1장) — 일일 배치(T2) 대상 집합."""
        return [s for s in self.list_all(owner_id) if s.is_active(now)]

    def touch(self, subject_id: str, at: datetime) -> None:
        """대화 이력 갱신 — 활성 판정 기준."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE subjects SET last_interaction_at=%s, updated_at=now() "
                "WHERE subject_id=%s",
                (at, subject_id),
            )

    def delete(self, subject_id: str) -> None:
        """대상 삭제(사전계산 무효화는 스케줄러/호출자 책임)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM subjects WHERE subject_id=%s", (subject_id,))

    @staticmethod
    def _to_record(row: tuple) -> SubjectRecord:
        """DB 행 → SubjectRecord."""
        (sid, owner, kind, label, aliases, rel, birth, gender, minor, subd, last) = row
        return SubjectRecord(
            subject_id=sid, owner_id=owner, kind=kind, label=label,
            aliases=aliases, relation_to_user=rel,
            birth=BirthInput.model_validate(birth),
            gender=gender, is_minor=minor, subscribed=subd, last_interaction_at=last,
        )
