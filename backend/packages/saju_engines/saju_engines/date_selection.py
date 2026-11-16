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

from saju_manse_analysis.luck.luck_calendar import luck_month_label, sewoon_year_of
from saju_manse_analysis.yongsin.operational_role_config import (
    is_favorable_role,
    is_unfavorable_role,
)

from saju_manse_core.calendar.solar_terms import get_table
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
from saju_shared_types.precompute import CompositeLevel, InteractionHit, LuckComposite

from . import period_v2_config
from .folk_direction import folk_note_for_day
from .relocation import (
    _signed_weight,
    is_son_eomneun_nal,
    load_date_selection_table,
    office_day_fit,
    ten_god_day_fit,
)
from .windfall_lens import windfall_day_lens

# 목적 → 계약일/이삿날 점수표 키(사용자 스펙 9~11장). 표가 있는 목적만 십성 블렌드.
_TEN_GOD_TABLE_BY_PURPOSE: dict[str, str] = {
    "relocation": "moveDay",
    "contract_document": "contractDay",
}
# 일운 실행 점수 = 도메인 신호 ½ + 십성 적합 ½ (초안 블렌드 — reviewed:false).
_TEN_GOD_BLEND = 0.5

# 12시진 — 지지별 시간대(子시는 23~01시).
_HOUR_RANGES: list[tuple[str, str]] = [
    ("子", "23:00–01:00"), ("丑", "01:00–03:00"), ("寅", "03:00–05:00"),
    ("卯", "05:00–07:00"), ("辰", "07:00–09:00"), ("巳", "09:00–11:00"),
    ("午", "11:00–13:00"), ("未", "13:00–15:00"), ("申", "15:00–17:00"),
    ("酉", "17:00–19:00"), ("戌", "19:00–21:00"), ("亥", "21:00–23:00"),
]

_VOLATILITY_CAUTION = (
    "당첨·수익 단정 불가 — 단기 재물 변동성과 투기 충동이 함께 커지는 시기일 수 있어 "
    "과몰입을 주의하세요. 본 추천은 투자 조언이 아닙니다."
)
# 도메인 영문 enum → 한글(택일 사유에 'wealth 신호' 같은 내부값이 노출되던 결함 차단, 2026-07-01).
_DOMAIN_KO: dict[str, str] = {
    "relocation": "이사", "wealth": "재물", "career": "직업", "relationship": "관계",
    "health": "건강", "education": "학업", "general": "전반",
}


#: 위험도에 드는 관계 종류(충·형·원진 계열) — `_risk_score` 와 표 사유가 같은 목록을 쓴다.
_RISK_KINDS = frozenset({
    "branch_clash", "stem_clash", "branch_punish", "self_punish", "wonjin",
})
#: 관계 ID 꼬리(한자) → 한글 종류. 긴 꼬리를 먼저 본다('自刑'이 '刑'보다 앞).
_RELATION_TAIL_KO: tuple[tuple[str, str], ...] = (
    ("自刑", "자형"), ("三刑", "삼형"), ("三合", "삼합"), ("方合", "방합"), ("怨嗔", "원진"),
    ("合", "합"), ("沖", "충"), ("刑", "형"), ("破", "파"), ("害", "해"),
)
#: 등급 기준(2026-11-16) — [추천] 조건 안내. 목적 옵션에 따라 둘 중 하나를 싣는다.
#: 실답: 재물 신호 0건·천간 기신인 날이 중립 50점으로 추천 문턱(70)을 넘어 '가장 추천'이 됐다.
#: ① recommendRequiresDayBasis(횡재·재물·개업·결혼): 그날 유리 방향 신호까지 요구.
GRADE_BASIS_NOTE = (
    "[추천]은 그날 {domain} 신호가 유리 방향으로 있고, 일진 천간이 기신·구신이 아니며, 걸리는 "
    "관계(충·형·원진)가 1건 이하인 날에만 붙는다. [무난]은 그런 근거가 없는 날이다 — [무난]인 "
    "날을 추천일·가장 좋은 날로 올려 말하지 않는다."
)
#: ② recommendBlocksUnfavorableStem 만(이사·계약·수술): 그날 근거는 십성 적합표(이사·계약)나
#: 걸리는 관계가 없는 것(수술)이라 신호를 요구하지 않고, 기신·구신 천간 날만 [추천]에서 뺀다.
GRADE_STEM_NOTE = (
    "[추천]은 일진 천간이 기신·구신이 아니고 걸리는 관계(충·형·원진)가 1건 이하인 날에만 "
    "붙는다. [무난]인 날을 추천일·가장 좋은 날로 올려 말하지 않는다."
)
GRADE_NONE_NOTE = (
    "이 기간에는 [추천] 등급 날이 없다 — 첫 문단에서 두드러지게 유리한 날은 없다고 먼저 밝히고, "
    "그다음 무난한 날을 안내한다."
)


