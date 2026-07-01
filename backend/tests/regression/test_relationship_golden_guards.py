"""관계 궁합 골든 샘플 — 자동 가드 회귀 (2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §9. P4~P1 관계 레이어가 실제 샘플(20건·8유형)에서 금지어·
낙인·과노출·shadow 유출 없이 동작하는지 자동 검증한다. 설명력(자연스러움)은 사람 검수용 스냅샷
러너(scripts/review_relationship_samples.py)로 별도 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.compatibility_engine import analyze_compatibility, compatibility_lines
from saju_engines.context_reducer import build_birth_summary
from saju_engines.palace_relationship_network import (
    analyze_palace_network,
    palace_network_lines,
)
from saju_engines.relationship_relative_sinsal import relative_sinsal_lines
from saju_engines.relationship_trine_dynamics import analyze_trine_dynamics
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import Domain

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "relationship_golden_samples.jsonl"

# 관계 서술에 등장하면 안 되는 낙인·승패·과단정 어휘.
_BANNED = [
    "악연", "속궁합", "집착", "징글징글", "이긴다", "진다", "승패", "서열",
    "상전", "못 이김", "무조건 좋음", "무조건 이별", "파국",
]
# 12신살 상대위치에서 내부(약노출) 신살 — 노출 문구에 등장 금지.
_INTERNAL_SINSAL = ["겁살", "재살", "월살"]


def _samples() -> list[dict]:
    with _FIXTURE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _exposed_layers(sample: dict) -> dict[str, list[str]]:
    """P4(궁합 라벨)·P2(12신살 상대위치)·P3(궁위 관계망) 노출 레이어를 렌더한다."""
    self_chart = calculate(BirthInput(**sample["self"]))
    partner_chart = calculate(BirthInput(**sample["partner"]))
    su = build_birth_summary(self_chart).useful_gods
    pu = build_birth_summary(partner_chart).useful_gods
    report = analyze_compatibility(self_chart, partner_chart, su, pu)
    p4 = compatibility_lines(report) if report is not None else []
    p2 = relative_sinsal_lines(self_chart, partner_chart)
    p3 = palace_network_lines(analyze_palace_network(self_chart), Domain.RELATIONSHIP)
    return {"p4": p4, "p2": p2, "p3": p3}


@pytest.fixture(scope="module")
def rendered() -> list[tuple[dict, dict[str, list[str]]]]:
    return [(s, _exposed_layers(s)) for s in _samples()]


def test_fixture_loads_20_samples() -> None:
    samples = _samples()
    assert len(samples) >= 20
    assert {s["relation_type"] for s in samples} >= {"부부", "연인", "부모자식", "상사부하", "동업"}


def test_no_banned_words(rendered) -> None:
    for sample, layers in rendered:
        text = "\n".join(layers["p4"] + layers["p2"] + layers["p3"])
        for banned in _BANNED:
            assert banned not in text, f"[{sample['id']}] 금지어 '{banned}' 노출"


def test_internal_sinsal_not_exposed(rendered) -> None:
    for sample, layers in rendered:
        text = "\n".join(layers["p2"])
        for internal in _INTERNAL_SINSAL:
            assert internal not in text, f"[{sample['id']}] 내부 신살 '{internal}' 노출"


def test_p1_shadow_not_leaked(rendered) -> None:
    # P1(삼합국 역학)은 shadow — 어떤 노출 레이어에도 그 reading 문구가 새지 않아야 한다.
    for sample, layers in rendered:
        self_chart = calculate(BirthInput(**sample["self"]))
        partner_chart = calculate(BirthInput(**sample["partner"]))
        dyn = analyze_trine_dynamics(self_chart, partner_chart)
        if dyn is None:
            continue
        assert dyn.exposure == "shadow"
        text = "\n".join(layers["p4"] + layers["p2"] + layers["p3"])
        assert dyn.reading not in text  # shadow 미유출


def test_p3_cross_palace_gated_for_career(rendered) -> None:
    # P3 cross-palace 조건부 노트는 career 도메인에선 절대 등장하지 않아야 한다.
    for sample, _layers in rendered:
        self_chart = calculate(BirthInput(**sample["self"]))
        career = "\n".join(
            palace_network_lines(analyze_palace_network(self_chart), Domain.CAREER)
        )
        assert "(조건부)" not in career, f"[{sample['id']}] career에 cross-palace 노출"
