"""AddendumGateModifier (Phase 5) — 과잉 해석을 막는 게이트 계층.

event_gate_safety_rules(안전 downgrade) + user_profile_event_gate(현실 상태 분기) +
void_repetition_modifier(공망 지연·해공)를 적용한다. 사양 조건(한글)을 기계 평가로 옮긴
reviewed:false 초안 — 점수 약화·라벨 강등·품질 태깅으로 후보를 줄인다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from saju_shared_types.event_engine import (
    EventCandidateV2,
    EventKeyV2,
    EventTiming,
    LuckLayer,
    TenGod,
)

from . import period_v2_config

_DICTS_DEFAULT = Path(__file__).resolve().parents[3] / "dictionaries"
#: 공망 충발 감점 기본값 — void_repetition_modifier.json score_effect.void_unresolved.
_VOID_UNRESOLVED_DEFAULT = -10


def load_void_unresolved_delta(dictionaries_dir: Path = _DICTS_DEFAULT) -> int:
    """공망 충발 감점을 사전에서 읽는다(사전이 SSOT — 2026-09-10 배선).

    2026-09-10 사문 감사: 이 모듈은 docstring 에서 `void_repetition_modifier.json` 을
    적용한다고 했지만 파일을 읽지 않았다(값이 우연히 같았을 뿐). 파일이 없거나 형식이
    깨지면 기본값으로 물러난다(운영 차단 금지).
    """
    path = Path(dictionaries_dir) / "event_engine" / "void_repetition_modifier.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return int(raw["void_activation_modifier"]["score_effect"]["void_unresolved"])
    except (OSError, KeyError, TypeError, ValueError):
        return _VOID_UNRESOLVED_DEFAULT


_WEALTH = {TenGod.ZHENGCAI, TenGod.PIANCAI}
_OUTPUT = {TenGod.SHISHEN, TenGod.SHANGGUAN}
_AUTHORITY = {TenGod.ZHENGGUAN, TenGod.QISHA}
_RESOURCE = {TenGod.ZHENGYIN, TenGod.PIANYIN}


#: 기혼 경계 태그 임계 — 전환 전 새 인연·결혼 신호 점수(게이트 55 + 10).
MARRIED_OUTSIDE_ATTRACTION_MIN = 65
#: 재직자 취업 신호를 이직으로 읽는 '이동운 동반' 임계 — 같은 기간 이사·이동 후보 점수.
EMPLOYEE_MOVE_WITH_JOB_MIN = 50

_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def period_end_year(period: str) -> int | None:
    """기간 라벨의 끝 연도 — '2026'·'2026-06'·'2024~2033'·'2024–2033' 모두 마지막 4자리 연도.

    연도를 찾지 못하면 None(일운 라벨 등 형식 미상 — 호출자는 '과거 아님'으로 다룬다).
    """
    years = _YEAR_RE.findall(period or "")
    return int(years[-1]) if years else None


def is_past_period(period: str, today_year: int | None) -> bool:
    """후보 기간이 오늘 연도보다 앞(끝 연도 < 오늘 연도)인가 — 프로필 시점 가드(2026-11-08).

    프로필(혼인·직업)은 '지금' 상태다. 생애 스캔·회고처럼 과거 연도를 채점할 때 현재 상태를
    그대로 적용하면 실제 결혼한 해의 결혼 신호가 '관계 이슈'로, 첫 취업 해가 '승진'으로 바뀐다.
    today_year 가 None 이거나 기간에서 연도를 못 읽으면 False(가드 없음 — 종전 동작).
    """
    if today_year is None:
        return False
    end = period_end_year(period)
    return end is not None and end < today_year


@dataclass
class GateContext:
    """게이트 평가 컨텍스트(엔진이 채움 — 미입력 필드는 게이트 미적용)."""

    present_gods: set[TenGod] = field(default_factory=set)
    layers: set[LuckLayer] = field(default_factory=set)
    void_active: bool = False  # 그 기간 운 지지가 원국 공망을 자극(종류 무관 — risk facts 호환)
    # 공망 자극 종류(2026-08-21 데굴님 확정 의미론 — 三命通會 '合則不能空'):
    #   'clash'   충발 — 확정 불변식(발현 지연+변동성 보조)대로 지연 게이트 적용
    #   'fill'    전실 — 가장 명확한 실체화(지연·감점 아님, 신호만)
    #   'combine' 합   — 공망 차단막 약화 + 억제되던 대상의 활성화(지연·감점 아님, 신호만)
    # 비어 있으면(구 호출자) void_active 만으로 기존 동작(충발 취급)을 유지한다.
    void_kinds: set[str] = field(default_factory=set)
    # 종류별 글자 쌍 라벨(예: combine → '申-巳(시지)') — reason code 접미로 보존해
    # LLM이 공망지를 다른 지지로 오지목하지 않게 한다.
    void_pairs: dict[str, str] = field(default_factory=dict)
    # student/employee/public_official/business_owner/freelancer/unemployed/retired
    occupation_status: str | None = None
    relationship_status: str | None = None  # single/dating/married/divorced
    # 시점 가드(2026-11-08): 후보 기간의 끝 연도가 이 연도보다 앞(과거)이면 입력된 프로필 상태
    # 분기(PROFILE_*)를 적용하지 않는다. 출산 안전 게이트(상대 확인 안 됨→창작)는 시점 무관.
    # None 이면 가드 없음(구 호출자·단위 테스트 유지).
    today_year: int | None = None


class AddendumGateModifier:
    """후보에 안전 게이트·프로필 분기·공망 보정을 적용한다.

    수치 파라미터 중 사전이 SSOT 인 것은 공망 충발 감점 하나
    (`void_repetition_modifier.json` score_effect.void_unresolved). 프로필 분기 규칙
    (`user_profile_event_gate.json`)은 서술 규격이며 구현은 이 클래스의 분기다 —
    JSON 의 `implemented_by` 가 규칙↔reason code 대응을 선언하고 테스트가 대조한다.
    """

    def __init__(self, dictionaries_dir: Path = _DICTS_DEFAULT) -> None:
        self._void_delta = load_void_unresolved_delta(dictionaries_dir)

    @property
    def void_unresolved_delta(self) -> int:
        """공망 충발 감점(음수) — 사전 값."""
        return self._void_delta

    def apply(
        self, candidates: list[EventCandidateV2], ctx: GateContext
    ) -> list[EventCandidateV2]:
        out: list[EventCandidateV2] = []
        # 같은 기간에 이사·이동 후보가 함께 있는지(재직자 취업 신호 → 이직 판정용, 2026-11-07).
        move_with = any(
            c.event_key is EventKeyV2.RELOCATION and c.score >= EMPLOYEE_MOVE_WITH_JOB_MIN
            for c in candidates
        )
        for c in candidates:
            ek = c.event_key
            score = c.score
            quality = c.quality
            timing = c.timing
            new_key = ek
            reasons = [*c.reason_codes]

            # ── event_gate_safety_rules ──────────────────────────
            if ek is EventKeyV2.BUSINESS_START and not (ctx.present_gods & _WEALTH):
                score -= 12
                timing = EventTiming.DELAY  # 방향(quality)은 그대로, 발현만 보류
                reasons.append("GATE_business_start_no_wealth")
            day_trigger = bool({LuckLayer.WOLWOON, LuckLayer.ILWOON} & ctx.layers)
            if ek is EventKeyV2.WINDFALL and not day_trigger:
                new_key = EventKeyV2.WEALTH_CHANGE
                reasons.append("GATE_windfall_to_wealth")
            # 시점 가드(2026-11-08) — 과거 연도 후보에는 **입력된** 프로필 상태 분기(PROFILE_*)를
            # 적용하지 않는다. 아래 출산 안전 게이트는 '상대 확인 안 됨'(미입력 포함)에 거는 안전
            # 기본값(출산 확정 금지)이라 시점과 무관하게 적용한다.
            profile_active = not is_past_period(c.period, ctx.today_year)
            # 출산 신호: 상대 없음(미입력 포함 — 사전 childbirth_signal_without_profile: 출산 확정
            # 금지, 결과물·프로젝트로 대체)이면 창작 산출로. 미입력도 전환하는 것은 사전 명시 규칙.
            no_partner_ctx = ctx.relationship_status in (None, "single", "divorced")
            if ek is EventKeyV2.CHILDBIRTH and no_partner_ctx:
                new_key = EventKeyV2.CREATIVE_OUTPUT
                reasons.append("GATE_childbirth_to_creative")
            # 미혼 감점(구 GATE_marriage_signal_weak −12)은 2026-11-07 데굴님 결정으로 폐지 — 미혼은
            # 결혼 가능성을 낮출 근거가 아니다(결혼 목적 만남은 3개월 만에도 성사). 기혼만 아래
            # user_profile_event_gate 에서 새 인연·결혼 신호를 배우자·가정 이슈로 전환한다.

            # ── user_profile_event_gate ──────────────────────────
            if profile_active:
                new_key, reasons = self._apply_profile_rules(
                    ek, score, new_key, reasons, ctx, move_with,
                )
            # 취업 보조 없음(관성 단독, 인성·재성 보조 없음) — 프로필 전환 **후** 키 기준
            # (2026-11-08): 종전엔 원래 키 기준이라 재직자 승진으로 바뀐 후보에 '취업' 감점·라벨이
            # 남고, 무직자 이직→취업 후보에는 빠지던 비대칭이 있었다.
            if new_key is EventKeyV2.JOB_GAIN and not (ctx.present_gods & (_RESOURCE | _WEALTH)):
                score -= 8
                reasons.append("GATE_job_gain_unsupported")

            # ── void_activation_modifier ─────────────────────────
            # 확정 의미론(2026-08-21): 지연·감점은 **충발에만**. 전실·합은 공망의
            # 억제가 풀리는 신호라 방향이 반대다 — 서술용 reason만 남긴다.
            # ('해소=공허·지연'으로 뒤집혀 서술되던 결함의 원인 수정 — 申·巳 육합 사례)
            if (
                "clash" in ctx.void_kinds or (ctx.void_active and not ctx.void_kinds)
            ) and not period_v2_config.GONGMANG_CLASH_DELAY_DISABLED:
                # 측정용 비활성 플래그(2026-10-23 P4)가 켜지면 감점·지연 없이 신호만 남긴다.
                score += self._void_delta  # 사전 score_effect.void_unresolved(기본 −10)
                timing = EventTiming.DELAY  # 공망 충발 — 방향은 유지하고 발현만 지연
                reasons.append("VOID_delay")
            if "fill" in ctx.void_kinds:
                _fp = ctx.void_pairs.get("fill", "")
                # 전실 — 실체화(감점·지연 없음). 접미=공망지(궁위).
                reasons.append(f"VOID_FILL:{_fp}" if _fp else "VOID_FILL")
            if "combine" in ctx.void_kinds:
                _cp = ctx.void_pairs.get("combine", "")
                # 합 — 차단막 약화·대상 활성화. 접미=운글자-공망지(궁위).
                reasons.append(
                    f"VOID_COMBINE_RELEASE:{_cp}" if _cp else "VOID_COMBINE_RELEASE"
                )

            new_score = max(0, score)  # 중간 100 클램프 제거 — raw 누적 보존(게이트는 감점만)
            out.append(c.model_copy(update={
                "event_key": new_key,
                "score": new_score,
                "quality": quality,
                "timing": timing,
                "reason_codes": reasons,
                "contributions": {**c.contributions, "gate": float(new_score - c.score)},
            }))
        return self._merge_and_sort(out)

    @staticmethod
    def _apply_profile_rules(
        ek: EventKeyV2,
        score: int,
        new_key: EventKeyV2,
        reasons: list[str],
        ctx: GateContext,
        move_with: bool,
    ) -> tuple[EventKeyV2, list[str]]:
        """user_profile_event_gate 분기 — 사건 종류 전환·태그만(점수 불변).

        호출자가 시점 가드(`is_past_period`)를 통과한 후보에만 부른다. `ek`는 원래 키, `new_key`는
        앞선 안전 게이트가 바꾼 키(없으면 ek)이며, 분기 조건은 사전 규격대로 원래 키를 본다.
        """
        if ek is EventKeyV2.JOB_GAIN and ctx.occupation_status == "employee":
            if move_with:
                # 재직자 + 취업 신호 + 이동운 동반 = 이직(2026-11-07 데굴님: "직장이 있는 경우에
                # 이동운과 취업운이 함께 들어온다면 이직 운"). 점수 불변·사건 종류 전환.
                new_key = EventKeyV2.CAREER_CHANGE
                reasons.append("PROFILE_job_gain_to_career_change_move")
            else:
                new_key = EventKeyV2.PROMOTION  # 재직자 → 취업보다 승진·직무변경
                reasons.append("PROFILE_job_gain_to_promotion")
        if ek is EventKeyV2.JOB_GAIN and ctx.occupation_status == "student":
            # 학생의 취업 신호 = 아르바이트·근로장학·인턴 등 단기 일자리로 읽음
            # (2026-11-07, 태그만).
            reasons.append("PROFILE_student_job_parttime")
        _career_key = ek in (EventKeyV2.JOB_GAIN, EventKeyV2.CAREER_CHANGE)
        if _career_key and ctx.occupation_status == "retired":
            # 은퇴자의 취업·이직 신호 = 재취업·아르바이트·자문까지 폭넓게, 늦은 나이 취업도
            # 배제하지 않음(2026-11-07, 태그만).
            reasons.append("PROFILE_retired_late_career")
        if ek is EventKeyV2.CAREER_CHANGE and ctx.occupation_status == "unemployed":
            # 무직자의 이직 신호 = 취업(옮길 직장이 없다, 2026-11-07 데굴님).
            new_key = EventKeyV2.JOB_GAIN
            reasons.append("PROFILE_career_change_to_job_gain")
        # 공직자(O02): 재직 공직자의 취업 신호는 승진으로, 승진·인사는 발령·근무지 전보를
        # 동반한다(자료 7-3·12-4 — 공직 승진 = 승진시험 + 발령 + 이동). 사건 종류는 유지하고
        # 동반 가능성만 reason_code로 부여(LLM이 발령·이동을 함께 서술, 점수 불변).
        if ctx.occupation_status == "public_official" and ek in (
            EventKeyV2.JOB_GAIN, EventKeyV2.PROMOTION
        ):
            if ek is EventKeyV2.JOB_GAIN:
                new_key = EventKeyV2.PROMOTION
                reasons.append("PROFILE_public_official_promotion")
            reasons.append("PROFILE_public_official_transfer")
        # 기혼(기혼·재혼·별거 — 별거도 법적 배우자가 있어 기혼 계열, 2026-11-08 통일).
        if ek is EventKeyV2.NEW_RELATIONSHIP and ctx.relationship_status == "married":
            new_key = EventKeyV2.RELATIONSHIP_CHANGE  # 기혼 → 배우자 이슈
            reasons.append("PROFILE_new_relationship_to_change")
        if ek is EventKeyV2.MARRIAGE_SIGNAL and ctx.relationship_status == "married":
            # 기혼의 결혼 신호 = 재혼이 아니라 배우자·가정 관계 이슈(2026-11-07 데굴님 결정:
            # "기혼인 경우에 연애·결혼 가능성이 떨어지는 것"). 사건 종류 전환, 점수 불변.
            new_key = EventKeyV2.RELATIONSHIP_CHANGE
            reasons.append("PROFILE_marriage_to_change")
        if (
            ek in (EventKeyV2.NEW_RELATIONSHIP, EventKeyV2.MARRIAGE_SIGNAL)
            and ctx.relationship_status == "married"
            and score >= MARRIED_OUTSIDE_ATTRACTION_MIN
        ):
            # 기혼인데도 새 인연·결혼 신호가 강하면 배우자 외 인연·유혹이 걸리기 쉬운 해로
            # 경계 주의를 안내한다(2026-11-07 데굴님 "바람 등에 대한 경고도 가능") — 외도 단정
            # 금지, 가능성·경계 어미만. 점수 불변, 태그만.
            reasons.append("PROFILE_married_outside_attraction_caution")
        if ek is EventKeyV2.WEALTH_CHANGE and ctx.occupation_status == "business_owner":
            if ctx.present_gods & _OUTPUT:
                new_key = EventKeyV2.BUSINESS_EXPANSION  # 사업자 + 식상 → 확장
                reasons.append("PROFILE_wealth_to_expansion")
        return new_key, reasons

    @staticmethod
    def _merge_and_sort(cands: list[EventCandidateV2]) -> list[EventCandidateV2]:
        """라벨 강등으로 같은 event_key가 생기면 점수 최댓값으로 병합한다.

        reason 합집합은 승패와 무관하게 양쪽을 남긴다(2026-11-08) — 종전엔 이기는 쪽이 바뀐 후보일
        때만 합쳐, 전환된 결혼·새 인연 후보가 기존 관계 이슈 후보보다 낮으면 기혼 전환·경계
        태그(PROFILE_marriage_to_change 등)가 통째로 사라졌다. 점수·방향·타이밍은 이기는 쪽.
        """
        best: dict[EventKeyV2, EventCandidateV2] = {}
        for c in cands:
            cur = best.get(c.event_key)
            if cur is None:
                best[c.event_key] = c
                continue
            winner = c if c.score > cur.score else cur
            best[c.event_key] = winner.model_copy(update={
                "reason_codes": sorted(set(c.reason_codes) | set(cur.reason_codes)),
            })
        return sorted(best.values(), key=lambda x: -x.score)
