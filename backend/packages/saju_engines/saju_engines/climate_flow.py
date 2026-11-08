"""인생 그래프 조후 흐름선(A안, 2026-11-08 데굴님 "조후로만 봐도 겨울에 태어나 가을로 가는 중이라
바닥에서 시작해 서서히 쌓여갈 수밖에").

억부 점수 곡선과 별도로 **조후 온도**만으로 본 대운·세운 선을 같은 척도(−1~+1)로 붙인다. 온도표·필요
방향은 `saju_manse_analysis.luck.climate` 가 SSOT. 설명용 층 — 점수·마커·창은 불변이고 명리 판정이
아니다.

- 대운 조후 = 대운 지지 온도(필요 방향·가중 적용).
- 연도 조후 = 0.7 × 소속 대운 조후 + 0.3 × 세운 지지 조후(대운이 바탕, 세운은 해마다의 오르내림).
- 중립 월(卯申酉)이면 축이 없어 선을 그리지 않는다(`climate_axis=""`, 값 None).
"""

from __future__ import annotations

from saju_manse_analysis.luck.climate import AXIS_KO, NEED_KO, climate_need, climate_score

from saju_shared_types.life_graph import LifeGraph

#: 연도 조후 합성 비중(대운 바탕 / 세운 오르내림).
DAEWOON_WEIGHT = 0.7
YEAR_WEIGHT = 0.3


def attach_climate(graph: LifeGraph, month_branch: str) -> None:
    """그래프에 조후 축·대운/연도 조후 값·요약(보통선 도달 대운·정점 대운)을 채운다(제자리)."""
    axis, need, weight = climate_need(month_branch)
    if not need or weight <= 0:
        graph.climate_axis = ""
        return
    graph.climate_axis = axis
    graph.climate_need_ko = NEED_KO.get(need, "")
    band: dict[int, float] = {}
    for d in graph.daewoons:
        d.climate = climate_score(month_branch, d.ganji[-1])
        for y in range(d.start_year, d.end_year + 1):
            band[y] = d.climate
    for yr in graph.years:
        own = climate_score(month_branch, yr.ganji[-1])
        yr.climate = round(DAEWOON_WEIGHT * band.get(yr.year, 0.0) + YEAR_WEIGHT * own, 3)
    reach = next(
        (d for d in graph.daewoons if d.climate is not None and d.climate >= 0), None,
    )
    graph.climate_baseline_daewoon = reach.ganji if reach is not None else None
    if graph.daewoons:
        peak = max(graph.daewoons, key=lambda d: d.climate if d.climate is not None else -9)
        graph.climate_peak_daewoon = peak.ganji


def climate_lines(graph: LifeGraph) -> list[str]:
    """[조후 흐름] 블록 — F-14 해설용. 축이 없으면 빈 목록."""
    if not graph.climate_axis or not graph.daewoons:
        return []
    status_ko = {"past": "지남", "current": "현재", "future": "예정", "unknown": ""}
    out = [
        f"[조후 흐름 — 월지가 {AXIS_KO.get(graph.climate_axis, graph.climate_axis)}이라 "
        f"{graph.climate_need_ko}가 필요한 명식. 아래는 억부(용신) 점수와 별도로 대운·세운 "
        "**지지의 온도**만 본 선(−1 가장 불리 ~ +1 가장 유리). 설명용 층이며 명리 판정이 아니다 — "
        "수치·순서 밖 판단 금지, 억부 점수와 다를 때는 '용신 흐름으로는 ~, 조후로는 ~'로 두 축을 "
        "나눠 쓸 것]",
    ]
    for d in graph.daewoons:
        tag = status_ko.get(d.status, "")
        val = "" if d.climate is None else f"{d.climate:+.2f}"
        out.append(
            f"- {d.ganji} {d.start_age}–{d.end_age}세{' [' + tag + ']' if tag else ''}: 조후 {val}"
        )
    if graph.climate_baseline_daewoon:
        out.append(f"- 조후 보통선(0) 도달 대운: {graph.climate_baseline_daewoon}")
    else:
        out.append("- 조후 보통선(0)에 이르는 대운 없음(생애 내내 필요 온도 부족)")
    if graph.climate_peak_daewoon:
        out.append(f"- 조후 정점 대운: {graph.climate_peak_daewoon}")
    return out
