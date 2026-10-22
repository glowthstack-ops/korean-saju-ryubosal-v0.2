"""직장 이력(JSONL, 사용자 제공 정본) → subject_life_events 적재.

SSOT: doc/v2_2/EMPLOYMENT_HISTORY_CALIBRATION.md §2-3.

입력 한 줄 = `EmploymentHistoryEntry`(date/kind/org/nature/channel/exit_reason/group/note).
행마다 만세력을 그 날짜 기준으로 계산해 절기월 라벨과 월운 지문(엔진 채점)을 붙이고
`source=employment_history`로 적재한다. 같은 (event_key, period)의 다른 소스 행(캘리브레이션
회상)은 정본에 밀려 삭제된다. 기본은 dry-run(표만 출력), `--execute`일 때만 DB에 쓴다.

사용법:
    python scripts/load_employment_history.py --subject <subject_id> --jsonl <경로> [--execute]
DSN은 SAJU_V2_DATABASE_URL(루트 .env 자동 로드). 출력에는 회사명(label)이 사용자 제공 그대로 찍힌다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.employment_history import (
    reference_date_for_label,
    rows_from_history,
    superseded_keys,
)
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.life_event_store import LifeEventStore
from saju_engines.reality_calibration import month_event_fingerprints, pillars_signature
from saju_engines.subject_store import SubjectStore
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import EmploymentHistoryEntry, SignalFingerprint

_BACKEND = Path(__file__).resolve().parent.parent
_ENV_PATHS = [_BACKEND.parent / ".env", _BACKEND / ".env"]


def _load_env() -> None:
    """루트 .env → 환경 변수(이미 설정된 키는 유지)."""
    for path in _ENV_PATHS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def read_entries(path: Path) -> list[EmploymentHistoryEntry]:
    """JSONL → 입력 모델(런타임 검증). 빈 줄·주석(#) 무시."""
    out: list[EmploymentHistoryEntry] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(EmploymentHistoryEntry.model_validate(json.loads(s)))
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. dry-run이면 0, 적재 후에도 0, 대상 없음이면 2."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", required=True, help="subjects.subject_id")
    ap.add_argument("--jsonl", required=True, type=Path)
    ap.add_argument("--execute", action="store_true", help="DB에 실제 적재(기본 dry-run)")
    args = ap.parse_args(argv)
    _load_env()

    subjects = SubjectStore()
    record = subjects.get(args.subject)
    if record is None:
        print(f"대상 없음: {args.subject}", file=sys.stderr)
        return 2
    entries = read_entries(args.jsonl)
    engine = EventEngineV2(_BACKEND / "dictionaries")
    base_chart = calculate(record.birth)
    sig = pillars_signature(base_chart)

    def resolver(d: date, label: str, event_key: str) -> SignalFingerprint | None:
        del d  # 월운 목록은 라벨 연도 기준으로 뽑는다(1월 라벨은 전년 목록)
        chart = calculate(record.birth.model_copy(
            update={"reference_date": reference_date_for_label(label)},
        ))
        cands = engine.score(chart, levels={GanjiLevel.MONTH})
        return month_event_fingerprints(cands, label).get(event_key)

    rows = rows_from_history(entries, args.subject, record.owner_id, sig, resolver)
    print(f"subject={args.subject} owner={record.owner_id} rows={len(rows)}")
    print("period   | key           | nature     | channel  | label")
    for r in rows:
        a = r.attrs
        fp = "fp" if r.signal_fingerprint.ten_god_groups else "--"
        print(f"{r.period} | {r.event_key:<13} | {a.nature or '':<10} | "
              f"{a.entry_channel or a.exit_reason or '':<8} | {a.label or ''} [{fp}]")
    if not args.execute:
        print("dry-run — --execute 로 적재")
        return 0
    store = LifeEventStore()
    store.migrate()
    removed = store.delete_superseded_rows(
        record.owner_id, args.subject, superseded_keys(rows), keep_source="employment_history",
    )
    stored = store.append_rows(rows)
    print(f"적재 {stored}행, 치환 삭제 {removed}행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
