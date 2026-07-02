"""구조 패턴 사전 → 검증·컴파일 스냅샷 빌드 (CLAUDE.md 원칙 5).

dictionaries/structure_patterns.json 을 validate + lint 한 뒤,
compiled/structure_patterns_v{VERSION}.json 스냅샷으로 기록한다. 운영 런타임은
이 스냅샷을 우선 로드한다(saju_engines.structure_patterns.load_structure_patterns).

설계: doc/v2_2/docs/13_STRUCTURE_PATTERNS.md (Step ③).

사용법:
    python scripts/build_structure_patterns_snapshot.py [dictionaries_dir] [compiled_dir]
종료 코드 0=성공, 1=검증/린트 실패.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from saju_engines.dictionaries import _lint_structure_patterns
from saju_shared_types.structure_patterns import StructurePatternDict

_BACKEND = Path(__file__).resolve().parent.parent
_DEFAULT_DICTS = _BACKEND / "dictionaries"
_DEFAULT_COMPILED = _BACKEND / "compiled"
STRUCTURE_PATTERNS_VERSION = "1.0.0"


def build(dictionaries_dir: Path, compiled_dir: Path) -> int:
    """스냅샷을 빌드한다. 성공 0, 실패 1."""
    src = dictionaries_dir / "structure_patterns.json"
    if not src.exists():
        print(f"[skip] 원본 없음: {src}", file=sys.stderr)
        return 1

    try:
        parsed = StructurePatternDict.model_validate(json.loads(src.read_text("utf-8")))
    except Exception as exc:  # noqa: BLE001 — 검증 실패는 종료코드로 보고
        print(f"[fail] 스키마 검증 실패: {exc}", file=sys.stderr)
        return 1

    errors = _lint_structure_patterns(parsed)
    if errors:
        for e in errors:
            print(f"[lint] {e}", file=sys.stderr)
        return 1

    snapshot = parsed.model_dump(by_alias=True)
    snapshot["compiled_at"] = datetime.now(UTC).isoformat()
    snapshot["snapshot_version"] = STRUCTURE_PATTERNS_VERSION

    compiled_dir.mkdir(parents=True, exist_ok=True)
    out = compiled_dir / f"structure_patterns_v{STRUCTURE_PATTERNS_VERSION}.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] {out} ({len(parsed.patterns)} patterns)")
    return 0


def main() -> int:
    dicts = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_DICTS
    compiled = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_COMPILED
    return build(dicts, compiled)


if __name__ == "__main__":
    raise SystemExit(main())
