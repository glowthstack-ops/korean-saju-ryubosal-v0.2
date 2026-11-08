"""인생 그래프(총운 개편, 2026-11-07 데굴님 결정) — 대운 곡선 + 세운 선 + 주요 이벤트 마커.

총운(RPT_FULL)의 2부 "내 인생의 흐름"에서 LLM과 무관하게 **엔진이 확정**하는 구조 데이터.
그래프 자체는 프론트가 그리고(SVG), 같은 데이터가 대운별 상세 페이지(F-14-D*)와 인생 흐름
종합(F-14b)·요약 카드(F-21)의 마커 목록으로 쓰여 그림과 글이 어긋나지 않는다.

원칙:
- 점수·사건은 전 생애 연 단위 재채점(`lifetime_scan`, 대운표 sewoon 재사용)의 후보를 그대로
  쓴다 — 여기서 재계산하지 않는다(절대원칙 9).
- 마커 종류: 결혼·취업·이직·이사·재물 유입·위기(건강/금전 두 갈래) — 데굴님 확정 5종 + 같은 날
  "돈 들어오는 시기도 표시" 요청으로 재물 유입(재물 변화 길 방향) 추가.
- 선별은 대운 단위(한 대운 안의 세운이 그 대운의 주요 이벤트를 정한다): 대운당 최대
  `PER_DAEWOON_CAP`, 같은 종류 최대 `PER_KIND_CAP`, 위기(건강+금전) 합산 `CRISIS_PER_DAEWOON_CAP`,
  품질 게이트 `SCORE_GATE`(총운 다변화의 절대 게이트와 같은 55). **좌석 보장**: 종류별 최고
  후보를 먼저 앉히고 남는 자리를 점수순으로 채운다 — 점수순만으로는 금전 위기 99·96이 결혼 92를
  밀어내 "76세에나 결혼"만 남던 실답(2026-11-07) 교정. 빈 대운은 비워 둔다(무신호 강제 충원 금지).
- 결혼 마커는 **방향 무관**으로 두되 2축 메모(인연 창 ○ / 운의 결 길·주의)를 단다 — 엔진의
  '주의'는 충·형이 아니라 용기신 길흉이라, "시기는 열리나 운이 유리하지 않음 → 숙고·궁합 확인"
  (결혼운 강의 1 핵심, 2026-11-07 정정). 위기 마커는 주의·혼합 방향만.
- 앞으로의 긍정 창(`positive_windows`): 오늘 이후 길·혼합 방향 후보(게이트 이상)를 **마커 상한과
  무관하게** 연속 연도로 묶어 가장 가까운 창부터 제공 — 해설·종합·요약 카드가 희망 창을 먼저 쓴다.
- 위험 엔진(건강·금전 family)은 **섞어 쓰되** 마커를 만들지 않고 같은 해 위기 후보의 우선순위를
  올리고 '위험 신호 동반' 메모를 단다(2026-11-07 결정 3 — 정확도가 오르는 방향으로만).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from saju_shared_types.events import EventCandidate
from saju_shared_types.life_graph import (
    LifeGraph,
    LifeGraphDaewoon,
    LifeGraphMarker,
    LifeGraphWindow,
    LifeGraphYear,
    MarkerKind,
)
from saju_shared_types.manse_result import ManseV2Result

from .context_reducer import overview_cluster_key
from .structural_context import (  # noqa: F401 — 재수출(리포트가 life_graph 경유로 쓴다)
    PARTNER_STAR_DAEWOON_TAG,
    PARTNER_STAR_GODS,
    partner_star_daewoon_tag,
)

#: 사건 키 → 마커 종류. 재물 변화는 방향으로 갈린다 — 길=재물 유입 / 주의·혼합=금전 위기
#: (아래 `_marker_kind`).
_EVENT_TO_KIND: dict[str, MarkerKind] = {
    "marriage_signal": MarkerKind.MARRIAGE,
    "job_gain": MarkerKind.JOB,
    "career_change": MarkerKind.CAREER_CHANGE,
    "relocation": MarkerKind.RELOCATION,
    # 인연(2026-11-07): 결혼 신호와 별개로 '만남·관계 형성' 층을 따로 보여 준다(참고 풀이
    # "27년까지 인연 유리"와 정합 — 도입 계기였던 미혼 게이트 −12 는 같은 날 폐지됐고, 인연 층은
    # 결혼 점수와 무관한 독립 마커로 유지). 주의 방향 관계 변동은 갈등이라 제외(_marker_kind).
    "new_relationship": MarkerKind.ROMANCE,
    "relationship_change": MarkerKind.ROMANCE,
    "health_attention": MarkerKind.CRISIS_HEALTH,
    "wealth_change": MarkerKind.CRISIS_MONEY,
}
#: 위험 도메인 → 위기 마커 종류(보조 — 마커 생성 아님).
_RISK_DOMAIN_TO_KIND: dict[str, MarkerKind] = {
    "health_safety": MarkerKind.CRISIS_HEALTH,
    "finance": MarkerKind.CRISIS_MONEY,
}
KIND_KO: dict[MarkerKind, str] = {
    MarkerKind.MARRIAGE: "결혼",
    MarkerKind.JOB: "취업",
    MarkerKind.CAREER_CHANGE: "이직",
    MarkerKind.RELOCATION: "이사",
    MarkerKind.WEALTH_GAIN: "재물 유입",
    MarkerKind.ROMANCE: "인연",
    MarkerKind.CRISIS_HEALTH: "건강 위기",
    MarkerKind.CRISIS_MONEY: "금전 위기",
}
_TONE_KO = {"pos": "길", "neg": "주의", "mixed": "혼합"}
SCORE_GATE = 55
# 2026-11-07: 좌석 종류 9(인연·결혼 길·결혼 주의·취업·이직·이사·재물 유입·건강 위기·금전 위기)를
# 전부 수용 — 실답에서 2027년 결혼(길) 65점이 8좌석에 밀려 사라졌다.
PER_DAEWOON_CAP = 9
PER_KIND_CAP = 2
#: 위기(건강+금전) 합산 상한 — 한 대운이 위기 마커로만 채워지지 않게
#: (2026-11-07 데굴님 "너무 극단적").
CRISIS_PER_DAEWOON_CAP = 2
#: 좌석 보장 대상이 아닌 종류(없음) — 자리는 종류별 최고 후보 우선순위순으로 배정한다.
_CRISIS_KINDS = frozenset({MarkerKind.CRISIS_HEALTH, MarkerKind.CRISIS_MONEY})
#: 긍정 창 대상 종류(길·혼합 방향만) — 위기는 창을 만들지 않는다.
_POSITIVE_KINDS = (
    MarkerKind.ROMANCE, MarkerKind.MARRIAGE, MarkerKind.JOB, MarkerKind.CAREER_CHANGE,
    MarkerKind.WEALTH_GAIN, MarkerKind.RELOCATION,
)
#: 위험 신호 동반 시 게이트 판정에 더하는 우선순위(저장 점수는 불변).
RISK_PRIORITY_BONUS = 10
#: 종류별 나이 타당성(만 나이, 서술 현실성 규칙 — 명리 판정 아님). 범위 밖은 마커에서 뺀다.
#: 결혼·취업은 성인부터, 이직은 첫 직장 이후, 취업·이직은 통상 경제활동 연령 안에서만
#: (2026-11-07 dry-run: 만 6세 이직·88세 이직 마커가 나와 추가). 이사·위기는 전 연령.
KIND_AGE_RANGE: dict[MarkerKind, tuple[int, int]] = {
    # 2026-11-07: 76세 결혼 마커 실답 → 취업·이직과 같은 현실성 상한.
    MarkerKind.MARRIAGE: (18, 70),
    MarkerKind.JOB: (18, 70),
    MarkerKind.CAREER_CHANGE: (20, 70),
    MarkerKind.RELOCATION: (0, 100),
    MarkerKind.WEALTH_GAIN: (18, 100),
    MarkerKind.ROMANCE: (18, 85),
    MarkerKind.CRISIS_HEALTH: (0, 100),
    MarkerKind.CRISIS_MONEY: (0, 100),
}
MINOR_AGE = 18
#: 결혼 마커 2축 메모(2026-11-07 결혼운 강의 1) — 주의 톤은 '결혼 불가'가 아니라 숙고 신호.
MARRIAGE_CAUTION_NOTE = (
    "인연 창 ○ · 운의 결 주의 — 시기는 열리나 운이 유리하지 않음(숙고·궁합 확인)"
)
MARRIAGE_FAVORABLE_NOTE = "인연 창 ○ · 운의 결 길"
#: 미성년 시기의 이사·금전 위기는 본인 사건이 아니라 가족 단위 사건으로 읽는다(서술 메모).
MINOR_NOTE = "미성년 — 가족(부모) 단위의 이동·형편으로 읽을 것"


def _marker_kind(c: EventCandidate, age: int) -> MarkerKind | None:
    """후보의 마커 종류 — 방향·나이 규칙.

    재물 변화는 길=재물 유입 / 주의·혼합=금전 위기. 건강 위기는 주의·혼합만. 결혼은 방향 무관
    (주의 = 시기 신호는 있으나 운이 유리하지 않음 — 마커 메모로 2축 표기). 종류별 나이 범위 밖은
    제외.
    """
    kind = _EVENT_TO_KIND.get(str(c.event_key))
    if kind is None:
        return None
    direction = overview_cluster_key(c)[1]
    if kind is MarkerKind.CRISIS_MONEY and direction == "pos":
        kind = MarkerKind.WEALTH_GAIN
    elif kind is MarkerKind.CRISIS_HEALTH and direction == "pos":
        return None
    elif kind is MarkerKind.ROMANCE and direction == "neg":
        return None  # 주의 방향 관계 변동 = 갈등·이별 쪽, 인연 마커 아님
    lo, hi = KIND_AGE_RANGE[kind]
    if not lo <= age <= hi:
        return None
    return kind


def build_life_graph(
    result: ManseV2Result,
    lifetime_result: ManseV2Result,
    pool: Iterable[EventCandidate],
    lo_year: int,
    hi_year: int,
    *,
    risk_years: Mapping[int, set[str]] | None = None,
    today_year: int | None = None,
    gender: str | None = None,
) -> LifeGraph | None:
    """전 생애 후보 풀 → 인생 그래프 데이터.

    Args:
        result: 본인 명식(대운표·현재 대운 판정 원천).
        lifetime_result: 전 생애 세운이 병합된 결과(연도별 세운 점수·라벨 원천).
        pool: 전 생애 연 단위 후보(기간 라벨 4자리).
        lo_year: 출생 연도(창 시작). hi_year: 창 끝(90세).
        risk_years: 연도 → 위험 도메인 집합(위험 엔진 shadow, 선택).
        today_year: 오늘 연도 — 앞으로의 긍정 창(`positive_windows`)의 시작. None이면 창 생략.
        gender: 'male'/'female' — 배우자성 대운 라벨(남=재성·여=관성). None이면
            result.input_summary.

    Returns:
        LifeGraph — 대운표가 없으면 None.
    """
    lc = result.luck_cycles
    lt = lifetime_result.luck_cycles
    if lc is None or lt is None or not lc.daewoon_table:
        return None
    pool = list(pool)
    cur = lc.current_daewoon_index
    _gender = gender or str((result.input_summary or {}).get("gender") or "")
    partner_gods = PARTNER_STAR_GODS.get(_gender, frozenset())
    years_by_label = {p.label: p for p in lt.yearly_luck if p.label.isdigit()}
    cands_by_year: dict[int, list[EventCandidate]] = {}
    for c in pool:
        if len(c.period) == 4 and c.period.isdigit():
            y = int(c.period)
            if lo_year <= y <= hi_year:
                cands_by_year.setdefault(y, []).append(c)
    risk_map = {y: set(v) for y, v in (risk_years or {}).items()}

    daewoons: list[LifeGraphDaewoon] = []
    all_markers: list[LifeGraphMarker] = []
    first_start = lc.daewoon_table[0].approx_start_date.year
    for d in lc.daewoon_table:
        y0 = d.approx_start_date.year
        y1 = min(d.approx_end_date.year - 1, hi_year)
        if y0 > hi_year:
            break
        # 첫 대운 페이지는 출생~첫 대운 전 유년을 함께 담는다(대운 없는 해를 비워 두지 않음).
        page_lo = lo_year if y0 == first_start else y0
        status = (
            "unknown" if cur is None
            else "current" if d.index == cur
            else "past" if d.index < cur
            else "future"
        )
        markers = _select_markers(
            d.index, range(page_lo, y1 + 1), cands_by_year, years_by_label, risk_map, lo_year,
        )
        all_markers += markers
        daewoons.append(LifeGraphDaewoon(
            index=d.index, ganji=d.ganji, stem_ten_god=d.stem_ten_god,
            branch_ten_god=d.branch_ten_god, start_age=d.start_age,
            end_age=min(d.start_age + 9, hi_year - lo_year),
            start_year=page_lo, end_year=y1, score=round(float(d.luck_score), 3),
            label=d.luck_label, status=status, markers=markers,
            partner_star_daewoon=bool(
                {str(d.stem_ten_god or ""), str(d.branch_ten_god or "")} & partner_gods
            ),
        ))
    years = [
        LifeGraphYear(
            year=y, age=y - lo_year, ganji=p.ganji, score=round(float(p.luck_score), 3),
            label=p.luck_label,
        )
        for y in range(lo_year, hi_year + 1)
        if (p := years_by_label.get(str(y))) is not None
    ]
    windows = (
        build_positive_windows(pool, lo_year, today_year, hi_year)
        if today_year is not None else []
    )
    graph = LifeGraph(
        birth_year=lo_year, end_year=hi_year, today_year=today_year, current_daewoon_index=cur,
        daewoons=daewoons, years=years, markers=all_markers, positive_windows=windows,
    )
    _attach_cumulative(graph)  # 누적 운세선·대운 추세(설명용 산술, 2026-11-08)
    return graph


#: 대운 추세 라벨 임계 — (세운+대운) 연 평균의 직전 대운 대비 차이. 점수 척도가 대략 −1~+1 이라 0.1.
TREND_EPS = 0.1


def _attach_cumulative(graph: LifeGraph) -> None:
    """누적 운세선·대운 추세·생애 분위를 채운다(제자리, docs/10 §3-1 '누적 운세선', 2026-11-08).

    연도 총점 = 세운 점수 + 그 해가 속한 대운 점수(첫 대운 페이지는 출생~유년 포함). 누적 =
    출생부터의 합. 대운 추세 = 그 대운 연도 총점 평균 − 직전 대운 평균(TREND_EPS 기준
    상승/하강/보합, 첫 대운은 '시작'). 주식 차트의 가격선처럼 '이전보다 좋아지는지'를 보이기 위한
    **설명용 산술**이며 명리 판정이 아니다(점수·마커·창은 불변).
    """
    band_score: dict[int, float] = {}
    band_index: dict[int, int] = {}
    for d in graph.daewoons:
        for y in range(d.start_year, d.end_year + 1):
            band_score[y] = d.score
            band_index[y] = d.index
    total_by_year: dict[int, float] = {}
    running = 0.0
    for yr in graph.years:
        total = yr.score + band_score.get(yr.year, 0.0)
        total_by_year[yr.year] = total
        running += total
        yr.cumulative = round(running, 3)
    prev_mean: float | None = None
    for d in graph.daewoons:
        totals = [
            total_by_year[y] for y in range(d.start_year, d.end_year + 1) if y in total_by_year
        ]
        mean = sum(totals) / len(totals) if totals else 0.0
        d.mean_total = round(mean, 3)
        if prev_mean is None:
            d.trend, d.trend_delta = "시작", None
        else:
            delta = mean - prev_mean
            d.trend_delta = round(delta, 3)
            d.trend = "상승" if delta > TREND_EPS else "하강" if delta < -TREND_EPS else "보합"
        prev_mean = mean
    if graph.years:
        peak = max(graph.years, key=lambda y: y.cumulative)
        low = min(graph.years, key=lambda y: y.cumulative)
        graph.cumulative_peak_year, graph.cumulative_low_year = peak.year, low.year
        if graph.today_year is not None:
            today = next((y for y in graph.years if y.year == graph.today_year), None)
            if today is not None:
                below = sum(1 for y in graph.years if y.cumulative < today.cumulative)
                graph.today_cumulative_percentile = round(100 * below / len(graph.years))


def cumulative_lines(graph: LifeGraph) -> list[str]:
    """[누적 흐름] 블록 — F-14 해설용. 대운별 평균·직전 대비·추세와 생애 최고/최저·오늘 분위."""
    if not graph.daewoons or not graph.years:
        return []
    status_ko = {"past": "지남", "current": "현재", "future": "예정", "unknown": ""}
    out = [
        "[누적 흐름 — 누적 운세선(점선)은 해마다의 운 점수에 소속 대운 점수를 더해 출생부터 쌓은 "
        "선이다(주식 차트의 가격선처럼 높이=쌓인 수준, 기울기=이전보다 좋아지는지). 설명용 "
        "산술이며 "
        "명리 판정이 아니다 — 아래 수치·구간만 쓰고 '이전보다 좋아지는 중/나빠지는 중/비슷'은 추세 "
        "라벨 그대로 쓸 것]",
    ]
    for d in graph.daewoons:
        tag = status_ko.get(d.status, "")
        delta = "" if d.trend_delta is None else f", 직전 대운 대비 {d.trend_delta:+.2f}"
        out.append(
            f"- {d.ganji} {d.start_age}–{d.end_age}세({d.start_year}–{d.end_year}년)"
            f"{' [' + tag + ']' if tag else ''}: 연 평균 {d.mean_total:+.2f}{delta} → {d.trend}"
        )
    if graph.cumulative_peak_year is not None and graph.cumulative_low_year is not None:
        out.append(
            f"- 누적 최고점 {graph.cumulative_peak_year}년 · "
            f"누적 최저점 {graph.cumulative_low_year}년"
        )
    out += baseline_phase_lines(graph)
    if graph.today_cumulative_percentile is not None and graph.today_year is not None:
        out.append(
            f"- 오늘({graph.today_year}년)의 누적 수준은 생애 연도 중 상위 "
            f"{100 - graph.today_cumulative_percentile}% 지점"
        )
    return out


def baseline_phase_lines(graph: LifeGraph) -> list[str]:
    """기준선(누적 0 = 운이 쌓이지도 깎이지도 않은 보통선) 대비 구간 서술(2026-11-08 데굴님
    "남들보다 못한 바닥에서 시작해 지난 대운에서 보통선에 도달, 앞으로 나아진다는 해석" 대조용).

    - 기준선 아래 구간(연도 범위·최저점), 기준선 위 구간, 아래→위 회복 연도(또는 미회복).
    - 오늘 위치(기준선 위/아래, 값)와 앞으로의 대운(평균 부호 → 나아지는지/내려가는지).
    설명용 산술 — 점수는 불변이며 명리 판정이 아니다. years 가 없으면 빈 목록.
    """
    years = graph.years
    if not years:
        return []
    below = [y for y in years if y.cumulative < 0]
    above = [y for y in years if y.cumulative >= 0]
    out: list[str] = []
    if below and above:
        b0, b1 = min(b.year for b in below), max(b.year for b in below)
        a0, a1 = min(a.year for a in above), max(a.year for a in above)
        out.append(
            f"- 기준선(누적 0, 보통선) 아래 구간: {b0}–{b1}년({len(below)}년) · "
            f"위 구간: {a0}–{a1}년({len(above)}년)"
        )
    elif below:
        out.append(
            f"- 생애 내내 기준선(누적 0, 보통선) 아래 — 최저점 {graph.cumulative_low_year}년"
        )
    else:
        out.append(f"- 생애 내내 기준선(누적 0, 보통선) 위 — 최고점 {graph.cumulative_peak_year}년")
    recover = [
        y.year for prev, y in zip(years, years[1:], strict=False)
        if prev.cumulative < 0 <= y.cumulative
    ]
    if recover:
        out.append(f"- 기준선 회복 연도(아래→위): {', '.join(str(v) for v in recover)}년")
    if graph.today_year is not None:
        today = next((y for y in years if y.year == graph.today_year), None)
        if today is not None:
            pos = "위" if today.cumulative >= 0 else "아래"
            out.append(f"- 오늘({today.year}년) 누적 {today.cumulative:+.2f} → 기준선 {pos}")
        future = [d for d in graph.daewoons if d.status == "future"]
        if future:
            desc = " · ".join(
                f"{d.ganji} {d.start_age}–{d.end_age}세 {d.mean_total:+.2f}({d.trend})"
                for d in future
            )
            rising = sum(1 for d in future if d.mean_total > 0)
            if rising == len(future):
                verdict = "앞으로의 대운 평균이 전부 양(+) — 쌓인 운이 계속 올라가는 쪽"
            elif rising == 0:
                verdict = "앞으로의 대운 평균이 전부 음(−) — 쌓인 운이 더 내려가는 쪽"
            else:
                verdict = (
                    f"앞으로의 대운 {len(future)}개 중 {rising}개가 양(+) — 오르내림이 섞인 쪽"
                )
            out.append(f"- 앞으로: {desc} → {verdict}")
    return out


def when_tag(year: int, today_year: int | None) -> str:
    """연도의 시제 표식 — ' [지남]' / ' [올해]' / ' [예정]'(오늘 연도 미상이면 빈 문자열).

    LLM이 지난 해를 '내년·다가올'로 쓰는 오류를 입력 단계에서 막는다(채팅·리포트 공용 가능).
    """
    if today_year is None:
        return ""
    if year < today_year:
        return " [지남]"
    if year == today_year:
        return " [올해]"
    return " [예정]"


def _select_markers(
    daewoon_index: int,
    years: Iterable[int],
    cands_by_year: Mapping[int, list[EventCandidate]],
    years_by_label: Mapping[str, object],
    risk_map: Mapping[int, set[str]],
    birth_year: int,
) -> list[LifeGraphMarker]:
    """한 대운 창의 마커 선별 — 연도×종류별 최고 후보 → 우선순위순 → 대운·종류 상한."""
    best: dict[tuple[int, MarkerKind], EventCandidate] = {}
    for y in years:
        for c in cands_by_year.get(y, []):
            kind = _marker_kind(c, y - birth_year)
            if kind is None:
                continue
            key = (y, kind)
            if key not in best or c.score > best[key].score:
                best[key] = c

    def priority(item: tuple[tuple[int, MarkerKind], EventCandidate]) -> tuple:
        (y, kind), c = item
        risk_hit = kind in {
            _RISK_DOMAIN_TO_KIND[d] for d in risk_map.get(y, set()) if d in _RISK_DOMAIN_TO_KIND
        }
        return (-(c.score + (RISK_PRIORITY_BONUS if risk_hit else 0)), y, kind.value)

    # 게이트 통과분만, 우선순위순.
    ranked = [
        item for item in sorted(best.items(), key=priority)
        if item[1].score + (RISK_PRIORITY_BONUS if _risk_hit(item[0], risk_map) else 0)
        >= SCORE_GATE
    ]
    # 1차(좌석 보장): 종류별 최고 후보 1건씩을 우선순위순으로 — 위기가 자리를 독점하지 않게.
    # 결혼은 길·혼합(인연 창+운 길)과 주의(인연 창+운 불리)가 다른 뜻이라 각각 한 좌석(2026-11-07
    # 실답: 2027년 결혼 66점 길이 2034년 95점 주의에 밀려 '가까운 길한 창'이 그래프에서 사라짐).
    # 2차: 남는 자리를 우선순위순으로(종류 상한·위기 합산 상한 안에서).
    def seat_key(item: tuple[tuple[int, MarkerKind], EventCandidate]) -> tuple[MarkerKind, str]:
        (_y, kind), c = item
        if kind is MarkerKind.MARRIAGE:
            return kind, "caution" if overview_cluster_key(c)[1] == "neg" else "fair"
        return kind, ""

    first_of_kind: list[tuple[tuple[int, MarkerKind], EventCandidate]] = []
    seen_seat: set[tuple[MarkerKind, str]] = set()
    for item in ranked:
        seat = seat_key(item)
        if seat not in seen_seat:
            seen_seat.add(seat)
            first_of_kind.append(item)
    order = first_of_kind + [item for item in ranked if item not in first_of_kind]

    picked: list[LifeGraphMarker] = []
    per_kind: dict[MarkerKind, int] = {}
    crisis_n = 0
    for (y, kind), c in order:
        if len(picked) >= PER_DAEWOON_CAP:
            break
        if per_kind.get(kind, 0) >= PER_KIND_CAP:
            continue
        if kind in _CRISIS_KINDS and crisis_n >= CRISIS_PER_DAEWOON_CAP:
            continue
        risk_hit = _risk_hit((y, kind), risk_map)
        pillar = years_by_label.get(str(y))
        age = y - birth_year
        tone = _TONE_KO.get(overview_cluster_key(c)[1], "혼합")
        note = (
            MINOR_NOTE
            if age < MINOR_AGE and kind in (
                MarkerKind.RELOCATION, MarkerKind.CRISIS_MONEY, MarkerKind.WEALTH_GAIN,
            )
            else ""
        )
        if kind is MarkerKind.MARRIAGE:
            note = MARRIAGE_CAUTION_NOTE if tone == "주의" else MARRIAGE_FAVORABLE_NOTE
        picked.append(LifeGraphMarker(
            year=y, age=age,
            ganji=str(getattr(pillar, "ganji", "") or ""),
            kind=kind, kind_ko=KIND_KO[kind], event_key=str(c.event_key), score=c.score,
            tone=_TONE_KO.get(overview_cluster_key(c)[1], "혼합"),
            daewoon_index=daewoon_index,
            risk_backed=risk_hit,
            note=note,
        ))
        per_kind[kind] = per_kind.get(kind, 0) + 1
        if kind in _CRISIS_KINDS:
            crisis_n += 1
    return sorted(picked, key=lambda m: (m.year, m.kind.value))


def _risk_hit(key: tuple[int, MarkerKind], risk_map: Mapping[int, set[str]]) -> bool:
    """같은 해 위험 엔진(건강·금전 family) 신호가 그 마커 종류와 맞물리는지."""
    y, kind = key
    return kind in {
        _RISK_DOMAIN_TO_KIND[d] for d in risk_map.get(y, set()) if d in _RISK_DOMAIN_TO_KIND
    }


def build_positive_windows(
    pool: Iterable[EventCandidate], birth_year: int, from_year: int, hi_year: int,
) -> list[LifeGraphWindow]:
    """앞으로의 긍정 창 — from_year 이후 길·혼합 방향 후보(게이트 이상, 나이 규칙 적용)를 종류별로
    연속 연도(공백 1년까지 허용)로 묶는다. 마커 상한과 무관. 가장 가까운 창부터."""
    years_by_kind: dict[MarkerKind, dict[int, int]] = {}
    for c in pool:
        y = int(c.period[:4]) if c.period[:4].isdigit() else -1
        if y < from_year or y > hi_year or c.score < SCORE_GATE:
            continue
        kind = _marker_kind(c, y - birth_year)
        if kind is None or kind not in _POSITIVE_KINDS:
            continue
        if overview_cluster_key(c)[1] == "neg":
            continue
        bucket = years_by_kind.setdefault(kind, {})
        bucket[y] = max(bucket.get(y, 0), c.score)
    out: list[LifeGraphWindow] = []
    for kind, bucket in years_by_kind.items():
        ys = sorted(bucket)
        groups: list[list[int]] = [[ys[0]]]
        for y in ys[1:]:
            if y - groups[-1][-1] <= 2:
                groups[-1].append(y)
            else:
                groups.append([y])
        for span in groups:
            start, end = span[0], span[-1]
            peak = max(span, key=lambda k: (bucket[k], -k))
            out.append(LifeGraphWindow(
                kind=kind, kind_ko=KIND_KO[kind],
                start_year=start, end_year=end,
                start_age=start - birth_year, end_age=end - birth_year,
                peak_year=peak, peak_score=bucket[peak], years_count=len(span),
            ))
    return sorted(out, key=lambda w: (w.start_year, w.kind.value))


def positive_window_lines(graph: LifeGraph, *, per_kind: int = 3) -> list[str]:
    """[앞으로의 긍정 창] 프롬프트 줄 — 종류별 가장 가까운 창부터 최대 per_kind개."""
    if not graph.positive_windows:
        return []
    by_kind: dict[MarkerKind, list[LifeGraphWindow]] = {}
    for w in graph.positive_windows:
        by_kind.setdefault(w.kind, []).append(w)
    out = [
        "[앞으로의 긍정 창 — 엔진 확정값. 오늘 이후 결혼·취업·이직·재물 유입·이사의 길·혼합 방향 "
        "후보(게이트 이상)를 연속 연도로 묶은 것. 마커 표에 없어도 창 안의 해는 서술 재료로 쓸 수 "
        "있다. 종류마다 **가장 가까운 창부터** 먼저 쓰고, 먼 창만 남겨 늦은 시기만 강조하지 말 것. "
        "한 해짜리 창은 그 해를 중심으로 전후 1년을 함께 보는 활성화 창으로 써도 된다(사건≠결과). "
        "연도·점수는 그대로]",
    ]
    for kind in _POSITIVE_KINDS:
        ws = by_kind.get(kind)
        if not ws:
            continue
        parts = []
        for w in ws[:per_kind]:
            span = (
                f"{w.start_year}년" if w.start_year == w.end_year
                else f"{w.start_year}–{w.end_year}년"
            )
            ages = (
                f"만 {w.start_age}세" if w.start_age == w.end_age
                else f"만 {w.start_age}–{w.end_age}세"
            )
            parts.append(f"{span}({ages}, 최고 {w.peak_year}년 {w.peak_score}점)")
        more = f" 외 {len(ws) - per_kind}개" if len(ws) > per_kind else ""
        out.append(f"- {KIND_KO[kind]}: " + " / ".join(parts) + more)
    return out


def marker_lines(graph: LifeGraph, daewoon_index: int | None = None) -> list[str]:
    """마커를 프롬프트 줄로 — 대운 지정 시 그 대운만. 간지·점수는 엔진값 그대로."""
    out: list[str] = []
    for m in graph.markers:
        if daewoon_index is not None and m.daewoon_index != daewoon_index:
            continue
        risk = " · 위험 신호 동반" if m.risk_backed else ""
        note = f" ({m.note})" if m.note else ""
        out.append(
            f"- {m.year}년(만 {m.age}세, {m.ganji}){when_tag(m.year, graph.today_year)} "
            f"{m.kind_ko} — {m.tone} {m.score}점{risk}{note}"
        )
    return out


def daewoon_summary_lines(graph: LifeGraph) -> list[str]:
    """대운별 한 줄(간지·나이·역할 라벨·상태·마커 종류) — 그래프 해설·요약 카드 공용."""
    status_ko = {"past": "지남", "current": "현재", "future": "예정", "unknown": ""}
    out: list[str] = []
    for d in graph.daewoons:
        kinds = "·".join(dict.fromkeys(m.kind_ko for m in d.markers)) or "두드러진 이벤트 후보 없음"
        tag = status_ko.get(d.status, "")
        out.append(
            f"- {d.ganji}(천간 {d.stem_ten_god}/지지 {d.branch_ten_god}) "
            f"{d.start_age}–{d.end_age}세({d.start_year}–{d.end_year}년)"
            f"{' [' + tag + ']' if tag else ''}"
            f" 〈{d.label or '역할 미상'}〉"
            + (PARTNER_STAR_DAEWOON_TAG if d.partner_star_daewoon else "")
            + f": {kinds}"
        )
    return out
