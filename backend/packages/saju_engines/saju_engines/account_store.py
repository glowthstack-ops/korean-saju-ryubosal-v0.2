"""계정 전역 설정(페르소나) PostgreSQL 저장소 (v2.2 프론트 확장 Phase 1).

페르소나는 문체 전용(점수·날짜·간지·판정 불변, docs/11 5장)이며 계정당 1개로 고정한다.
궁합/관계처럼 두 사주를 함께 풀 때 상담가 문체가 둘이면 충돌하므로 사주별이 아니다.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from saju_shared_types.profile import PersonaConfig

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "005_accounts_and_settings.sql"


class AccountSettingsStore:
    """account_settings 테이블 — 호출당 단기 커넥션(동기 psycopg)."""

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

    def get_persona(self, owner_id: str) -> PersonaConfig | None:
        """계정 페르소나 조회 — 미설정 시 None(호출 측이 기본값 적용)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT persona FROM account_settings WHERE owner_id=%s", (owner_id,)
            ).fetchone()
        if row is None:
            return None
        return PersonaConfig.model_validate(row[0])

    def save_persona(self, owner_id: str, persona: PersonaConfig) -> None:
        """계정 페르소나 저장/갱신."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO account_settings (owner_id, persona)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (owner_id) DO UPDATE SET
                  persona = EXCLUDED.persona, updated_at = now()
                """,
                (owner_id, persona.model_dump_json()),
            )
