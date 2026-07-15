"""위험 3프로필 노출 단계 baseline — 기계 판독 고정본 (감수 24차, 데굴님 §4).

RISK_PROFILE_BASELINE.md(사람 감수 기록)와 짝을 이루는 JSON 고정본이다. TYP-0
(테스트 타입 부채 정리)는 런타임 동작을 바꾸지 않는 차수이므로, 전후 profile
baseline은 허용 오차가 아니라 **완전 일치**가 원칙 — --check가 이를 기계 강제한다.

비교 규칙: meta.generated_at / meta.baseline_commit(기록 시점 정보)만 제외하고
전 키 exact match. env·해시 스키마·사전 해시·프로필 컨텍스트 해시가 다르면
지표가 같아도 실패한다(다른 상태의 baseline과 비교하는 실수 차단).

실행: python scripts/risk_profile_baseline.py --write | --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))
sys.path.insert(0, str(_BACKEND / "scripts"))

from risk_shadow_density import (  # noqa: E402
    _CORPUS,
    _DICTS,
    _LEVELS,
    _build_exposure_profiles,
    collect_profile_metrics,
)
from saju_engines.dictionaries import (  # noqa: E402
    _RISK_HASH_SCHEMA_VERSION,
    RISK_REVIEW_ENVIRONMENT_VERSION,
)

_BASELINE_PATH = _BACKEND.parent / "doc" / "v2_2" / "RISK_PROFILE_BASELINE.json"
# 기록 시점 정보 — 지표 불변 비교에서 제외되는 유일한 키들.
_RECORDING_ONLY_META = ("generated_at", "baseline_commit")


def _dictionary_hash() -> str:
    """risks/*.json 전체 바이트 해시 — suppression baseline과 동일 규격."""
    return hashlib.sha256(b"".join(
        path.read_bytes() for path in sorted((_DICTS / "risks").glob("*.json"))
    )).hexdigest()[:16]


def _profile_context_hash() -> str:
    """3프로필 컨텍스트 정의의 결정적 해시 — 프로필 구성 변경 감지.

    frozen dataclass repr은 필드 순서 고정이라 결정적이다. 프로필을 바꾸면
    baseline과의 비교가 무의미하므로 해시 불일치로 즉시 실패시킨다.
    """
    canonical = repr([
        (name, sorted((k, repr(v)) for k, v in ctxs.items()))
        for name, ctxs in _build_exposure_profiles()
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_payload() -> dict:
    """현재 상태의 3프로필 baseline payload를 결정적으로 산출한다."""
    levels = {_LEVELS["year"], _LEVELS["month"]}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, cwd=_BACKEND.parent,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        commit = "unknown"
    profiles = collect_profile_metrics(levels, _CORPUS)
    return {
        "meta": {
            "baseline_commit": commit,
            "review_environment_version": RISK_REVIEW_ENVIRONMENT_VERSION,
            "hash_schema_version": _RISK_HASH_SCHEMA_VERSION,
            "dictionary_hash": _dictionary_hash(),
            "corpus_version": "seoul-busan-10 (year+month)",
            "profile_context_hash": _profile_context_hash(),
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        "profiles": profiles,
    }


def _comparable(payload: dict) -> dict:
    """기록 시점 키를 제외한 비교 대상 뷰."""
    meta = {k: v for k, v in payload["meta"].items()
            if k not in _RECORDING_ONLY_META}
    return {"meta": meta, "profiles": payload["profiles"]}


def _diff_keys(base: dict, cur: dict, prefix: str = "") -> list[str]:
    """중첩 dict의 불일치 경로 목록(결정적 정렬)."""
    out: list[str] = []
    for key in sorted(set(base) | set(cur)):
        path = f"{prefix}.{key}" if prefix else str(key)
        b, c = base.get(key), cur.get(key)
        if isinstance(b, dict) and isinstance(c, dict):
            out.extend(_diff_keys(b, c, path))
        elif b != c:
            out.append(f"{path}: {b!r} → {c!r}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="baseline 기록(승인 후)")
    mode.add_argument("--check", action="store_true",
                      help="완전 일치 검사(TYP-0 전후 게이트)")
    args = parser.parse_args()
    current = build_payload()
    if args.write:
        _BASELINE_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"profile baseline 기록: {_BASELINE_PATH}")
        return 0
    if not _BASELINE_PATH.exists():
        print("baseline 없음 — 먼저 --write로 기록")
        return 1
    stored = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    print(f"baseline meta: {stored['meta']}")
    diffs = _diff_keys(_comparable(stored), _comparable(current))
    if not diffs:
        print("profile baseline 완전 일치 (exact match)")
        return 0
    print(f"불일치 {len(diffs)}건:")
    for d in diffs:
        print(f"  - {d}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
