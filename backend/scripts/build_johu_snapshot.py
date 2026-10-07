"""궁통보감 조후용신표 사전 → 컴파일 스냅샷 (validate → compile, 절대 원칙 5).

검증: 10천간 × 12지지 전 셀 존재, 천간 유효성, stems 비어있지 않음, UTF-8/BOM.
통과 시 compiled/johu_yongsin_v{version}.json 스냅샷을 쓴다(git 추적).

사용법:
    python scripts/build_johu_snapshot.py
종료 코드 0=성공, 1=검증 실패.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_SRC = _BACKEND / "dictionaries" / "johu_yongsin.json"
_COMPILED = _BACKEND / "compiled"

_STEMS = list("甲乙丙丁戊己庚辛壬癸")
_BRANCHES = list("寅卯辰巳午未申酉戌亥子丑")
# 감수 확정 enum(2026-07-13) — cold/heat(한난)·dry/damp(조습)·mixed·neutral.
_AXES = {"cold", "heat", "dry", "damp", "mixed", "neutral"}


# v0.3.0(2026-10-07 C2, 데굴님 결정 A): 천간별 역할 태그. 조후 축 점수는 climate_* 역할만 쓴다.
_ROLES = {
    "climate_warm", "climate_cool", "climate_dry", "climate_moisten",
    "source", "drain", "control", "wealth", "peer", "pair",
}
_RELATIONS = {"priority", "pair", "alternative"}
_TAG_SOURCES = {"override", "mechanical", "reviewed"}
_COLD_HOT = set("亥子丑巳午未")
WARNINGS: list[str] = []


def _validate_needs(stem: str, branch: str, cell: dict) -> list[str]:
    """needs[] 구조 검증(v0.3.0). 한난 월 셀에 climate 역할이 없으면 경고(오류 아님 — 결정 A)."""
    errors: list[str] = []
    needs = cell.get("needs")
    if needs is None:
        return [f"{stem}×{branch}: needs 누락(v0.3.0 필수)"]
    if not isinstance(needs, list) or not needs:
        return [f"{stem}×{branch}: needs 목록 아님/빈 목록"]
    listed = {s for key in ("primary", "secondary") for s in cell.get(key, [])}
    seen: set[str] = set()
    for n in needs:
        if not isinstance(n, dict):
            errors.append(f"{stem}×{branch}: needs 항목 비객체")
            continue
        s = n.get("stem")
        if s not in _STEMS:
            errors.append(f"{stem}×{branch}: needs 무효 천간 {s!r}")
            continue
        if s in seen:
            errors.append(f"{stem}×{branch}: needs 천간 중복 {s}")
        seen.add(s)
        roles = n.get("roles")
        if not isinstance(roles, list) or not roles or not set(roles) <= _ROLES:
            errors.append(f"{stem}×{branch}: {s} roles 무효 {roles!r}")
        if n.get("relation") not in _RELATIONS:
            errors.append(f"{stem}×{branch}: {s} relation 무효 {n.get('relation')!r}")
        if n.get("tag_source") not in _TAG_SOURCES:
            errors.append(f"{stem}×{branch}: {s} tag_source 무효 {n.get('tag_source')!r}")
    if seen != listed:
        errors.append(
            f"{stem}×{branch}: needs 천간 집합 {sorted(seen)} ≠ primary∪secondary {sorted(listed)}"
        )
    if not isinstance(cell.get("conditions", []), list):
        errors.append(f"{stem}×{branch}: conditions 목록 아님")
    if branch in _COLD_HOT and not any(
        isinstance(n, dict) and any(str(r).startswith("climate_") for r in n.get("roles", []))
        for n in needs
    ):
        WARNINGS.append(
            f"{stem}×{branch}: 한난 월인데 climate 역할 천간 없음 — 조후 후보 없음(경고만)"
        )
    return errors


def validate(raw: dict) -> list[str]:
    """조후 사전 v0.2 구조 검증 — 위반 메시지 목록(빈 목록=통과).

    감수 게이트(2026-07-13): 셀마다 primary/secondary/avoid/climate_axis 명시,
    천간 유효성, 축 enum, 120셀 완전성. reviewed 의 의미는 canonical need 검토 한정.
    """
    errors: list[str] = []
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        return ["entries 누락 또는 비객체"]
    for stem in _STEMS:
        row = entries.get(stem)
        if not isinstance(row, dict):
            errors.append(f"{stem}: 행 누락")
            continue
        for branch in _BRANCHES:
            cell = row.get(branch)
            if not isinstance(cell, dict):
                errors.append(f"{stem}×{branch}: 셀 누락/비객체")
                continue
            primary = cell.get("primary")
            if not isinstance(primary, list) or not primary:
                errors.append(f"{stem}×{branch}: primary 누락/빈 목록")
            for key in ("primary", "secondary", "avoid"):
                vals = cell.get(key)
                if not isinstance(vals, list):
                    errors.append(f"{stem}×{branch}: {key} 목록 아님")
                    continue
                for s in vals:
                    if s not in _STEMS:
                        errors.append(f"{stem}×{branch}: {key} 무효 천간 {s!r}")
            if cell.get("climate_axis") not in _AXES:
                errors.append(
                    f"{stem}×{branch}: climate_axis 무효 {cell.get('climate_axis')!r}"
                )
            errors.extend(_validate_needs(stem, branch, cell))
        extra = set(row) - set(_BRANCHES)
        if extra:
            errors.append(f"{stem}: 무효 월지 키 {sorted(extra)}")
    if "version" not in raw:
        errors.append("version 누락")
    return errors


def main() -> int:
    raw_bytes = _SRC.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        print("BOM 발견 — UTF-8(BOM 없음)이어야 한다", file=sys.stderr)
        return 1
    raw = json.loads(raw_bytes.decode("utf-8"))
    errors = validate(raw)
    if errors:
        for e in errors:
            print(f"[error] {e}", file=sys.stderr)
        return 1
    for w in WARNINGS:
        print(f"[warn] {w}", file=sys.stderr)
    out = _COMPILED / f"johu_yongsin_v{raw['version']}.json"
    out.write_text(
        json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"validated 120 cells ({len(WARNINGS)} warnings) → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
