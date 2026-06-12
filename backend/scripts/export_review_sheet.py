"""해석 사전 감수 시트 export 스크립트 (v2.2.1, docs/05 interpretations/).

전문가 감수를 위해 interpretations/ 사전 4종의 핵심 내용과 명리 근거(basis)를
Markdown 표로 추출한다. 감수자는 basis 열을 기준으로 정통 명리(자평) 관점의
정오를 표시하고, 통과 항목은 사전의 `reviewed: true`로 반영한다.

사용법:
    python scripts/export_review_sheet.py [dictionaries_dir] [output.md]
출력 파일 생략 시 표준 출력. 종료 코드 0=성공, 1=사전 로드 실패.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "dictionaries"


def _load(directory: Path, name: str) -> dict:
    """interpretations/ 하위 사전 JSON 한 개를 로드한다."""
    return json.loads((directory / "interpretations" / name).read_text(encoding="utf-8"))


def _cell(text: str, limit: int = 120) -> str:
    """Markdown 표 셀용 정리 — 파이프 이스케이프 + 길이 제한."""
    flat = text.replace("|", "\\|").replace("\n", " ")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def build_sheet(directory: Path) -> str:
    """감수 시트 Markdown 전문을 생성한다."""
    lines: list[str] = ["# 해석 사전 감수 시트 (interpretations/)", ""]

    ilju = _load(directory, "ilju.json")
    lines += [
        f"## 1. 일주 60갑자 (ilju.json v{ilju['version']})",
        "",
        "| 간지 | 동물 | 일지십성 | 십이운성 | 물상(imagery) | 근거(basis) | 검수 |",
        "|---|---|---|---|---|---|---|",
    ]
    for it in ilju["items"]:
        animal = f"{it['animal']['color']}{it['animal']['name']}"
        computed = it["computed"]
        lines.append(
            f"| {it['ganji']} | {animal} | {computed['iljiTenGod']} | "
            f"{computed['twelveStage']} | {_cell(it['imagery'], 60)} | "
            f"{_cell(it['basis'])} | {'✔' if it['reviewed'] else '☐'} |"
        )

    ten_gods = _load(directory, "ten_gods_text.json")
    lines += [
        "",
        f"## 2. 십성 10종 (ten_gods_text.json v{ten_gods['version']})",
        "",
        "| 십성 | 핵심(core) | 운 유입(incoming) | 근거(basis) | 검수 |",
        "|---|---|---|---|---|",
    ]
    for it in ten_gods["items"]:
        lines.append(
            f"| {it['tenGod']} | {_cell(it['core'], 80)} | {_cell(it['incoming'], 80)} | "
            f"{_cell(it['basis'])} | {'✔' if it['reviewed'] else '☐'} |"
        )

    stages = _load(directory, "twelve_stages_text.json")
    lines += [
        "",
        f"## 3. 십이운성 12종 (twelve_stages_text.json v{stages['version']})",
        "",
        "| 운성 | 핵심(core) | 근거(basis) | 검수 |",
        "|---|---|---|---|",
    ]
    for it in stages["items"]:
        lines.append(
            f"| {it['stage']}({it['hanja']}) | {_cell(it['core'], 80)} | "
            f"{_cell(it['basis'])} | {'✔' if it['reviewed'] else '☐'} |"
        )

    relations = _load(directory, "relations_text.json")
    rel_count, rel_version = len(relations["items"]), relations["version"]
    lines += [
        "",
        f"## 4. 관계 해석 {rel_count}종 (relations_text.json v{rel_version})",
        "",
        "| id | 이름 | 구분 | 의미(meaning) | 근거(basis) | 검수 |",
        "|---|---|---|---|---|---|",
    ]
    for it in relations["items"]:
        role = "보조" if it["role"] == "auxiliary" else "핵심"
        lines.append(
            f"| {it['id']} | {it['name']} | {role} | {_cell(it['meaning'], 80)} | "
            f"{_cell(it['basis'])} | {'✔' if it['reviewed'] else '☐'} |"
        )

    names = (
        "ilju.json", "ten_gods_text.json", "twelve_stages_text.json", "relations_text.json",
    )
    total = sum(len(_load(directory, name)["items"]) for name in names)
    reviewed = sum(
        1 for name in names for it in _load(directory, name)["items"] if it["reviewed"]
    )
    lines += ["", f"**검수 현황: {reviewed}/{total} 항목 완료**", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """엔트리포인트 — 시트를 생성해 파일 또는 표준 출력으로 내보낸다."""
    directory = Path(argv[1]) if len(argv) > 1 else _DEFAULT_DIR
    if not (directory / "interpretations").exists():
        print(f"해석 사전 디렉토리 없음: {directory / 'interpretations'}")
        return 1
    sheet = build_sheet(directory)
    if len(argv) > 2:
        Path(argv[2]).write_text(sheet, encoding="utf-8")
        print(f"감수 시트 저장: {argv[2]}")
    else:
        print(sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
