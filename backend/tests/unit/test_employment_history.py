"""직장 이력 적재 P0 검증 — EMPLOYMENT_HISTORY_CALIBRATION.md §2-4.

절기 경계 3건(PDF 26쪽 경계표)·사건 키 매핑·attrs·행 id·원장 전용 키의 시드 차단을 확인한다.
DB는 쓰지 않는다(순수 함수). 골든 차트 1980-11-22 09:40 서울.
"""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.employment_history import (
    EMPLOYMENT_STAT_NATURES,
    luck_month_label,
    parse_history_date,
    reference_date_for_label,
    rows_from_history,
    superseded_keys,
)
from saju_engines.personal_calibration import seed_missing_events
from saju_engines.reality_calibration import pillars_signature
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.event_engine import EventKeyV2
from saju_shared_types.life_event import (
    LEDGER_ONLY_EVENT_KEYS,
    EmploymentHistoryEntry,
    LifeEventOutcome,
    LifeEventRow,
    LifeEventSource,
    SignalFingerprint,
)

_BIRTH = BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
    birth_place_name="서울", gender="male",
)


def _month_ganji(label: str) -> dict[str, str]:
    """라벨 연도 기준 만세력의 월운 라벨→간지(엔진 라벨 규칙의 SSOT)."""
    chart = calculate(_BIRTH.model_copy(update={"reference_date": reference_date_for_label(label)}))
    return {p.label: p.ganji for p in chart.luck_cycles.monthly_luck}


# ── 절기 경계(PDF 26쪽): 정오 KST 판정 ───────────────────────────────────────
@pytest.mark.parametrize(
    ("d", "label", "ganji"),
    [
        (date(2019, 8, 8), "2019-08", "壬申"),    # 입추 04:13 — 정오는 절입 이후
        (date(2022, 1, 5), "2021-12", "庚子"),    # 소한 18:14 — 정오는 절입 이전
        (date(2022, 10, 8), "2022-09", "己酉"),   # 한로 16:22 — 정오는 절입 이전
        (date(2025, 12, 1), "2025-11", "丁亥"),   # 타임소프트 입사 — 기존 period 2025-11 와 동일
        (date(2015, 3, 1), "2015-02", "戊寅"),    # 곰앤컴퍼니 상실 — 기존 period 2015-02 와 동일
        (date(2022, 2, 7), "2022-02", "壬寅"),    # 집닥 입사 — 입춘 2.04 이후
    ],
)
def test_luck_month_label_matches_engine_month_ganji(d: date, label: str, ganji: str) -> None:
    assert luck_month_label(d) == label
    assert _month_ganji(label)[label] == ganji


def test_reference_date_for_label_january_uses_previous_solar_year() -> None:
    """1월 라벨(丑월)은 전년 입춘 기준 목록에만 있다 — 캘리브레이션 1월 회상도 같은 규칙."""
    assert reference_date_for_label("2022-01") == date(2021, 7, 1)
    assert reference_date_for_label("2022-02") == date(2022, 7, 1)
    assert "2022-01" in _month_ganji("2022-01")
    assert "2022-01" not in _month_ganji("2022-02")


def test_parse_history_date_precision() -> None:
    assert parse_history_date("2004-09-06") == (date(2004, 9, 6), "day")
    assert parse_history_date("2003-11") == (date(2003, 11, 15), "month")
    assert parse_history_date("2003-11-??") == (date(2003, 11, 15), "month")
    with pytest.raises(ValueError):
        parse_history_date("2003")


# ── 행 변환 ───────────────────────────────────────────────────────────────────
def _entries() -> list[EmploymentHistoryEntry]:
    return [
        EmploymentHistoryEntry(date="2006-06-01", kind="entry", org="키스템프", nature="dispatch",
                               channel="direct", group="g04"),
        EmploymentHistoryEntry(date="2008-05-19", kind="conversion", org="곰앤컴퍼니",
                               nature="conversion", channel="conversion", group="g04"),
        EmploymentHistoryEntry(date="2015-03-01", kind="exit", org="곰앤컴퍼니", group="g04"),
        EmploymentHistoryEntry(date="2026-10-??", kind="exit", org="타임소프트",
                               exit_reason="involuntary", group="g11"),
        EmploymentHistoryEntry(date="2001-08", kind="entry", org="군복무", nature="military",
                               group="military"),
    ]


