"""오늘의 운세 사전 파이프라인 회귀 (CLAUDE.md 원칙 5).

이 사전들은 이미 사용자에게 서비스되고 있으면서 validate → compile(snapshot) →
regression 단계를 거치지 않았다. 그 상태에서 생기는 두 사고를 여기서 막는다:

1. 사전을 고치고 `DICT_VERSION` 을 올리지 않아 **이미 생성된 보드가 옛 문구를 계속
   서비스**하는 캐시 오염.
2. 사전을 고치고 스냅샷을 재컴파일하지 않아 **원본과 서비스 내용이 어긋나는** 상태.

재컴파일: `python scripts/build_daily_fortune_snapshot.py`
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_engines.daily_fortune_snapshot import (
    SOURCES,
    load_snapshot,
    snapshot_path,
    source_digests,
    validate_sources,
)
from saju_engines.daily_ilju_fortune import load_daily_dicts
from saju_shared_types.daily_fortune import DICT_VERSION

_BACKEND = Path(__file__).resolve().parents[2]
_DICTS = _BACKEND / "dictionaries" / "daily_fortune"
_COMPILED = _BACKEND / "compiled"


def test_sources_pass_validation() -> None:
    """원본 3종이 컴파일 가능한 상태여야 한다."""
    assert validate_sources(_DICTS) == []


def test_every_source_declares_review_status() -> None:
    """3종 모두 `reviewed`(명리 감수 여부)를 boolean 으로 선언한다.

    미선언을 통과시키면 감수 워크플로가 무의미해진다 — 과거에는 3종 중 1종만
    선언했고 나머지는 검증을 그대로 통과했다.
    """
    for name, _key in SOURCES:
        data = json.loads((_DICTS / name).read_text(encoding="utf-8"))
        assert isinstance(data.get("reviewed"), bool), f"{name}: reviewed 미선언"


def test_snapshot_exists_for_current_dict_version() -> None:
    """현재 `DICT_VERSION` 스냅샷이 있어야 한다 — 없으면 버전을 올리고 재컴파일하지 않은 것."""
    path = snapshot_path(DICT_VERSION, _COMPILED)
    assert path.exists(), (
        f"{path.name} 없음 — 사전 수정 후 "
        "`python scripts/build_daily_fortune_snapshot.py` 를 실행할 것"
    )


def test_snapshot_matches_sources() -> None:
    """스냅샷 digest 가 원본과 일치해야 한다(재컴파일 누락 감지)."""
    snapshot = load_snapshot(DICT_VERSION, _COMPILED)
    assert snapshot is not None
    current = source_digests(_DICTS)
    for name, meta in snapshot["sources"].items():
        assert meta["sha256"] == current[name], (
            f"{name} 이 스냅샷 이후 변경됨 — DICT_VERSION 을 올리고 재컴파일할 것"
        )


def test_snapshot_declares_structural_validation_not_expert_review() -> None:
    """구조 검증과 명리 감수는 분리된 채로 기록된다.

    파이프라인 통과가 `reviewed` 를 참으로 만들면 안 된다 — 그건 사람의 판단이다.
    """
    snapshot = load_snapshot(DICT_VERSION, _COMPILED)
    assert snapshot is not None
    assert snapshot["structural_validation"] == "passed"
    assert snapshot["dict_version"] == DICT_VERSION
    for name, meta in snapshot["sources"].items():
        source = json.loads((_DICTS / name).read_text(encoding="utf-8"))
        assert meta["reviewed"] == source["reviewed"], f"{name}: 감수 상태 위조"


def test_runtime_serves_snapshot_content() -> None:
    """런타임 로더가 스냅샷을 쓰고, 그 내용이 원본과 같아야 한다."""
    load_daily_dicts.cache_clear()
    served = load_daily_dicts()
    snapshot = load_snapshot(DICT_VERSION, _COMPILED)
    assert snapshot is not None
    assert served.catalog == snapshot["catalog"]
    assert served.templates == snapshot["templates"]
    assert served.places == snapshot["places"]
    # 스냅샷 우선이더라도 내용은 원본과 동일해야 한다(스냅샷이 갈라지면 무의미).
    for name, key in SOURCES:
        assert getattr(served, key) == json.loads(
            (_DICTS / name).read_text(encoding="utf-8")
        )
    load_daily_dicts.cache_clear()


def test_missing_snapshot_falls_back_to_sources(tmp_path: Path) -> None:
    """스냅샷이 없는 환경(신규 클론·fixture)에서도 서비스가 멈추지 않는다."""
    for name, _key in SOURCES:
        (tmp_path / name).write_bytes((_DICTS / name).read_bytes())
    load_daily_dicts.cache_clear()
    dicts = load_daily_dicts(str(tmp_path))
    assert dicts.catalog["events"]
    load_daily_dicts.cache_clear()


def test_validation_rejects_undeclared_review_status(tmp_path: Path) -> None:
    """`reviewed` 미선언 사전은 컴파일되지 않는다."""
    for name, _key in SOURCES:
        data = json.loads((_DICTS / name).read_text(encoding="utf-8"))
        data.pop("reviewed", None)
        (tmp_path / name).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    errors = validate_sources(tmp_path)
    assert len(errors) == len(SOURCES)
    assert all("미선언" in e for e in errors)

    from saju_engines.daily_fortune_snapshot import build_snapshot

    with pytest.raises(ValueError, match="사전 검증 실패"):
        build_snapshot(DICT_VERSION, tmp_path)


def test_runtime_and_review_status_are_separate() -> None:
    """`review_status=PENDING` 을 '계산 미사용'으로 오해하지 않게 두 축을 분리한다."""
    for name, _key in SOURCES:
        data = json.loads((_DICTS / name).read_text(encoding="utf-8"))
        assert data["runtime_status"] in {"ACTIVE", "INACTIVE"}, name
        assert data["review_status"] in {"PENDING", "APPROVED"}, name
        # 미감수여도 runtime 은 ACTIVE 일 수 있다 — 그 조합이 현재 상태다.
        assert data["runtime_status"] == "ACTIVE", f"{name}: 실제로 서비스 중이다"


def test_validation_requires_both_status_fields(tmp_path: Path) -> None:
    """상태 축이 빠진 사전은 컴파일되지 않는다."""
    for name, _key in SOURCES:
        data = json.loads((_DICTS / name).read_text(encoding="utf-8"))
        data.pop("runtime_status", None)
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = validate_sources(tmp_path)
    assert errors and all("runtime_status" in e for e in errors)
