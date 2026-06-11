"""이사 Composite Resolver — M10 (v2.2 Phase 2.5 T2.5.7, docs/09 7장 전체 사양).

처리 단계 S1~S10은 순서 고정이며 전부 코드 계산이다(LLM 조합 판단 금지, 절대 원칙 9).

  S1  구성원별 이동운 시계열 (month-level relocation DomainSignal)
  S2  그룹 집계 (aggregationRule + weights) + 구성원 경고
  S3  월 후보 확정 (group 상위 + macro flow 통과)
  S4  일 후보 생성 (day-level dayExecutionScore)
  S5  방위 적합 (direction_rules × region_elements — 방위 미정이면 분리 산출)
  S6  주거 타입 보정 (housing_rules — 정의된 최소 규칙만, 신축/구축 0 보정)
  S7  Calendar Rule (손없는 날=음력 끝자리 9·0, 주말 표기, 충+기신일 회피)
  S8  Reality Constraint 필터 (주말만 등)
  S9  체인 스케줄 (이사 창 확정 → 계약 창 배치 — 기본형)
  S10 최종 랭킹 (부분점수 5종 합성)

가중 계수는 전부 초안(reviewed:false 사전 + 코드 상수) — 실테스트로 조정한다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from korean_lunar_calendar import KoreanLunarCalendar

from saju_shared_types.constants import GENERATES
from saju_shared_types.enums import Element
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.relocation import (
    AvoidDate,
    GroupSummary,
    MemberWarning,
    MoveDateCandidate,
    MoveDateScores,
    RelocationQuery,
    RelocationResult,
)

_TOP_MONTHS = 3
_TOP_DATES = 5
_FAVORABLE = ("용신", "희신")
_UNFAVORABLE = ("기신", "구신")

# 기본 구성원 가중(docs/09 7장): 호주 0.5 / 배우자 0.3 / 기타 균등.
_DEFAULT_W_HEAD = 0.5
_DEFAULT_W_SPOUSE = 0.3


def _signed_weight(c: LuckComposite, domain: str) -> float:
    """도메인 신호 합 — 기간 favorability로 부호화(용·희 +, 기·구 −, 한신 절반)."""
    total = sum(s.weight for s in c.domain_signals if s.domain == domain)
    if c.favorability in _FAVORABLE:
        return total
    if c.favorability in _UNFAVORABLE:
        return -total
    return total * 0.5


def _member_weights(query: RelocationQuery) -> dict[str, float]:
    """구성원별 가중 — 명시 weights 우선, 없으면 규칙 기본값."""
    labels = [s.label for s in query.group_subjects]
    if query.weights:
        return {label: query.weights.get(label, 0.0) for label in labels}
    if len(labels) == 1:
        return {labels[0]: 1.0}
    rest = labels[2:]
    weights = {labels[0]: _DEFAULT_W_HEAD}
    if len(labels) >= 2:
        weights[labels[1]] = _DEFAULT_W_SPOUSE
    remain = max(1.0 - sum(weights.values()), 0.0)
    for label in rest:
        weights[label] = remain / len(rest)
    return weights


def is_son_eomneun_nal(day: date) -> bool:
    """손없는 날 — 음력 일(日) 끝자리 9·0 (민속 규칙, 명리 계산 아님)."""
    cal = KoreanLunarCalendar()
    cal.setSolarDate(day.year, day.month, day.day)
    return cal.lunarDay % 10 in (9, 0)


class RelocationResolver:
    """M10 이사 복합 해석기 — 동일 입력 → 동일 출력(결정론)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """방위/지역오행/주거 사전 로드."""
        cal_dir = dictionaries_dir / "calendar"
        directions = json.loads(
            (cal_dir / "direction_rules.json").read_text("utf-8")
        )
        self._dir_by_element: dict[str, list[str]] = {
            i["element"]: i["directions"] for i in directions["items"]
        }
        self._all_directions: list[str] = directions["allDirections"]
        regions = json.loads(
            (dictionaries_dir / "region_elements.json").read_text("utf-8")
        )
        self._region_element: dict[str, str] = {
            i["region"]: i["element"] for i in regions["items"]
        }
        housing = json.loads(
            (dictionaries_dir / "housing_rules.json").read_text("utf-8")
        )
        self._housing: dict[str, dict[str, float]] = {
            i["housingType"]: i["domainWeights"] for i in housing["items"]
        }

    # ── 공개 API ─────────────────────────────────────────────────

    def resolve(
        self,
        query: RelocationQuery,
        composites_by_subject: dict[str, list[LuckComposite]],
        yongsin_by_subject: dict[str, str],
    ) -> RelocationResult:
        """S1~S10 실행.

        Args:
            query: 이사 질의(기간·그룹·제약).
            composites_by_subject: 대상 라벨 → LuckComposite 목록(T1·T2 데이터).
            yongsin_by_subject: 대상 라벨 → 용신 오행(한자, T0 데이터).

        Returns:
            이사일 랭킹 + 그룹 요약 + 회피일(설명할 결론 — LLM 입력용).
        """
        weights = _member_weights(query)

        # S1 — 구성원별 월 시계열.
        member_series = {
            label: self._month_series(comps, query)
            for label, comps in composites_by_subject.items()
        }
        # S2 — 그룹 집계 + 경고.
        group_scores, warnings, conflicts = self._aggregate_group(
            member_series, weights, query.aggregation_rule
        )
        # S3 — 월 후보 (상위 + macro flow 통과).
        months = self._candidate_months(group_scores, composites_by_subject, query)
        # S4~S8 — 일 후보 생성·보정·필터.
        candidates, avoid = self._day_candidates(
            months, group_scores, composites_by_subject, query,
            yongsin_by_subject, warnings,
        )
        # S10 — 최종 랭킹.
        candidates.sort(key=lambda c: (-c.final_score, c.date))
        move_dates = candidates[:_TOP_DATES]

        # S9 — 체인 모드: 이사 창 확정 후 계약 창 배치(문서운 기준 기본형).
        contract = (
            self._contract_window(move_dates, composites_by_subject, query)
            if query.chained_schedule
            else []
        )
        return RelocationResult(
            contract_window=contract,
            move_dates=move_dates,
            group_summary=GroupSummary(monthly_scores=group_scores, conflicts=conflicts),
            avoid_dates=avoid,
        )

    # ── S1 ──────────────────────────────────────────────────────

    def _month_series(
        self, comps: list[LuckComposite], query: RelocationQuery
    ) -> dict[str, float]:
        """월 키 → 이동운 점수(부호화)."""
        return {
            c.period_key: _signed_weight(c, "relocation")
            for c in comps
            if c.level is CompositeLevel.MONTH
            and query.period.start <= c.period_key <= query.period.end
        }

    # ── S2 ──────────────────────────────────────────────────────

    def _aggregate_group(
        self,
        member_series: dict[str, dict[str, float]],
        weights: dict[str, float],
        rule: str,
    ) -> tuple[dict[str, float], list[MemberWarning], list[str]]:
        """그룹 월 점수 + 구성원 경고 + 충돌 월."""
        all_months = sorted({m for s in member_series.values() for m in s})
        group: dict[str, float] = {}
        warnings: list[MemberWarning] = []
        conflicts: list[str] = []
        for month in all_months:
            per_member = {
                label: series.get(month, 0.0)
                for label, series in member_series.items()
            }
            if rule == "protect_weakest":
                group[month] = min(per_member.values())
            elif rule == "balanced":
                group[month] = sum(per_member.values()) / len(per_member)
            else:  # householder_primary
                group[month] = sum(
                    score * weights.get(label, 0.0)
                    for label, score in per_member.items()
                )
            negatives = [label for label, sc in per_member.items() if sc < 0]
            if negatives and group[month] > 0:
                conflicts.append(month)
                warnings.extend(
                    MemberWarning(
                        subject_label=label, signal=f"{month} 이동운 충돌(음수 신호)"
                    )
                    for label in negatives
                )
        return group, warnings, conflicts

    # ── S3 ──────────────────────────────────────────────────────

    def _candidate_months(
        self,
        group_scores: dict[str, float],
        composites_by_subject: dict[str, list[LuckComposite]],
        query: RelocationQuery,
    ) -> list[str]:
        """그룹 상위 월 중 macro flow(대운/세운 허용) 통과 월."""
        ranked = sorted(group_scores, key=lambda m: -group_scores[m])
        out: list[str] = []
        for month in ranked:
            if self._macro_pass(month, composites_by_subject):
                out.append(month)
            if len(out) >= _TOP_MONTHS:
                break
        return out

    def _macro_pass(
        self, month: str, composites_by_subject: dict[str, list[LuckComposite]]
    ) -> bool:
        """세운 이동운이 강한 음수면 큰 흐름이 막는 것으로 본다(초안 기준)."""
        year_key = month[:4]
        for comps in composites_by_subject.values():
            for c in comps:
                if c.level is CompositeLevel.YEAR and c.period_key == year_key:
                    if _signed_weight(c, "relocation") < -0.3:
                        return False
        return True

    # ── S4~S8 ────────────────────────────────────────────────────

    def _day_candidates(
        self,
        months: list[str],
        group_scores: dict[str, float],
        composites_by_subject: dict[str, list[LuckComposite]],
        query: RelocationQuery,
        yongsin_by_subject: dict[str, str],
        warnings: list[MemberWarning],
    ) -> tuple[list[MoveDateCandidate], list[AvoidDate]]:
        """후보 월 내 일 후보 — 점수 합성과 필터."""
        direction_fit = self._direction_fit(query, yongsin_by_subject)  # S5
        housing = self._housing.get(query.housing_type or "", {})  # S6
        weekend_only = any("주말" in c for c in query.reality_constraints)  # S8

        candidates: list[MoveDateCandidate] = []
        avoid: list[AvoidDate] = []
        seen_days: set[str] = set()
        for comps in composites_by_subject.values():
            for c in comps:
                if c.level is not CompositeLevel.DAY or c.period_key in seen_days:
                    continue
                if c.period_key[:7] not in months:
                    continue
                seen_days.add(c.period_key)
                day = date.fromisoformat(c.period_key)

                # S7 — 회피일: 기신 기조 + 충 계열 상호작용.
                clashes = [
                    h.relation_id for h in c.interactions
                    if h.kind.value in ("branch_clash", "stem_clash")
                ]
                if c.favorability in _UNFAVORABLE and clashes:
                    avoid.append(AvoidDate(
                        date=c.period_key,
                        reason=f"기신 기조 + 충({', '.join(clashes)})",
                    ))
                    continue

                # S8 — 현실 제약.
                is_weekend = day.weekday() >= 5
                if weekend_only and not is_weekend:
                    continue

                day_exec = _signed_weight(c, "relocation")  # S4
                for domain, w in housing.items():  # S6
                    day_exec += _signed_weight(c, domain) * w

                son = is_son_eomneun_nal(day)  # S7
                calendar_score = 0.1 if son else 0.0

                month_fit = group_scores.get(c.period_key[:7], 0.0)
                scores = MoveDateScores(
                    macro_flow=70,  # S3 통과 월만 진입(통과=허용 흐름) — 초안 고정값
                    month_fit=_to100(month_fit),
                    day_execution=_to100(day_exec),
                    calendar_rule=_to100(calendar_score),
                    reality_fit=100 if (not weekend_only or is_weekend) else 0,
                    final=0,
                )
                final = round(
                    0.20 * scores.macro_flow + 0.25 * scores.month_fit
                    + 0.35 * scores.day_execution + 0.10 * scores.calendar_rule
                    + 0.10 * scores.reality_fit
                )
                scores.final = max(0, min(100, final))
                reasons = [f"{c.period_key[:7]} 그룹 이동운 {month_fit:+.2f}"]
                if son:
                    reasons.append("손없는 날")
                candidates.append(MoveDateCandidate(
                    date=c.period_key,
                    ganji=f"{c.ganji.stem}{c.ganji.branch}",
                    final_score=scores.final,
                    scores=scores,
                    direction_fit=direction_fit,
                    member_warnings=[
                        w for w in warnings if w.signal.startswith(c.period_key[:7])
                    ],
                    son_eomneun_nal=son,
                    reasons=reasons,
                ))
        return candidates, avoid

    # ── S5 ──────────────────────────────────────────────────────

    def _direction_fit(
        self, query: RelocationQuery, yongsin_by_subject: dict[str, str]
    ) -> dict[str, float]:
        """방위별 적합도 — 미지정이면 8방위 전부 분리 산출(단일 답 강제 금지)."""
        directions = query.candidate_directions or self._all_directions
        fit: dict[str, float] = {}
        members = [s.label for s in query.group_subjects]
        for d in directions:
            scores: list[float] = []
            for label in members:
                yongsin = yongsin_by_subject.get(label)
                favorable = self._dir_by_element.get(yongsin or "", [])
                scores.append(1.0 if d in favorable else 0.5)
            fit[d] = round(sum(scores) / len(scores), 3) if scores else 0.5
        return fit

    def region_fit(
        self, regions: list[str], yongsin_by_subject: dict[str, str]
    ) -> dict[str, float]:
        """후보 지역 오행 × 구성원 용신 적합(동일 1.0 / 용신을 생 0.8 / 그 외 0.5).

        미등재 지역은 보정 없음(0.5 중립) — region_elements는 전 항목 검수 전 출시 금지.
        """
        out: dict[str, float] = {}
        for region in regions:
            element = self._region_element.get(region)
            if element is None:
                out[region] = 0.5
                continue
            scores: list[float] = []
            for yongsin in yongsin_by_subject.values():
                if element == yongsin:
                    scores.append(1.0)
                elif yongsin and GENERATES[Element(element)] == Element(yongsin):
                    scores.append(0.8)
                else:
                    scores.append(0.5)
            out[region] = round(sum(scores) / len(scores), 3) if scores else 0.5
        return out

    # ── S9 ──────────────────────────────────────────────────────

    def _contract_window(
        self,
        move_dates: list[MoveDateCandidate],
        composites_by_subject: dict[str, list[LuckComposite]],
        query: RelocationQuery,
    ) -> list[MoveDateCandidate]:
        """체인 기본형: 최상위 이사일에서 역산해 30~90일 전 문서운 좋은 날 배치."""
        if not move_dates:
            return []
        anchor = date.fromisoformat(move_dates[0].date)
        lo, hi = anchor - timedelta(days=90), anchor - timedelta(days=30)
        out: list[MoveDateCandidate] = []
        seen: set[str] = set()
        for comps in composites_by_subject.values():
            for c in comps:
                if c.level is not CompositeLevel.DAY or c.period_key in seen:
                    continue
                seen.add(c.period_key)
                day = date.fromisoformat(c.period_key)
                if not lo <= day <= hi:
                    continue
                doc = _signed_weight(c, "wealth")  # 문서운(document→wealth 도메인)
                score = _to100(doc)
                out.append(MoveDateCandidate(
                    date=c.period_key,
                    ganji=f"{c.ganji.stem}{c.ganji.branch}",
                    final_score=score,
                    scores=MoveDateScores(
                        macro_flow=70, month_fit=50, day_execution=score,
                        calendar_rule=50, reality_fit=100, final=score,
                    ),
                    reasons=[f"이사일({move_dates[0].date}) 역산 계약 창"],
                ))
        out.sort(key=lambda c: (-c.final_score, c.date))
        return out[:_TOP_DATES]


def _to100(signed: float) -> int:
    """부호화 신호(-1~+1 근방) → 0~100 스케일(50 중립)."""
    return max(0, min(100, round(50 + signed * 50)))
