"""오행 보완 색 첨언(用喜忌仇閑 × 오행 정색) — 색 질문 턴 전용(2026-10-01 데굴님 승인).

`yongsin_direction`(용희기구한 × 정오행 방위)과 같은 모델의 색 판이다. 실로그(커튼 색)에서 엔진은
`용신 火 · 기신 木`을 줬지만 색 후보표가 없어 LLM이 '목이 화를 생하니 연두·초록도 좋다'는 상생
연쇄로 기신 색을 추천했고, 다음 턴에 같은 정보로 번복했다. 추천 정책의 빈칸을 LLM이 임의 명리
논리로 채우지 않도록, 엔진이 역할별 색 후보와 톤을 모두 제시한다.

- 색 사전 = `calendar/color_rules.json`(정색 5 + 계열, reviewed:false 통설 초안). 사전에 없는 색
  (보라·파랑 등)은 임의 배정하지 않고 '오행 배정 보류'로 표기한다.
- 역할 출처 = `event_scoring.favorability_map`(엔진 도출) 또는 사용자 확정 용신 override.
- 기신·구신 색은 '피함'이 아니라 '보완 효과 없음 — 넓은 면적으로는 삼가'로 완화한다(방향 첨언과
  같은 완화 정책, 회피 목록 이중화 방지).
- 효과 단정 금지: 색은 선택의 가벼운 기준이지 집중력·실행력을 바꾸는 원인이 아니다.
- 서술 전용(inert): 점수·판정·날짜·간지 불변. 순수 함수 `(favorability, asked, dict) -> note`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from saju_shared_types.sinsal_direction import YongsinColorEntry, YongsinColorNote

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

ROLE_ORDER: tuple[str, ...] = ("용신", "희신", "한신", "기신", "구신")
ROLE_TONE: dict[str, str] = {
    "용신": "보완 색·우선",
    "희신": "보완 색·보조",
    "한신": "무난",
    "기신": "보완 효과 없음 — 넓은 면적(커튼·벽지·침구)으로는 삼가",
    "구신": "보완 효과 없음 — 넓은 면적(커튼·벽지·침구)으로는 삼가",
}

# 색 질문 표지 — 색 자체를 묻거나 색이 들어가는 생활 선택(커튼·벽지·소품·옷·차)을 묻는 발화.
_COLOR_QUESTION_RE = re.compile(
    r"색(?:깔|상)?(?:이|은|을|으로|도|만|이나|과|와)?(?![가-힣])|컬러|무슨\s*색|어떤\s*색"
    r"|커[튼텐]|벽지|인테리어|이불|침구|옷\s*색|차\s*색|지갑\s*색"
)


@lru_cache(maxsize=4)
def _load_rules(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict:
    return json.loads((dictionaries_dir / "calendar" / "color_rules.json").read_text("utf-8"))


def load_color_rules(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, list[str]]:
    """`calendar/color_rules.json` → {오행(한자): [색 한글…]} (사전 순서 보존)."""
    return {
        item["element"]: list(item["colors"]) for item in _load_rules(dictionaries_dir)["items"]
    }


@lru_cache(maxsize=4)
def _color_lexicon(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str | None]:
    """색 어휘 → 오행(한자) | None(보류 큐). 긴 어휘가 먼저 매칭되도록 호출부가 정렬한다."""
    raw = _load_rules(dictionaries_dir)
    lex: dict[str, str | None] = {}
    for item in raw["items"]:
        for c in item["colors"]:
            lex[c] = item["element"]
    for word, el in raw.get("aliases", {}).items():
        lex.setdefault(word, el)
    for word in raw.get("unmapped_review_queue", []):
        lex.setdefault(word, None)
    return lex


def color_element_of(word: str, dictionaries_dir: Path = _DICTS_DEFAULT) -> str | None:
    """색 어휘 1개 → 오행(한자). 사전에 없거나 보류 큐면 None.

    시스템 발언 원장의 토큰 정규화에 공용.
    """
    if len(word) < 2:
        return None
    return _color_lexicon(dictionaries_dir).get(word)


def is_color_question(text: str) -> bool:
    """색 질문 표지가 있으면 True(라우팅 불변 — 블록만 더한다)."""
    return bool(_COLOR_QUESTION_RE.search(text))


def detect_asked_colors(text: str, dictionaries_dir: Path = _DICTS_DEFAULT) -> list[str]:
    """발화에서 지목된 색 어휘(사전 키, 등장 순) — 긴 어휘 우선('초록색'이 '초록'을 가린다)."""
    lex = _color_lexicon(dictionaries_dir)
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for word in sorted(lex, key=len, reverse=True):
        if len(word) < 2 and word not in ("청", "적", "황", "백", "흑"):
            continue
        for m in re.finditer(re.escape(word), text):
            span = (m.start(), m.end())
            if any(s <= span[0] < e or s < span[1] <= e for s, e in taken):
                continue
            # 1글자 정색 약어('청·적·황·백·흑')는 '색'이 바로 뒤에 올 때만 색으로 본다.
            if len(word) == 1 and not text[m.end(): m.end() + 1] == "색":
                continue
            taken.append(span)
            found.append((m.start(), word))
    found.sort()
    out: list[str] = []
    for _, w in found:
        if w not in out:
            out.append(w)
    return out


def build_yongsin_color_note(
    favorability: dict[str, str],
    asked_colors: list[str] | None = None,
    *,
    confirmed: bool = False,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> YongsinColorNote | None:
    """용희기구한 {오행: 역할} → 오행 보완 색 첨언. 역할이 비어 있으면(용신 미도출) None.

    Args:
        favorability: `favorability_map` 포맷({'火': '용신', …}). 사용자 확정 override 가능.
        asked_colors: 사용자가 지목한 색 어휘 — 사전에 있으면 오행·역할 줄, 없으면 보류 목록.
        confirmed: True 면 출처를 '사용자 확정 용신'으로 표시한다.
    """
    if not favorability:
        return None
    rules = load_color_rules(dictionaries_dir)
    by_role = {role: el for el, role in favorability.items()}
    entries = [
        YongsinColorEntry(
            role=role, element=by_role[role], colors=rules.get(by_role[role], []),
            tone=ROLE_TONE[role],
        )
        for role in ROLE_ORDER
        if role in by_role
    ]
    if not entries:
        return None
    lex = _color_lexicon(dictionaries_dir)
    asked_entries: list[YongsinColorEntry] = []
    unmapped: list[str] = []
    for word in asked_colors or []:
        el = lex.get(word)
        if el is None:
            if word not in unmapped:
                unmapped.append(word)
            continue
        role = favorability.get(el, "한신")
        asked_entries.append(YongsinColorEntry(
            role=role, element=el, colors=[word], tone=ROLE_TONE.get(role, "무난"),
        ))
    return YongsinColorNote(
        entries=entries, source="confirmed" if confirmed else "engine",
        asked_entries=asked_entries, unmapped_colors=unmapped,
    )


def format_yongsin_color_lines(note: YongsinColorNote | None) -> list[str]:
    """LLM 입력 직렬화 — 빈 블록이면 헤더도 내지 않는다(무소음)."""
    if note is None or not note.entries:
        return []
    src = "사용자 확정 용신" if note.source == "confirmed" else "엔진 도출 용신"
    lines = ["", f"[오행 보완 색 — 용희기구한 기준(첨언 · {src}) — 색 후보는 이 표에서만 고를 것]"]
    for e in note.entries:
        cols = "·".join(e.colors) if e.colors else "해당 색 없음"
        lines.append(f"- {e.role} {e.element} → {cols} ({e.tone})")
    for a in note.asked_entries:
        lines.append(f"- 지목한 색 '{a.colors[0]}' = {a.element}({a.role}) — {a.tone}")
    if note.unmapped_colors:
        lines.append(
            "- 지목한 색 " + "·".join(f"'{c}'" for c in note.unmapped_colors)
            + " = 오행 배정 보류(사전 미등재) — 오행을 임의로 배정하지 말고 "
            + "'통설이 갈려 보류'로 안내"
        )
    return lines


YONGSIN_COLOR_INSTRUCTION = (
    "[오행 보완 색 지침] 색 추천·판정은 위 [오행 보완 색] 표의 역할·톤을 그대로 따를 것. "
    "①상생 연쇄로 후보를 늘리지 말 것 — '목이 화를 생하니 녹색도 좋다'처럼 기신·구신 오행의 색을 "
    "용신을 돕는 색으로 끌어오는 것은 금지. ②기신·구신 색은 '피하라'가 아니라 '보완 효과 없음 — "
    "넓은 면적으로는 삼가' 수준으로 완화해 말할 것. ③색은 선택의 가벼운 기준이지 원인이 아니다 — "
    "'이 색 때문에 잡생각이 늘어난다/실행력이 떨어진다'처럼 색이 심리·성과를 직접 바꾼다는 인과 "
    "단정은 금지(전통 상징으로 설명). ④사용자가 배제한 색([사용자 제공 정보]의 배제 조건)은 "
    "대안으로 "
    "다시 내밀지 말 것. ⑤사전에 없는 색은 오행을 지어내지 말고 보류로 안내할 것. "
    "⑥용신 색 일변도 금지(2026-10-01 데굴님 지적) — 용신 색(우선)과 희신 색(보조)을 함께 제시하고, "
    "용신 색이 배제됐거나 부담스럽다면 **희신 색이 1차 대안**이다(기신 색을 상생 논리로 끌어오지 "
    "말고). 한신 색은 '무난한 중립 선택'으로 덧붙일 수 있다."
)
