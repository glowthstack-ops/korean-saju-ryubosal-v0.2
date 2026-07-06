"""해석 사전 감수 시트 export 스크립트 (v2.2.1, docs/05 interpretations/).

전문가 감수를 위해 interpretations/ 사전의 핵심 내용과 명리 근거(basis)를
Markdown 표로 추출한다. 감수자는 basis 열을 기준으로 정통 명리(자평) 관점의
정오를 표시하고, 통과 항목은 사전의 `reviewed: true`로 반영한다.

§5~7은 상담 사례 트랙(CAL-P0/P1) 파생 사전 — 명리 규칙이 아니라 **사용자 노출 문구**
감수다(R-1 기준: 결핍≠결함, 오행/십성 길흉 단정 금지, 자기비난 유발 금지, 전문용어
과다 금지, A/B 쌍이 정적 체감과 운 작동을 실제로 분리해서 묻는가).

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

    # ── §5~7 상담 사례 트랙(CAL-P0/P1) 파생 사전 — 사용자 노출 문구 감수(R-1). ──
    pairs = _load(directory, "deficiency_pair_questions.json")
    lines += [
        "",
        f"## 5. 이원 질문 쌍 10축 (deficiency_pair_questions.json v{pairs['version']})",
        "",
        "감수 기준(R-1): ①결핍을 결함처럼 표현 금지 ②오행/십성 길흉 단정 금지 "
        "③자기비난 유발 금지 ④전문용어 과다 금지 ⑤A/B가 정적 체감·운 작동을 분리해서 묻는가.",
        "",
        "| 축 | A. 평소 체감(static) | B. 해당 시기 체감(transit) | 검수 |",
        "|---|---|---|---|",
    ]
    for it in pairs["entries"]:
        lines.append(
            f"| {it['korean']}({it['axis_type']}) | {_cell(it['static_question'], 90)} | "
            f"{_cell(it['transit_question'], 90)} | {'✔' if it['reviewed'] else '☐'} |"
        )

    keywords = _load(directory, "activity_keyword_map.json")
    lines += [
        "",
        f"## 6. 활동 키워드 번역 (activity_keyword_map.json v{keywords['version']})",
        "",
        "| 축 | 활동 키워드 | 주의(caution)/안전규칙 | 검수 |",
        "|---|---|---|---|",
    ]
    for it in keywords["entries"]:
        caution = it.get("caution") or it.get("safe_rule") or ""
        lines.append(
            f"| {it['korean']} | {_cell(', '.join(it['activity_keywords']), 80)} | "
            f"{_cell(caution, 70)} | {'✔' if it['reviewed'] else '☐'} |"
        )

    remedy = _load(directory, "remedy_action_map.json")
    lines += [
        "",
        f"## 7. 개운 행동(오행 보완) (remedy_action_map.json v{remedy['version']})",
        "",
        "| 오행 | 보완 필요(core_need) | 권장 행동 | 피할 것 | 검수 |",
        "|---|---|---|---|---|",
    ]
    remedy_actions = remedy["element_actions"]
    for key, it in remedy_actions.items():
        lines.append(
            f"| {key} | {_cell(it['core_need'], 40)} | "
            f"{_cell(', '.join(it['recommended_actions']), 70)} | "
            f"{_cell(', '.join(it.get('avoid', [])), 50)} | "
            f"{'✔' if it['reviewed'] else '☐'} |"
        )

    names = (
        "ilju.json", "ten_gods_text.json", "twelve_stages_text.json", "relations_text.json",
    )
    total = sum(len(_load(directory, name)["items"]) for name in names)
    reviewed = sum(
        1 for name in names for it in _load(directory, name)["items"] if it["reviewed"]
    )
    case_items = [*pairs["entries"], *keywords["entries"], *remedy_actions.values()]
    total += len(case_items)
    reviewed += sum(1 for it in case_items if it["reviewed"])
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
