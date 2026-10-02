"""리포트(테마사주) 비동기 잡 저장소 (v2.2 프론트 확장 Phase 6 — saju-v2-db 전용).

RPT_FULL은 섹션별 LLM 호출을 순차로 도는 수 분 작업이라 잡 + 폴링 모델을 쓴다. 본 저장소는
잡 상태·진행·결과·실패 사유만 관리하며, 실제 생성은 호출 측(라우터 BackgroundTasks)이 수행한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

from .precompute_store import default_dsn

_KST = ZoneInfo("Asia/Seoul")

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "006_report_jobs.sql"


class ReportJobRecord:
    """잡 1건(읽기 전용 뷰)."""

    def __init__(self, row: tuple) -> None:
        (
            self.job_id,
            self.owner_id,
            self.spec,
            self.status,
            self.sections_done,
            self.sections_total,
            self.result,
            self.error,
            self.created_at,
            self.updated_at,
        ) = row


class ReportJobStore:
    """report_jobs 테이블 — 동기 psycopg, 호출당 단기 커넥션."""

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

    def create(self, job_id: str, owner_id: str, spec: dict, sections_total: int) -> None:
        """잡 생성(queued)."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO report_jobs (job_id, owner_id, spec, sections_total) "
                "VALUES (%s, %s, %s::jsonb, %s)",
                (job_id, owner_id, json.dumps(spec, ensure_ascii=False), sections_total),
            )

    def mark_running(self, job_id: str) -> None:
        """실행 시작 표시."""
        self._set_status(job_id, "running")

    def update_progress(self, job_id: str, sections_done: int, sections_total: int) -> None:
        """진행 섹션 수 갱신 — 분모는 분할 페이지 확장 후 실제 총수로 동기화."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE report_jobs SET sections_done=%s, sections_total=%s, "
                "updated_at=now() WHERE job_id=%s",
                (sections_done, sections_total, job_id),
            )

    def complete(self, job_id: str, result: dict, sections_done: int) -> None:
        """완료 — 결과 저장. 총수도 실제 작성 장 수와 일치시킨다."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE report_jobs SET status='completed', result=%s::jsonb, "
                "sections_done=%s, sections_total=%s, updated_at=now() WHERE job_id=%s",
                (json.dumps(result, ensure_ascii=False), sections_done, sections_done, job_id),
            )

    def fail(self, job_id: str, error: str) -> None:
        """실패 — 사유 저장(LLM 키 미설정 등)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE report_jobs SET status='failed', error=%s, updated_at=now() "
                "WHERE job_id=%s",
                (error, job_id),
            )

    def get(self, job_id: str) -> ReportJobRecord | None:
        """잡 조회(없으면 None)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT job_id, owner_id, spec, status, sections_done, sections_total, "
                "result, error, created_at, updated_at FROM report_jobs WHERE job_id=%s",
                (job_id,),
            ).fetchone()
        return ReportJobRecord(row) if row else None

    def list_by_owner(self, owner_id: str) -> list[dict]:
        """소유자의 잡 목록(최신순) — 본문(result)은 제외한 메타만 반환(가벼운 내역용)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT job_id, spec, status, sections_done, sections_total, error, created_at "
                "FROM report_jobs WHERE owner_id=%s ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
        return [
            {
                "job_id": r[0],
                "spec": r[1],
                "status": r[2],
                "sections_done": r[3],
                "sections_total": r[4],
                "error": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ]

    def list_recent(self, status: str | None = None, limit: int = 100) -> list[dict]:
        """관리자용 — 전 소유자 잡 목록(최신순). status 필터 가능. 본문(result) 제외."""
        where, params = ("WHERE status=%s", [status]) if status else ("", [])
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT job_id, owner_id, spec, status, sections_done, sections_total, "
                f"error, created_at FROM report_jobs {where} ORDER BY created_at DESC "
                "LIMIT %s",
                [*params, limit],
            ).fetchall()
        return [
            {
                "job_id": r[0], "owner_id": r[1],
                "product_code": (r[2] or {}).get("product_code"),
                "status": r[3], "sections_done": r[4], "sections_total": r[5],
                "error": r[6],
                "created_at": r[7].astimezone(_KST).strftime("%Y-%m-%d %H:%M") if r[7] else None,
            }
            for r in rows
        ]

    def status_counts(self) -> dict[str, int]:
        """상태별 잡 수(KPI)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM report_jobs GROUP BY status"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def _set_status(self, job_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE report_jobs SET status=%s, updated_at=now() WHERE job_id=%s",
                (status, job_id),
            )
