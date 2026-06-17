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
    DirectionFit,
    HourFit,
)
from saju_shared_types.enums import Branch, Element
from saju_shared_types.events import EventKey
from saju_shared_types.precompute import CompositeLevel, LuckComposite

from .relocation import (
    _signed_weight,
    is_son_eomneun_nal,
    load_date_selection_table,
    office_day_fit,
    ten_god_day_fit,
)

# 목적 → 계약일/이삿날 점수표 키(사용자 스펙 9~11장). 표가 있는 목적만 십성 블렌드.
_TEN_GOD_TABLE_BY_PURPOSE: dict[str, str] = {
    "relocation": "moveDay",
    "contract_document": "contractDay",
}
# 일운 실행 점수 = 도메인 신호 ½ + 십성 적합 ½ (초안 블렌드 — reviewed:false).
_TEN_GOD_BLEND = 0.5

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
        # R3 — 계약일/이삿날 십성 점수표(목적별 day_execution 블렌드용).
        self._date_table = load_date_selection_table(dictionaries_dir)
        holidays = self._read(dictionaries_dir / "calendar" / "holidays.json")
        self._fixed_holidays: dict[str, str] = {
            i["date"]: i["name"] for i in holidays["fixedSolar"]
        }
        # 방위 적합도(S5) — 오행→길방(8방위) 사전. 이사 택일에서 사용자 지정 방위 평가용.
        dirs = self._read(dictionaries_dir / "calendar" / "direction_rules.json")
        self._dir_to_element: dict[str, str] = {
            d: i["element"] for i in dirs["items"] for d in i["directions"]
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
        wealth_element: str | None = None,
        favorability: dict[str, str] | None = None,
        stated_direction: str | None = None,
        relocation_kind: str = "home",
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
        # R3·R4 — 계약일/이삿날이면 십성 점수표를 일운 실행 점수에 블렌드.
        # 이사 목적 + 사무실 이전(office)이면 월주 중심 officeMove 규격을 적용한다.
        table_key = _TEN_GOD_TABLE_BY_PURPOSE.get(str(purpose))
        office_move = (
            str(purpose) == "relocation" and relocation_kind == "office"
        )
        ten_god_table = self._date_table[table_key] if table_key else None
        constraints = reality_constraints or []
        weekend_only = any("주말만" in c for c in constraints)
        # 평일 한정('평일만')은 주말 제외, 평일 선호('평일')는 주말 허용+평일 가점(2026-06-16).
        weekday_only = any("평일만" in c for c in constraints)
        weekday_pref = any("평일 선호" in c for c in constraints)

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
            if weekday_only and is_weekend:
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

            # ⑥ 현실 적합도 — 주말/평일 제약·선호 반영. '평일 선호'는 주말도 허용하되
            # 평일을 가점(70<100)해 주말 편중을 완화한다(2026-06-16 '주말만 추천' 결함 보정).
            if weekday_pref and not (weekend_only or weekday_only):
                reality_fit = 100 if not is_weekend else 70
            else:
                reality_fit = 100  # 한정 제약은 위에서 이미 후보를 걸러냄(통과한 날은 모두 적합)

            # ①~③ 점수. 계약일/이삿날은 일운 실행 점수에 십성 적합을 블렌드.
            day_execution = _to100(_signed_weight(c, domain))
            if office_move:
                fit = office_day_fit(c, self._date_table["officeMove"])
                day_execution = round(
                    (1 - _TEN_GOD_BLEND) * day_execution + _TEN_GOD_BLEND * fit
                )
                reasons.append(f"사무실(월주) 적합 {fit}")
            elif ten_god_table is not None:
                fit = ten_god_day_fit(c, ten_god_table)
                day_execution = round(
                    (1 - _TEN_GOD_BLEND) * day_execution + _TEN_GOD_BLEND * fit
                )
                reasons.append(f"{c.ten_god.stem}/{c.ten_god.branch_main} 십성 적합 {fit}")
            scores = DateScores(
                macro_flow=_to100(years.get(c.period_key[:4], 0.0)),
                month_fit=_to100(months.get(c.period_key[:7], 0.0)),
                day_execution=day_execution,
                calendar_rule=min(100, calendar_score),
                reality_fit=reality_fit,
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
        # 방위: 재물 목적이면 재성 기반(direction_fits), 이사·이동이면 용희기구한 역할 기반
        # 8방위 적합도. 사용자가 방위를 지정했으면(예: 남동) 그 방위의 길흉을 한 줄로 안내한다.
        if wealth_element:
            directions = direction_fits(wealth_element, favorability)
        elif favorability and domain == "relocation":
            directions = self._relocation_directions(favorability)
            verdict = self._stated_direction_caution(stated_direction, favorability)
            if verdict:
                result_cautions.append(verdict)
        else:
            directions = []
        return DateSelectionResult(
            purpose=purpose,
            candidates=picked,
            avoid_dates=avoid_dates,
            cautions=result_cautions,
            directions=directions,
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

    def _relocation_directions(self, favorability: dict[str, str]) -> list[DirectionFit]:
        """이사·이동 8방위 적합도 — 방위 오행의 용희기구한 역할(용신 1.0…구신 0.15)이 기준.

        direction_rules.json(통설 정오행 방위, 검수 대상)을 재사용한다. 재물 가점은 없다 —
        이사는 거처 안정이 목적이라 용·희 방위가 유리, 기·구 방위는 피한다(2026-06-16).
        """
        out: list[DirectionFit] = []
        for direction, element in self._dir_to_element.items():
            role = favorability.get(element, "한신")
            out.append(DirectionFit(
                direction=direction, element=element,
                fit=round(_ROLE_FIT.get(role, 0.55), 2), note=role,
            ))
        out.sort(key=lambda d: -d.fit)
        return out

    def _stated_direction_caution(
        self, stated: str | None, favorability: dict[str, str]
    ) -> str | None:
        """사용자가 지정한 이사 방위(예: 남동)의 길흉을 한 줄로 안내(단정 금지·참고)."""
        if not stated:
            return None
        element = self._dir_to_element.get(stated)
        if element is None:
            return None
        role = favorability.get(element, "한신")
        tone = {
            "용신": "용신 방위로 가장 유리", "희신": "희신 방위로 유리",
            "한신": "무난(특별한 유불리 약함)", "기신": "기신 방위라 권하기 어려움",
            "구신": "구신 방위라 권하기 어려움",
        }.get(role, "무난")
        favs = [d for d, e in self._dir_to_element.items()
                if favorability.get(e) in ("용신", "희신")]
        tail = f" 유리한 방위: {', '.join(favs)}." if favs else ""
        return f"지정 방위 {stated}({element}·{role}) — {tone}.{tail}"

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


# 정오행 방위(方位) — 표준 명리(木동·火남·土중앙·金서·水북).
_ELEMENT_DIRECTION: dict[Element, str] = {
    Element.WOOD: "동", Element.FIRE: "남", Element.EARTH: "중앙",
    Element.METAL: "서", Element.WATER: "북",
}
# 용희기구한 역할별 기본 방위 적합도 — 흉신(기신·구신) 방위는 재물 관련이어도 추천하지 않는다.
_ROLE_FIT: dict[str, float] = {
    "용신": 1.0, "희신": 0.85, "한신": 0.55, "기신": 0.3, "구신": 0.15,
}


def direction_fits(
    wealth_element: str, favorability_by_element: dict[str, str] | None = None
) -> list[DirectionFit]:
    """재물(횡재) 방위 적합도 — **용희기구한 역할**이 기본, 재성/식상(생재)은 유리할 때만 가점.

    정오행 방위(docs/08 D2-5)이되, 방위 오행이 **기신·구신이거나 구신을 생하는** 방향이면 재물
    관련이어도 추천하기 어렵다(2026-06-16 사용자 지적). 따라서 역할(용신 1.0…구신 0.15)을 기준으로
    하고, 재성(+0.1)·식상생재(+0.05) 가점은 역할이 용신/희신/한신일 때만 적용한다. 구신을 생하는
    방위는 0.6배로 감점한다. 당첨 보장이 아니며 번호 생성은 거부한다.
    """
    fav = favorability_by_element or {}
    wealth = Element(wealth_element)
    output = next((e for e in Element if GENERATES[e] is wealth), None)  # 재성을 생하는 식상
    gusin = next((Element(k) for k, v in fav.items() if v == "구신"), None)
    out: list[DirectionFit] = []
    for el, direction in _ELEMENT_DIRECTION.items():
        role = fav.get(el.value, "한신")  # 용신 분석 부재 시 중립 처리
        fit = _ROLE_FIT.get(role, 0.55)
        parts: list[str] = []
        if el is wealth:
            parts.append("재성 방위")
            if role in ("용신", "희신", "한신"):
                fit = min(1.0, fit + 0.1)
        elif output is not None and el is output:
            parts.append("식상(생재) 방위")
            if role in ("용신", "희신", "한신"):
                fit = min(1.0, fit + 0.05)
        parts.append(role)
        if gusin is not None and GENERATES[el] is gusin:  # 구신을 생하는 방위 — 흉신 강화
            fit *= 0.6
            parts.append("구신 생(주의)")
        out.append(DirectionFit(
            direction=direction, element=el.value, fit=round(fit, 2), note=" · ".join(parts),
        ))
    out.sort(key=lambda d: -d.fit)
    return out


def _to100(signed: float) -> int:
    """부호화 신호(−1~+1 근방) → 0~100(50 중립)."""
    return max(0, min(100, round(50 + signed * 50)))
