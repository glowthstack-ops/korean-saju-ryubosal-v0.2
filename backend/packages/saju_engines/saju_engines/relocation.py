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

from saju_shared_types.constants import GENERATES, STEM_ELEMENT
from saju_shared_types.enums import Element, Stem
from saju_shared_types.precompute import CompositeLevel, LuckComposite
from saju_shared_types.relocation import (
    AvoidDate,
    GroupSummary,
    MemberWarning,
    MoveDateCandidate,
    MoveDateScores,
    RelocationQuery,
    RelocationReasonProfile,
    RelocationResult,
)

_TOP_MONTHS = 3
_TOP_DATES = 5
_FAVORABLE = ("용신", "희신")
_UNFAVORABLE = ("기신", "구신")

# 기본 구성원 가중(docs/09 7장): 호주 0.5 / 배우자 0.3 / 기타 균등.
_DEFAULT_W_HEAD = 0.5
_DEFAULT_W_SPOUSE = 0.3

# ── R3 계약일/이삿날 십성 점수표 결합 (date_selection_ten_gods.json) ──

# 십성 → 군(재관 조합 판정용).
_TEN_GOD_GROUP = {
    "비견": "비겁", "겁재": "비겁", "식신": "식상", "상관": "식상",
    "정재": "재성", "편재": "재성", "정관": "관성", "편관": "관성",
    "정인": "인성", "편인": "인성",
}
# 점수→0~100 변환 스케일(초안 — reviewed:false). 정재+30→100, 상관−30→0.
_FIT_SCALE = 30.0
# 사무실 이전(officeMove) 리스트 기반 가감 — 정량 점수 미제공이라 고정 티어(초안, region_fit 선례).
_OFFICE_TIER = 15.0


def load_date_selection_table(dictionaries_dir: Path) -> dict:
    """계약일/이삿날 십성 점수표 로드 (calendar/date_selection_ten_gods.json)."""
    return json.loads(
        (dictionaries_dir / "calendar" / "date_selection_ten_gods.json")
        .read_text("utf-8")
    )


def branch_relations(c: LuckComposite) -> set[str]:
    """일운 지지와 원국 일지·월지의 합·충을 라벨로 판정(택일 점수표 키와 일치).

    합 계열(육합·삼합·방합)은 '일지합/월지합', 충은 '일지충/월지충'으로 매핑한다.
    참여자 소스에 natal_day/natal_month가 있는 상호작용만 본다(원국 자리 자극).
    """
    rels: set[str] = set()
    combine = {"branch_six_combine", "branch_three_combine", "branch_directional"}
    for h in c.interactions:
        sources = {p.source.value for p in h.participants}
        kind = h.kind.value
        if kind == "branch_clash":
            if "natal_day" in sources:
                rels.add("일지충")
            if "natal_month" in sources:
                rels.add("월지충")
        elif kind in combine:
            if "natal_day" in sources:
                rels.add("일지합")
            if "natal_month" in sources:
                rels.add("월지합")
    return rels


def stem_relations(c: LuckComposite) -> set[str]:
    """일운 천간과 원국 일간·월간의 합·극을 라벨로 판정(사무실 이전 월주 평가용).

    합은 '일간합/월간합', 충(천간충=극)은 '일간극/월간극'으로 매핑한다. 월주 생/극(오행)은
    상호작용에 직접 표현되지 않아 현 단계 미반영(검수 대상 — RELOCATION_ENHANCEMENT.md).
    """
    rels: set[str] = set()
    for h in c.interactions:
        sources = {p.source.value for p in h.participants}
        kind = h.kind.value
        if kind == "stem_combine":
            if "natal_day" in sources:
                rels.add("일간합")
            if "natal_month" in sources:
                rels.add("월간합")
        elif kind == "stem_clash":
            if "natal_day" in sources:
                rels.add("일간극")
            if "natal_month" in sources:
                rels.add("월간극")
    return rels


def office_day_fit(c: LuckComposite, office_spec: dict) -> int:
    """사무실 이전 일운 적합도(0~100) — 월주 중심 선호/회피 십성·관계(사용자 스펙 12장).

    officeMove는 정량 점수가 없는 리스트 규격이라 고정 티어(±_OFFICE_TIER)로 가감한다
    (region_fit의 1.0/0.8/0.5 선례). 정재·정관 우대, 상관·겁재·편관 회피, 월지합·월간합
    우대, 월지충·월간극 회피.
    """
    pref_tg = set(office_spec["preferredTenGods"])
    avoid_tg = set(office_spec["avoidTenGods"])
    pref_rel = set(office_spec["preferredRelations"])
    avoid_rel = set(office_spec["avoidRelations"])
    score = 50.0
    for tg in (c.ten_god.stem, c.ten_god.branch_main):
        if tg in pref_tg:
            score += _OFFICE_TIER
        elif tg in avoid_tg:
            score -= _OFFICE_TIER
    for rel in branch_relations(c) | stem_relations(c):
        if rel in pref_rel:
            score += _OFFICE_TIER
        elif rel in avoid_rel:
            score -= _OFFICE_TIER
    return max(0, min(100, round(score)))


