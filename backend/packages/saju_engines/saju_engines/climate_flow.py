"""인생 그래프 조후 흐름선(A안, 2026-11-08 데굴님 "조후로만 봐도 겨울에 태어나 가을로 가는 중이라
바닥에서 시작해 서서히 쌓여갈 수밖에").

억부 점수 곡선과 별도로 **조후 온도**만으로 본 대운·세운 선을 같은 척도(−1~+1)로 붙인다. 온도표·필요
방향은 `saju_manse_analysis.luck.climate` 가 SSOT. 설명용 층 — 점수·마커·창은 불변이고 명리 판정이
아니다.

- 대운 조후 = 대운 지지 온도(필요 방향·가중 적용).
- 연도 조후 = 0.7 × 소속 대운 조후 + 0.3 × 세운 지지 조후(대운이 바탕, 세운은 해마다의 오르내림).
- 중립 월(卯申酉)이면 축이 없다(`climate_axis=""`, 값 None) — 추세선은 억부 점수 그대로.
- 선 자체는 따로 그리지 않고 `life_graph._attach_trend` 가 억부 점수와 평균해 **추세선** 한 줄로
  합친다(2026-11-08 데굴님 "누적 운세는 의미가 없어 — 대운별 운세와 조후 운세를 합쳐 하나의
  추세선으로").
"""

from __future__ import annotations

from saju_manse_analysis.luck.climate import NEED_KO, climate_need, climate_score

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
    if graph.pre_daewoon is not None:  # 대운 전 유년 = 월지 자체의 온도
        graph.pre_daewoon.climate = climate_score(month_branch, graph.pre_daewoon.ganji[-1])
    reach = next(
        (d for d in graph.daewoons if d.climate is not None and d.climate >= 0), None,
    )
    graph.climate_baseline_daewoon = reach.ganji if reach is not None else None
    if graph.daewoons:
        peak = max(graph.daewoons, key=lambda d: d.climate if d.climate is not None else -9)
        graph.climate_peak_daewoon = peak.ganji
