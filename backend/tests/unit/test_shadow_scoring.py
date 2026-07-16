"""operational shadow scoring (#9a) — 계산·검증 전용, 실제 scoring 미소비.

legacy 불변 + shadow 병행 산출 + diff. 조건부 희신/병=0.0(mixed)·조후보조신<용신·operability 용신만.
exact label·fail-fast·enum 전체 매핑. 규격: doc/v2_2/YONGSIN_OPERATIONAL_ROLE_SPEC.md §10
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast, get_args

import pytest
from saju_manse_analysis import analyze_chart
from saju_manse_analysis.yongsin.operational_role_config import SHADOW_ROLE_WEIGHT

from saju_engines.event_scoring import favorability_map
from saju_engines.shadow_scoring import (
    operational_shadow_weights,
    shadow_vs_legacy_diff,
)
from saju_shared_types.enums import Branch, Stem
from saju_shared_types.manse_result import ManseV2Result
from saju_shared_types.yongsin import OperationalRole

_STD = ((Stem.JEONG, Branch.SA), (Stem.IM, Branch.JA),
        (Stem.JEONG, Branch.MI), (Stem.GYE, Branch.MYO), Stem.JEONG)


def _ya(make_pillars):
    return analyze_chart(make_pillars(*_STD)).yongsin


def test_all_operational_roles_have_shadow_weight() -> None:
    # 새 operational label 이 추가되면 fail-fast 되도록 enum 전체가 매핑돼 있어야 한다.
    assert set(get_args(OperationalRole)) == set(SHADOW_ROLE_WEIGHT)


def test_standard_golden_shadow_weights(make_pillars) -> None:
    w = operational_shadow_weights(_ya(make_pillars))
    assert w == {"木": 0.595, "水": 0.0, "火": 0.35, "土": 0.1, "金": -1.0}


def test_conditional_heesin_is_zero_not_positive() -> None:
    # ★ '조건부 희신/병'은 mixed — positive 아님(0.0).
    assert SHADOW_ROLE_WEIGHT["조건부 희신/병"] == 0.0
    # 계층: 용신 > 희신 > 조후보조신 > 조건부 제살보조 > 조건부 희신/병·한신 > 구신 > 기신.
    assert (SHADOW_ROLE_WEIGHT["용신"] > SHADOW_ROLE_WEIGHT["희신"]
            > SHADOW_ROLE_WEIGHT["조후보조신"] > SHADOW_ROLE_WEIGHT["조건부 제살보조"]
            > SHADOW_ROLE_WEIGHT["한신"] > SHADOW_ROLE_WEIGHT["구신"]
            > SHADOW_ROLE_WEIGHT["기신"])


def test_operability_only_on_yongsin(make_pillars) -> None:
    ya = _ya(make_pillars)
    w = operational_shadow_weights(ya)
    # 용신 木: base 1.0 × operability 0.595. 비용신은 base 가중(operability 미적용).
    assert w["木"] == 0.595
    assert w["火"] == SHADOW_ROLE_WEIGHT["조후보조신"]  # 비용신 — operability 미반영


def test_diff_has_all_fields_and_delta(make_pillars) -> None:
    # 희신 과다 교정(2026-07-12) 후 legacy(final)=모델맵: 水=한신·火=희신.
    diff = shadow_vs_legacy_diff(cast(
        "ManseV2Result", SimpleNamespace(yongsin_analysis=_ya(make_pillars))))
    water = diff["水"]
    assert water == {
        "legacy_role": "한신", "legacy_weight": 0.0,
        "operational_role": "조건부 한신/병", "shadow_weight": 0.0, "delta": 0.0,
    }
    fire = diff["火"]
    assert fire["legacy_weight"] == 0.6 and fire["shadow_weight"] == 0.35
    assert fire["delta"] == pytest.approx(-0.25)


def test_fail_fast_on_unknown_label() -> None:
    # 미등록 operational_role 은 조용히 0 처리하지 말고 KeyError(fail-fast).
    fake = SimpleNamespace(operational_roles=[
        SimpleNamespace(element="木", operational_role="존재안함", operability=None),
    ])
    with pytest.raises(KeyError):
        operational_shadow_weights(fake)  # type: ignore[arg-type]


def test_legacy_unchanged(make_pillars) -> None:
    # shadow 산출이 legacy favorability_map(final/canonical)을 바꾸지 않는다.
    ya = _ya(make_pillars)
    fav = favorability_map(SimpleNamespace(yongsin_analysis=ya))  # type: ignore[arg-type]
    assert fav.get("水") == "한신" and fav.get("火") == "희신"  # canonical(교정 후) 그대로
