"""D1-B 기간 근거 전달 — 계산 불변, 전달만 보강 (2026-07-27 데굴님 확정).

엔진은 source_layers와 억제 사유를 이미 알고 있었지만 LLM에는 confidence 문자열
하나만 갔다. 정규화한 layer_grounding으로 '왜 신뢰도가 낮은지'를 전달한다.
후보 자격 판정(Top-N 제외·LOCAL_TRIGGER_ONLY)은 하지 않는다 — 그건 P2 소관.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from saju_engines.context_reducer import _layer_grounding


def _c(layers, reasons=()):
    return SimpleNamespace(source_layers=list(layers), reason_codes=list(reasons))


@pytest.mark.parametrize(
    ("layers", "minor_only", "upper"),
    [
        (["ilwoon"], True, False),
        (["wolwoon", "ilwoon"], True, False),
        (["sewoon", "ilwoon"], False, True),
        (["daewoon", "sewoon", "wolwoon", "ilwoon"], False, True),
        (["daewoon"], False, True),
    ],
)
def test_upper_support_uses_candidate_provenance(layers, minor_only, upper):
    """stack 구성이 아니라 후보 provenance로 판정한다.

    stack_for가 관할 상위 운을 자동으로 붙이므로, 스택만 보면 전 후보가 상위 지지를
    가진 것처럼 보인다. source_layers(실제 기여)로 봐야 한다.
    """
    g = _layer_grounding(_c(layers))
    assert g.minor_layer_only is minor_only
    assert g.has_upper_layer_support is upper


def test_reason_codes_are_allowlisted():
    """원시 reason_codes를 통째로 넘기지 않는다 — allowlist만."""
    g = _layer_grounding(_c(
        ["ilwoon"],
        ["SUPPRESS_minor_layer_only", "INTERNAL_SHADOW_XYZ", "SOME_MODIFIER"],
    ))
    assert g.grounding_codes == ["MINOR_LAYER_ONLY"]
    assert g.confidence_adjusted is True
    assert "INTERNAL_SHADOW_XYZ" not in str(g.model_dump())


def test_empty_layers_yield_none():
    """legacy·미상 후보는 근거를 지어내지 않는다."""
    assert _layer_grounding(_c([])) is None


def test_no_adjustment_flag_without_allowlisted_code():
    """억제 사유가 없으면 confidence_adjusted는 False다."""
    g = _layer_grounding(_c(["sewoon", "ilwoon"]))
    assert g.confidence_adjusted is False
    assert g.grounding_codes == []
