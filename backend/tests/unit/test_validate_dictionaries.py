"""validate_dictionaries 골격 검증 (v2.2 Phase 0 T0.2)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_dictionaries.py"
_spec = importlib.util.spec_from_file_location("validate_dictionaries", _SCRIPT)
assert _spec is not None and _spec.loader is not None
validate_dictionaries = importlib.util.module_from_spec(_spec)
# dataclass가 cls.__module__을 sys.modules에서 조회하므로 등록 후 실행.
sys.modules["validate_dictionaries"] = validate_dictionaries
_spec.loader.exec_module(validate_dictionaries)


def test_valid_dict_passes(tmp_path: Path) -> None:
    """reviewed:bool 플래그를 가진 정상 JSON은 통과."""
    (tmp_path / "ok.json").write_text(
        '{"items": [{"key": "甲己合", "reviewed": false}]}', encoding="utf-8"
    )
    report = validate_dictionaries.validate_dir(tmp_path)
    assert report.ok and report.checked == ["ok.json"]


def test_bom_rejected(tmp_path: Path) -> None:
    """UTF-8 BOM이 붙은 파일은 위반."""
    (tmp_path / "bom.json").write_bytes(b"\xef\xbb\xbf{}")
    report = validate_dictionaries.validate_dir(tmp_path)
    assert not report.ok and any("BOM" in e for e in report.errors)


def test_bad_json_rejected(tmp_path: Path) -> None:
    """파싱 불가 JSON은 위반."""
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    report = validate_dictionaries.validate_dir(tmp_path)
    assert not report.ok and any("파싱 실패" in e for e in report.errors)


def test_non_boolean_reviewed_rejected(tmp_path: Path) -> None:
    """reviewed가 boolean이 아니면 위반."""
    (tmp_path / "flag.json").write_text('{"reviewed": "yes"}', encoding="utf-8")
    report = validate_dictionaries.validate_dir(tmp_path)
    assert not report.ok and any("boolean" in e for e in report.errors)


def test_missing_dir_returns_error_code() -> None:
    """없는 디렉토리는 종료 코드 1."""
    assert validate_dictionaries.main(["prog", "/nonexistent/xyz"]) == 1


@pytest.mark.parametrize("name", ["a.json", "nested/b.json"])
def test_recursive_discovery(tmp_path: Path, name: str) -> None:
    """하위 디렉토리까지 재귀 탐색한다."""
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"reviewed": true}', encoding="utf-8")
    report = validate_dictionaries.validate_dir(tmp_path)
    assert name.split("/")[-1] in report.checked[0] or any(
        name.endswith(c) for c in report.checked
    )
