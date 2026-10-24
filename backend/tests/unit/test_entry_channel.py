"""진입 통로 공용 모듈(채팅·리포트) — EMPLOYMENT_HISTORY_CALIBRATION.md §4-4 (2026-10-22).

후보 선별(진입 키·점수순·기간 중복 없이 최대 2)·기둥 없음 → 빈 블록·가족 칸 없음을 확인한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from saju_engines.entry_channel import (
    ENTRY_CHANNEL_HEADER,
    entry_channel_lines,
    entry_periods,
)


def _c(key: str, period: str, score: int) -> SimpleNamespace:
    return SimpleNamespace(event_key=key, period=period, score=score)


def _pillar(label: str, stem: str, branch: str, stg: str, btg: str) -> SimpleNamespace:
    return SimpleNamespace(label=label, ganji=stem + branch, stem=stem, branch=branch,
                           stem_ten_god=stg, branch_ten_god=btg, luck_sinsal=[])


def test_entry_periods_filters_keys_and_dedups_in_score_order() -> None:
    cands = [_c("relocation", "2026-12", 95), _c("job_gain", "2026-11", 60),
             _c("career_change", "2026-11", 70), _c("job_gain", "2027-02", 80),
             _c("job_gain", "2027-05", 75)]
    assert entry_periods(cands) == ["2027-02", "2027-05"]
    assert entry_periods(cands, limit=3) == ["2027-02", "2027-05", "2026-11"]
    assert entry_periods([_c("relocation", "2026-12", 95)]) == []


def test_entry_channel_lines_header_no_family_and_empty_when_no_pillar() -> None:
    pillars = {"2027-02": _pillar("2027-02", "壬", "寅", "정재", "정관")}
    cands = [_c("job_gain", "2027-02", 80), _c("job_gain", "2027-05", 75)]
    lines, keys, periods = entry_channel_lines(cands, pillars.get, {}, "male")
    assert periods == ["2027-02", "2027-05"]
    assert lines[0] == ENTRY_CHANNEL_HEADER and len(lines) == 2  # 2027-05 기둥 없음 → 건너뜀
    assert "거래처" in lines[1] and "상사" in lines[1] and "가족:" not in lines[1]
    assert keys == ["relation:재성@2027-02", "relation:관성@2027-02"]
    assert entry_channel_lines(cands, lambda _lb: None, {}, "male") == ([], [], periods)
