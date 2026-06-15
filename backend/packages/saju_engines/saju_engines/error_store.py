"""시스템 에러 중앙 저장소 (운영 콘솔 — 에러 모니터링).

미처리 예외(http 5xx)·LLM 호출 실패(llm)·리포트 잡 실패(report_job) 등을 한 테이블(system_errors)에
적재하고, fingerprint(출처+종류+정규화 메시지)로 묶어 빈도·미해결 여부를 본다. 기록은 best-effort —
모니터링이 본 기능을 깨지 않도록 호출 측(error_logging)에서 예외를 삼킨다.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import psycopg

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "010_system_errors.sql"
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def fingerprint(source: str, kind: str, message: str) -> str:
    """유사 에러 묶음 키 — 메시지의 숫자(아이디·시각·토큰 등)를 '#'로 지운 뒤 출처·종류와 해시한다.

    같은 원인의 에러가 매번 다른 식별자·수치를 달고 와도 하나의 그룹으로 묶기 위함이다.
    """
    norm = _WS.sub(" ", _DIGITS.sub("#", message or "")).strip()[:200]
    raw = f"{source}|{kind}|{norm}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class ErrorStore:
    """system_errors 적재·집계·해결 처리 — DSN 단기 커넥션."""

    def __init__(self, dsn: str | None = None) -> None:
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

    def record(
        self, *, source: str, kind: str, message: str, severity: str = "error",
        detail: str | None = None, path: str | None = None,
        owner_id: str | None = None, ref_id: str | None = None,
    ) -> None:
        """에러 1건 적재(fingerprint 자동 계산). 호출 측에서 예외를 삼킨다(best-effort)."""
        fp = fingerprint(source, kind, message)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO system_errors (source, severity, kind, message, detail, "
                "path, owner_id, ref_id, fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (source, severity, kind, message, detail, path, owner_id, ref_id, fp),
            )

    def list_recent(
        self, *, source: str | None = None, severity: str | None = None,
        unresolved_only: bool = False, fingerprint: str | None = None, limit: int = 100,
    ) -> list[dict]:
        """최근 에러 목록(필터: 출처·심각도·미해결·fingerprint). 시각은 KST 표기."""
        clauses: list[str] = []
        params: list = []
        if source:
            clauses.append("source = %s")
            params.append(source)
        if severity:
            clauses.append("severity = %s")
            params.append(severity)
        if fingerprint:
            clauses.append("fingerprint = %s")
            params.append(fingerprint)
        if unresolved_only:
            clauses.append("resolved_at IS NULL")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, "
                "to_char(created_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS'), "
                "source, severity, kind, message, detail, path, owner_id, ref_id, "
                "fingerprint, resolved_at IS NOT NULL "
                f"FROM system_errors {where} ORDER BY created_at DESC LIMIT %s",
                params,
            ).fetchall()
        return [
            {
                "id": r[0], "created_at": r[1], "source": r[2], "severity": r[3],
                "kind": r[4], "message": r[5], "detail": r[6], "path": r[7],
                "owner_id": r[8], "ref_id": r[9], "fingerprint": r[10], "resolved": r[11],
            }
            for r in rows
        ]

    def group_summary(
        self, *, days: int = 7, unresolved_only: bool = False, limit: int = 50,
    ) -> list[dict]:
        """fingerprint별 묶음 — 발생 횟수·미해결 수·최초/최종 발생·대표 메시지(최신)."""
        clauses = ["created_at >= now() - make_interval(days => %s)"]
        params: list = [days]
        if unresolved_only:
            clauses.append("resolved_at IS NULL")
        where = "WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT fingerprint, COUNT(*), "
                "COUNT(*) FILTER (WHERE resolved_at IS NULL), "
                "to_char(MAX(created_at) AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS'), "
                "to_char(MIN(created_at) AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS'), "
                "MAX(source), MAX(severity), MAX(kind), "
                "(array_agg(message ORDER BY created_at DESC))[1], "
                "(array_agg(path ORDER BY created_at DESC))[1] "
                f"FROM system_errors {where} "
                "GROUP BY fingerprint ORDER BY MAX(created_at) DESC LIMIT %s",
                params + [limit],
            ).fetchall()
        return [
            {
                "fingerprint": r[0], "count": r[1], "unresolved": r[2],
                "last_seen": r[3], "first_seen": r[4], "source": r[5],
                "severity": r[6], "kind": r[7], "message": r[8], "path": r[9],
            }
            for r in rows
        ]

    def resolve(
        self, *, ids: list[int] | None = None, fingerprint: str | None = None,
    ) -> int:
        """미해결 에러를 해결 처리(resolved_at=now). ids 또는 fingerprint 단위. 처리 건수 반환."""
        if ids:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE system_errors SET resolved_at = now() "
                    "WHERE id = ANY(%s) AND resolved_at IS NULL",
                    (list(ids),),
                )
                return cur.rowcount
        if fingerprint:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE system_errors SET resolved_at = now() "
                    "WHERE fingerprint = %s AND resolved_at IS NULL",
                    (fingerprint,),
                )
                return cur.rowcount
        return 0

    def counts(self, *, days: int = 7) -> dict:
        """기간 내 총 발생·미해결 수."""
        with self._connect() as conn:
            r = conn.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE resolved_at IS NULL) "
                "FROM system_errors WHERE created_at >= now() - make_interval(days => %s)",
                (days,),
            ).fetchone() or (0, 0)
        return {"total": r[0] or 0, "unresolved": r[1] or 0}

    def unresolved_total(self) -> int:
        """전체 미해결 에러 수(KPI)."""
        with self._connect() as conn:
            r = conn.execute(
                "SELECT COUNT(*) FROM system_errors WHERE resolved_at IS NULL"
            ).fetchone()
        return r[0] if r else 0