def test_rows_from_history_keys_attrs_and_ids() -> None:
    chart = calculate(_BIRTH)
    sig = pillars_signature(chart)
    seen: list[tuple[date, str, str]] = []

    def resolver(d: date, label: str, key: str) -> SignalFingerprint | None:
        seen.append((d, label, key))
        return SignalFingerprint(ten_god_groups=["peer"]) if key == "job_gain" else None

    rows = rows_from_history(_entries(), "subj", "owner", sig, resolver)
    by_key = {(r.event_key, r.period): r for r in rows}
    entry = by_key[("job_gain", "2006-05")]  # 6.01은 망종 전 — 癸巳월(PDF 17쪽)
    conv = by_key[("career_change", "2008-05")]
    exit_ = by_key[("resignation", "2015-02")]
    layoff = by_key[("resignation", "2026-10")]
    mil = by_key[("job_gain", "2001-08")]

    # 키 매핑: entry→job_gain / exit→resignation(원장 전용) / conversion→career_change.
    assert exit_.event_key in LEDGER_ONLY_EVENT_KEYS
    assert all(r.outcome is LifeEventOutcome.CONFIRMED for r in rows)
    assert all(r.source is LifeEventSource.EMPLOYMENT_HISTORY for r in rows)
    # attrs: 날짜·정밀도·성격·통로·사유·묶기·회사명·절기월 라벨.
    assert entry.attrs.event_date == date(2006, 6, 1) and entry.attrs.date_precision == "day"
    assert entry.attrs.nature == "dispatch" and entry.attrs.entry_channel == "direct"
    assert entry.attrs.employment_group == conv.attrs.employment_group
    assert conv.attrs.employment_group == exit_.attrs.employment_group
    assert conv.attrs.entry_channel == "conversion" and conv.attrs.exit_reason is None
    assert exit_.attrs.entry_channel is None and exit_.attrs.exit_reason is None
    assert layoff.attrs.exit_reason == "involuntary"
    assert layoff.attrs.event_date is None and layoff.attrs.date_precision == "month"
    assert layoff.attrs.luck_month_label == "2026-10"
    assert entry.attrs.label == "키스템프"
    assert mil.attrs.nature == "military" and mil.attrs.nature not in EMPLOYMENT_STAT_NATURES
    # 행 id는 캘리브레이션 행 형식('{subject}:{period}:{key}')과 겹치지 않는다.
    assert entry.event_row_id == "subj:eh:2006-06-01:job_gain"  # id는 날짜, period는 절기월
    assert layoff.event_row_id == "subj:eh:2026-10:resignation"
    assert len({r.event_row_id for r in rows}) == len(rows)
    # 지문은 resolver가 준 것만, 없으면 빈 지문(규칙 11).
    assert entry.signal_fingerprint.ten_god_groups == ["peer"]
    assert exit_.signal_fingerprint == SignalFingerprint()
    # resolver 는 (대표 날짜, 절기월 라벨, 키)로 호출된다 — 월 정밀도는 15일.
    assert (date(2026, 10, 15), "2026-10", "resignation") in seen
    # 치환 대상 = (key, period) 중복 없이.
    assert ("job_gain", "2006-05") in superseded_keys(rows)
    assert len(superseded_keys(rows)) == len(rows)


# ── 원장 전용 키는 시드되지 않는다(EventKeyV2 변환 크래시 방지) ────────────────
def _row(key: str, period: str) -> LifeEventRow:
    return LifeEventRow(
        event_row_id=f"s:eh:{period}:{key}", subject_id="s", pillar_year="庚申",
        pillar_month="丁亥", pillar_day="己亥", event_key=key, period=period,
        outcome=LifeEventOutcome.CONFIRMED, source=LifeEventSource.EMPLOYMENT_HISTORY,
    )


def test_seed_missing_events_skips_ledger_only_keys() -> None:
    sig = [_row("resignation", "2015-02"), _row("resignation", "2022-11"),
           _row("job_gain", "2016-01"), _row("job_gain", "2018-03")]
    seeds = seed_missing_events([], sig, ["2027-02"])
    keys = {str(c.event_key) for c in seeds}
    assert keys == {EventKeyV2.JOB_GAIN.value}
    assert "resignation" not in keys


def test_life_event_row_attrs_default_and_roundtrip() -> None:
    r = _row("job_gain", "2016-01")
    assert r.attrs.model_dump(exclude_none=True) == {}
    loaded = LifeEventRow.model_validate({
        **r.model_dump(mode="json"), "attrs": {"label": "미래엔", "nature": "regular"},
    })
    assert loaded.attrs.label == "미래엔" and loaded.attrs.nature == "regular"