def relation_label_ko(relation_id: str) -> str:
    """관계 ID('rel_巳申破') → 표 사유용 표기('巳申 파'). 모르는 꼴은 꼬리를 그대로 돌려준다."""
    tail = relation_id.removeprefix("rel_")
    for hanja, ko in _RELATION_TAIL_KO:
        if tail.endswith(hanja) and len(tail) > len(hanja):
            return f"{tail[: -len(hanja)]} {ko}"
    return tail


#: 부분 성립(2자) 관계의 종류 표기 — 관계 ID 는 완성형('寅巳申三刑')이라 그대로 쓰면 없는
#: 글자(寅)가 있는 것처럼 읽힌다. 실제 참여 글자로 표기한다.
_PARTIAL_TAIL_KO: dict[str, str] = {"삼형": "형(삼형 일부)", "삼합": "반합", "방합": "방합 일부"}


def hit_label_ko(hit: InteractionHit) -> str:
    """상호작용 1건 → 표 사유용 표기. 부분 성립은 실제 참여 글자로 적는다('巳申 형(삼형 일부)')."""
    label = relation_label_ko(hit.relation_id)
    if not hit.partial or " " not in label:
        return label
    kind = _PARTIAL_TAIL_KO.get(label.rsplit(" ", 1)[1])
    if kind is None:
        return label
    glyphs = "".join(dict.fromkeys(pt.ganji for pt in hit.participants))
    return f"{glyphs} {kind}"


def _count_labels(labels: list[str]) -> list[str]:
    """같은 표기를 '亥亥 자형 ×2'로 묶는다(처음 나온 순서 유지)."""
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return [label if n == 1 else f"{label} ×{n}" for label, n in counts.items()]


