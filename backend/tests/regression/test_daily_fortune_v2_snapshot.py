"""v2 카탈로그 ↔ 컴파일 스냅샷 동기 회귀 (docs/17 §22-6, CLAUDE.md 원칙 5).

v1 파이프라인(test_daily_fortune_snapshot)과 같은 규약: 원본을 고치고 재컴파일하지
않으면 digest 불일치로 잡힌다. v1 스냅샷과 분리된 파일이라 C10 동결에 영향 없음.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from saju_shared_types.daily_fortune_v2 import MODEL_V2_VERSION

_BACKEND = Path(__file__).resolve().parents[2]
_SOURCE = _BACKEND / "dictionaries" / "daily_fortune" / "daily_event_catalog_v2.json"
_SNAPSHOT = _BACKEND / "compiled" / f"daily_fortune_v2_{MODEL_V2_VERSION}.json"


def test_v2_snapshot_exists_for_current_model_version() -> None:
    """MODEL_V2_VERSION 에 대응하는 스냅샷이 없으면 버전 범프 후 재컴파일 누락이다."""
    assert _SNAPSHOT.exists(), (
        f"{_SNAPSHOT.name} 부재 — scripts/build_daily_fortune_v2_snapshot.py 실행 필요"
    )


def test_v2_snapshot_matches_source_digest() -> None:
    """스냅샷 digest 가 원본과 일치해야 한다(재컴파일 누락 감지)."""
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert snapshot["model_version"] == MODEL_V2_VERSION
    assert snapshot["structural_validation"] == "passed"
    current = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()
    assert snapshot["source"]["sha256"] == current, (
        "daily_event_catalog_v2.json 이 스냅샷 이후 변경됨 — 재컴파일할 것"
    )
    # 구조 검증 통과가 감수 상태를 위조하면 안 된다.
    source = json.loads(_SOURCE.read_text(encoding="utf-8"))
    assert snapshot["source"]["reviewed"] == source["reviewed"]
