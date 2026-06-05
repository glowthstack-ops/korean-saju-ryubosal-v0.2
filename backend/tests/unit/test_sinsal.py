"""전체 신살 계산/표시 (spec §9 검증 기준)."""

from __future__ import annotations

from saju_api.services.manse_service import calculate
from saju_shared_types.birth_input import BirthInput

_BASE = dict(birth_date="1980-11-22", birth_time="09:08", birth_place_name="서울", gender="male")


def _sinsal(**over):
    r = calculate(BirthInput(**{**_BASE, **over}))
    assert r.traditional_extras is not None and r.traditional_extras.sinsal is not None
    return r, r.traditional_extras.sinsal


def test_all_detections_in_full_list_and_views_share_source() -> None:
    _r, s = _sinsal()
    full_names = {it.name for it in s.full_list}
    # 주별/카테고리별 이름은 모두 full_list에서 파생(동일 source).
    for names in s.by_pillar.values():
        assert set(names) <= full_names
    for names in s.by_category.values():
        assert set(names) <= full_names
    # 각 full_list 항목은 위치/근거/궁성을 갖춘다(이름만 나열 금지).
    for it in s.full_list:
        assert it.basis and it.position and it.palace


def test_known_sinsal_anchor() -> None:
    # 일간 己 → 천을귀인 子/申; 원국 申(년지) → 천을귀인 @year.
    _r, s = _sinsal()
    cheoneul = [it for it in s.full_list if it.name == "천을귀인"]
    assert any(it.position == "year" for it in cheoneul)
    # 년지 申 기준 12신살: 亥=망신살(월·일).
    mangsin = [it for it in s.full_list if it.name == "망신살"]
    assert {it.position for it in mangsin} >= {"month", "day"}


def test_repeated_sinsal_intensity_increases() -> None:
    # 亥亥 → 망신살 반복 → repeated=True, 강도 상승.
    _r, s = _sinsal()
    mangsin = [it for it in s.full_list if it.name == "망신살"]
    assert all(it.repeated for it in mangsin)
    assert any(it.intensity in ("high", "very_high") for it in mangsin)
    assert "망신살" in s.summary.repeated


def test_hour_unknown_suppresses_hour_sinsal() -> None:
    _r, s = _sinsal(birth_time=None, birth_time_unknown=True)
    assert s.hour_unknown is True
    assert s.by_pillar.get("hour", []) == []
    assert all(it.position != "hour" for it in s.full_list)


def test_sinsal_does_not_affect_strength_or_yongsin() -> None:
    # 신살이 신강약/용신/격국 점수를 바꾸지 않는다(정책).
    r, s = _sinsal()
    assert all(it.use_for_yongsin_decision is False for it in s.full_list)
    assert r.force_analysis.strength.band == "신약"
    assert r.force_analysis.strength.score == 30.61  # 분포 버그픽스(budget/월령본기) 반영 스냅샷
    assert r.yongsin_analysis.final["yongsin"] == "土"
    assert r.geokguk.main_structure == "정재격"
