"""subject_life_events PostgreSQL 저장소 (Life Event Inference — 수집 단계).

doc/v2_2/LIFE_EVENT_INFERENCE.md §4.5. 확인 사건을 원자 행으로 적재하고, 코호트 표본 수를
granularity별로 집계한다(코호트 활성 게이트 §4.4의 판정 근거). 본 단계는 적재·집계만 하며
랭킹에는 반영하지 않는다. SubjectStore와 동일 DSN(SAJU_V2_DATABASE_URL)·단기 커넥션.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from saju_shared_types.life_event import LifeEventRow

from .precompute_store import default_dsn

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "008_life_events.sql"


class LifeEventStore:
    """subject_life_events 저장소 — 동기 psycopg, 호출당 단기 커넥션."""

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

    def append_rows(self, rows: list[LifeEventRow]) -> int:
        """확인 사건 적재(동일 event_row_id는 갱신 — 재제출 멱등). 적재 행 수 반환."""
        if not rows:
            return 0
        with self._connect() as conn:
            for r in rows:
                conn.execute(
                    """
                    INSERT INTO subject_life_events
                      (event_row_id, subject_id, owner_id, pillar_year, pillar_month,
                       pillar_day, pillar_hour, gender, event_key, period,
                       signal_fingerprint, outcome, source, weight)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    ON CONFLICT (event_row_id) DO UPDATE SET
                      signal_fingerprint=EXCLUDED.signal_fingerprint,
                      outcome=EXCLUDED.outcome, source=EXCLUDED.source,
                      weight=EXCLUDED.weight
                    """,
                    (
                        r.event_row_id, r.subject_id, r.owner_id,
                        r.pillar_year, r.pillar_month, r.pillar_day, r.pillar_hour,
                        r.gender, r.event_key, r.period,
                        r.signal_fingerprint.model_dump_json(),
                        str(r.outcome), str(r.source), r.weight,
                    ),
                )
        return len(rows)

    def cohort_count(
        self, *, pillar_day: str, gender: str | None, event_key: str | None = None,
        fine_pillars: tuple[str, str, str, str | None] | None = None,
    ) -> int:
        """코호트 표본 수(확정 사건 기준) — 활성 게이트 판정용.

        fine_pillars(年月日時) 지정 시 fine 코호트(전체 사주+성별), 아니면 coarse(일주+성별).
        """
        where = ["outcome='confirmed'", "pillar_day=%s"]
        params: list[object] = [pillar_day]
        if gender is not None:
            where.append("gender=%s")
            params.append(gender)
        if event_key is not None:
            where.append("event_key=%s")
            params.append(event_key)
        if fine_pillars is not None:
            py, pm, _pd, ph = fine_pillars
            where += ["pillar_year=%s", "pillar_month=%s"]
            params += [py, pm]
            if ph is not None:
                where.append("pillar_hour=%s")
                params.append(ph)
        sql = f"SELECT count(*) FROM subject_life_events WHERE {' AND '.join(where)}"  # noqa: S608
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return int(row[0]) if row else 0

    def cohort_event_counts(
        self, *, pillar_day: str, gender: str | None,
        fine_pillars: tuple[str, str, str, str | None] | None = None,
    ) -> tuple[int, dict[str, int]]:
        """코호트의 (확정 사건 보유 인원 수, 이벤트별 보유 인원 수) — 익명 집계(개인 비노출).

        fine_pillars(年月日時) 지정 시 fine 코호트(전체 사주+성별), 아니면 coarse(일주+성별).
        분모·분자 모두 distinct subject 수 → '이 코호트에서 그 사건을 겪은 사람 비율'의 근거.
        """
        where = ["outcome='confirmed'", "pillar_day=%s"]
        params: list[object] = [pillar_day]
        if gender is not None:
            where.append("gender=%s")
            params.append(gender)
        if fine_pillars is not None:
            py, pm, _pd, ph = fine_pillars
            where += ["pillar_year=%s", "pillar_month=%s"]
            params += [py, pm]
            if ph is not None:
                where.append("pillar_hour=%s")
                params.append(ph)
        clause = " AND ".join(where)
        with self._connect() as conn:
            total_row = conn.execute(
                f"SELECT count(DISTINCT subject_id) FROM subject_life_events WHERE {clause}",  # noqa: S608
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                "SELECT event_key, count(DISTINCT subject_id) FROM subject_life_events "  # noqa: S608
                f"WHERE {clause} GROUP BY event_key",
                tuple(params),
            ).fetchall()
        total = int(total_row[0]) if total_row else 0
        return total, {str(r[0]): int(r[1]) for r in rows}

    def subject_signature(self, owner_id: str, subject_id: str) -> list[LifeEventRow]:
        """그 subject의 확인 사건 전체(개인 시그니처) — 랭킹 배선 단계에서 사용."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_row_id, subject_id, owner_id, pillar_year, pillar_month,
                       pillar_day, pillar_hour, gender, event_key, period,
                       signal_fingerprint, outcome, source, weight
                FROM subject_life_events
                WHERE owner_id=%s AND subject_id=%s
                """,
                (owner_id, subject_id),
            ).fetchall()
        out: list[LifeEventRow] = []
        for r in rows:
            out.append(LifeEventRow(
                event_row_id=r[0], subject_id=r[1], owner_id=r[2],
                pillar_year=r[3], pillar_month=r[4], pillar_day=r[5], pillar_hour=r[6],
                gender=r[7], event_key=r[8], period=r[9],
                signal_fingerprint=r[10], outcome=r[11], source=r[12], weight=r[13],
            ))
        return out
