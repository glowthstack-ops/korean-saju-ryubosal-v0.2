"""오행 보완 방향 첨언(用喜忌仇閑 길방) — 수동 방향 질문 전용(2026-09-22 데굴님 승인).

12신살 방위 활용(docs/18)은 '신살 × 목적' 모델이고, 이 모듈은 **용희기구한 역할 × 정오행 방위**
모델이다. 두 층은 서로 다른 질문이라 합산·상쇄하지 않는다(docs/18 §1-5) — 답에서는 12신살 답
뒤에 '오행 보완 방향' 첨언 한 문단으로만 병기한다.

- 방위 사전 = `calendar/direction_rules.json`(8방위, 택일·이사 경로와 같은 SSOT, `reviewed: false`
  통설 초안 — 데굴님 결정으로 그대로 사용).
- 역할 출처 = `event_scoring.favorability_map`(엔진 도출) 또는 사용자 확정 용신 override.
- 기신·구신 방위는 '피함'이 아니라 '보완 효과 없음 — 오래 머무는 자리로는 삼가'로 완화한다.
  12신살의 '주의(목적 충돌)'와 회피 목록이 둘이 되지 않게 하기 위해서다.
- 서술 전용(inert): 점수·판정·날짜·간지 불변. 순수 함수 `(favorability, asked, dict) -> note`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from saju_shared_types.sinsal_direction import YongsinDirectionEntry, YongsinDirectionNote

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

#: 역할 표기 순서(용→희→한→기→구)와 첨언 톤. '피함' 어휘를 쓰지 않는다(완화 정책).
ROLE_ORDER: tuple[str, ...] = ("용신", "희신", "한신", "기신", "구신")
ROLE_TONE: dict[str, str] = {
    "용신": "보완 방향·우선",
    "희신": "보완 방향·보조",
    "한신": "무난",
    "기신": "보완 효과 없음 — 오래 머무는 자리로는 삼가",
    "구신": "보완 효과 없음 — 오래 머무는 자리로는 삼가",
}

#: 질문 방향 코드(16방위) → 8방위 한글. 정방·간방은 1개, 그 사이(북북동 등)는 인접 8방위 2개.
_ASKED_TO_DIR8: dict[str, tuple[str, ...]] = {
    "N": ("북",), "NNE": ("북", "북동"), "NE": ("북동",), "ENE": ("북동", "동"),
    "E": ("동",), "ESE": ("동", "남동"), "SE": ("남동",), "SSE": ("남동", "남"),
    "S": ("남",), "SSW": ("남", "남서"), "SW": ("남서",), "WSW": ("남서", "서"),
    "W": ("서",), "WNW": ("서", "북서"), "NW": ("북서",), "NNW": ("북서", "북"),
}
_ASKED_KO: dict[str, str] = {
    "N": "북", "NNE": "북북동", "NE": "북동", "ENE": "동북동", "E": "동", "ESE": "동남동",
    "SE": "남동", "SSE": "남남동", "S": "남", "SSW": "남남서", "SW": "남서", "WSW": "서남서",
    "W": "서", "WNW": "서북서", "NW": "북서", "NNW": "북북서",
}


@lru_cache(maxsize=4)
def load_direction_rules(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, list[str]]:
    """`calendar/direction_rules.json` → {오행(한자): [8방위 한글…]} (사전 순서 보존)."""
    raw = json.loads((dictionaries_dir / "calendar" / "direction_rules.json").read_text("utf-8"))
    return {item["element"]: list(item["directions"]) for item in raw["items"]}


def build_yongsin_direction_note(
    favorability: dict[str, str],
    asked_code: str | None = None,
    *,
    confirmed: bool = False,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> YongsinDirectionNote | None:
    """용희기구한 {오행: 역할} → 오행 보완 방향 첨언. 역할이 비어 있으면(용신 미도출) None.

    Args:
        favorability: `favorability_map` 포맷({'土': '용신', …}). 사용자 확정 override 가능.
        asked_code: 질문한 방향 16방위 코드(`IntentJson.direction_asked`) — 있으면 그 방향의
            오행·역할 줄을 함께 만든다.
        confirmed: True 면 출처를 '사용자 확정 용신'으로 표시한다.
    """
    if not favorability:
        return None
    rules = load_direction_rules(dictionaries_dir)
    by_role = {role: el for el, role in favorability.items()}
    entries = [
        YongsinDirectionEntry(
            role=role, element=by_role[role], directions=rules.get(by_role[role], []),
            tone=ROLE_TONE[role],
        )
        for role in ROLE_ORDER
        if role in by_role
    ]
    if not entries:
        return None
    asked_entries: list[YongsinDirectionEntry] = []
    asked_ko: str | None = None
    if asked_code in _ASKED_TO_DIR8:
        asked_ko = _ASKED_KO[asked_code]
        dir_to_element = {d: el for el, dirs in rules.items() for d in dirs}
        for d in _ASKED_TO_DIR8[asked_code]:
            el = dir_to_element.get(d)
            if el is None:
                continue
            role = favorability.get(el, "한신")
            asked_entries.append(YongsinDirectionEntry(
                role=role, element=el, directions=[d], tone=ROLE_TONE.get(role, "무난"),
            ))
    return YongsinDirectionNote(
        entries=entries, source="confirmed" if confirmed else "engine",
        asked_direction_ko=asked_ko, asked_entries=asked_entries,
    )


def format_yongsin_direction_lines(note: YongsinDirectionNote | None) -> list[str]:
    """LLM 입력 직렬화 — 빈 블록이면 헤더도 내지 않는다(무소음)."""
    if note is None or not note.entries:
        return []
    src = "사용자 확정 용신" if note.source == "confirmed" else "엔진 도출 용신"
    lines = [
        "",
        f"[오행 보완 방향 — 용희기구한 기준(첨언, 12신살 활용 방향과 별개 · {src})]",
    ]
    for e in note.entries:
        dirs = "·".join(e.directions) if e.directions else "해당 방위 없음"
        lines.append(f"- {e.role} {e.element} → {dirs} ({e.tone})")
    if note.asked_direction_ko is not None and note.asked_entries:
        parts = " / ".join(
            f"{a.directions[0]} {a.element}({a.role}) — {a.tone}" for a in note.asked_entries
        )
        prefix = "" if len(note.asked_entries) == 1 else "인접 8방위 기준 "
        lines.append(f"- 질문한 방향 '{note.asked_direction_ko}' = {prefix}{parts}")
    return lines


YONGSIN_DIRECTION_INSTRUCTION = (
    "[오행 보완 방향 지침] 위 [오행 보완 방향] 블록은 용희기구한 오행을 정오행 방위에 "
    "대응한 '보완 방향' 자료이며 12신살 활용 방향과는 **다른 층**이다. "
    "①답의 본체([기본 방향]·[상황별 조언]·[피할 방향])는 12신살 블록으로 쓰고, 이 블록은 "
    "그 뒤에 '오행으로 보면 …' 첨언 한 문단으로만 덧붙일 것. "
    "②두 층을 합산·상쇄하지 말 것 — '용신 방향이니 그 목적의 주의를 무시해도 된다', "
    "'기신 방향이니 적극 활용 방향도 피하라'는 서술 금지. 다르게 나오면 '활용 방향'과 "
    "'오행 보완 방향'을 그대로 분리해 병기한다. "
    "③어휘: 용신·희신 방위는 '보완 방향', 한신은 '무난', 기신·구신은 '보완 효과가 없어 "
    "오래 머무는 자리로는 삼가는 편' — '피해야 할 방향'·'흉방'·'나쁜 방향' 표현 금지. "
    "④질문한 방향 줄이 있으면 그 방향의 오행·역할을 한 문장으로 짚을 것. "
    "⑤'이 방향이면 운이 풀린다' 류 단정 금지 — '보완해 볼 수 있다' 톤."
)
