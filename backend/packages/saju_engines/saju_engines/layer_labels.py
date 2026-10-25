"""참여 글자 층위 라벨 공용 SSOT(2026-10-25 데굴님 승인).

실답(2026-10-25 '올해 운세')에서 LLM 이 丁壬合을 "대운의 壬와 세운의 丁"으로 썼다 — 세운은
丙午라 丁이 없고 실제는 원국 월간 丁 × 대운 壬이다. 원인은 `[관계 확정 문장]`이 "두 글자가 손을
잡고"처럼 참여 글자의 층위 없이 나가고, 계층 블록은 대운×원국 관계를 싣지 않아 주어를 LLM 이
추측한 것이다.

이 모듈은 ①생성 전 — 관계 확정 문장에 붙일 `[원국 월간 丁 + 대운 壬]` 라벨, ②생성 후 —
"세운의 丁"처럼 층위를 잘못 붙인 표기를 바로잡는 감사(`layer_label_audit`)가 같은 규칙을 쓰도록
라벨 계산을 한 곳에 둔다. 계층 블록의 `participant_label`(원국 월간/월지 구분)과 같은 어휘다.
"""

from __future__ import annotations

from saju_shared_types.enums import Stem
from saju_shared_types.relation_semantics import RelationOccurrence

_STEM_CHARS: frozenset[str] = frozenset(s.value for s in Stem)
_PALACE_KO = {"year": "연", "month": "월", "day": "일", "hour": "시"}
#: 운 층위 라벨 표준 순서(대운 → 세운 → 월운 → 일진).
LUCK_LAYER_ORDER = ("대운", "세운", "월운", "일진")


def is_stem_char(char: str) -> bool:
    """천간 글자인가(아니면 지지로 본다)."""
    return char in _STEM_CHARS


def natal_label(position: str, char: str) -> str:
    """원국 자리 라벨 — 'month'+丁 → '원국 월간', 'month'+亥 → '원국 월지'. 모르는 자리는 '원국'."""
    palace = _PALACE_KO.get(position)
    if palace is None:
        return "원국"
    return f"원국 {palace}{'간' if is_stem_char(char) else '지'}"


def luck_layers_of(char: str, stack_ganji: dict[str, str]) -> list[str]:
    """운 스택에서 이 글자를 (천간은 천간 자리, 지지는 지지 자리에) 가진 층위 목록(표준 순서)."""
    idx = 0 if is_stem_char(char) else 1
    out: list[str] = []
    for layer in LUCK_LAYER_ORDER:
        g = stack_ganji.get(layer) or ""
        if len(g) >= 2 and g[idx] == char:
            out.append(layer)
    return out


def natal_positions_of(char: str, natal_pillars: dict[str, str]) -> list[str]:
    """원국에서 이 글자가 있는 자리(position 키 'year'|'month'|'day'|'hour') 목록."""
    idx = 0 if is_stem_char(char) else 1
    return [
        pos for pos in ("year", "month", "day", "hour")
        if len(natal_pillars.get(pos) or "") >= 2 and natal_pillars[pos][idx] == char
    ]


def occurrence_label(occ: RelationOccurrence, stack_ganji: dict[str, str]) -> str:
    """발생 1건의 라벨 — 원국은 자리로, 운('luck')은 스택에서 층위를 찾아 붙인다."""
    if occ.position != "luck":
        return f"{natal_label(occ.position, occ.char)} {occ.char}"
    layers = luck_layers_of(occ.char, stack_ganji)
    head = "·".join(layers) if layers else "운"
    return f"{head} {occ.char}"


def participants_label(
    occurrences: list[RelationOccurrence], stack_ganji: dict[str, str] | None,
) -> str:
    """관계 참여 글자 라벨 — '원국 월간 丁 + 대운 壬'. 발생 정보가 없으면 빈 문자열."""
    if not occurrences:
        return ""
    return " + ".join(occurrence_label(o, stack_ganji or {}) for o in occurrences)


__all__ = [
    "LUCK_LAYER_ORDER", "is_stem_char", "luck_layers_of", "natal_label", "natal_positions_of",
    "occurrence_label", "participants_label",
]
