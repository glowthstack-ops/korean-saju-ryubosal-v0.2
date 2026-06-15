"""발현 분기(Manifestation Branch) — 2026-06-14 사용자 확정.

한 사건의 에너지는 같은 계열(EVENT_CATEGORY) 안에서 형제 사건으로도 발현될 수 있다.
예: '이직·직업 변화'와 '이사·이동'은 모두 'move(이동·변동)' 계열이라, 강한 이동 에너지가
재취업이 아니라 더 강한 형제(이사)로 발현됐을 가능성이 있다. 이 분기 가능성을 풀이에 함께
밝히기 위한 재료를 만든다 — 이사는 한 예시이며 재물·관계·학업 등 모든 계열에 일반 적용된다.

원칙(추측 배제): 형제를 임의로 지어내지 않고 **같은 시점에 실제로 점수화된 같은 계열 사건만**
분기로 노출한다. 점수·판정은 변경하지 않으며 서술용 재료만 덧붙인다(절대 원칙 1).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from saju_shared_types.event_taxonomy_v2 import EVENT_CATEGORY, EVENT_KO

# str(EventKeyV2) → 계열/한글. 후보 event_key(str 호환)로 직접 조회한다.
_CATEGORY_BY_STR: dict[str, str] = {str(k): v for k, v in EVENT_CATEGORY.items()}
_KO_BY_STR: dict[str, str] = {str(k): v for k, v in EVENT_KO.items()}
# 계열 코드 → 사용자 노출 라벨.
_FAMILY_KO: dict[str, str] = {
    "move": "이동·변동",
    "career": "직업·성취",
    "affection": "관계·애정",
    "money": "재물",
    "study": "학업·자격",
    "health": "건강",
}

# 계열 코드 → 소속 사건 전체(EVENT_CATEGORY 역인덱스).
_FAMILY_MEMBERS: dict[str, list[str]] = {}
for _ek, _cat in EVENT_CATEGORY.items():
    _FAMILY_MEMBERS.setdefault(_cat, []).append(str(_ek))

# 발현이 상호 교환되는 계열 — 같은 에너지가 두 갈래 중 어느 쪽으로도 발현되므로, 한 멤버만
# 점수화돼도 나머지를 '잠재 형제'로 함께 노출한다(이사만 특수처리하지 않고 동형 사례 전반에
# 일반 적용 — 2026-06-14). EVENT_CATEGORY에서 멤버가 정확히 2종인 계열을 구조적으로 도출한다:
#   move(이직↔이사) / money(재물 변화↔횡재) / study(진학·자격↔수료·졸업).
# (career 6종·affection 4종은 서로 구별되는 사건이라 제외 — co-scored된 형제만 노출.)
_INTERCHANGEABLE_FAMILIES = {
    fam for fam, members in _FAMILY_MEMBERS.items() if len(members) == 2
}


def _family(event_key: Any) -> str | None:
    """후보의 event_key가 속한 EVENT_CATEGORY 계열 코드(없으면 None)."""
    return _CATEGORY_BY_STR.get(str(event_key))


def branch_events(
    focal_key: Any, period_candidates: Iterable[Any]
) -> list[tuple[str, int]]:
    """focal과 같은 계열이며 같은 시점에 점수화된 사건을 강도순(점수 desc)으로 반환한다.

    period_candidates는 한 시점(달/연)에 점수화된 후보 목록이다(호출 측이 시점으로 스코프).
    distinct event_key 기준이며 focal 자신도 포함한다. 계열 내 사건이 1종뿐이면(분기 없음)
    빈 목록을 반환한다.

    Returns:
        [(event_key_str, score), ...] — 점수 내림차순. 분기가 없으면 [].
    """
    fam = _family(focal_key)
    if fam is None:
        return []
    best: dict[str, int] = {}
    for c in period_candidates:
        if _family(c.event_key) != fam:
            continue
        key = str(c.event_key)
        if c.score > best.get(key, -1):
            best[key] = c.score
    # 상호 교환 계열(move 등)은 점수화 안 된 형제도 잠재 발현으로 포함(같은 에너지).
    if fam in _INTERCHANGEABLE_FAMILIES:
        for member in _FAMILY_MEMBERS.get(fam, []):
            best.setdefault(member, 0)
    if len(best) < 2:
        return []
    return sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))


def branch_line(focal_key: Any, period_candidates: Iterable[Any]) -> str | None:
    """발현 분기 1줄 — 단일 초점의 같은 계열 형제 사건을 강도순으로 제시. 분기 없으면 None.

    예: "발현 분기: 같은 '이동·변동' 계열에서 이직·직업 변화 / 이사·이동 순(강도 순)으로
    갈릴 수 있음 — 더 강한 형제 신호로 발현됐을 가능성을 함께 밝히고 하나로 단정하지 말 것"
    """
    ranked = branch_events(focal_key, period_candidates)
    if not ranked:
        return None
    fam_label = _FAMILY_KO.get(_family(focal_key) or "", "같은")
    names = " / ".join(_KO_BY_STR.get(k, k) for k, _ in ranked)
    return (
        f"발현 분기: 같은 '{fam_label}' 계열에서 {names} 순(강도 순)으로 갈릴 수 있음 — "
        "더 강한 형제 신호로 발현됐을 가능성을 함께 밝히고 하나로 단정하지 말 것"
    )


def branch_summary(
    focal_keys: Iterable[Any], period_candidates: list[Any], *, cap: int = 3
) -> str | None:
    """여러 초점 사건의 계열 전부에서 형제를 뽑아 압축 문자열로 합친다. 분기 없으면 None.

    초점을 한 사건(그 달 1위)으로만 잡으면, 같은 점수의 다른 사건이 1위가 될 때 의미 있는
    형제 분기(예: 이직↔이사)가 통째로 누락된다. 표시되는 상위 사건들(focal_keys)의 계열을
    모두 훑어, 각 계열에서 같은 시점에 점수화된 형제를 강도순(계열당 cap개)으로 제시한다.

    반환은 계열·형제 목록만(지시문 없음) — 호출 측이 표/블록에 맞춰 한 번만 안내를 붙인다.
    예: "'이동·변동'(이직·직업 변화/이사·이동), '직업·성취'(취업·합격/승진·인정)"
    """
    seen_fam: set[str] = set()
    parts: list[str] = []
    for fk in focal_keys:
        fam = _family(fk)
        if fam is None or fam in seen_fam:
            continue
        seen_fam.add(fam)
        ranked = branch_events(fk, period_candidates)
        if not ranked:
            continue
        names = "/".join(_KO_BY_STR.get(k, k) for k, _ in ranked[:cap])
        parts.append(f"'{_FAMILY_KO.get(fam, fam)}'({names})")
    if not parts:
        return None
    return ", ".join(parts)
