"""Marriage Production Readiness v1 — MT feature 프로파일 (marriage_timing_profile).

핵심 검증: ① default=전부 OFF(기존 불변) ② production_candidate=MT1·2·3 ON·MT4 shadow ③ 활성
프로파일은 가드 완비 전까지 default ④ default 프로파일 엔진이 무인자 엔진과 동일 결과(비파괴).
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines.event_engine_v2 import EventEngineV2
from saju_engines.marriage_timing_profile import (
    ACTIVE_MARRIAGE_PROFILE,
    MARRIAGE_TIMING_PROFILES,
    marriage_engine_flags,
)
from saju_shared_types.birth_input import BirthInput

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def test_default_profile_all_off() -> None:
    f = marriage_engine_flags("default")
    assert f == {
        "enable_mt1_awareness": False,
        "enable_mt2_emergence": False,
        "enable_mt3_directional": False,
        "enable_mt4_subtype": "off",
    }


def test_production_candidate_profile() -> None:
    f = marriage_engine_flags("production_candidate")
    assert f["enable_mt1_awareness"] is True
    assert f["enable_mt2_emergence"] is True
    assert f["enable_mt3_directional"] is True
    assert f["enable_mt4_subtype"] == "shadow"


def test_active_profile_is_production_candidate() -> None:
    """상용 전환 완료(2026-06-30 승인) — 활성 프로파일=production_candidate."""
    assert ACTIVE_MARRIAGE_PROFILE == "production_candidate"
    assert marriage_engine_flags() == marriage_engine_flags("production_candidate")


def test_unknown_profile_falls_back_to_default() -> None:
    assert marriage_engine_flags("bogus") == marriage_engine_flags("default")


def test_returned_flags_are_copy() -> None:
    """반환값 변형이 원본 프로파일을 오염시키지 않는다."""
    f = marriage_engine_flags("default")
    f["enable_mt1_awareness"] = True
    assert MARRIAGE_TIMING_PROFILES["default"]["enable_mt1_awareness"] is False


def test_default_flagged_engine_matches_bare_engine() -> None:
    """default 프로파일로 만든 엔진 == 무인자 엔진(플러밍 비파괴 — 점수·reason 동일)."""
    r = calculate(BirthInput(
        calendar_type="solar", birth_date="1985-03-15", birth_time="10:00",
        birth_place_name="서울", gender="female",
    ))
    years = list(range(2018, 2030))
    bare = EventEngineV2(_DICTS).score_years(r, years)
    flagged = EventEngineV2(_DICTS, **marriage_engine_flags("default")).score_years(r, years)
    assert [c.score for c in bare] == [c.score for c in flagged]
    assert [c.reason_codes for c in bare] == [c.reason_codes for c in flagged]
