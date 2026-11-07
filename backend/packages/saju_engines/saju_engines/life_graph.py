"""인생 그래프(총운 개편, 2026-11-07 데굴님 결정) — 대운 곡선 + 세운 선 + 주요 이벤트 마커.

총운(RPT_FULL)의 2부 "내 인생의 흐름"에서 LLM과 무관하게 **엔진이 확정**하는 구조 데이터.
그래프 자체는 프론트가 그리고(SVG), 같은 데이터가 대운별 상세 페이지(F-14-D*)와 인생 흐름
종합(F-14b)·요약 카드(F-21)의 마커 목록으로 쓰여 그림과 글이 어긋나지 않는다.

원칙:
- 점수·사건은 전 생애 연 단위 재채점(`lifetime_scan`, 대운표 sewoon 재사용)의 후보를 그대로
  쓴다 — 여기서 재계산하지 않는다(절대원칙 9).
- 마커 종류는 데굴님이 든 5종으로 고정: 결혼·취업·이직·이사·위기(건강/금전 두 갈래).
- 선별은 대운 단위(한 대운 안의 세운이 그 대운의 주요 이벤트를 정한다): 대운당 최대
  `PER_DAEWOON_CAP`, 같은 종류 최대 `PER_KIND_CAP`, 품질 게이트 `SCORE_GATE`(총운 다변화의
  절대 게이트와 같은 55). 빈 대운은 비워 둔다(무신호 강제 충원 금지).
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
    LifeGraphYear,
    MarkerKind,
)
from saju_shared_types.manse_result import ManseV2Result

from .context_reducer import overview_cluster_key

#: 사건 키 → 마커 종류. 금전 위기는 재물 변화 중 흉 방향만(아래 `_marker_kind`).
_EVENT_TO_KIND: dict[str, MarkerKind] = {
    "marriage_signal": MarkerKind.MARRIAGE,
    "job_gain": MarkerKind.JOB,
    "career_change": MarkerKind.CAREER_CHANGE,
    "relocation": MarkerKind.RELOCATION,
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
    MarkerKind.CRISIS_HEALTH: "건강 위기",
    MarkerKind.CRISIS_MONEY: "금전 위기",
}
_TONE_KO = {"pos": "길", "neg": "주의", "mixed": "혼합"}
SCORE_GATE = 55
PER_DAEWOON_CAP = 4
PER_KIND_CAP = 2
#: 위험 신호 동반 시 게이트 판정에 더하는 우선순위(저장 점수는 불변).
RISK_PRIORITY_BONUS = 10
#: 종류별 나이 타당성(만 나이, 서술 현실성 규칙 — 명리 판정 아님). 범위 밖은 마커에서 뺀다.
#: 결혼·취업은 성인부터, 이직은 첫 직장 이후, 취업·이직은 통상 경제활동 연령 안에서만
#: (2026-11-07 dry-run: 만 6세 이직·88세 이직 마커가 나와 추가). 이사·위기는 전 연령.
KIND_AGE_RANGE: dict[MarkerKind, tuple[int, int]] = {
    MarkerKind.MARRIAGE: (18, 100),
    MarkerKind.JOB: (18, 70),
    MarkerKind.CAREER_CHANGE: (20, 70),
    MarkerKind.RELOCATION: (0, 100),
    MarkerKind.CRISIS_HEALTH: (0, 100),
    MarkerKind.CRISIS_MONEY: (0, 100),
}
MINOR_AGE = 18
#: 미성년 시기의 이사·금전 위기는 본인 사건이 아니라 가족 단위 사건으로 읽는다(서술 메모).
MINOR_NOTE = "미성년 — 가족(부모) 단위의 이동·형편으로 읽을 것"


def _marker_kind(c: EventCandidate, age: int) -> MarkerKind | None:
    """후보의 마커 종류 — 위기(건강·금전)는 흉 방향(주의·혼합)만, 종류별 나이 범위 밖은 제외."""
    kind = _EVENT_TO_KIND.get(str(c.event_key))
    if kind is None:
        return None
    if (
        kind in (MarkerKind.CRISIS_MONEY, MarkerKind.CRISIS_HEALTH)
        and overview_cluster_key(c)[1] == "pos"
    ):
        return None
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
) -> LifeGraph | None:
    """전 생애 후보 풀 → 인생 그래프 데이터.

    Args:
        result: 본인 명식(대운표·현재 대운 판정 원천).
        lifetime_result: 전 생애 세운이 병합된 결과(연도별 세운 점수·라벨 원천).
        pool: 전 생애 연 단위 후보(기간 라벨 4자리).
        lo_year: 출생 연도(창 시작). hi_year: 창 끝(90세).
        risk_years: 연도 → 위험 도메인 집합(위험 엔진 shadow, 선택).

    Returns:
        LifeGraph — 대운표가 없으면 None.
    """
    lc = result.luck_cycles
    lt = lifetime_result.luck_cycles
    if lc is None or lt is None or not lc.daewoon_table:
        return None
    cur = lc.current_daewoon_index
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
        ))
    years = [
        LifeGraphYear(
            year=y, age=y - lo_year, ganji=p.ganji, score=round(float(p.luck_score), 3),
            label=p.luck_label,
        )
        for y in range(lo_year, hi_year + 1)
        if (p := years_by_label.get(str(y))) is not None
    ]
    return LifeGraph(
        birth_year=lo_year, end_year=hi_year, current_daewoon_index=cur,
        daewoons=daewoons, years=years, markers=all_markers,
    )


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

    picked: list[LifeGraphMarker] = []
    per_kind: dict[MarkerKind, int] = {}
    for (y, kind), c in sorted(best.items(), key=priority):
        risk_hit = kind in {
            _RISK_DOMAIN_TO_KIND[d] for d in risk_map.get(y, set()) if d in _RISK_DOMAIN_TO_KIND
        }
        if c.score + (RISK_PRIORITY_BONUS if risk_hit else 0) < SCORE_GATE:
            continue
        if per_kind.get(kind, 0) >= PER_KIND_CAP:
            continue
        pillar = years_by_label.get(str(y))
        age = y - birth_year
        note = (
            MINOR_NOTE
            if age < MINOR_AGE and kind in (MarkerKind.RELOCATION, MarkerKind.CRISIS_MONEY)
            else ""
        )
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
        if len(picked) >= PER_DAEWOON_CAP:
            break
    return sorted(picked, key=lambda m: (m.year, m.kind.value))


def marker_lines(graph: LifeGraph, daewoon_index: int | None = None) -> list[str]:
    """마커를 프롬프트 줄로 — 대운 지정 시 그 대운만. 간지·점수는 엔진값 그대로."""
    out: list[str] = []
    for m in graph.markers:
        if daewoon_index is not None and m.daewoon_index != daewoon_index:
            continue
        risk = " · 위험 신호 동반" if m.risk_backed else ""
        note = f" ({m.note})" if m.note else ""
        out.append(
            f"- {m.year}년(만 {m.age}세, {m.ganji}) {m.kind_ko} — {m.tone} {m.score}점{risk}{note}"
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
            f" 〈{d.label or '역할 미상'}〉: {kinds}"
        )
    return out