def _to_component(points: float) -> float:
    """점수(±) → 0~100(50 중립) 부분 점수."""
    return max(0.0, min(100.0, 50.0 + points * (50.0 / _FIT_SCALE)))


def _combo_points(stem_tg: str, branch_tg: str, combos: dict[str, int]) -> int:
    """이삿날 조합 보너스 — 정재+정관, 재관(재성+관성) 동시 성립 시 가산."""
    pts = 0
    pair = {stem_tg, branch_tg}
    if "정재" in pair and "정관" in pair:
        pts += combos.get("정재+정관", 0)
    groups = {_TEN_GOD_GROUP.get(stem_tg), _TEN_GOD_GROUP.get(branch_tg)}
    if "재성" in groups and "관성" in groups:
        pts += combos.get("재관", 0)
    return pts


def ten_god_day_fit(c: LuckComposite, table: dict) -> int:
    """일운의 천간/지지 십성·관계로 계약일/이삿날 적합도(0~100)를 산출한다.

    작업별 가중(사용자 스펙 11장)으로 축을 결합한다: 계약일은 천간 십성, 이삿날은
    지지 관계에 비중을 둔다. 점수는 코드가 계산한다(절대원칙 1).
    """
    stem_tg = c.ten_god.stem
    branch_tg = c.ten_god.branch_main
    pref = table["preferredTenGods"]
    avoid = table["avoidTenGods"]
    weights = table["weights"]
    rels = branch_relations(c)
    rel_pts = sum(table["branchRelations"].get(r, 0) for r in rels)

    stem_pts = pref.get(stem_tg, 0) + avoid.get(stem_tg, 0)
    rel_component = _to_component(rel_pts)
    stem_component = _to_component(stem_pts)

    if "elementSupport" in weights:  # 계약일 — 천간 오행 가점 + 충돌 회피.
        elem = STEM_ELEMENT[Stem(c.ganji.stem)].value
        elem_pts = table.get("preferredElements", {}).get(elem, 0)
        fit = (
            weights["dayStemTenGod"] * stem_component
            + weights["dayBranchRelation"] * rel_component
            + weights["elementSupport"] * _to_component(elem_pts)
        )
    else:  # 이삿날 — 지지 관계 우세 + 천간/지지 십성 + 재관 조합.
        combo = _combo_points(stem_tg, branch_tg, table.get("preferredCombinations", {}))
        branch_pts = pref.get(branch_tg, 0) + avoid.get(branch_tg, 0) + combo
        fit = (
            weights["dayBranchRelation"] * rel_component
            + weights["dayStemTenGod"] * _to_component(stem_pts + combo)
            + weights["dayBranchTenGod"] * _to_component(branch_pts)
        )
    return max(0, min(100, round(fit)))


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
        # R2 — 십성별 이사 이유·집성격·리스크 분류(해석 라벨 전용, 점수 미개입).
        reason = json.loads(
            (dictionaries_dir / "interpretations" / "relocation_ten_gods.json")
            .read_text("utf-8")
        )
        self._reason_by_ten_god: dict[str, dict] = {
            i["tenGod"]: i for i in reason["items"]
        }
        # R3 — 계약일/이삿날 십성 점수표(S9 계약창 + 택일 엔진 공용).
        self._date_table = load_date_selection_table(dictionaries_dir)

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
        # R2 — 십성 이유분류(해석 라벨 전용 — 위 점수 계산에 미개입).
        reason_profiles = self._reason_profiles(months, composites_by_subject, query)
        return RelocationResult(
            contract_window=contract,
            move_dates=move_dates,
            reason_profiles=reason_profiles,
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

    # ── R3·R4 일운 십성 적합 (집=이삿날 점수표 / 사무실=officeMove) ──

    def _day_fit(self, c: LuckComposite, kind: str) -> int:
        """일운의 십성·관계 적합도(0~100) — relocation_kind로 점수표를 가른다.

        집 이사(home)는 일지 중심 이삿날 점수표, 사무실 이전(office)은 월주 중심
        officeMove 규격을 적용한다(사용자 스펙 11·12장).
        """
        if kind == "office":
            return office_day_fit(c, self._date_table["officeMove"])
        return ten_god_day_fit(c, self._date_table["moveDay"])

    # ── R2 이유분류 (해석 라벨 전용 — 점수 미개입) ──────────────────

    def _reason_profiles(
        self,
        months: list[str],
        composites_by_subject: dict[str, list[LuckComposite]],
        query: RelocationQuery,
    ) -> list[RelocationReasonProfile]:
        """최상위 후보월의 세운·월운 십성으로 이사 이유·집성격·리스크를 분류한다.

        천간=명분(이유) / 지지본기=현장(집 성격)으로 본다(사용자 스펙 5장). 의사결정
        주체(첫 대상 — 대상 우선 원칙 7)의 운만 본다. 후보월이 없으면(이사운 미약) 빈
        리스트. 점수·날짜에 개입하지 않는 해석 라벨 전용(절대원칙 1·12).
        """
        if not months or not query.group_subjects:
            return []
        primary = query.group_subjects[0].label
        comps = composites_by_subject.get(primary, [])
        top_month = months[0]
        year_key = top_month[:4]
        month_comp = next(
            (c for c in comps
             if c.level is CompositeLevel.MONTH and c.period_key == top_month),
            None,
        )
        year_comp = next(
            (c for c in comps
             if c.level is CompositeLevel.YEAR and c.period_key == year_key),
            None,
        )
        # 천간(명분) 먼저, 지지(현장) 다음 — 세운 → 월운 순.
        ordered: list[tuple[str, str | None]] = [
            ("세운 천간(명분)", year_comp.ten_god.stem if year_comp else None),
            ("월운 천간(명분)", month_comp.ten_god.stem if month_comp else None),
            ("세운 지지(현장)", year_comp.ten_god.branch_main if year_comp else None),
            ("월운 지지(현장)", month_comp.ten_god.branch_main if month_comp else None),
        ]
        profiles: list[RelocationReasonProfile] = []
        seen: set[str] = set()
        for source, ten_god in ordered:
            if ten_god is None or ten_god in seen:
                continue
            entry = self._reason_by_ten_god.get(ten_god)
            if entry is None:
                continue
            seen.add(ten_god)
            profiles.append(RelocationReasonProfile(
                ten_god=ten_god,
                source=source,
                type=entry["type"],
                move_reason=entry["moveReason"],
                property_tendency=entry["propertyTendency"],
                risk=entry["risk"],
                required_checks=entry["requiredChecks"],
                risk_level=entry["riskLevel"],
                main_question=entry["mainQuestion"],
            ))
        return profiles

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
                # R3·R4 — 일운 실행 점수에 십성 적합(집=이삿날 점수표 / 사무실=officeMove) 블렌드.
                day_fit = self._day_fit(c, query.relocation_kind)
                day_execution = round(0.5 * _to100(day_exec) + 0.5 * day_fit)

                son = is_son_eomneun_nal(day)  # S7
                calendar_score = 0.1 if son else 0.0

                month_fit = group_scores.get(c.period_key[:7], 0.0)
                scores = MoveDateScores(
                    macro_flow=70,  # S3 통과 월만 진입(통과=허용 흐름) — 초안 고정값
                    month_fit=_to100(month_fit),
                    day_execution=day_execution,
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
        """체인: 최상위 이사일에서 역산해 30~90일 전 계약일을 계약일 점수표로 배치.

        계약일은 정관·정인(서류·약속)을 우대하고 편인·겁재·상관·편관·충을 회피한다
        (사용자 스펙 9장). 충은 탐지엔 긍정이나 택일엔 감점 — 점수표로 자연 반영.
        """
        if not move_dates:
            return []
        anchor = date.fromisoformat(move_dates[0].date)
        lo, hi = anchor - timedelta(days=90), anchor - timedelta(days=30)
        contract_table = self._date_table["contractDay"]
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
                score = ten_god_day_fit(c, contract_table)  # 계약일 십성 적합
                out.append(MoveDateCandidate(
                    date=c.period_key,
                    ganji=f"{c.ganji.stem}{c.ganji.branch}",
                    final_score=score,
                    scores=MoveDateScores(
                        macro_flow=70, month_fit=50, day_execution=score,
                        calendar_rule=50, reality_fit=100, final=score,
                    ),
                    reasons=[
                        f"이사일({move_dates[0].date}) 역산 계약 창 — "
                        f"{c.ten_god.stem}(천간) 계약일 적합 {score}"
                    ],
                ))
        out.sort(key=lambda c: (-c.final_score, c.date))
        return out[:_TOP_DATES]


def _to100(signed: float) -> int:
    """부호화 신호(-1~+1 근방) → 0~100 스케일(50 중립)."""
    return max(0, min(100, round(50 + signed * 50)))
