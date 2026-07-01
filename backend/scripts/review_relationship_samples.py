#!/usr/bin/env python3
"""관계 궁합 골든 샘플 스냅샷 러너 — 사람 검수용 (2026-07-01).

SSOT: doc/v2_2/RELATIONSHIP_READING.md §9~§10. P4(관계질 라벨)·P2(12신살 상대위치)·P3(궁위
관계망)·P1(삼합국 역학 shadow)의 실제 출력을 샘플별로 한눈에 찍어, 문구가 과하거나 낙인처럼
보이지 않는지·설명력이 렌더 승급할 만한지 사람이 검수한다(자동 가드는 tests/regression에 있음).

사용: python backend/scripts/review_relationship_samples.py [--id R13_spouse_palace]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    / "relationship_golden_samples.jsonl"
)


def _print_block(title: str, lines: list[str]) -> None:
    print(f"  ── {title} " + "─" * max(0, 40 - len(title)))
    if lines:
        for ln in lines:
            print(f"    {ln}")
    else:
        print("    (없음)")


def _review(sample: dict) -> None:
    self_chart = calculate(BirthInput(**sample["self"]))
    partner_chart = calculate(BirthInput(**sample["partner"]))
    su = build_birth_summary(self_chart).useful_gods
    pu = build_birth_summary(partner_chart).useful_gods
    def _day(chart) -> str:
        d = chart.pillars.day if chart.pillars else None
        return f"{d.stem}{d.branch}" if d else "?"
    sd, pd = _day(self_chart), _day(partner_chart)

    print("=" * 78)
    print(f"[{sample['id']}] {sample['relation_type']}  |  본인 {sd} ↔ 상대 {pd}")
    report = analyze_compatibility(self_chart, partner_chart, su, pu)
    _print_block("P4 궁합(관계질 라벨)", compatibility_lines(report) if report else [])
    _print_block("P2 12신살 상대위치", relative_sinsal_lines(self_chart, partner_chart))
    _print_block(
        "P3 궁위 관계망(본인·관계맥락)",
        palace_network_lines(analyze_palace_network(self_chart), Domain.RELATIONSHIP),
    )
    dyn = analyze_trine_dynamics(self_chart, partner_chart)
    if dyn is not None:
        _print_block(
            "P1 삼합국 역학(shadow — 미노출)",
            [f"{dyn.base_group}({dyn.base_element}) ↔ {dyn.target_group}({dyn.target_element}) "
             f"= {dyn.dynamics_label}: {dyn.reading}"],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="관계 궁합 골든 샘플 스냅샷")
    parser.add_argument("--id", help="특정 샘플 id만 출력", default=None)
    args = parser.parse_args()
    with _FIXTURE.open(encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()]
    for s in samples:
        if args.id and s["id"] != args.id:
            continue
        _review(s)


if __name__ == "__main__":
    main()
