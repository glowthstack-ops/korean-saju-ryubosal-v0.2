"""LLM 서비스 중단 상태 저장소 (단일 행 — migrations/019_llm_service_state.sql).

비용 소진으로 메인·폴백이 모두 막혔을 때의 '일시 중단' 상태와 공급자별 소진/쿨다운 기록을
DB 한 행에 둔다. 읽기·쓰기 모두 단기 커넥션이며, 캐시·전이 규칙은 서비스 계층
(`saju_api.services.llm_service_state`)이 담당한다 — 이 모듈은 영속화만 한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "019_llm_service_state.sql"

_COLUMNS = (
    "state", "reason", "suspended_at", "resumed_at", "resumed_by", "providers", "last_probe",
)


class LLMServiceStateStore:
    """llm_service_state 단일 행 — 동기 psycopg, 호출당 단기 커넥션."""

    def __init__(self, dsn: str | None = None) -> None:
        """dsn 미지정 시 SAJU_V2_DATABASE_URL 사용(없으면 ValueError)."""
        resolved = dsn or default_dsn()
        if not resolved:
            raise ValueError("DB 접속 문자열 필요 — 인자 또는 SAJU_V2_DATABASE_URL")
        self._dsn = resolved

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def migrate(self) -> None:
        """마이그레이션 적용(멱등) — 테이블 + 기본 행(id=1)."""
        with self._connect() as conn:
            conn.execute(_MIGRATION.read_text(encoding="utf-8"))

    def load(self) -> dict[str, Any]:
        """단일 행을 dict로 읽는다. 행이 없으면(마이그레이션 전) 기본 active 상태를 돌려준다."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM llm_service_state WHERE id = 1"
            ).fetchone()
        if row is None:
            return {
                "state": "active", "reason": None, "suspended_at": None,
                "resumed_at": None, "resumed_by": None, "providers": {}, "last_probe": None,
            }
        data = dict(zip(_COLUMNS, row, strict=True))
        data["providers"] = data.get("providers") or {}
        return data

    def save(
        self,
        *,
        state: str,
        reason: str | None,
        suspended_at: datetime | None,
        resumed_at: datetime | None,
        resumed_by: str | None,
        providers: dict[str, Any],
        last_probe: dict[str, Any] | None,
    ) -> None:
        """단일 행 전체를 덮어쓴다(읽기-수정-쓰기는 서비스 계층 책임)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE llm_service_state SET state=%s, reason=%s, suspended_at=%s, "
                "resumed_at=%s, resumed_by=%s, providers=%s::jsonb, last_probe=%s::jsonb, "
                "updated_at=now() WHERE id = 1",
                (
                    state, reason, suspended_at, resumed_at, resumed_by,
                    json.dumps(providers, ensure_ascii=False),
                    json.dumps(last_probe, ensure_ascii=False) if last_probe is not None else None,
                ),
            )
