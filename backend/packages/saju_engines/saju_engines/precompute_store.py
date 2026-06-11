"""Precompute Store — luck_composites PostgreSQL 저장소 (v2.2 Phase 2.5 T2.5.3·T2.5.5).

대상 인스턴스는 v1 DB(5432)와 분리된 전용 `saju-v2-db`(호스트 5433, docker-compose.yml)다.
접속 문자열은 `SAJU_V2_DATABASE_URL` 환경 변수로 받는다(.env.example 참조).

규칙(docs/09·07):
- (subject_id, level, period_key, dict_version) 기본키 — 조회는 항상 dict_version 필터
  필수(버전 불일치 데이터 혼용 금지, 리스크 13).
- 사전 버전 변경 → 구버전 레코드 무효화(invalidate). 출생정보 수정 → 대상 전체 삭제.
- day 레벨 보존: 과거 90일/미래 400일 외 삭제 배치(T2.5.5).
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import psycopg

from saju_shared_types.precompute import CompositeLevel, LuckComposite

_ENV_KEY = "SAJU_V2_DATABASE_URL"
_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "001_luck_composites.sql"

DAY_KEEP_PAST_DAYS = 90
DAY_KEEP_FUTURE_DAYS = 400


def default_dsn() -> str | None:
    """환경 변수에서 접속 문자열을 읽는다(미설정이면 None)."""
    return os.environ.get(_ENV_KEY)


class PrecomputeStore:
    """luck_composites 테이블 저장소 — 동기 psycopg, 호출당 단기 커넥션."""

    def __init__(self, dsn: str | None = None) -> None:
        """dsn 미지정 시 SAJU_V2_DATABASE_URL 사용.

        Raises:
            ValueError: 접속 문자열이 어디에도 없을 때.
        """
        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError(f"DB 접속 문자열 필요 — 인자 또는 {_ENV_KEY} 환경 변수")
        self._dsn = resolved

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    # ── 스키마 ───────────────────────────────────────────────────

    def migrate(self) -> None:
        """마이그레이션 SQL 적용(멱등 — IF NOT EXISTS)."""
        sql = _MIGRATION.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.execute(sql)

    # ── 쓰기 ────────────────────────────────────────────────────

    def upsert(self, composites: list[LuckComposite]) -> int:
        """LuckComposite 목록을 저장(동일 키는 payload 갱신). 저장 건수를 반환."""
        if not composites:
            return 0
        rows = [
            (
                c.subject_id, str(c.level), c.period_key, c.dict_version,
                json.dumps(c.model_dump(), ensure_ascii=False), c.computed_at,
            )
            for c in composites
        ]
        with self._connect() as conn:
            conn.cursor().executemany(
                """
                INSERT INTO luck_composites
                  (subject_id, level, period_key, dict_version, payload, computed_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::timestamptz)
                ON CONFLICT (subject_id, level, period_key, dict_version)
                DO UPDATE SET payload = EXCLUDED.payload,
                              computed_at = EXCLUDED.computed_at
                """,
                rows,
            )
        return len(rows)

    # ── 읽기 (dict_version 필터 필수) ─────────────────────────────

    def get(
        self, subject_id: str, level: CompositeLevel, period_key: str, dict_version: str
    ) -> LuckComposite | None:
        """단건 조회 — 키 전체 일치(버전 포함)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM luck_composites
                WHERE subject_id=%s AND level=%s AND period_key=%s AND dict_version=%s
                """,
                (subject_id, str(level), period_key, dict_version),
            ).fetchone()
        return LuckComposite.model_validate(row[0]) if row else None

    def list_for(
        self, subject_id: str, dict_version: str, level: CompositeLevel | None = None
    ) -> list[LuckComposite]:
        """대상의 레코드 목록(레벨 선택) — 항상 버전 필터."""
        query = (
            "SELECT payload FROM luck_composites "
            "WHERE subject_id=%s AND dict_version=%s"
        )
        params: list[object] = [subject_id, dict_version]
        if level is not None:
            query += " AND level=%s"
            params.append(str(level))
        query += " ORDER BY level, period_key"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [LuckComposite.model_validate(r[0]) for r in rows]

    # ── 무효화/정리 ───────────────────────────────────────────────

    def invalidate_other_versions(self, current_dict_version: str) -> int:
        """사전 버전 변경 시 구버전 레코드 전체 삭제(docs/09 무효화 규칙)."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM luck_composites WHERE dict_version <> %s",
                (current_dict_version,),
            )
            return cur.rowcount or 0

    def invalidate_subject(self, subject_id: str) -> int:
        """출생정보 수정 시 해당 대상의 T0~T2 전체 무효화."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM luck_composites WHERE subject_id = %s", (subject_id,)
            )
            return cur.rowcount or 0

    def purge_day_records(self, today: date) -> int:
        """day 레벨 보존 정리(T2.5.5): 과거 90일/미래 400일 범위 밖 삭제."""
        low = (today - timedelta(days=DAY_KEEP_PAST_DAYS)).isoformat()
        high = (today + timedelta(days=DAY_KEEP_FUTURE_DAYS)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                DELETE FROM luck_composites
                WHERE level = 'day' AND (period_key < %s OR period_key > %s)
                """,
                (low, high),
            )
            return cur.rowcount or 0
