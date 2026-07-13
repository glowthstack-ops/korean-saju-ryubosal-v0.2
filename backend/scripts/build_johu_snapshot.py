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
    out = _COMPILED / f"johu_yongsin_v{raw['version']}.json"
    out.write_text(
        json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"validated 120 cells → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
