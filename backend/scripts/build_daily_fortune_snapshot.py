"""오늘의 운세 사전 → 검증·컴파일 스냅샷 빌드 (CLAUDE.md 원칙 5).

`dictionaries/daily_fortune/` 3종을 validate 한 뒤
`compiled/daily_fortune_{DICT_VERSION}.json` 스냅샷으로 기록한다. 운영 런타임은 이
스냅샷을 우선 로드한다(`saju_engines.daily_ilju_fortune.load_daily_dicts`).

스냅샷 파일명에 `DICT_VERSION` 이 들어가므로, **사전을 고치고 버전을 올리지 않으면
스냅샷이 없는 상태**가 되어 회귀가 잡는다(캐시 오염 방지).

사용법:
    python scripts/build_daily_fortune_snapshot.py [dictionaries_dir] [compiled_dir]
종료 코드 0=성공, 1=검증 실패.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from saju_engines.daily_fortune_snapshot import (
    build_snapshot,
    snapshot_path,
    validate_sources,
)
from saju_shared_types.daily_fortune import DICT_VERSION

_BACKEND = Path(__file__).resolve().parent.parent
_DEFAULT_DICTS = _BACKEND / "dictionaries" / "daily_fortune"
_DEFAULT_COMPILED = _BACKEND / "compiled"


def build(dictionaries_dir: Path, compiled_dir: Path) -> int:
    """스냅샷을 빌드한다. 성공 0, 실패 1."""
    errors = validate_sources(dictionaries_dir)
    if errors:
        for e in errors:
            print(f"[fail] {e}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(
        DICT_VERSION, dictionaries_dir, compiled_at=datetime.now(UTC).isoformat()
    )
    compiled_dir.mkdir(parents=True, exist_ok=True)
    out = snapshot_path(DICT_VERSION, compiled_dir)
    out.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    reviewed = {n: s["reviewed"] for n, s in snapshot["sources"].items()}
    print(f"[ok] {out}")
    print(f"     structural_validation=passed / 명리 감수(reviewed)={reviewed}")
    return 0


def main() -> int:
    dicts = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_DICTS
    compiled = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_COMPILED
    return build(dicts, compiled)


if __name__ == "__main__":
    raise SystemExit(main())
