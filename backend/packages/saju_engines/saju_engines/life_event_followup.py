"""지연 outcome 회수 + 채팅 평가 + 캘리브레이션 상태 — LIFE_EVENT_INFERENCE §4.1 ②③ (2026-10-24).

설계 문서의 수집 소스 3종 중 ①(온보딩 캘리브레이션)만 구현돼 있어 2026-10-24 실측 명식 65개 중
사건 보유 9개였다. 이 모듈은 나머지 두 소스의 **순수 계산부**다(DB·HTTP 없음).

- ③ 지연 outcome: 채팅 답변이 제시한 사건 후보(미래·당월) 중 상위 몇 건을 답변 메타에 남겨 두고,
  그 기간이 지난 뒤 "실제로 있었나요?"를 물어 `source=delayed_outcome` 행으로 적재한다.
  설계상 신뢰 "최상" 소스라 같은 (subject, period, event_key) 의 캘리브레이션 행을 덮는다.
- ② 채팅 평가(👍/👎·한 줄 메모)는 **메시지 메타에만** 기록한다. `personal_calibration` 은
  confirmed/planned 외의 모든 행을 '미발생'으로 집계하므로 reality_fit_only 행을 만들면 👍가
  '안 일어남'으로 읽혀 점수를 왜곡한다. 평가는 후속 확인 우선순위(👍 답변 먼저)에만 쓴다.

기간 라벨 비교는 양력 달이 아니라 절기 월운 라벨(YYYY-MM)로 한다(월 라벨 비교 기준 규칙).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_taxonomy_v2 import event_ko_v2
from saju_shared_types.ganji_calendar import GanjiLevel
from saju_shared_types.life_event import (
    LEDGER_ONLY_EVENT_KEYS,
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

from .employment_history import reference_date_for_label
from .personal_calibration import candidate_fingerprint

#: 답변 메타에 남기는 후속 확인 후보 수(답변 1건당). 질문 1회에 3건까지 묻는다.
FOLLOWUP_LIMIT = 3
#: 캘리브레이션 갱신 설문 권유 기준(마지막 제출 후 경과일).
STALE_DAYS = 365

FollowupOutcome = Literal["confirmed", "not_happened", "unknown"]


class FollowupCandidate(BaseModel):
    """답변이 제시한 사건 후보 1건 — 기간이 지나면 실제 발생 여부를 묻는다.

    fingerprint 는 답변 시점에 V2 후보였을 때만 채워진다. 채팅 경로의 최종 후보는 legacy
    `EventCandidate`(십성·궁성 필드 없음)라 비어 있고, 적재 시점에 `resolve_fingerprints` 가
    캘리브레이션 제출과 같은 규칙으로 엔진에서 다시 산출한다.
    """

    event_key: str
    event_ko: str
    period: str            # 'YYYY' | 'YYYY-MM' | 'YYYY-MM-DD'
    score: int = 0
    fingerprint: SignalFingerprint = Field(default_factory=SignalFingerprint)


class FollowupAnswer(BaseModel):
    """후속 확인 답 1건. unknown 은 적재하지 않는다(미입력 무해 — 규칙11)."""

    event_key: str
    period: str
    outcome: FollowupOutcome


class CalibrationStatus(BaseModel):
    """명식의 사건 수집 상태 — 미완료 유도(P2)·연 1회 갱신(P3) 판단 근거."""

    has_events: bool = False
    confirmed: int = 0
    not_happened: int = 0
    last_submitted_at: str | None = None   # 캘리브레이션 설문 마지막 제출(ISO) — 없으면 None
    stale: bool = False                    # 제출 후 STALE_DAYS 경과
    suggested_mode: Literal["initial", "refresh"] | None = None


def _period_kind(period: str) -> Literal["year", "month", "day", "other"]:
    if len(period) == 4 and period.isdigit():
        return "year"
    if len(period) == 7 and period[:4].isdigit() and period[5:7].isdigit():
        return "month"
    if len(period) == 10 and period[:4].isdigit():
        return "day"
    return "other"


def is_elapsed(period: str, current_luck_month: str, today: date) -> bool:
    """후보 기간이 끝났는가 — 연은 해가 바뀐 뒤, 월은 절기 월운 라벨이 지난 뒤, 일은 다음 날."""
    kind = _period_kind(period)
    if kind == "year":
        return int(period) < today.year
    if kind == "month":
        return period < current_luck_month
    if kind == "day":
        return period < today.isoformat()
    return False


def is_open(period: str, current_luck_month: str, today: date) -> bool:
    """후보 기간이 아직 진행 중이거나 미래인가(후속 확인 대상으로 남길 조건)."""
    kind = _period_kind(period)
    if kind == "year":
        return int(period) >= today.year
    if kind == "month":
        return period >= current_luck_month
    if kind == "day":
        return period >= today.isoformat()
    return False


def _fingerprint_if_v2(c: Any) -> SignalFingerprint:
    """V2 후보면 지문을 만들고, legacy 후보(필드 없음)면 빈 지문."""
    if getattr(c, "source_ten_gods", None) is None:
        return SignalFingerprint()
    return candidate_fingerprint(c)


def followup_candidates(
    candidates: Sequence[Any], *, current_luck_month: str, today: date,
    limit: int = FOLLOWUP_LIMIT,
) -> list[FollowupCandidate]:
    """답변 후보 중 아직 지나지 않은 기간의 상위 사건을 후속 확인 후보로 고른다.

    V2·legacy 후보 모두 받는다(event_key·period·score 만 쓴다). 월 단위가 연 단위보다
    정밀하므로 같은 사건이면 월 후보를 우선한다. (event_key, period) 중복 제거, 원장 전용 키
    제외, 점수 내림차순.
    """
    chosen: list[FollowupCandidate] = []
    seen: set[tuple[str, str]] = set()
    seen_keys_month: set[str] = set()
    ordered = sorted(candidates, key=lambda c: (-c.score, c.period))
    # 1차: 월 후보, 2차: 연 후보(같은 사건의 월 후보가 이미 있으면 제외)
    for pass_kind in ("month", "year", "day"):
        for c in ordered:
            key = str(c.event_key)
            if key in LEDGER_ONLY_EVENT_KEYS:
                continue
            if _period_kind(c.period) != pass_kind:
                continue
            if not is_open(c.period, current_luck_month, today):
                continue
            if (key, c.period) in seen or (pass_kind == "year" and key in seen_keys_month):
                continue
            seen.add((key, c.period))
            if pass_kind == "month":
                seen_keys_month.add(key)
            chosen.append(FollowupCandidate(
                event_key=key, event_ko=event_ko_v2(key), period=c.period,
                score=int(c.score), fingerprint=_fingerprint_if_v2(c),
            ))
            if len(chosen) >= limit:
                return chosen
    return chosen


def elapsed_candidates(
    stored: list[dict], *, current_luck_month: str, today: date,
) -> list[FollowupCandidate]:
    """메시지 메타에 저장된 후보 중 기간이 지난 것만 복원한다(잘못된 항목은 건너뜀)."""
    out: list[FollowupCandidate] = []
    for item in stored:
        try:
            cand = FollowupCandidate.model_validate(item)
        except Exception:  # noqa: BLE001 — 구버전·손상 메타는 묻지 않는다
            continue
        if is_elapsed(cand.period, current_luck_month, today):
            out.append(cand)
    return out


def _is_empty(fp: SignalFingerprint) -> bool:
    return not (fp.ten_god_groups or fp.palace or fp.relation or fp.twelve_stage or fp.glyphs)


def resolve_fingerprints(
    candidates: list[FollowupCandidate], *, birth: BirthInput, engine: Any,
    calculate: Callable[[BirthInput], Any],
) -> list[FollowupCandidate]:
    """빈 지문을 엔진으로 채운다 — 연 후보는 `score_years`, 월 후보는 그 달 월운 채점.

    캘리브레이션 제출(`_month_fingerprints`)과 같은 규칙: 월 라벨은 절기월이라 그 달 15일이 아닌
    `reference_date_for_label` 기준으로 차트를 잡는다. 엔진이 그 기간에 그 사건을 내지 않으면
    지문은 비어 있는 채로 둔다(미입력 무해).
    """
    out: list[FollowupCandidate] = []
    year_cache: dict[int, dict[str, SignalFingerprint]] = {}
    month_cache: dict[str, dict[str, SignalFingerprint]] = {}
    for c in candidates:
        if not _is_empty(c.fingerprint):
            out.append(c)
            continue
        fp = SignalFingerprint()
        kind = _period_kind(c.period)
        try:
            if kind == "year":
                year = int(c.period)
                if year not in year_cache:
                    chart = calculate(birth.model_copy(update={"reference_date": date(year, 7, 1)}))
                    year_cache[year] = {
                        str(v.event_key): candidate_fingerprint(v)
                        for v in engine.score_years(chart, [year]) if v.period == c.period
                    }
                fp = year_cache[year].get(c.event_key, fp)
            elif kind == "month":
                if c.period not in month_cache:
                    chart = calculate(birth.model_copy(
                        update={"reference_date": reference_date_for_label(c.period)},
                    ))
                    month_cache[c.period] = {
                        str(v.event_key): candidate_fingerprint(v)
                        for v in engine.score(chart, levels={GanjiLevel.MONTH})
                        if v.period == c.period
                    }
                fp = month_cache[c.period].get(c.event_key, fp)
        except Exception:  # noqa: BLE001 — 지문 산출 실패는 적재를 막지 않는다(규칙11)
            fp = SignalFingerprint()
        out.append(c.model_copy(update={"fingerprint": fp}))
    return out


def period_ko(period: str) -> str:
    """기간 라벨 → 사용자 표기('2026년 9월' / '2026년' / '2026년 9월 3일'). 월은 절기월 기준."""
    kind = _period_kind(period)
    if kind == "year":
        return f"{period}년"
    if kind == "month":
        return f"{int(period[:4])}년 {int(period[5:7])}월"
    if kind == "day":
        return f"{int(period[:4])}년 {int(period[5:7])}월 {int(period[8:10])}일"
    return period


def followup_question(candidates: list[FollowupCandidate]) -> str:
    """후속 확인 문구(템플릿 — 즉석 작문 금지). 후보가 없으면 빈 문자열."""
    if not candidates:
        return ""
    first = candidates[0]
    if len(candidates) == 1:
        return (
            f"지난 {period_ko(first.period)}에 '{first.event_ko}' 흐름을 말씀드렸는데, "
            "실제로 그런 일이 있었나요? 답해 주시면 이 사주 풀이가 더 정확해져요."
        )
    return (
        f"지난 {period_ko(first.period)} 전후로 말씀드린 흐름들이 실제로 있었는지 알려주세요. "
        "답해 주시면 이 사주 풀이가 더 정확해져요."
    )


def rows_from_followup(
    *, subject_id: str, owner_id: str,
    pillars_sig: tuple[str, str, str, str | None, str | None],
    answers: list[FollowupAnswer], candidates: list[FollowupCandidate],
) -> list[LifeEventRow]:
    """후속 답 → `delayed_outcome` 행. 후보에 없는 (event_key, period) 와 unknown 은 버린다.

    event_row_id 는 캘리브레이션과 같은 `{subject}:{period}:{event_key}` — 지연 outcome 이
    신뢰 최상 소스라 같은 칸의 회상 행을 덮는다(append_rows 의 ON CONFLICT 갱신).
    """
    by_key = {(c.event_key, c.period): c for c in candidates}
    py, pm, pd, ph, gender = pillars_sig
    rows: list[LifeEventRow] = []
    for a in answers:
        cand = by_key.get((a.event_key, a.period))
        if cand is None or a.outcome == "unknown":
            continue
        rows.append(LifeEventRow(
            event_row_id=f"{subject_id}:{a.period}:{a.event_key}",
            subject_id=subject_id, owner_id=owner_id,
            pillar_year=py, pillar_month=pm, pillar_day=pd, pillar_hour=ph, gender=gender,
            event_key=a.event_key, period=a.period,
            signal_fingerprint=cand.fingerprint,
            outcome=(
                LifeEventOutcome.CONFIRMED if a.outcome == "confirmed"
                else LifeEventOutcome.NOT_HAPPENED
            ),
            source=LifeEventSource.DELAYED_OUTCOME,
            weight=1.0,
        ))
    return rows


def calibration_status(
    rows: list[LifeEventRow], last_submitted_at: datetime | None, today: date,
) -> CalibrationStatus:
    """사건 행·마지막 제출 시각으로 수집 상태를 만든다.

    - 사건 행이 없으면 initial 권유.
    - 마지막 제출(캘리브레이션 설문)로부터 STALE_DAYS 가 지났으면 refresh 권유.
      설문 없이 직장 이력·지연 outcome 만 있는 명식은 제출 시각이 없으므로 stale 로 보지 않는다.
    """
    confirmed = sum(1 for r in rows if r.outcome is LifeEventOutcome.CONFIRMED)
    not_happened = sum(1 for r in rows if r.outcome is LifeEventOutcome.NOT_HAPPENED)
    has = bool(rows)
    stale = False
    if last_submitted_at is not None:
        stale = (today - last_submitted_at.date()).days >= STALE_DAYS
    mode: Literal["initial", "refresh"] | None = None
    if not has:
        mode = "initial"
    elif stale:
        mode = "refresh"
    return CalibrationStatus(
        has_events=has, confirmed=confirmed, not_happened=not_happened,
        last_submitted_at=last_submitted_at.isoformat() if last_submitted_at else None,
        stale=stale, suggested_mode=mode,
    )
