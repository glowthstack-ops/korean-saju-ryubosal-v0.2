"""Date Selection Engine — E10 택일 + E10-a Calendar Rule + E10-b Risk Avoidance
(v2.2 Phase 7 T7.1~T7.4·T7.7).

계산 순서(docs/02 E10 — 고정): ① 대운/세운 macro flow ② 월운 적합 ③ 일운 실행 점수
④ 금기일/회피일 필터 ⑤ 손없는 날/공휴일/요일 ⑥ 현실 제약 ⑦ 목적별 가중 합산 랭킹.
모든 계산은 코드가 한다(LLM은 결론 서술만 — 절대 원칙 9).

시진(T7.7): 일 아래 12시진 적합도 — 시지 오행 × 용신(동일 1.0/생용신 0.8/기신 0.3).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from saju_shared_types.constants import BRANCH_ELEMENT, GENERATES
from saju_shared_types.date_selection import (
    DateCandidate,
    DateScores,
    DateSelectionResult,
    HourFit,
)
from saju_shared_types.enums import Branch, Element
from saju_shared_types.events import EventKey
from saju_shared_types.precompute import CompositeLevel, LuckComposite

from .relocation import _signed_weight, is_son_eomneun_nal

# 12시진 — 지지별 시간대(子시는 23~01시).
_HOUR_RANGES: list[tuple[str, str]] = [
    ("子", "23:00~01:00"), ("丑", "01:00~03:00"), ("寅", "03:00~05:00"),
    ("卯", "05:00~07:00"), ("辰", "07:00~09:00"), ("巳", "09:00~11:00"),
    ("午", "11:00~13:00"), ("未", "13:00~15:00"), ("申", "15:00~17:00"),
    ("酉", "17:00~19:00"), ("戌", "19:00~21:00"), ("亥", "21:00~23:00"),
]

_VOLATILITY_CAUTION = (
    "당첨·수익 단정 불가 — 단기 재물 변동성과 투기 충동이 함께 커지는 시기일 수 있어 "
    "과몰입을 주의하세요. 본 추천은 투자 조언이 아닙니다."
)


class DateSelectionEngine:
    """목적별 택일 — purpose_profiles/avoid_days/holidays 사전 기반(결정론)."""

    def __init__(self, dictionaries_dir: Path) -> None:
        """사전 로드: 목적 프로파일·금기일 규칙·공휴일."""
        profiles = self._read(dictionaries_dir / "purpose_profiles.json")
        self._profiles: dict[str, dict] = {i["purpose"]: i for i in profiles["items"]}
        avoid = self._read(dictionaries_dir / "calendar" / "avoid_days.json")
        self._avoid_rules: list[dict] = avoid["rules"]
        holidays = self._read(dictionaries_dir / "calendar" / "holidays.json")
        self._fixed_holidays: dict[str, str] = {
            i["date"]: i["name"] for i in holidays["fixedSolar"]
        }

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ── 공개 API (T7.3) ──────────────────────────────────────────

    def select(
        self,
        purpose: EventKey,
        composites: list[LuckComposite],
        start: str,
        end: str,
        yongsin_element: str | None = None,
        reality_constraints: list[str] | None = None,
        include_hour_fit: bool = False,
        top_n: int = 5,
    ) -> DateSelectionResult:
        """기간 [start, end](ISO 일자) 안에서 목적별 실행일을 랭킹한다.

        Args:
            purpose: 택일 목적(EventKey — purpose_profiles 키).
            composites: 대상의 LuckComposite(연/월/일 — Precompute Store 데이터).
            start, end: 후보 일자 범위.
            yongsin_element: 용신 오행(시진 적합도용 — T0 데이터).
            reality_constraints: 현실 제약("주말만 가능" 등) — T7.4.
            include_hour_fit: True면 상위 후보에 12시진 적합도 동반(T7.7).
            top_n: 반환 후보 수.
        """
        profile = self._profiles.get(str(purpose)) or self._profiles["relocation"]
        weights = profile["weights"]
        options = profile["options"]
        domain = profile.get("domainOverride", "relocation")
        constraints = reality_constraints or []
        weekend_only = any("주말" in c for c in constraints)

        years = {
            c.period_key: _signed_weight(c, domain)
            for c in composites if c.level is CompositeLevel.YEAR
        }
        months = {
            c.period_key: _signed_weight(c, domain)
            for c in composites if c.level is CompositeLevel.MONTH
        }

        candidates: list[DateCandidate] = []
        avoid_dates: list[dict] = []
        for c in composites:
            if c.level is not CompositeLevel.DAY:
                continue
            if not (start <= c.period_key <= end):
                continue
            day = date.fromisoformat(c.period_key)

            # ④ 금기일/회피일 필터(E10-b) — 룰 사전 기반.
            avoid_reason = self._avoid_reason(c, str(purpose), options)
            if avoid_reason:
                avoid_dates.append({"date": c.period_key, "reason": avoid_reason})
                continue

            # ⑥ Reality Constraint(T7.4) — 가능한 날 중 가장 좋은 날.
            is_weekend = day.weekday() >= 5
            if weekend_only and not is_weekend:
                continue

            # ⑤ Calendar Rule(E10-a): 손없는 날·공휴일·요일.
            son = is_son_eomneun_nal(day)
            holiday_name = self._fixed_holidays.get(day.strftime("%m-%d"))
            calendar_score = 50
            reasons: list[str] = []
            if son and options.get("sonEomneunNalBonus"):
                calendar_score += 30
                reasons.append("손없는 날")
            if holiday_name:
                calendar_score += 10
                reasons.append(f"공휴일({holiday_name})")

            # ①~③ 점수.
            scores = DateScores(
                macro_flow=_to100(years.get(c.period_key[:4], 0.0)),
                month_fit=_to100(months.get(c.period_key[:7], 0.0)),
                day_execution=_to100(_signed_weight(c, domain)),
                calendar_rule=min(100, calendar_score),
                reality_fit=100 if (not weekend_only or is_weekend) else 0,
                final=0,
            )
            # ⑦ 목적별 가중 합산.
            final = round(
                scores.macro_flow * weights["macroFlow"]
                + scores.month_fit * weights["monthFit"]
                + scores.day_execution * weights["dayExecution"]
                + scores.calendar_rule * weights["calendarRule"]
                + scores.reality_fit * weights["realityFit"]
            )
            scores.final = max(0, min(100, final))

            risk = self._risk_score(c)
            cautions: list[str] = []
            if options.get("volatilityWarning"):
                cautions.append(_VOLATILITY_CAUTION)
            candidates.append(DateCandidate(
                date=c.period_key,
                purpose=purpose,
                ganji=f"{c.ganji.stem}{c.ganji.branch}",
                scores=scores,
                risk_score=risk,
                reasons=reasons or [f"{domain} 신호 기반"],
                cautions=cautions,
                recommendation=(
                    "recommended" if scores.final >= 70 and risk < 40
                    else "avoid" if risk >= 70 else "acceptable"
                ),
                is_holiday=holiday_name is not None,
                is_weekend=is_weekend,
                son_eomneun_nal=son,
            ))

        candidates.sort(key=lambda c: (-c.scores.final, c.date))
        picked = candidates[:top_n]
        if include_hour_fit and yongsin_element:
            picked = [
                c.model_copy(update={"hour_fits": hour_fits(yongsin_element)})
                for c in picked
            ]
        result_cautions = (
            [_VOLATILITY_CAUTION] if options.get("volatilityWarning") else []
        )
        return DateSelectionResult(
            purpose=purpose,
            candidates=picked,
            avoid_dates=avoid_dates,
            cautions=result_cautions,
        )

    # ── E10-b Risk Avoidance(T7.2) ───────────────────────────────

    def _avoid_reason(
        self, c: LuckComposite, purpose: str, options: dict
    ) -> str | None:
        """금기일 규칙(avoid_days.json) — 해당 목적에 적용되는 첫 규칙 사유 반환."""
        if not options.get("avoidClash", True):
            return None
        kinds = {h.kind.value for h in c.interactions}
        for rule in self._avoid_rules:
            if purpose not in rule["appliesTo"]:
                continue
            cond = rule["condition"]
            fav_ok = (
                "favorability" not in cond or c.favorability in cond["favorability"]
            )
            kind_hit = bool(kinds & set(cond["interactionKinds"]))
            if fav_ok and kind_hit:
                return rule["ko"]
        return None

    @staticmethod
    def _risk_score(c: LuckComposite) -> int:
        """일운 위험도 — 충·형 계열 상호작용 수 기반(0~100, 초안)."""
        risky = sum(
            1 for h in c.interactions
            if h.kind.value in (
                "branch_clash", "stem_clash", "branch_punish", "self_punish", "wonjin",
            )
        )
        return min(100, risky * 30)


# ── T7.7 시진 적합도 ─────────────────────────────────────────────


def hour_fits(yongsin_element: str) -> list[HourFit]:
    """12시진 적합도 — 시지 오행 × 용신(동일 1.0 / 생용신 0.8 / 그 외 0.5).

    "기묘일에 로또 사러 가기 좋은 시간대"(docs/08 C17) 류의 시(時) 단위 요청 대응.
    """
    out: list[HourFit] = []
    target = Element(yongsin_element)
    for branch_str, time_range in _HOUR_RANGES:
        el = BRANCH_ELEMENT[Branch(branch_str)]
        if el is target:
            fit, note = 1.0, f"용신 {yongsin_element} 기운의 시간대"
        elif GENERATES[el] is target:
            fit, note = 0.8, f"용신 {yongsin_element}을 생하는 시간대"
        else:
            fit, note = 0.5, ""
        out.append(HourFit(
            branch=branch_str, time_range=time_range, fit=fit, note=note,
        ))
    return out


def _to100(signed: float) -> int:
    """부호화 신호(−1~+1 근방) → 0~100(50 중립)."""
    return max(0, min(100, round(50 + signed * 50)))
