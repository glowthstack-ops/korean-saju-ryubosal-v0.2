"""EXPRESSION_CLAMP_ENABLED rollback 플래그 (Phase 5b-2a 안전장치).

True(기본)면 [표현 제한] 라인 노출, False면 미노출(즉시 off). 플래그와 무관하게 shadow 계산·
score/rank/favorability/final/polarity는 불변. 규격: YONGSIN_OPERATIONAL_ROLE_SPEC §11-7
"""

from __future__ import annotations

from types import SimpleNamespace

import saju_manse_analysis.yongsin.operational_role_config as op_config

import saju_engines.chart_interpretation as ci
from saju_api.services.manse_service import calculate
from saju_engines.chart_interpretation import build_luck_grounding
from saju_engines.shadow_scoring import luck_expression_clamp
from saju_shared_types.birth_input import BirthInput

_STD_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1977-12-16", birth_time="05:30",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def _grounding():
    result = calculate(_STD_BIRTH)
    luck = SimpleNamespace(
        ganji="壬子", twelve_unseong="", relations_to_chart=[], yongsin_alignment="",
        gongmang_activation=[],
    )
    return result, build_luck_grounding(result, luck)


def test_default_flag_is_true() -> None:
    assert op_config.EXPRESSION_CLAMP_ENABLED is True


def test_flag_on_surfaces_expression_limit() -> None:
    _result, g = _grounding()
    assert "[표현 제한]" in g["pillar_line"]


def test_flag_off_hides_expression_limit(monkeypatch) -> None:
    monkeypatch.setattr(ci._op_config, "EXPRESSION_CLAMP_ENABLED", False)
    _result, g = _grounding()
    assert "[표현 제한]" not in g["pillar_line"]


def test_shadow_calc_unchanged_regardless_of_flag(monkeypatch) -> None:
    # 플래그를 꺼도 shadow/operational 계산 자체는 그대로(소비처만 게이트).
    result = calculate(_STD_BIRTH)
    on = luck_expression_clamp(result, "壬子")
    monkeypatch.setattr(ci._op_config, "EXPRESSION_CLAMP_ENABLED", False)
    off = luck_expression_clamp(result, "壬子")
    assert on == off and on is not None  # luck_expression_clamp 은 플래그와 무관
