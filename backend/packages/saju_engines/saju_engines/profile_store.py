"""user_profiles 저장소 (v2.2 Phase 8.5 — docs/11 6장, saju-v2-db 전용 인스턴스)."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg

from saju_shared_types.profile import (
    BasicProfile,
    ExtendedProfile,
    PersonaConfig,
    UserProfile,
)

from .precompute_store import default_dsn

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_MIGRATION_FILES = (
    "004_user_profiles.sql",
    "012_subject_yongsin.sql",
    "013_subject_yongsin_calibration.sql",
)


class ProfileStore:
    """user_profiles 테이블 — 호출당 단기 커넥션(동기 psycopg)."""

    def __init__(self, dsn: str | None = None) -> None:
        """dsn 미지정 시 SAJU_V2_DATABASE_URL 사용."""
        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError("DB 접속 문자열 필요 — 인자 또는 SAJU_V2_DATABASE_URL")
        self._dsn = resolved

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def migrate(self) -> None:
        """마이그레이션 적용(멱등) — user_profiles(004) + 확정 용신 전용 테이블(012)."""
        with self._connect() as conn:
            for name in _MIGRATION_FILES:
                conn.execute((_MIGRATIONS_DIR / name).read_text(encoding="utf-8"))

    def save(self, profile: UserProfile) -> None:
        """프로필 저장/갱신 — basic 변경 시 T0~T2 무효화는 호출 측(docs/09)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles
                  (user_id, basic, extended, persona, extended_completed_at)
                VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  basic = EXCLUDED.basic,
                  extended = EXCLUDED.extended,
                  persona = EXCLUDED.persona,
                  extended_completed_at = EXCLUDED.extended_completed_at,
                  updated_at = now()
                """,
                (
                    profile.user_id,
                    profile.basic.model_dump_json(),
                    profile.extended.model_dump_json() if profile.extended else None,
                    profile.persona.model_dump_json(),
                    profile.extended_completed_at,
                ),
            )

    def load(self, user_id: str) -> UserProfile | None:
        """프로필 복원(없으면 None)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT basic, extended, persona, extended_completed_at
                FROM user_profiles WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        basic, extended, persona, completed = row
        return UserProfile(
            user_id=user_id,
            basic=BasicProfile.model_validate(basic),
            extended=ExtendedProfile.model_validate(extended) if extended else None,
            persona=PersonaConfig.model_validate(persona),
            extended_completed_at=completed.isoformat() if completed else None,
        )

    def set_yongsin(self, user_id: str, element: str | None) -> None:
        """확정 용신 저장(사주별, 전용 테이블 UPSERT) — migration 012.

        프로필 행(basic/persona NOT NULL) 유무와 무관하게 동작한다 — 만세력 페이지의 용신 검증
        확정을 프로필 없이도 영속하기 위해 전용 테이블(subject_yongsin)을 쓴다.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO subject_yongsin (subject_id, confirmed_yongsin) VALUES (%s, %s) "
                "ON CONFLICT (subject_id) DO UPDATE SET "
                "  confirmed_yongsin = EXCLUDED.confirmed_yongsin, updated_at = now()",
                (user_id, element),
            )

    def get_yongsin(self, user_id: str) -> str | None:
        """확정 용신 조회(없으면 None) — 전용 테이블(subject_yongsin)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT confirmed_yongsin FROM subject_yongsin WHERE subject_id = %s",
                (user_id,),
            ).fetchone()
        return row[0] if row and row[0] else None

    def set_yongsin_calibration(
        self, user_id: str, element: str | None, calibration: dict | None
    ) -> None:
        """확정 용신 + 검증 Q&A(답변·결과) 동시 저장(사주별 UPSERT) — migration 013.

        어느 기기에서든 재검증 시 과거 답변을 프리필하기 위해 검증 답변을 서버에 영속한다.
        확정 용신만 저장하는 :meth:`set_yongsin`과 달리 calibration(jsonb)까지 갱신한다.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO subject_yongsin (subject_id, confirmed_yongsin, calibration) "
                "VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (subject_id) DO UPDATE SET "
                "  confirmed_yongsin = EXCLUDED.confirmed_yongsin, "
                "  calibration = EXCLUDED.calibration, updated_at = now()",
                (user_id, element, json.dumps(calibration) if calibration is not None else None),
            )

    def get_yongsin_calibration(self, user_id: str) -> dict | None:
        """검증 Q&A(답변·결과) 조회(없으면 None) — 전용 테이블(subject_yongsin)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT calibration FROM subject_yongsin WHERE subject_id = %s",
                (user_id,),
            ).fetchone()
        return row[0] if row and row[0] else None

    def delete_extended_field(self, user_id: str, field: str) -> None:
        """2단계 필드 개별 삭제(JSONB 키 제거) — 캐시 무효화는 호출 측."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE user_profiles SET extended = extended - %s, "
                "updated_at = now() WHERE user_id = %s",
                (field, user_id),
            )

    @staticmethod
    def _json(value: dict | None) -> str | None:
        return json.dumps(value, ensure_ascii=False) if value is not None else None
