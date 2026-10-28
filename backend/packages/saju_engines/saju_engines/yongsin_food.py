"""오행 보완 음식 첨언(用喜忌仇閑 × 五味·식재료 계열) — 음식 질문 턴 전용(2026-10-28 데굴님 승인).

`yongsin_color`(용희기구한 × 정색)와 같은 모델의 음식 판이다. 실로그("오늘 점심은 뭘 먹는게 좋을까")
에서 파서는 음식 어휘를 어떤 신호로도 만들지 못해 '오늘'만 남아 일운 5영역 총운으로 답했고 점심은
한 글자도 없었다. docs/03 Q10("맞는 음식")·docs/08 D2-4·D-3 5번(오행 생활화: 색/방향/음식)이 전부
음식을 규격으로 올려 두었으나 색·방향만 구현돼 있던 빈칸을 채운다.

- 음식 사전 = `calendar/food_rules.json`(오행 × 五味·색·식재료·끼니 예시, reviewed:false 통설 초안).
  사전에 없는 음식·복합 요리(김치찌개 등)는 임의 배정하지 않고 '오행 배정 보류'로 표기한다.
- 역할 출처 = `event_scoring.favorability_map`(엔진 도출) 또는 사용자 확정 용신 override.
- 기신·구신 음식은 '피함'이 아니라 '보완 효과 없음 — 주식으로 몰아 먹지는 말기'로 완화한다
  (색·방향 첨언과 같은 완화 정책, 회피 목록 이중화 방지).
- 효과 단정 금지: 음식은 선택의 가벼운 기준이지 운·성과·건강을 바꾸는 원인이 아니다. 영양·의료
  조언이 아니다(remedy.json disclaimers.health 와 같은 선).
- 라우팅: 색과 달리 음식 질문은 도메인어가 없으면 Q1 총운 폴백으로 떨어져 답 전체가 어긋나므로,
  **룰이 Q1(FORTUNE_OVERVIEW)로 폴백한 경우에만** Q10 REMEDY 로 승격한다(query_parser). 룰이 확정한
  다른 유형(건강 분석·택일·비교 등)은 그대로 두고 블록만 더한다.
- 서술 전용(inert): 점수·판정·날짜·간지 불변. 순수 함수 `(favorability, asked, dict) -> note`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from saju_shared_types.sinsal_direction import YongsinFoodEntry, YongsinFoodNote

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"

ROLE_ORDER: tuple[str, ...] = ("용신", "희신", "한신", "기신", "구신")
ROLE_TONE: dict[str, str] = {
    "용신": "보완 음식·우선",
    "희신": "보완 음식·보조",
    "한신": "무난",
    "기신": "보완 효과 없음 — 주식(主食)으로 몰아 먹지는 말기 정도(금지 아님)",
    "구신": "보완 효과 없음 — 주식(主食)으로 몰아 먹지는 말기 정도(금지 아님)",
}

# 음식 질문 표지 — 끼니·메뉴·음식 자체를 묻거나 '뭘 먹을까' 류 선택을 묻는 발화.
# '점심 약속'·'저녁 미팅'은 일정이고, '약 먹어도'는 건강 행위이며, '해먹고 살'은 생계 관용구다.
_FOOD_QUESTION_RE = re.compile(
    r"음식|식사|메뉴|식단|야식|간식|반찬|요리|맛집|도시락"
    r"|(?:점심|저녁|아침|조식|중식|석식)(?:은|엔|에|으로|밥은|밥|때)?\s*(?:뭘|뭐|무엇|어떤|무슨)?\s*(?:먹|메뉴|고르|추천|좋)"
    r"|(?:뭘|뭐를|뭐|무엇을|무엇|어떤\s*걸?|무슨\s*걸?)\s*먹"
    r"|먹(?:으면|는\s*게|는\s*것|을\s*(?:거|것|까|지|만한)|어도|어야|자|을까)"
)
_FOOD_EXCLUDE_RE = re.compile(
    r"(?:점심|저녁|아침)\s*(?:약속|미팅|회의|모임|자리|식사\s*자리)"
    r"|약(?:을|은)?\s*먹|영양제\s*먹"
    r"|(?:해\s*먹고|먹고\s*살|먹고살|밥벌이|밥\s*먹고\s*살)"
    r"|(?:나이|욕|한\s*방|한방|겁|마음|더위|물)\s*먹"
)


@lru_cache(maxsize=4)
def _load_rules(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict:
    return json.loads((dictionaries_dir / "calendar" / "food_rules.json").read_text("utf-8"))


def load_food_rules(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, dict]:
    """`calendar/food_rules.json` → {오행(한자): {taste, foods, menus}} (사전 순서 보존)."""
    return {
        item["element"]: {
            "taste": item["taste"],
            "foods": list(item["foods"]),
            "menus": list(item["menus"]),
        }
        for item in _load_rules(dictionaries_dir)["items"]
    }


@lru_cache(maxsize=4)
def _food_lexicon(dictionaries_dir: Path = _DICTS_DEFAULT) -> dict[str, str | None]:
    """음식 어휘 → 오행(한자) | None(보류 큐). 긴 어휘가 먼저 매칭되도록 호출부가 정렬한다."""
    raw = _load_rules(dictionaries_dir)
    lex: dict[str, str | None] = {}
    for item in raw["items"]:
        for f in item["foods"]:
            lex[f] = item["element"]
        for m in item["menus"]:
            lex.setdefault(m, item["element"])
    for word, el in raw.get("aliases", {}).items():
        lex.setdefault(word, el)
    for word in raw.get("unmapped_review_queue", []):
        lex.setdefault(word, None)
    return lex


def food_element_of(word: str, dictionaries_dir: Path = _DICTS_DEFAULT) -> str | None:
    """음식 어휘 1개 → 오행(한자). 사전에 없거나 보류 큐(복합 요리)면 None."""
    if len(word) < 2:
        return None
    return _food_lexicon(dictionaries_dir).get(word)


def is_food_question(text: str) -> bool:
    """음식·끼니 질문 표지가 있으면 True. 일정(점심 약속)·복약·생계 관용구는 제외."""
    if _FOOD_EXCLUDE_RE.search(text):
        return False
    return bool(_FOOD_QUESTION_RE.search(text))


def detect_asked_foods(text: str, dictionaries_dir: Path = _DICTS_DEFAULT) -> list[str]:
    """발화에서 지목된 음식 어휘(사전 키, 등장 순) — 긴 어휘 우선(복합어가 단일어를 가림)."""
    lex = _food_lexicon(dictionaries_dir)
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for word in sorted(lex, key=len, reverse=True):
        if len(word) < 2:
            continue
        for m in re.finditer(re.escape(word), text):
            span = (m.start(), m.end())
            if any(s <= span[0] < e or s < span[1] <= e for s, e in taken):
                continue
            taken.append(span)
            found.append((m.start(), word))
    found.sort()
    out: list[str] = []
    for _, w in found:
        if w not in out:
            out.append(w)
    return out


def build_yongsin_food_note(
    favorability: dict[str, str],
    asked_foods: list[str] | None = None,
    *,
    confirmed: bool = False,
    dictionaries_dir: Path = _DICTS_DEFAULT,
) -> YongsinFoodNote | None:
    """용희기구한 {오행: 역할} → 오행 보완 음식 첨언. 역할이 비어 있으면(용신 미도출) None.

    Args:
        favorability: `favorability_map` 포맷({'火': '용신', …}). 사용자 확정 override 가능.
        asked_foods: 사용자가 지목한 음식 어휘 — 사전에 있으면 오행·역할 줄, 없으면 보류 목록.
        confirmed: True 면 출처를 '사용자 확정 용신'으로 표시한다.
    """
    if not favorability:
        return None
    rules = load_food_rules(dictionaries_dir)
    by_role = {role: el for el, role in favorability.items()}
    entries: list[YongsinFoodEntry] = []
    for role in ROLE_ORDER:
        if role not in by_role:
            continue
        el = by_role[role]
        rule = rules.get(el, {"taste": "", "foods": [], "menus": []})
        entries.append(YongsinFoodEntry(
            role=role, element=el, taste=rule["taste"], foods=rule["foods"],
            menus=rule["menus"], tone=ROLE_TONE[role],
        ))
    if not entries:
        return None
    lex = _food_lexicon(dictionaries_dir)
    asked_entries: list[YongsinFoodEntry] = []
    unmapped: list[str] = []
    for word in asked_foods or []:
        asked_el = lex.get(word)
        if asked_el is None:
            if word not in unmapped:
                unmapped.append(word)
            continue
        role = favorability.get(asked_el, "한신")
        asked_entries.append(YongsinFoodEntry(
            role=role, element=asked_el, taste=rules.get(asked_el, {}).get("taste", ""),
            foods=[word], tone=ROLE_TONE.get(role, "무난"),
        ))
    return YongsinFoodNote(
        entries=entries, source="confirmed" if confirmed else "engine",
        asked_entries=asked_entries, unmapped_foods=unmapped,
    )


def format_yongsin_food_lines(note: YongsinFoodNote | None) -> list[str]:
    """LLM 입력 직렬화 — 빈 블록이면 헤더도 내지 않는다(무소음)."""
    if note is None or not note.entries:
        return []
    src = "사용자 확정 용신" if note.source == "confirmed" else "엔진 도출 용신"
    lines = [
        "",
        f"[오행 보완 음식 — 용희기구한 기준(첨언 · {src}) — 음식·메뉴 후보는 이 표에서만 고를 것]",
    ]
    for e in note.entries:
        foods = "·".join(e.foods) if e.foods else "해당 재료 없음"
        menus = f" / 끼니 예: {'·'.join(e.menus)}" if e.menus else ""
        taste = f" {e.taste}" if e.taste else ""
        lines.append(f"- {e.role} {e.element}{taste} → {foods}{menus} ({e.tone})")
    for a in note.asked_entries:
        lines.append(f"- 지목한 음식 '{a.foods[0]}' = {a.element}({a.role}) — {a.tone}")
    if note.unmapped_foods:
        lines.append(
            "- 지목한 음식 " + "·".join(f"'{f}'" for f in note.unmapped_foods)
            + " = 오행 배정 보류(사전 미등재·복합 요리) — 오행을 임의로 배정하지 말고 "
            + "'재료가 여러 오행에 걸쳐 보류'로 안내"
        )
    return lines


YONGSIN_FOOD_CLOSING_DIRECTIVE = (
    "[끼니 질문 — 말미 고정] 이 턴의 답은 **메뉴 추천**이다. 첫 문장에서 [오행 보완 음식] 표의 "
    "용신·희신 음식 중 2~3가지를 바로 고르고, 이유는 각 한 문장(쉬운 말, 첫 문장엔 "
    "한자·오행 원어 금지). 질문한 날의 운([질문한 날짜의 일운]·[해당 일 일운])은 **한 줄**로만 "
    "덧붙인다. 일·재물·관계·건강 영역별 총운, 사건·시기 나열, 성격·일주 서사는 쓰지 말 것. "
    "영양·의료 조언이 아님을 한 구절로 밝힌다. 질문(무엇을 먹을까)에 답하지 않고 그날 운세로 "
    "바꿔 답하는 것은 금지."
)

YONGSIN_FOOD_INSTRUCTION = (
    "[오행 보완 음식 지침] 음식·메뉴 추천은 위 [오행 보완 음식] 표의 역할·톤을 그대로 따를 것. "
    "①답의 형태: 첫 문장에서 메뉴 2~3가지를 바로 고르고(용신 음식 우선 + 희신 음식 보조), "
    "각 이유는 한 문장('용신 火를 보완하는 붉은·쓴맛 계열')으로 짧게. 질문이 '오늘·내일' 등 "
    "특정 날의 끼니면 그날 운의 기운은 **한 줄**만 덧붙이고, 일·재물·관계·건강 영역별 총운을 "
    "펼치지 말 것(이 턴은 끼니 질문이다). ②상생 연쇄로 후보를 늘리지 말 것 — '목이 화를 "
    "생하니 신맛도 좋다'처럼 기신·구신 오행 음식을 용신을 돕는 음식으로 끌어오는 것은 금지. "
    "③기신·구신 음식은 '피하라·먹지 말라'가 아니라 '보완 효과 없음 — 주식으로 몰아 먹지는 "
    "말기' 수준으로 완화해 말할 것. ④음식은 선택의 가벼운 기준이지 원인이 아니다 — '이걸 "
    "먹으면 일이 풀린다/건강이 좋아진다'처럼 운·성과·건강을 직접 바꾼다는 인과 단정은 "
    "금지(전통 상징으로 설명). 영양·의료 조언이 아님을 한 구절로 밝힐 것. ⑤사전에 없는 "
    "음식·복합 요리는 오행을 지어내지 말고 보류로 안내할 것. ⑥용신 음식 일변도 금지 — 희신 "
    "음식을 함께 제시하고, 용신 음식이 부담스럽거나 배제됐다면 희신 음식이 1차 대안이다. 한신 "
    "음식은 '무난한 중립 선택'으로 덧붙일 수 있다. ⑦사용자가 배제한 음식([사용자 제공 정보]의 "
    "배제 조건)은 대안으로 다시 내밀지 말 것."
)
