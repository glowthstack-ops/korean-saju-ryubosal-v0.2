"""사전(JSON) 검증 스크립트 (v2.2 Phase 1 T1.6, docs/05·07).

사전 원본을 운영에 직접 반영하기 전 거치는 `validate → lint` 단계다(절대 원칙 5).

1. generic: UTF-8/BOM·JSON 파싱·`reviewed: bool` 플래그(검수 워크플로 강제)
2. dict:validate: pydantic 스키마 검증 — 필수 필드, EventKey 유효성, score 범위
   (`saju_engines.dictionaries`, 설계 문서의 zod 역할)
3. dict:lint: 충돌 검사 — relation id 중복 / 기신인데 polarity=positive 류 모순 /
   같은 신호의 상반 이벤트 동시 강유발

사용법:
    python scripts/validate_dictionaries.py [dictionaries_dir]
종료 코드 0=통과, 1=위반.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from saju_engines.dictionaries import lint_dictionaries, validate_dictionaries

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "dictionaries"


@dataclass
class ValidationReport:
    """검증 결과 누적. errors가 비어 있으면 통과."""

    checked: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """위반이 하나도 없으면 True."""
        return not self.errors


def _iter_review_flags(node: object) -> list[bool | None]:
    """JSON 트리에서 'reviewed' 플래그를 수집(사전 항목의 검수 상태 추적)."""
    flags: list[bool | None] = []
    if isinstance(node, dict):
        if "reviewed" in node:
            value = node["reviewed"]
            flags.append(value if isinstance(value, bool) else None)
        for value in node.values():
            flags.extend(_iter_review_flags(value))
    elif isinstance(node, list):
        for item in node:
            flags.extend(_iter_review_flags(item))
    return flags


def validate_file(path: Path) -> list[str]:
    """JSON 사전 파일 한 개를 검증하고 위반 메시지 목록을 반환한다."""
    errors: list[str] = []
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append(f"{path.name}: UTF-8 BOM 금지")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: JSON 파싱 실패 ({exc})")
        return errors
    for flag in _iter_review_flags(data):
        if flag is None:
            errors.append(f"{path.name}: 'reviewed' 플래그는 boolean이어야 함")
            break
    return errors


def validate_dir(directory: Path) -> ValidationReport:
    """디렉토리 하위 모든 *.json 사전을 generic → 스키마 → lint 순으로 검증한다."""
    report = ValidationReport()
    for path in sorted(directory.rglob("*.json")):
        report.checked.append(str(path.relative_to(directory)))
        report.errors.extend(validate_file(path))
    report.errors.extend(validate_dictionaries(directory))  # dict:validate (스키마)
    report.errors.extend(lint_dictionaries(directory))  # dict:lint (충돌)
    return report


def main(argv: list[str]) -> int:
    """엔트리포인트. 위반이 있으면 1, 없으면 0을 반환한다."""
    directory = Path(argv[1]) if len(argv) > 1 else _DEFAULT_DIR
    if not directory.exists():
        print(f"사전 디렉토리 없음: {directory}")
        return 1
    report = validate_dir(directory)
    print(f"검사한 사전 파일: {len(report.checked)}개")
    for err in report.errors:
        print(f"  ✗ {err}")
    if report.ok:
        print("통과: 위반 없음")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
