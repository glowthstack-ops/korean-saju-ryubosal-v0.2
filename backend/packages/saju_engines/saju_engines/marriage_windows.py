"""상대(동반자) 결혼·인연 신호 창 — 궁합 리포트·채팅 궁합 공용 (2026-11-07).

강의(거친 문체 편): 결혼은 둘이 하므로 본인 창이 약해도 상대 운이 들어오면 가능하다
("배우자 운 따라감").
상대 명식의 세운 후보 중 결혼·새 인연(게이트 55 이상, 주의 방향 제외)을 연도별 최고 점수로 묶어
서술 재료로만 준다. 점수·판정 무관.
"""

from __future__ import annotations

from collections.abc import Iterable

from saju_shared_types.events import EventCandidate

from .context_reducer import overview_cluster_key

WINDOW_GATE = 55
_LABEL_KO = {"marriage_signal": "결혼 신호", "new_relationship": "새 인연"}


def marriage_window_lines(
    label: str,
    scored: Iterable[EventCandidate],
    today_year: int,
    *,
    limit: int = 5,
) -> list[str]:
    """[상대 결혼·인연 신호 창] 줄 목록 — 오늘 이후 연도만, 후보가 없으면 빈 목록.

    Args:
        label: 상대 표시 라벨(별명).
        scored: 상대 명식의 점수화 후보(연 단위 포함).
        today_year: 오늘 연도(이전 해 제외).
        limit: 최대 연도 수.
    """
    best: dict[int, tuple[int, str]] = {}
    for c in scored:
        key = str(c.event_key)
        if key not in _LABEL_KO or c.score < WINDOW_GATE or not c.period[:4].isdigit():
            continue
        year = int(c.period[:4])
        if year < today_year or overview_cluster_key(c)[1] == "neg":
            continue
        if year not in best or c.score > best[year][0]:
            best[year] = (c.score, _LABEL_KO[key])
    if not best:
        return []
    rows = [f"- {y}년 {lbl} {sc}점" for y, (sc, lbl) in sorted(best.items())[:limit]]
    return [
        f"[상대({label}) 결혼·인연 신호 창 — 엔진 확정값. 결혼은 둘이 하므로 본인 창이 약해도 상대 "
        "창이 열려 있으면 가능성을 열어 둘 것(한쪽 운 따라감). 연도·점수 그대로]",
        *rows,
    ]


__all__ = ["WINDOW_GATE", "marriage_window_lines"]
