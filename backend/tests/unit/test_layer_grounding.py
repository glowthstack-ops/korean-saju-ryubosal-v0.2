"""층위 grounding 정규화 단위 테스트 — 분류 규칙만 본다.

⚠ 이 파일은 **덕타이핑 스텁**을 쓴다. 실제 DTO 경로 계약은
`tests/integration/test_layer_grounding_production_path.py`가 담당한다.
1차 구현에서 이 스텁만 믿었다가 `to_legacy_candidate`가 층위를 떨어뜨리는 것을
놓쳤으므로, 여기서 통과했다고 운영 배선이 검증됐다고 보면 안 된다.

입력은 `candidate_source_layers`(후보별 기여)다. P2-1부터 엔진이 이를 채우지만,
**노출은 `SAJU_EVENT_LOCAL_TRIGGER_GATE_ENABLED` 뒤에 있다** — 산출과 노출을 분리해
P2-1이 프롬프트를 바꾸지 않게 했다. 이 파일은 분류 규칙만 보므로 플래그를 켠다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from saju_engines import period_v2_config
from saju_engines.context_reducer import _layer_grounding


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    """P2-1부터 grounding 노출은 플래그 뒤에 있다 — 분류 규칙 검증은 켠 상태로 한다."""
    monkeypatch.setattr(
        period_v2_config, "EVENT_LOCAL_TRIGGER_GATE_ENABLED", True, raising=False
    )


def _c(layers, reasons=()):
    """후보별 기여 층위와 근거 코드만 가진 최소 스텁."""
    return SimpleNamespace(
        candidate_source_layers=list(layers), evidence_path=list(reasons)
    )


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
def test_scope_is_derived_from_candidate_contribution(layers, minor_only, upper) -> None:
    """상위 지지는 스택 구성이 아니라 후보 기여로 판정한다."""
    g = _layer_grounding(_c(layers))
    assert g is not None
    assert g.minor_layer_only is minor_only
    assert g.has_upper_layer_support is upper


def test_reason_codes_are_allowlisted() -> None:
    """원시 근거 코드를 통째로 넘기지 않는다 — allowlist만."""
    g = _layer_grounding(_c(
        ["ilwoon"],
        ["SUPPRESS_minor_layer_only", "INTERNAL_SHADOW_XYZ", "SOME_MODIFIER"],
    ))
    assert g is not None
    assert g.grounding_codes == ["MINOR_LAYER_ONLY"]
    assert g.confidence_adjusted is True
    assert "INTERNAL_SHADOW_XYZ" not in str(g.model_dump())


def test_empty_provenance_yields_none() -> None:
    """후보 기여가 비면 층위를 지어내지 않는다 — 운영 경로의 현재 상태."""
    assert _layer_grounding(_c([])) is None


def test_no_adjustment_flag_without_allowlisted_code() -> None:
    """억제 사유가 없으면 confidence_adjusted는 False다."""
    g = _layer_grounding(_c(["sewoon", "ilwoon"]))
    assert g is not None
    assert g.confidence_adjusted is False
    assert g.grounding_codes == []


def test_stack_layers_are_never_read() -> None:
    """`stack_layers`만 있는 후보는 상위 지지로 승격되지 않는다 — 오독 차단 불변식."""
    stub = SimpleNamespace(
        stack_layers=["daewoon", "sewoon"], candidate_source_layers=[], evidence_path=[]
    )
    assert _layer_grounding(stub) is None
