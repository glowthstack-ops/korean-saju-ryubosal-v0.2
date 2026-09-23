"""사전 원본 지문(fingerprint) — 리포트·부록에 찍는 '사전 버전'의 실값.

`ReportBuilder(dict_version=...)` 기본값 "1.0.0" 이 한 번도 갱신되지 않은 채 모든 리포트에
찍히고 있었다(2026-09-10 사문 감사). 수동 버전 상수는 또 정체되므로, 사전 디렉터리의
JSON 내용 해시를 짧게 잘라 버전 문자열로 쓴다 — 사전이 바뀌면 값이 바뀌고, 같은 사전이면
어디서 만들어도 같다(결정론).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
#: 지문 길이(hex) — 충돌 우려보다 표지 가독성이 우선.
_FINGERPRINT_LEN = 12


@lru_cache(maxsize=8)
def dictionaries_fingerprint(dictionaries_dir: Path = _DICTS_DEFAULT) -> str:
    """사전 디렉터리(재귀) JSON·JSONL 전체의 sha256 앞 12자리.

    Args:
        dictionaries_dir: 사전 원본 루트.

    Returns:
        예: ``"3f9a1c0b7d2e"``. 디렉터리가 없거나 파일이 없으면 ``"none"``.
    """
    root = Path(dictionaries_dir)
    if not root.is_dir():
        return "none"
    h = hashlib.sha256()
    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl")
    )
    if not files:
        return "none"
    for path in files:
        h.update(str(path.relative_to(root)).encode("utf-8"))
        h.update(b"\\0")
        h.update(path.read_bytes())
        h.update(b"\\0")
    return h.hexdigest()[:_FINGERPRINT_LEN]


def report_dict_version(dictionaries_dir: Path = _DICTS_DEFAULT) -> str:
    """리포트 표지용 사전 버전 문자열 — ``dict-<지문>``."""
    return f"dict-{dictionaries_fingerprint(Path(dictionaries_dir))}"