#: 민속 흉방 근거 줄을 붙이는 택일 목적(사전 applies_actions: 이사·개업·혼례 — docs/19 §5-3).
_FOLK_NOTE_PURPOSES = frozenset({"relocation", "business_start", "marriage_signal"})


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

    def grade_basis_note(
        self, purpose: EventKey, domain_override: str | None = None
    ) -> str | None:
        """그 목적의 [추천] 조건 안내 문장 — 등급 옵션이 없는 목적이면 None.

        목적 옵션이 단일 기준이다: recommendRequiresDayBasis → `GRADE_BASIS_NOTE`(도메인명
        치환), recommendBlocksUnfavorableStem 만 → `GRADE_STEM_NOTE`.
        """
        profile = self._profiles.get(str(purpose)) or self._profiles["relocation"]
        options = profile["options"]
        if options.get("recommendRequiresDayBasis"):
            domain = domain_override or profile.get("domainOverride", "relocation")
            return GRADE_BASIS_NOTE.format(domain=_DOMAIN_KO.get(domain, domain))
        if options.get("recommendBlocksUnfavorableStem"):
            return GRADE_STEM_NOTE
        return None

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
        domain_override: str | None = None,
        body: str | None = None,
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
            domain_override: 연·월 신호 가중의 도메인을 프로필 domainOverride 대신 지정
                (목적 별칭 — 취업 서류 제출이 계약·문서 프로필을 빌릴 때 career, 2026-10-19).
            body: 일간 쪽(``windfall_lens.body_side`` — strong/weak/neutral). 횡재 목적에서
                일진 십성의 횡재 관점 라벨을 붙일 때만 쓴다(점수·등급 불변). None 이면 라벨 없음.
        """
        profile = self._profiles.get(str(purpose)) or self._profiles["relocation"]
        weights = profile["weights"]
        options = profile["options"]
        domain = domain_override or profile.get("domainOverride", "relocation")
        domain_ko = _DOMAIN_KO.get(domain, domain)
        # 등급·사유 옵션(2026-11-16) — 기신·구신 천간 날의 [추천] 차단(전 목적)과 그날 유리 방향
        # 신호 요구(횡재·재물·개업·결혼). 옵션이 없는 프로필은 종전 그대로(점수 문턱만).
        block_unfavorable = bool(options.get("recommendBlocksUnfavorableStem"))
        require_basis = bool(options.get("recommendRequiresDayBasis"))
        basis_notes = bool(options.get("dayBasisNotes"))
        wealth_role = (favorability or {}).get(wealth_element) if wealth_element else None
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
            signed_day = _signed_weight(c, domain)
            day_execution = _to100(signed_day)
            # 그날 신호의 방향과 출처 — 표 사유·등급 근거(점수 계산에는 쓰지 않는다).
            domain_hits = [s for s in c.domain_signals if s.domain == domain]
            day_signal = (
                "positive" if domain_hits and signed_day > 0
                else "negative" if domain_hits and signed_day < 0
                else "none"
            )
            hit_by_id = {h.relation_id: h for h in reversed(c.interactions)}
            signal_relations = list(dict.fromkeys(
                hit_label_ko(hit_by_id[s.source_interaction])
                if s.source_interaction in hit_by_id
                else relation_label_ko(s.source_interaction)
                for s in domain_hits
            ))
            risk_relations = _count_labels([hit_label_ko(h) for h in self._risk_hits(c)])
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
            year_key, month_key = _parent_keys(c.period_key)
            scores = DateScores(
                macro_flow=_to100(years.get(year_key, 0.0)),
                month_fit=_to100(months.get(month_key, 0.0)),
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
            signal_note = {
                "positive": f"{domain_ko} 신호 있음(유리 방향)",
                "negative": f"{domain_ko} 신호 있음(불리 방향)",
                "none": f"{domain_ko} 신호 없음",
            }[day_signal]
            lens_notes: list[str] = []
            if basis_notes:
                # 표 사유를 엔진 값으로 채운다 — 천간·지지 십성, 천간 역할, 신호 출처, 걸리는 관계.
                if signal_relations and day_signal != "none":
                    signal_note = signal_note[:-1] + f": {'·'.join(signal_relations)})"
                risk_note = (
                    f"걸리는 관계 {len(self._risk_hits(c))}건({'·'.join(risk_relations)})"
                    if risk_relations else "걸리는 관계(충·형·원진) 없음"
                )
                if str(purpose) == "windfall" and body:
                    lens_notes = windfall_day_lens(
                        stem_ten_god=c.ten_god.stem, branch_ten_god=c.ten_god.branch_main,
                        body=body, wealth_role=wealth_role,
                    )
                reasons = [
                    f"천간 {c.ganji.stem} {c.ten_god.stem}({c.favorability}) · "
                    f"지지 {c.ganji.branch} {c.ten_god.branch_main}",
                    signal_note,
                    risk_note,
                    *(["횡재 관점: " + " / ".join(lens_notes)] if lens_notes else []),
                    *reasons,
                ]
            # [추천] = 점수 문턱 + 낮은 위험도 + 등급 옵션. 길흉은 용신·기신이 정하므로 천간이
            # 기신·구신인 날은 어느 목적에서도 [추천]이 아니다. 근거 요구 목적은 그날 유리 방향
            # 신호까지 있어야 한다(신호 0건인 날의 중립 50점은 근거가 아니다).
            basis_ok = (
                not (block_unfavorable and is_unfavorable_role(c.favorability))
                and (not require_basis or day_signal == "positive")
            )
            cautions: list[str] = []
            if options.get("volatilityWarning"):
                cautions.append(_VOLATILITY_CAUTION)
            # 민속 흉방 근거 줄(docs/19 §5-3) — 이사·개업·혼례 목적에만, 점수 불변(추가 정보).
            folk_note = (
                folk_note_for_day(day) if str(purpose) in _FOLK_NOTE_PURPOSES else None
            )
            candidates.append(DateCandidate(
                date=c.period_key,
                purpose=purpose,
                ganji=f"{c.ganji.stem}{c.ganji.branch}",
                scores=scores,
                risk_score=risk,
                reasons=reasons or [signal_note],
                cautions=cautions,
                recommendation=(
                    "recommended" if scores.final >= 70 and risk < 40 and basis_ok
                    else "avoid" if risk >= 70 else "acceptable"
                ),
                is_holiday=holiday_name is not None,
                is_weekend=is_weekend,
                son_eomneun_nal=son,
                folk_direction_note=folk_note,
                stem_ten_god=c.ten_god.stem,
                branch_ten_god=c.ten_god.branch_main,
                stem_role=c.favorability,
                day_signal=day_signal,
                signal_relations=signal_relations,
                risk_relations=risk_relations,
                lens_notes=lens_notes,
            ))

        if require_basis or block_unfavorable:
            # 등급 옵션이 있는 목적은 [추천] 날을 앞에 둔다 — 점수만 높고 [추천]이 아닌 날이 표
            # 머리에 오면 그 날이 추천처럼 읽힌다. 등급 안에서는 종전 순서(점수 내림차순·날짜).
            candidates.sort(key=lambda c: (
                c.recommendation != "recommended", -c.scores.final, c.date,
            ))
        else:
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
                if is_favorable_role(favorability.get(e))]
        tail = f" 유리한 방위: {', '.join(favs)}." if favs else ""
        return f"지정 방위 {stated}({element}·{role}) — {tone}.{tail}"

    @staticmethod
    def _risk_hits(c: LuckComposite) -> list[InteractionHit]:
        """위험도에 드는 상호작용(충·형·원진 계열) 목록."""
        return [h for h in c.interactions if h.kind.value in _RISK_KINDS]

    @classmethod
    def _risk_score(cls, c: LuckComposite) -> int:
        """일운 위험도 — 충·형 계열 상호작용 수 기반(0~100, 초안)."""
        return min(100, len(cls._risk_hits(c)) * 30)


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


def _parent_keys(day_key: str) -> tuple[str, str]:
    """일운 날짜('YYYY-MM-DD')의 (연 흐름 키 'YYYY', 월 적합 키 'YYYY-MM').

    종전에는 양력 연·월이다. 절기 기준 플래그가 켜지면 — `JEOLGI_PARENT_MONTH_ENABLED`: 절입 전
    초순 날은 앞 절기월, `JEOLGI_PARENT_YEAR_ENABLED`: 입춘 전 날은 전년 세운(타임존은 월운 라벨
    생성 기본값 Asia/Seoul).
    """
    by_month = period_v2_config.JEOLGI_PARENT_MONTH_ENABLED
    by_year = period_v2_config.JEOLGI_PARENT_YEAR_ENABLED
    if not (by_month or by_year):
        return day_key[:4], day_key[:7]
    try:
        jeolgi_month = luck_month_label(date.fromisoformat(day_key[:10]), get_table())
    except (ValueError, TypeError):
        return day_key[:4], day_key[:7]
    jeolgi_year = sewoon_year_of(jeolgi_month)
    year_key = str(jeolgi_year) if by_year and jeolgi_year is not None else day_key[:4]
    return year_key, (jeolgi_month if by_month else day_key[:7])


def _to100(signed: float) -> int:
    """부호화 신호(−1~+1 근방) → 0~100(50 중립)."""
    return max(0, min(100, round(50 + signed * 50)))
