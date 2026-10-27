"""진입 통로 블록 — 입사·이직 후보 상위 달의 운 십성을 관계 범주로 옮긴 근거.

채팅·리포트 공용.

EMPLOYMENT_HISTORY_CALIBRATION.md §4(2026-10-22). `ten_god_relations` 근거표(`agent_relations`)를
그대로 쓰고 가족 칸은 붙이지 않는다. 관성=조직 / 비겁·재성=지인 같은 개인 이력 규칙은 넣지 않는다 —
근거표 범주만. 특정인·특정 회사 지목 금지는 지시문이 담당한다. 순수 함수(운 기둥은 호출자가 넘긴다).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .agent_relations import agent_relation_lines

#: 진입 사건 키 — 통로 블록 대상.
ENTRY_CHANNEL_KEYS: frozenset[str] = frozenset({"job_gain", "career_change"})
ENTRY_CHANNEL_HEADER = (
    "[진입 통로 — 후보 달 운 십성의 관계 범주(엔진 값·근거표). 제안·소개·공고가 올 수 있는 "
    "관계 범주이지 특정인·특정 회사가 아니다]"
)
ENTRY_CHANNEL_DIRECTIVE = (
    "[진입 통로] 위 근거표의 관계 범주를 그대로 옮겨 '어떤 관계 쪽에서 제안·소개·공고가 올 수 "
    "있는가'를 후보 달마다 한 줄로만 쓰라. 통로를 단정하거나 특정인·특정 회사를 지목하지 말고, "
    "근거표에 없는 관계 범주를 더하지 말 것."
)

PillarResolver = Callable[[str], object | None]
"""기간 라벨('YYYY' / 'YYYY-MM') → 그 기간의 운 기둥(LuckPillar) 또는 None."""


def entry_periods(candidates: Iterable[object], limit: int = 2) -> list[str]:
    """진입 사건 후보를 점수순으로 훑어 서로 다른 기간 라벨 최대 `limit`개."""
    periods: list[str] = []
    for c in sorted(candidates, key=lambda c: -int(getattr(c, "score", 0))):
        if str(getattr(c, "event_key", "")) not in ENTRY_CHANNEL_KEYS:
            continue
        label = str(getattr(c, "period", ""))
        if label and label not in periods:
            periods.append(label)
        if len(periods) >= limit:
            break
    return periods


def entry_channel_lines(
    candidates: Iterable[object],
    pillar_for_label: PillarResolver,
    fav: dict[str, str],
    gender: str,
    limit: int = 2,
) -> tuple[list[str], list[str], list[str]]:
    """(헤더 포함 LLM 입력 줄, 노출 키, 쓰인 기간) — 후보·기둥이 없으면 전부 빈 목록."""
    periods = entry_periods(candidates, limit)
    pillars = [pl for pl in (pillar_for_label(lb) for lb in periods) if pl]
    if not pillars:
        return [], [], periods
    lines, keys = agent_relation_lines(pillars, fav, gender, include_family=False)
    if not lines:
        return [], [], periods
    return [ENTRY_CHANNEL_HEADER, *lines], keys, periods
