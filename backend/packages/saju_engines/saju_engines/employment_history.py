"""직장 이력(사용자 제공 사실) → LifeEventRow 변환 — EMPLOYMENT_HISTORY_CALIBRATION.md P0.

자격득실 내역 수준의 입퇴사 날짜를 **정본**으로 받아 원장(`subject_life_events`)에 적재할 행을
만든다. 순수 함수: 간지·절기월은 만세력 엔진(절기표)이 정하고, 월운 지문은 호출자가 넘긴
resolver(엔진 채점)로 얻는다. LLM·손 계산 없음.

규칙
- 날짜 정밀도: 'YYYY-MM-DD' = day, 'YYYY-MM'/'YYYY-MM-??' = month(그 달 15일로 대표).
- 절기월 판정 시각: 날짜만 있을 때 **정오 KST** — 절입 당일(예: 2019-08-08 입추 04:13)은 절입
  이후로 본다. 라벨은 엔진 월운 라벨 규칙과 같다(절입 로컬 날짜의 'YYYY-MM').
- 사건 키: entry→job_gain, exit→resignation(원장 전용), conversion→career_change(같은 직장 내
  신분 전환 — 입사·퇴사로 세지 않는다).
- 행 id: '{subject}:eh:{날짜 또는 YYYY-MM}:{event_key}' — 캘리브레이션 행
  ('{subject}:{period}:{key}')과 충돌하지 않는다. 같은 (event_key, period)의 캘리브레이션 회상 행은
  정본 적재 시 치환 대상이다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from saju_manse_core.calendar.solar_terms import get_table
from saju_shared_types.life_event import (
    DatePrecision,
    EmploymentHistoryEntry,
    LifeEventAttrs,
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_KST = ZoneInfo("Asia/Seoul")
_NOON = time(12, 0)
_MONTH_DAY = 15  # 월 정밀도 회상의 대표일(현실 캘리브레이션 `_month_fingerprints`와 동일 규칙)

#: kind → 원장 사건 키
EVENT_KEY_BY_KIND: dict[str, str] = {
    "entry": "job_gain",
    "exit": "resignation",
    "conversion": "career_change",
}

#: 취업 통계(기저율·통로 집계)에 넣는 성격 — 군복무·인턴·전환은 제외(P1에서 사용).
EMPLOYMENT_STAT_NATURES: frozenset[str] = frozenset({"regular", "dispatch"})

MonthFingerprintResolver = Callable[[date, str, str], SignalFingerprint | None]
"""(사건 날짜, 절기월 라벨, event_key) → 그 달 월운 지문. 후보가 없으면 None."""


def parse_history_date(raw: str) -> tuple[date, DatePrecision]:
    """입력 날짜 문자열 → (대표 날짜, 정밀도). 일 미상('??')·월만 있으면 15일로 대표한다."""
    s = raw.strip()
    parts = s.split("-")
    if len(parts) >= 3 and parts[2].isdigit():
        return date(int(parts[0]), int(parts[1]), int(parts[2])), "day"
    if len(parts) >= 2 and parts[1].isdigit():
        return date(int(parts[0]), int(parts[1]), _MONTH_DAY), "month"
    raise ValueError(f"날짜 형식 오류: {raw!r} (YYYY-MM-DD 또는 YYYY-MM)")


def luck_month_label(d: date, at: time = _NOON) -> str:
    """날짜가 속한 절기월 라벨('YYYY-MM') — 직전 節의 KST 날짜 기준(엔진 월운 라벨과 동일 규칙)."""
    instant = datetime.combine(d, at, tzinfo=_KST)
    prev, _nxt = get_table().bounding_month_terms(instant)
    local = prev.astimezone(_KST)
    return f"{local.year}-{local.month:02d}"


def reference_date_for_label(label: str) -> date:
    """월운 라벨('YYYY-MM')이 들어 있는 만세력 기준일(그 절기년 7월 1일).

    엔진의 monthly_luck 은 기준일이 속한 **달력 연도**의 입춘부터 12개월을 나열하므로, 1월 라벨
    ('YYYY-01' = 丑월)은 전년 목록에만 있다. 기준일을 라벨 연도(1월이면 전년)의 7월 1일로 잡으면
    항상 그 라벨이 목록에 있다(2026-10-22 실측: 2022-01-05 기준 → 2022-02~2023-01만 나열).
    """
    y, m = int(label[:4]), int(label[5:7])
    return date(y - 1 if m == 1 else y, 7, 1)


def _row_id(subject_id: str, d: date, precision: DatePrecision, event_key: str) -> str:
    stamp = d.isoformat() if precision == "day" else d.strftime("%Y-%m")
    return f"{subject_id}:eh:{stamp}:{event_key}"


def rows_from_history(
    entries: list[EmploymentHistoryEntry],
    subject_id: str,
    owner_id: str,
    pillars_sig: tuple[str, str, str, str | None, str | None],
    month_fp: MonthFingerprintResolver | None = None,
) -> list[LifeEventRow]:
    """이력 줄 → LifeEventRow(confirmed, source=employment_history).

    period는 날짜의 절기월 라벨이다(캘리브레이션의 달력 월과 달리 절입 경계를 정확히 반영).
    월운 지문은 resolver가 돌려줄 때만 채우고, 없으면 빈 지문(규칙 11 — 미입력 무해).
    """
    py, pm, pd, ph, gender = pillars_sig
    rows: list[LifeEventRow] = []
    for e in entries:
        d, precision = parse_history_date(e.date)
        event_key = EVENT_KEY_BY_KIND[e.kind]
        label = luck_month_label(d)
        fp = month_fp(d, label, event_key) if month_fp is not None else None
        rows.append(LifeEventRow(
            event_row_id=_row_id(subject_id, d, precision, event_key),
            subject_id=subject_id,
            owner_id=owner_id,
            pillar_year=py, pillar_month=pm, pillar_day=pd, pillar_hour=ph,
            gender=gender,
            event_key=event_key,
            period=label,
            signal_fingerprint=fp or SignalFingerprint(),
            outcome=LifeEventOutcome.CONFIRMED,
            source=LifeEventSource.EMPLOYMENT_HISTORY,
            weight=1.0,
            attrs=LifeEventAttrs(
                event_date=d if precision == "day" else None,
                date_precision=precision,
                nature=e.nature,
                entry_channel=e.channel if e.kind in ("entry", "conversion") else None,
                exit_reason=e.exit_reason if e.kind == "exit" else None,
                employment_group=e.group,
                label=e.org,
                luck_month_label=label,
            ),
        ))
    return rows


def superseded_keys(rows: list[LifeEventRow]) -> list[tuple[str, str]]:
    """정본 행이 덮는 (event_key, period) 목록 — 다른 소스의 같은 달 회상 행 치환용."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for r in rows:
        k = (r.event_key, r.period)
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out
