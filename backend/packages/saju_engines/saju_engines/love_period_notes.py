"""관계 사건 후보 기간의 연애 운 결 — 서술 전용(2026-10-27 데굴님 승인).

관계 사건 후보(new_relationship·relationship_change·marriage_signal)의 기간 간지가 원국과 맺는
조건 네 가지를 '그럴 수 있다' 수준의 서술 구절로 바꾼다. 점수·순위·판정은 바꾸지 않는다.

1. 일지 충 — 운 지지가 일지(배우자 자리)를 충하면 급작스러운 시작·빠른 진행·강한 끌림, 끝난 뒤
   긴 여운.
2. 운의 역할 — 기·구신 운에 만난 인연은 빠르게 빠져들고 오래 기억될 수 있고, 용·희신 운에 만난
   인연은 처음에 확신·설렘이 덜할 수 있다.
3. 원국에 약한 오행 — 그 오행이 운으로 들어와 생긴 인연은 운이 지나면 관계의 결도 달라질 수 있다.
4. 운 천간 십성 — 비견·식상·재성·관성 운의 연애 결(인성 운은 정의된 결이 없어 생략).

'반드시 끝난다'·'운명이다' 같은 단정은 쓰지 않는다(절대원칙 3).
"""

from __future__ import annotations

from saju_shared_types.constants import (
    BRANCH_CLASHES,
    BRANCH_ELEMENT,
    STEM_ELEMENT,
    ten_god,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result

#: 연애 운 결을 붙이는 관계 사건 키.
LOVE_NOTE_EVENT_KEYS: frozenset[str] = frozenset(
    {"new_relationship", "relationship_change", "marriage_signal"}
)
_FAVORABLE = frozenset({"용신", "희신"})
_UNFAVORABLE = frozenset({"기신", "구신"})

_CLASH_NOTE = (
    "일지(배우자 자리)를 충하는 운 — 이때 시작되는 인연은 급작스럽게 시작돼 빠르게 진행될 수 있고, "
    "안정감은 덜해도 끌림이 강해 운명처럼 느껴질 수 있으며, 끝난 뒤에도 여운이 오래 남을 수 있다"
)
_HARD_NOTE = (
    "흐름이 무거운(기·구신) 운 — 이때 만난 인연은 빠르게 빠져들고 운명처럼 느껴질 수 있으며, "
    "나를 크게 흔든 인연이라 관계가 끝난 뒤에도 오래 기억될 수 있다"
)
_GOOD_NOTE = (
    "흐름이 좋은(용·희신) 운 — 이때 만난 인연은 처음부터 확신이 서지 않고 설렘이 덜해 "
    "긴가민가할 수 있다"
)
_WEAK_ELEMENT_NOTE = (
    "원국에 약한 {el} 기운이 운으로 들어오는 때 — 이때 생긴 인연은 그 운이 지나가면 관계의 결도 "
    "함께 달라질 수 있다"
)
#: 십성 → 연애 결 라벨(월별 표 압축 표기용 — 구절 본문은 `_TEN_GOD_NOTE`).
_TEN_GOD_LABEL: dict[str, str] = {
    "비견": "비견 운 연애 결", "식신": "식상 운 연애 결", "상관": "식상 운 연애 결",
    "편재": "재성 운 연애 결", "정재": "재성 운 연애 결",
    "편관": "관성 운 연애 결", "정관": "관성 운 연애 결",
}
_TEN_GOD_NOTE: dict[str, str] = {
    "비견": "비견 운 — 자기 감정과 선택을 앞세우는 연애 결이 될 수 있다",
    "식신": "식상 운 — 설렘·표현·재미·끌림이 앞서는 연애 결이 될 수 있다",
    "상관": "식상 운 — 설렘·표현·재미·끌림이 앞서는 연애 결이 될 수 있다",
    "편재": "재성 운 — 미래와 현실 조건을 따져 보는 연애 결이 될 수 있다",
    "정재": "재성 운 — 미래와 현실 조건을 따져 보는 연애 결이 될 수 있다",
    "편관": "관성 운 — 운명 같은 인연이라는 감각이 강해질 수 있다",
    "정관": "관성 운 — 운명 같은 인연이라는 감각이 강해질 수 있다",
}


def _role_note(stem_role: str, branch_role: str) -> tuple[str, str]:
    """천간·지지 역할이 한쪽으로 모일 때만 (라벨, 구절)을 고른다(엇갈리면 빈 값)."""
    roles = {r for r in (stem_role, branch_role) if r}
    if roles & _UNFAVORABLE and not roles & _FAVORABLE:
        return "무거운 운의 인연", _HARD_NOTE
    if roles & _FAVORABLE and not roles & _UNFAVORABLE:
        return "좋은 운의 인연", _GOOD_NOTE
    return "", ""


def love_period_note_items(
    result: ManseV2Result | None,
    period_ganji: str,
    fav_map: dict[str, str] | None,
) -> list[tuple[str, str]]:
    """기간 간지의 연애 운 결 (라벨, 구절) 목록 — 사건 키 판정 없이 간지 조건만 본다.

    월별 표처럼 같은 구절이 여러 달에 반복되는 곳은 라벨만 행에 달고 구절은 한 번만 싣는다.

    Args:
        result: 원국 결과(일간·일지·오행 결핍). None·명식 없음이면 빈 목록.
        period_ganji: 기간 간지 2글자.
        fav_map: {오행 한자: 역할}. 없으면 역할 구절 생략.

    Returns:
        (라벨, 구절) 목록 — 일지 충 → 운의 역할 → 약한 오행 → 십성 순.
    """
    if result is None or result.pillars is None or len(period_ganji) < 2:
        return []
    try:
        stem = Stem(period_ganji[0])
        branch = Branch(period_ganji[1])
        day_branch = Branch(result.pillars.day.branch)
        day_master = Stem(result.pillars.day_master)
    except ValueError:
        return []
    items: list[tuple[str, str]] = []
    if frozenset({branch, day_branch}) in BRANCH_CLASHES:
        items.append(("일지 충 인연", _CLASH_NOTE))
    stem_el = str(STEM_ELEMENT[stem])
    branch_el = str(BRANCH_ELEMENT[branch])
    fav = fav_map or {}
    label, note = _role_note(fav.get(stem_el, ""), fav.get(branch_el, ""))
    if note:
        items.append((label, note))
    if result.force_analysis is not None:
        deficient = set(result.force_analysis.five_elements.deficient_elements)
        weak = [el for el in dict.fromkeys((stem_el, branch_el)) if el in deficient]
        if weak:
            joined = "·".join(weak)
            items.append((f"약한 {joined} 운의 인연", _WEAK_ELEMENT_NOTE.format(el=joined)))
    tg = str(ten_god(day_master, stem))
    if tg in _TEN_GOD_NOTE:
        items.append((_TEN_GOD_LABEL[tg], _TEN_GOD_NOTE[tg]))
    return items


def love_period_notes(
    result: ManseV2Result | None,
    period_ganji: str,
    event_key: str,
    fav_map: dict[str, str] | None,
) -> list[str]:
    """관계 사건 후보 기간의 연애 운 결 구절 목록(서술 전용).

    Args:
        result: 원국 결과(일간·일지·오행 결핍 사용). None 이면 빈 목록.
        period_ganji: 후보 기간 간지 2글자.
        event_key: 후보 사건 키 — `LOVE_NOTE_EVENT_KEYS` 밖이면 빈 목록.
        fav_map: {오행 한자: 역할} — `event_scoring.favorability_map`. 없으면 역할 구절 생략.

    Returns:
        구절 목록(일지 충 → 운의 역할 → 약한 오행 → 십성 순). 해당 없으면 빈 목록.
    """
    if event_key not in LOVE_NOTE_EVENT_KEYS:
        return []
    return [note for _label, note in love_period_note_items(result, period_ganji, fav_map)]


__all__ = ["LOVE_NOTE_EVENT_KEYS", "love_period_note_items", "love_period_notes"]
