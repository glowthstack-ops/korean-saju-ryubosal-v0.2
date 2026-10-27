"""명식(subjects)이 사라진 뒤 남은 종속 개인 행 정리 — 보안 점검 S7 일회성 포렌식(2026-10-24).

subjects 삭제에 FK 가 없어 user_profiles·subject_yongsin·subject_life_events·
subject_reality_calibration·career_shadow_state 행이 고아로 남았다(2026-10-24 실측 각 88건).
라우터는 `purge_subject_data` 로 교정됐고, 이 스크립트는 **기존** 고아만 지운다.

사용:
    python scripts/purge_orphan_subject_rows.py --dry-run   # 건수만
    python scripts/purge_orphan_subject_rows.py --apply     # 삭제(되돌릴 수 없음)
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

_TABLES: tuple[tuple[str, str], ...] = (
    ("user_profiles", "user_id"),
    ("subject_yongsin", "subject_id"),
    ("subject_life_events", "subject_id"),
    ("subject_reality_calibration", "subject_id"),
    ("career_shadow_state", "subject_id"),
)


def main() -> int:
    """고아 행을 세거나(--dry-run) 지운다(--apply)."""
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dsn = os.environ.get("SAJU_V2_DATABASE_URL")
    if not dsn:
        print("SAJU_V2_DATABASE_URL 미설정", file=sys.stderr)
        return 2
    with psycopg.connect(dsn) as conn:
        for table, col in _TABLES:
            where = f"NOT EXISTS (SELECT 1 FROM subjects s WHERE s.subject_id = {table}.{col})"
            n = conn.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()  # noqa: S608
            count = int(n[0]) if n else 0
            if args.apply and count:
                cur = conn.execute(f"DELETE FROM {table} WHERE {where}")  # noqa: S608
                print(f"{table}: deleted {cur.rowcount}")
            else:
                print(f"{table}: orphan {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
