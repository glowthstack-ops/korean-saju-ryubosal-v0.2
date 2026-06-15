"""계정(ID+PIN) PostgreSQL 저장소 (v2.2 프론트 확장 Phase 1 — saju-v2-db 전용).

PIN은 pbkdf2-sha256으로 해시 저장(평문 금지). 본 인증은 OAuth 도입 전 임시 수단으로
낮은 보안 등급이며, 검증 로직은 추후 OAuth로 대치될 수 있도록 저장소에 격리한다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

import psycopg

from saju_shared_types.account import AccountRecord

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "005_accounts_and_settings.sql"
_PBKDF2_ITERATIONS = 200_000


def _hash_pin(pin: str, *, salt: bytes | None = None, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """PIN을 'iterations$salt_hex$hash_hex' 형식으로 해시한다."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return f"{iterations}${salt.hex()}${digest.hex()}"


def _verify_pin(pin: str, stored: str) -> bool:
    """저장된 해시와 PIN을 상수시간 비교한다."""
    try:
        iter_s, salt_hex, hash_hex = stored.split("$", 2)
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate.hex(), hash_hex)


class AccountExistsError(ValueError):
    """이미 존재하는 login_id로 등록 시도."""


class AccountAuthStore:
    """accounts 테이블 저장소 — 동기 psycopg, 호출당 단기 커넥션."""

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

    def register(self, login_id: str, pin: str) -> AccountRecord:
        """신규 계정 등록 — owner_id=login_id. 중복 시 AccountExistsError."""
        owner_id = login_id
        pin_hash = _hash_pin(pin)
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO accounts (owner_id, login_id, pin_hash) VALUES (%s, %s, %s)",
                    (owner_id, login_id, pin_hash),
                )
        except psycopg.errors.UniqueViolation as exc:
            raise AccountExistsError(f"이미 존재하는 ID: {login_id}") from exc
        return AccountRecord(owner_id=owner_id, login_id=login_id)

    def verify(self, login_id: str, pin: str) -> AccountRecord | None:
        """login_id+PIN 검증 — 성공 시 AccountRecord, 실패 시 None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_id, login_id, pin_hash, created_at FROM accounts WHERE login_id=%s",
                (login_id,),
            ).fetchone()
        if row is None:
            return None
        owner_id, login_id_db, pin_hash, created_at = row
        if not _verify_pin(pin, pin_hash):
            return None
        return AccountRecord(owner_id=owner_id, login_id=login_id_db, created_at=created_at)

    def get(self, owner_id: str) -> AccountRecord | None:
        """owner_id로 계정 조회(없으면 None)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_id, login_id, created_at FROM accounts WHERE owner_id=%s",
                (owner_id,),
            ).fetchone()
        if row is None:
            return None
        owner, login_id, created_at = row
        return AccountRecord(owner_id=owner, login_id=login_id, created_at=created_at)

    def is_admin(self, owner_id: str) -> bool:
        """관리자 권한 여부(009 is_admin)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_admin FROM accounts WHERE owner_id=%s", (owner_id,),
            ).fetchone()
        return bool(row and row[0])

    def set_admin(self, login_id: str, value: bool = True) -> bool:
        """login_id에 관리자 권한 부여/회수(존재하는 계정만). 반영 여부 반환."""
        with self._connect() as conn:
            n = conn.execute(
                "UPDATE accounts SET is_admin=%s WHERE login_id=%s", (value, login_id),
            ).rowcount
        return n > 0
