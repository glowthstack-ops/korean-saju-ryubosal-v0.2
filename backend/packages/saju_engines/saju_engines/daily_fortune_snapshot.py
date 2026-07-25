"""오늘의 운세 사전 — validate → compile(snapshot) 파이프라인 (CLAUDE.md 원칙 5).

`daily_fortune` 사전 3종은 이미 사용자에게 서비스되고 있으면서도 컴파일 스냅샷 단계를
거치지 않았다. 그래서 두 가지 구멍이 있었다:

1. **캐시 오염** — 사전을 고치고 `DICT_VERSION`(캐시 키의 일부)을 올리지 않으면, 이미
   생성된 보드가 옛 문구를 계속 서비스한다. 이를 잡는 장치가 없었다.
2. **검수 상태 불명** — 3종 중 `daily_event_catalog.json` 만 `reviewed` 를 선언했고
   나머지는 미선언이라, 검증 스크립트가 "boolean 이 아님"만 잡고 **미선언은 통과**시켰다.

본 모듈은 `structure_patterns` 와 같은 규약으로 그 단계를 채운다 — 원본 digest 를 스냅샷에
고정하고, 런타임은 스냅샷을 우선 로드하며, 회귀가 동기 상태를 강제한다.

**구조 검증과 명리 감수는 분리한다.** 스냅샷의 `structural_validation` 은 파이프라인이
보장하는 기계적 검증(스키마·커버리지·금지어)이고, 각 원본의 `reviewed` 는 **사람의 명리
감수** 여부다. 전자가 통과했다고 후자가 참이 되지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries" / "daily_fortune"
_COMPILED_DEFAULT = Path(__file__).resolve().parents[3] / "compiled"

#: 스냅샷에 담기는 원본 3종 — (파일명, 스냅샷 키).
SOURCES: tuple[tuple[str, str], ...] = (
    ("daily_event_catalog.json", "catalog"),
    ("daily_phrase_templates.json", "templates"),
    ("daily_lucky_places.json", "places"),
)


def source_digest(path: Path) -> str:
    """원본 파일 1개의 sha256 — 바이트 그대로 해싱한다(정규화 없음)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digests(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str]:
    """원본 3종의 digest 표 — 스냅샷 동기 여부 판정의 기준."""
    return {name: source_digest(dictionaries_dir / name) for name, _ in SOURCES}


def snapshot_path(dict_version: str, compiled_dir: Path = _COMPILED_DEFAULT) -> Path:
    """`DICT_VERSION` 에 대응하는 스냅샷 경로.

    파일명에 버전을 넣어, 버전을 올리지 않은 사전 수정은 **스냅샷 부재**로 드러난다.
    """
    return compiled_dir / f"daily_fortune_{dict_version}.json"


def validate_sources(dictionaries_dir: Path = _DICTS_DEFAULT) -> list[str]:
    """컴파일 전 검증 — 위반 메시지 목록(비어 있으면 통과).

    깊은 스키마·커버리지·금지어 검사는 `tests/unit/test_daily_fortune_dicts.py` 가
    전담한다. 여기서는 **컴파일 가능 여부와 검수 상태 선언**만 강제한다 — 미선언을
    통과시키면 감수 워크플로가 무의미해지기 때문이다.

    Args:
        dictionaries_dir: 원본 사전 디렉터리.

    Returns:
        위반 메시지 목록.
    """
    errors: list[str] = []
    for name, _key in SOURCES:
        path = dictionaries_dir / name
        if not path.exists():
            errors.append(f"{name}: 원본 없음")
            continue
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            errors.append(f"{name}: UTF-8 BOM 금지")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: JSON 파싱 실패 ({exc})")
            continue
        if not isinstance(data, dict):
            errors.append(f"{name}: 최상위는 object 여야 함")
            continue
        if "reviewed" not in data:
            errors.append(f"{name}: 'reviewed'(명리 감수 여부) 미선언 — 서비스 사전은 선언 필수")
        elif not isinstance(data["reviewed"], bool):
            errors.append(f"{name}: 'reviewed' 는 boolean 이어야 함")
        if "version" not in data:
            errors.append(f"{name}: 'version' 미선언")
    return errors


def build_snapshot(
    dict_version: str,
    dictionaries_dir: Path = _DICTS_DEFAULT,
    compiled_at: str = "",
) -> dict[str, Any]:
    """검증된 원본 3종을 하나의 스냅샷 dict 로 컴파일한다.

    Args:
        dict_version: 이 스냅샷이 대응하는 `DICT_VERSION`.
        dictionaries_dir: 원본 사전 디렉터리.
        compiled_at: 컴파일 시각(ISO). 호출자가 주입한다(결정론 유지).

    Returns:
        스냅샷 dict.

    Raises:
        ValueError: 검증 위반이 있을 때(검증 실패분은 컴파일하지 않는다).
    """
    errors = validate_sources(dictionaries_dir)
    if errors:
        raise ValueError("사전 검증 실패: " + " / ".join(errors))
    payload: dict[str, Any] = {
        "dict_version": dict_version,
        "compiled_at": compiled_at,
        # 파이프라인이 보장하는 기계적 검증. 명리 감수(reviewed)와 별개다.
        "structural_validation": "passed",
        "sources": {},
    }
    for name, key in SOURCES:
        path = dictionaries_dir / name
        data = json.loads(path.read_text(encoding="utf-8"))
        payload["sources"][name] = {
            "sha256": source_digest(path),
            "version": data.get("version"),
            # 사람 감수 여부 — 파이프라인이 참으로 바꾸지 않는다.
            "reviewed": data.get("reviewed"),
        }
        payload[key] = data
    return payload


def load_snapshot(
    dict_version: str, compiled_dir: Path = _COMPILED_DEFAULT
) -> dict[str, Any] | None:
    """스냅샷을 읽는다 — 없으면 None(호출자가 원본으로 폴백)."""
    path = snapshot_path(dict_version, compiled_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "SOURCES",
    "build_snapshot",
    "load_snapshot",
    "snapshot_path",
    "source_digest",
    "source_digests",
    "validate_sources",
]
