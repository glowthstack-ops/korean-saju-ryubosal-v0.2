"""오늘의 운세 v2 카탈로그 → 검증·컴파일 스냅샷 빌드 (docs/17 §22, CLAUDE.md 원칙 5).

`daily_event_catalog_v2.json` 을 검증한 뒤
`compiled/daily_fortune_v2_{MODEL_V2_VERSION}.json` 스냅샷으로 기록한다.

v1 파이프라인(`build_daily_fortune_snapshot.py`)과 분리한다 — C10 동결 기간에 v1
스냅샷·digest 를 건드리지 않기 위해서다. 검증 항목:

1. pydantic 스키마 (64종 — §22-3 48 + §22-7 16·채널 참조·가중 범위·extra 금지)
2. v1 카탈로그와의 정합 — key/label/domain/valence 일치, weather_water_safety 제외
3. **signature 성립 가능성** (§22-4): 고정 연도 전 일자 × 60일주에서 성립 0회 게이트는
   결함으로 차단(v1 초판 낙상 사례)

사용법:
    python scripts/build_daily_fortune_v2_snapshot.py [--skip-satisfiability]
종료 코드 0=성공, 1=검증 실패.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from saju_engines.daily_fortune_v2 import (
    load_catalog_v2,
    unsatisfiable_signatures,
    validate_against_v1,
)
from saju_shared_types.daily_fortune_v2 import MODEL_V2_VERSION

_BACKEND = Path(__file__).resolve().parent.parent
_CATALOG_V2 = _BACKEND / "dictionaries" / "daily_fortune" / "daily_event_catalog_v2.json"
_CATALOG_V1 = _BACKEND / "dictionaries" / "daily_fortune" / "daily_event_catalog.json"
_COMPILED = _BACKEND / "compiled"


def build(skip_satisfiability: bool = False) -> int:
    """스냅샷을 빌드한다. 성공 0, 실패 1."""
    try:
        catalog = load_catalog_v2(str(_CATALOG_V2))
    except Exception as exc:  # pydantic 검증 실패 포함
        print(f"[fail] 스키마 검증 실패: {exc}", file=sys.stderr)
        return 1

    v1_catalog = json.loads(_CATALOG_V1.read_text(encoding="utf-8"))
    errors = validate_against_v1(catalog, v1_catalog)
    if not skip_satisfiability:
        dead = unsatisfiable_signatures(catalog)
        errors.extend(f"{key}: signature 성립 0회(§22-4 결함)" for key in dead)
    if errors:
        for e in errors:
            print(f"[fail] {e}", file=sys.stderr)
        return 1

    raw = _CATALOG_V2.read_bytes()
    snapshot = {
        "model_version": MODEL_V2_VERSION,
        "compiled_at": datetime.now(UTC).isoformat(),
        "source": {
            "name": _CATALOG_V2.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "reviewed": catalog.reviewed,
            "review_note": catalog.review_note,
        },
        "structural_validation": "passed",
        "satisfiability_checked": not skip_satisfiability,
        "catalog": json.loads(raw.decode("utf-8")),
    }
    _COMPILED.mkdir(parents=True, exist_ok=True)
    out = _COMPILED / f"daily_fortune_v2_{MODEL_V2_VERSION}.json"
    out.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"[ok] {out}")
    print(
        f"     events={len(catalog.events)} / structural_validation=passed"
        f" / satisfiability={'checked' if not skip_satisfiability else 'SKIPPED'}"
        f" / 명리 감수(reviewed)={catalog.reviewed}"
    )
    return 0


def main() -> int:
    skip = "--skip-satisfiability" in sys.argv[1:]
    return build(skip_satisfiability=skip)


if __name__ == "__main__":
    raise SystemExit(main())
