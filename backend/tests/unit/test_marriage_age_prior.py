"""MT6 배우자성 위치별 혼기 static prior 테스트 (MARRIAGE_TIMING_ENHANCEMENT §11).

핵심 검증: ① band 매핑(년 early/월 normal/일 spouse_palace_direct/시 late) ② 다중 위치는
가장 이른 자리 headline + 일지는 structural flag 별도 보존 ③ event 아님(triggers_event False)
④ gender 미상=confidence low·threshold 미사용 ⑤ inert(event_engine·MarriageResourceProfile 미배선).
"""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_engines.marriage_age_prior import (
    _headline_band,
    analyze_marriage_age_prior,
)
from saju_shared_types.birth_input import BirthInput


def _r(date: str, gender: str = "female"):
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date, birth_time="10:00",
        birth_place_name="서울", gender=gender,
    ))


def test_headline_band_mapping() -> None:
    assert _headline_band(["year"]) == "early"
    assert _headline_band(["month"]) == "normal"
    assert _headline_band(["day"]) == "spouse_palace_direct"
    assert _headline_band(["hour"]) == "late"
    assert _headline_band([]) == "unknown"


def test_headline_takes_earliest_pillar() -> None:
    """다중 위치 → headline은 가장 이른 자리(년 우선)."""
    assert _headline_band(["year", "day"]) == "early"
    assert _headline_band(["month", "hour"]) == "normal"
    assert _headline_band(["day", "hour"]) == "spouse_palace_direct"


def test_spouse_palace_direct_preserved_as_structural_flag() -> None:
    """일지 배우자성은 headline이 더 이른 자리여도 structural_flag로 별도 보존."""
    r = _r("1985-03-15")  # 일지 포함 다중 위치
    pr = analyze_marriage_age_prior(r)
    if "day" in pr.positions:
        assert "spouse_palace_direct" in pr.structural_flags
    # band는 positions의 가장 이른 자리와 일치.
    assert pr.band == _headline_band(pr.positions)


def test_is_static_prior_not_event() -> None:
    """MT6는 event가 아니다 — triggers_event False·role static_prior 고정."""
    pr = analyze_marriage_age_prior(_r("1985-03-15"))
    assert pr.triggers_event is False
    assert pr.role == "static_prior"


def test_gender_unknown_low_confidence_not_usable() -> None:
    """gender 미상 — confidence low·threshold 보정 미사용(설명 참고만)."""
    pr = analyze_marriage_age_prior(_r("1985-03-15", "unknown"))
    assert pr.confidence == "low"
    assert pr.usable_for_threshold is False


def test_known_gender_usable_when_band_present() -> None:
    """gender 확정 + 배우자성 드러남 → confidence normal·threshold 사용 가능."""
    pr = analyze_marriage_age_prior(_r("1985-03-15", "female"))
    if pr.positions:
        assert pr.confidence == "normal"
        assert pr.usable_for_threshold is True


def test_no_pillars_graceful() -> None:
    """원국 부재 → band unknown·usable False(graceful)."""
    r = _r("1985-03-15")
    r2 = r.model_copy(update={"pillars": None})
    pr = analyze_marriage_age_prior(r2)
    assert pr.band == "unknown" and pr.usable_for_threshold is False


def test_visible_only_no_hidden_stem() -> None:
    """드러난 것만(천간 투간 + 지지 본기) — 분석기가 정상 산출하고 band가 positions와 일관."""
    for d, g in (("1990-06-08", "male"), ("1972-11-20", "female"), ("1961-09-30", "female")):
        pr = analyze_marriage_age_prior(_r(d, g))
        assert pr.band == _headline_band(pr.positions)
        assert set(pr.positions) <= {"year", "month", "day", "hour"}
