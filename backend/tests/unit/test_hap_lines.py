"""천간합 모드 → LLM 입력 줄 직렬화 검증 (Phase 2a — HAP_INTERACTION_SPEC §F-4).

포매터(모드별 한 줄)와, 실제 차트의 원국/운 합 모드 줄 생성을 확인한다.
"""

from __future__ import annotations

from datetime import date

from saju_manse_analysis.relations.hap_modes import AffectedGod, StemHapResolution

from saju_api.services.manse_service import calculate
from saju_engines.hap_lines import (
    _format,
    luck_hap_mode_lines,
    natal_hap_mode_lines,
)
from saju_shared_types.birth_input import BirthInput


def _res(**kw) -> StemHapResolution:
    base = dict(
        pair=("甲", "己"), positions=("year", "month"), transform_element="土",
        transform_tier="none", hap_mode="bind",
    )
    base.update(kw)
    return StemHapResolution(**base)


def test_format_transform() -> None:
    r = _res(hap_mode="transform", transform_tier="confirmed")
    assert _format(r, {"土": "용신"}) == "甲己合 → 합화 土(용신) · 化 확정"


def test_format_combine_self() -> None:
    r = _res(
        hap_mode="combine_self", transform_tier="conditional",
        affected=[AffectedGod("甲", "정관", "木", "기신", "neutral")],
    )
    out = _format(r, {})
    assert "본신지합(합거 아님)" in out and "甲 정관=기신 유지" in out


def test_format_bind_with_remove_effect() -> None:
    r = _res(
        hap_mode="bind", luck_origin=True, direction="away",
        affected=[
            AffectedGod("庚", "정재", "金", "기신", "boon"),
            AffectedGod("乙", "겁재", "木", "희신", "harm"),
        ],
    )
    out = _format(r, {})
    assert out.startswith("운 ")  # 운 합 접두
    assert "합반" in out and "합거" in out
    assert "庚 정재=기신 유리(흉 제거)" in out
    assert "乙 겁재=희신 불리(길 상실)" in out


def test_format_pair_normalized_order() -> None:
    """자리 순서가 癸戊여도 표기는 천간 표준순(戊癸)."""
    r = _res(pair=("癸", "戊"), hap_mode="combine_self",
             affected=[AffectedGod("戊", "정관", "土", "", "neutral")])
    assert _format(r, {}).startswith("戊癸合")


def test_natal_lines_real_chart() -> None:
    """원국 천간합(戊癸合)이 있는 차트 → 본신지합 줄 생성(중복 없이)."""
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1985, 3, 5), birth_time="12:00",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    )
    lines = natal_hap_mode_lines(calculate(birth))
    assert any("戊癸合" in line and "본신지합" in line for line in lines)
    assert len(lines) == len(set(lines))  # dedup


def test_luck_lines_distinguish_day_master_from_peer() -> None:
    """己亥(일간 己)+시간 己 비견 + 운 甲: 일간은 본신지합, 시간 비견은 합거(쟁합)."""
    birth = BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:40",
        birth_place_name="서울", gender="male", apply_true_solar_time=False,
    )
    lines = luck_hap_mode_lines(calculate(birth), ["甲"])
    assert any("본신지합" in line for line in lines)       # 일간 己
    assert any("합거" in line for line in lines)           # 시간 비견 己
