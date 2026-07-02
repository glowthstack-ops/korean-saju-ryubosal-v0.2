"""구조 패턴 감지 회귀 — 차트별 감지 pattern_id 집합 고정(Step ③).

현재 감지 동작을 고정(golden)한다. 감지기·사전 변경으로 집합이 바뀌면 실패시켜
의도치 않은 회귀를 잡는다. 케이스: tests/fixtures/structure_patterns_cases.jsonl

설계: doc/v2_2/docs/13_STRUCTURE_PATTERNS.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.structure_patterns import detect_structure_patterns
from saju_shared_types.birth_input import BirthInput

_CASES_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "structure_patterns_cases.jsonl"


def _load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in _CASES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["chartId"])
def test_detected_pattern_ids_match_golden(case: dict) -> None:
    r = calculate(BirthInput(
        birth_date=case["birth_date"], birth_time=case["birth_time"],
        birth_place_name=case["birth_place_name"], gender=case["gender"],
    ))
    assert r.geokguk is not None
    assert r.geokguk.main_structure == case["main_structure"], (
        f"{case['chartId']}: 주격 회귀 {r.geokguk.main_structure} != {case['main_structure']}"
    )
    detected = sorted(d.pattern_id for d in detect_structure_patterns(r))
    expected = sorted(case["expected_pattern_ids"])
    assert detected == expected, (
        f"{case['chartId']}: 감지 집합 회귀\n  got={detected}\n  exp={expected}"
    )
