"""절기 기준 월운(月運) 라벨 유틸 — 양력 today를 월운 라벨(YYYY-MM)에 정합한다.

월운 LuckPillar의 라벨은 **절기(節) 시작 시각의 로컬 월**이다(``luck_cycles._monthly`` 참조).
예: 未월(소서 2026-07-07~)의 라벨은 ``2026-07`` 이지만, 양력 7월 1~6일은 절기상 아직
午월(``2026-06``)에 속한다. 따라서 ``f"{today.year}-{today.month:02d}"`` 로 만든 양력 라벨은
각 달의 節 이전(보통 1일~7일경) 구간에서 한 달 앞서며, '당월 운세'·'이번 달'·미래 롤링 창의
시작점이 실제 절기 월운과 한 칸 어긋난다. 이 모듈은 그 어긋남을 절기 기준으로 보정한다.

런타임 의존성을 두지 않기 위해 ``SolarTermTable`` 은 타입 힌트로만 참조하고(호출 측이 주입),
실제로는 ``table.month_branch`` 만 호출한다(덕 타이핑).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from saju_manse_core.calendar.solar_terms import SolarTermTable


def luck_month_label(day: date, table: SolarTermTable, tz_name: str = "Asia/Seoul") -> str:
    """주어진 양력 날짜가 속한 절기 월운의 라벨(YYYY-MM)을 반환한다.

    월운 라벨 생성과 동일한 규칙(節 시작 시각의 로컬 월)으로 정합을 맞춘다. 기준 시각은
    그 날 정오(tz_name)로 고정해 간지달력 표시(``ganji_calendar.build_month``)와 일치시킨다.

    Args:
        day: 기준 양력 날짜(보통 today).
        table: 절기 테이블(``month_branch`` 보유). 호출 측이 주입.
        tz_name: 라벨을 만들 타임존. 월운 라벨이 생성된 차트 타임존과 동일해야 정합한다
            (기본 Asia/Seoul 폴백).

    Returns:
        절기 기준 월운 라벨 ``"YYYY-MM"``.
    """
    tz = ZoneInfo(tz_name)
    instant = datetime(day.year, day.month, day.day, 12, 0, tzinfo=tz)
    _branch, (prev_inst, _name), _next = table.month_branch(instant)
    local = prev_inst.astimezone(tz)
    return f"{local.year}-{local.month:02d}"


def shift_month_label(label: str, delta: int) -> str:
    """``"YYYY-MM"`` 라벨을 delta개월 이동한 라벨을 반환한다.

    절기 월운은 양력 월과 1:1로 순증(입춘 2월·경칩 3월·…·소한 1월)하므로 라벨 산술은
    달력 월 산술과 같다. '다음 달'(+1)·미래/과거 롤링 창의 양끝 계산에 쓴다.

    Args:
        label: 기준 라벨 ``"YYYY-MM"``.
        delta: 이동할 개월 수(음수 허용).

    Returns:
        이동된 라벨 ``"YYYY-MM"``.
    """
    year, month = int(label[:4]), int(label[5:7])
    idx = year * 12 + (month - 1) + delta
    return f"{idx // 12}-{idx % 12 + 1:02d}"
