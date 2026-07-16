"""사신사 좌향 sector 회귀(docs/12 §14-2·§14-3, P5-1 스캐폴딩).

좌향이 바뀌면 현무(back)도 바뀌어야 한다 — '북산=항상 현무' 오류 방지의 핵심. 채점은 감수 대기라
여기선 sector 기하만 고정한다.
"""

from __future__ import annotations

import pytest

from saju_engines.fengshui_form import compass_from_bearing, sasinsa_sectors
from saju_shared_types.region_element import RegionDirectionalElementSummary


@pytest.mark.parametrize(
    ("bearing", "label"),
    [(0, "북"), (45, "북동"), (90, "동"), (180, "남"), (270, "서"), (359, "북")],
)
def test_compass_from_bearing(bearing: float, label: str) -> None:
    assert compass_from_bearing(bearing) == label


def test_sasinsa_facing_relative() -> None:
    """좌향별 전후좌우 — 남향이면 현무=북, 동향이면 현무=서(좌향 상대)."""
    s = sasinsa_sectors(180)  # 남향
    assert (s.front_sector, s.back_sector, s.left_sector, s.right_sector) == (
        "남", "북", "동", "서")  # 주작 남 / 현무 북 / 청룡 동 / 백호 서
    e = sasinsa_sectors(90)  # 동향
    assert e.back_sector == "서"  # 동향이면 현무=서(북산 고정 아님)
    assert (e.front_sector, e.left_sector, e.right_sector) == ("동", "북", "남")
    n = sasinsa_sectors(0)  # 북향
    assert (n.back_sector, n.left_sector, n.right_sector) == ("남", "서", "동")


def test_facing_bearing_modulo() -> None:
    assert sasinsa_sectors(540).facing_bearing == 180.0  # 360 밖 보정


def _dir(code: str, *, earth=0.0, wood=0.0, water=0.0, mnt=None,
         riv=None) -> RegionDirectionalElementSummary:
    return RegionDirectionalElementSummary(
        region_code="t", direction_code=code, earth_score=earth, wood_score=wood,
        water_score=water, nearest_mountain_m=mnt, nearest_river_m=riv, confidence=0.65)


def test_form_quality_open_mountain_vs_water() -> None:
    """좌향 없음: 산지형은 mountain_support 가산, 수변과다는 overwater 감점(§14-12)."""
    from saju_engines.fengshui_form import (
        compute_form_quality_open,
        derive_open_signals,
        form_quality_bonus,
    )
    # 산수혼합(土·水·木 공존) → balance 가산, 양(+) bonus.
    mixed = [_dir("N", earth=0.6, mnt=1500), _dir("E", water=0.45, riv=1200),
             _dir("W", wood=0.4), _dir("S")]
    pm = compute_form_quality_open(mixed, "t")
    assert pm.available and pm.form_quality_score > 0
    assert -5 <= form_quality_bonus(pm) <= 5  # 첫 릴리즈 cap
    # 수변과다(水만 강, 土/木 약) → overwater 페널티.
    over = [_dir("S", water=0.9, riv=300), _dir("N"), _dir("E"), _dir("W")]
    so = derive_open_signals(over)
    assert so["overwater_penalty"] > 0 and so["mountain_support"] < 0.2


def test_form_quality_facing_sasinsa() -> None:
    """좌향 있음: 남향(현무=북)에 북산이 있으면 back_mountain 반영(§14-3)."""
    from saju_engines.fengshui_form import compute_form_quality_facing
    rows = [_dir("N", earth=0.7, mnt=1800), _dir("S", water=0.4, riv=1500),
            _dir("E", earth=0.3, wood=0.3), _dir("W", earth=0.25)]
    p = compute_form_quality_facing(rows, "t", 180.0)  # 남향
    assert p.back_mountain_score > 0.5  # 북(현무)의 土
    assert any("현무 북" in e for e in p.evidence)


def test_form_quality_bonus_cannot_dominate() -> None:
    """form_quality_bonus는 cap 내(base_match_score 미반전 보장 — §14-12 금지 7)."""
    from saju_engines.fengshui_form import compute_form_quality_open, form_quality_bonus
    rows = [_dir("N", earth=1.0, mnt=100), _dir("E", wood=1.0), _dir("S", water=1.0, riv=100)]
    p = compute_form_quality_open(rows, "t")
    assert abs(form_quality_bonus(p, cap=5)) <= 5
    assert abs(form_quality_bonus(p, cap=8)) <= 8


def test_road_rush_signal_proximity_tiers() -> None:
    """P5-3D: 전방 도로·철도 근접 티어(§14-12). 미공급(None)→0, 철도가 도로보다 강함."""
    from saju_engines.fengshui_form import compute_form_quality_facing, road_rush_signal
    assert road_rush_signal(None, None) == 0.0  # 미공급/좌향없음 → 직충 없음
    assert road_rush_signal(80, None) == 0.7  # 도로 100m 이내
    assert road_rush_signal(250, None) == 0.4  # 도로 300m 이내
    assert road_rush_signal(500, None) == 0.0  # 300m 초과
    assert road_rush_signal(None, 80) == 1.0  # 철도 100m 이내(살기 강)
    # facing form_quality에 결합(전방 도로 직충 → road_rush_penalty 반영, 점수 하락).
    rows = [_dir("N", earth=0.6, mnt=1800), _dir("S", water=0.3)]
    clean = compute_form_quality_facing(rows, "t", 180.0).form_quality_score
    rushed = compute_form_quality_facing(
        rows, "t", 180.0, front_road_m=80).form_quality_score
    assert rushed < clean  # 직충이 형국 점수를 낮춘다


def test_paltaek_stub_off_by_default() -> None:
    """P5-3E: 팔택 stub 기본 OFF(빈 결과·confidence 0) — 추천 점수에 미결합."""
    from saju_engines.fengshui_form import compute_paltaek
    off = compute_paltaek(1980, "male")
    assert off.enabled is False and off.confidence == 0.0 and not off.auspicious_directions
    on = compute_paltaek(1980, "male", enabled=True)
    assert on.confidence == 0.0  # 산식 감수 대기 — 켜도 빈 결과
