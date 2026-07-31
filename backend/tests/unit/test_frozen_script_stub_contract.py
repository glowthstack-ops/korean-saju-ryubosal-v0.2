"""동결 스크립트 sidecar stub 계약 회귀 (2026-07-31).

`legacy_oa10b_runner.py` 는 바이트가 동결돼 있다(artifact digest 결합). 타입 주석 한 줄만
넣어도 동결이 깨지므로 `.py` 는 그대로 두고 `.pyi` 로 타입을 제공한다.

이 방식의 위험은 **스텁이 구현에서 멀어지는 것**이다. mypy 는 `.pyi` 만 읽으므로, 구현에
없는 심볼을 선언하거나 이름이 바뀌어도 타입 검사는 계속 통과한다. 그 상태에서 테스트가
런타임에 실패하면 원인이 스텁이라는 것을 알기 어렵다.

그래서 **스텁에 선언된 심볼이 실제 모듈에 존재하는지** 를 런타임에서 대조한다.
`stubtest` 를 붙이면 더 엄밀하지만 이번 작업 범위를 키우지 않는다 — 존재 대조만으로도
드리프트의 주된 형태(이름 변경·삭제)를 잡는다.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_SCRIPTS = _BACKEND / "scripts"

#: 동결 소스 → sidecar stub. 다른 동결 스크립트가 같은 방식을 쓰면 여기 추가한다.
FROZEN_WITH_STUB = ("legacy_oa10b_runner",)


def _stub_symbols(stub: Path) -> set[str]:
    """`.pyi` 가 선언한 최상위 심볼(밑줄 이름 포함)."""
    tree = ast.parse(stub.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
    return out


@pytest.mark.parametrize("module_name", FROZEN_WITH_STUB)
def test_stub_exists_for_frozen_module(module_name: str) -> None:
    """스텁이 사라지면 동결 모듈이 다시 타입 게이트 밖으로 나간다."""
    assert (_SCRIPTS / f"{module_name}.pyi").is_file()
    assert (_SCRIPTS / f"{module_name}.py").is_file()


@pytest.mark.parametrize("module_name", FROZEN_WITH_STUB)
def test_stub_declares_only_existing_symbols(module_name: str) -> None:
    """스텁이 구현에 없는 심볼을 선언하면 mypy 는 통과하고 런타임만 깨진다."""
    declared = _stub_symbols(_SCRIPTS / f"{module_name}.pyi")
    assert declared, "스텁에서 심볼을 읽지 못했다 — 이 검사가 공허해진다"

    added = str(_SCRIPTS) not in sys.path
    if added:
        sys.path.insert(0, str(_SCRIPTS))
    try:
        module = importlib.import_module(module_name)
        missing = sorted(n for n in declared if not hasattr(module, n))
    finally:
        if added:
            sys.path.remove(str(_SCRIPTS))
    assert not missing, f"{module_name}.pyi 에만 있고 구현에 없는 심볼: {missing}"


def test_frozen_source_digest_binding_is_still_enforced() -> None:
    """동결 결합 자체가 살아 있어야 이 sidecar 방식의 전제가 성립한다.

    digest 결합이 사라지면 `.py` 를 직접 고쳐도 아무도 모르고, 그러면 스텁을 둘 이유도
    없어진다. 결합을 검사하는 테스트가 존재하는지 확인한다.
    """
    characterization = (
        _BACKEND / "tests" / "unit" / "test_legacy_oa10b_characterization.py"
    ).read_text(encoding="utf-8")
    assert "legacy_runner_source_sha256" in characterization
    assert "test_artifact_is_bound_to_the_frozen_source" in characterization
