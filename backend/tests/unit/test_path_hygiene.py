"""OA-H1 — 사전·감사 경로가 실행 위치에 독립적인가.

리포 루트에서 pytest를 돌렸을 때만 9건이 실패해 **코드 결함으로 오진할 뻔했다**.
측정 스크립트가 cwd에 의존하면 감사 결과 자체를 잘못 해석하게 된다.
"""

from __future__ import annotations

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
#: cwd 의존 경로 패턴 — `Path("dictionaries")` 처럼 상대 문자열로 시작하는 것.
_CWD_RELATIVE = re.compile(
    r'Path\(\s*["\'](?:dictionaries|compiled|var|doc)[/"\']'
)


def _sources():
    for root in (_BACKEND / "tests", _BACKEND / "scripts", _BACKEND / "packages"):
        yield from (p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_cwd_relative_dictionary_paths() -> None:
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue   # 주석 속 예시는 대상이 아니다(이 파일 자신 포함)
            if _CWD_RELATIVE.search(line):
                offenders.append(f"{path.relative_to(_BACKEND)}:{i} {stripped}")
    assert not offenders, (
        "cwd 의존 경로 — `Path(__file__).resolve().parents[N]` 기준으로 바꿀 것:\n"
        + "\n".join(offenders)
    )


def test_audit_scripts_resolve_paths_from_module_file() -> None:
    """감사 스크립트는 모듈 파일 기준으로 리포 경로를 잡는다."""
    for script in (_BACKEND / "scripts").glob("audit_*.py"):
        text = script.read_text(encoding="utf-8")
        if "Path(" not in text:
            continue
        assert "Path(__file__).resolve()" in text, script.name
