"""이벤트 채점 층별 ablation 감사 — 측정 가능성 고정.

EVENT_SCORING_3LAYER_PROPOSAL P0 (2026-09-10 승인).

감사는 판정하지 않는다: 수치 상한(예: 12운성 포화율 ≤ X%)은 명리 판단이라 여기서 강제하지
않고, 산출물의 형태·범위·결정론만 고정한다. 기준선 수치는 WORKLOG/제안서 §3 에 기록.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def audit() -> ModuleType:
    script = _BACKEND / "scripts" / "audit_event_layer_ablation.py"
    spec = importlib.util.spec_from_file_location("audit_event_layer_ablation", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_event_layer_ablation"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def report(audit: ModuleType):
    return audit.run_ablation(4, 2026)


def test_report_shape_and_ranges(audit: ModuleType, report) -> None:
    assert report.charts == 4 and report.candidates > 0 and report.periods > 0
    assert abs(sum(report.share.values()) - 1.0) < 1e-6
    for layer in audit.LAYERS:
        assert 0.0 <= report.period_top_changed[layer] <= 1.0
        assert 0.0 <= report.year_top5_changed[layer] <= 1.0
    assert 0.0 <= report.stage_cap_share <= 1.0
    assert report.stage_mean_by_stage  # 스테이지별 평균이 비어 있지 않다


def test_base_layer_dominates_and_stage_is_measurable(report) -> None:
    """현행 구조의 특징을 측정으로 고정 — base 가 최대 기여, stage 포화율이 산출된다."""
    assert max(report.share, key=report.share.get) == "base"
    assert "stage" in report.share and report.stage_cap_share >= 0.0


def test_corpus_is_deterministic(audit: ModuleType) -> None:
    assert audit.synthetic_corpus(3) == audit.synthetic_corpus(3)
    assert audit.synthetic_corpus(3)[0] == ("1955-01-01", "00:00", "female")
