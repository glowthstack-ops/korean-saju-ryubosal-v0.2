"""유지 대상 스크립트의 런타임 진입점 회귀 (2026-07-31).

mypy 만으로는 부족하다. `ignore_missing_imports` 가 전역에서 켜져 있어 **없는 모듈 경로가
Any 로 흡수**되고 mypy 가 `Success` 를 내는 사례가 실제로 있었다(런타임 pytest 가 잡았다).
내부 package 는 이제 override 로 차단하지만, 스크립트끼리의 top-level import 나 동적·조건부
경로까지 정적 검사만으로 보장되지는 않는다.

그래서 allowlist 스크립트가 **실제로 import 되는지** 를 런타임에서 확인한다.

    외부 호출 없음 · DB 변경 없음 · 유료 호출 없음
    live 호출은 opt-in 인자가 없으면 실행되지 않는 계약을 함께 고정한다

allowlist 는 `scripts/typecheck_maintained_scripts.sh` 가 SSOT 다. 두 곳에 목록을 두면
어긋나므로 여기서 그 파일을 읽어 대조한다.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_GATE = _BACKEND.parent / "scripts" / "typecheck_maintained_scripts.sh"


def _allowlist() -> list[str]:
    """게이트 스크립트의 MAINTAINED 배열을 읽는다(목록 SSOT는 그쪽)."""
    text = _GATE.read_text(encoding="utf-8")
    body = text.split("MAINTAINED=(", 1)[1].split(")", 1)[0]
    return [
        m.group(0) for m in re.finditer(r"scripts/[A-Za-z0-9_./]+\.py", body)
    ]


ALLOWLIST = _allowlist()


def test_allowlist_is_not_empty() -> None:
    """목록을 읽지 못하면 아래 검사가 전부 공허하게 통과한다."""
    assert ALLOWLIST, f"{_GATE} 에서 MAINTAINED 목록을 읽지 못했다"


@pytest.mark.parametrize("rel", ALLOWLIST)
def test_maintained_script_files_exist(rel: str) -> None:
    """목록에 있는데 파일이 없으면 게이트만 초록으로 남는다."""
    assert (_BACKEND / rel).is_file(), rel


@pytest.mark.parametrize("rel", ALLOWLIST)
def test_maintained_script_imports_cleanly(rel: str) -> None:
    """모듈 import 가 성공한다 — import 시점에 외부 호출·DB 변경이 없어야 한다.

    `runpy` 가 아니라 모듈 import 로 확인한다. 스크립트들은 `if __name__ == "__main__"`
    가드 뒤에서만 실행하므로 import 자체는 부작용이 없다.
    """
    path = _BACKEND / rel
    module_dir = str(path.parent)
    added = module_dir not in sys.path
    if added:
        sys.path.insert(0, module_dir)
    try:
        module = importlib.import_module(path.stem)
        assert module is not None
    finally:
        if added:
            sys.path.remove(module_dir)


def test_live_call_scripts_do_nothing_without_opt_in() -> None:
    """opt-in 인자가 없으면 외부 호출을 하지 않는다.

    폴백 smoke 는 유료 OpenAI 호출을 한다 — 인자 없이 실행했을 때 호출이 나가면
    CI·개발 환경에서 조용히 비용이 발생한다.
    """
    script = _BACKEND / "scripts" / "smoke_openai_fallback.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=300, cwd=str(_BACKEND),
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert "--confirm-live-call" in result.stdout


def test_gate_script_is_executable() -> None:
    """게이트가 실행 권한을 잃으면 CI 에서 조용히 건너뛸 수 있다."""
    assert _GATE.is_file()
    assert _GATE.stat().st_mode & 0o111, f"{_GATE} 실행 권한 없음"
