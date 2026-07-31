"""reason_codes raw byte 결정성 회귀 — CAREER_TRANSITION_SYSTEM §15-3.

`EventCandidateV2.reason_codes`가 `set` 순회 + `PYTHONHASHSEED` 무작위화 때문에
프로세스마다 순서가 달라지던 결함(`REASON_CODES_ORDER_NONDETERMINISTIC`)의 회귀.

reason_codes 순서는 `llm_event_serializer.reason_codes_ko`가 그대로 보존해 LLM 입력의
근거 순서가 되므로 **순서에 의미가 있다**. 따라서 정렬로 뭉개지 않고 생성 지점의 순회를
canonical 십성 순서로 고정했다 — 내용·점수는 그대로이고 순서만 결정적이다.

여러 seed에서 **raw serialization이 byte-identical**임을 요구한다(canonical 정규화 없이).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent

#: control 포함 4회 실행 — 고정 seed 3종 + 무작위 seed.
_SEEDS = ("1", "17", "123", "random")

_RUNNER = r"""
import json, sys
from datetime import date
from pathlib import Path

from saju_api.services.manse_service import calculate
from saju_engines import EventEngineV2
from saju_engines.llm_event_serializer import reason_codes_ko
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.ganji_calendar import GanjiLevel

engine = EventEngineV2(Path(sys.argv[1]))
chart = calculate(BirthInput(
    calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
))
cands = engine.score(chart, levels={GanjiLevel.YEAR})
# raw 직렬화 — 정규화·정렬 없이 그대로 비교한다.
out = {
    "count": len(cands),
    "candidates": [c.model_dump(mode="json") for c in cands],
    "signals_ko": [reason_codes_ko(c.reason_codes) for c in cands],
}
print(json.dumps(out, ensure_ascii=False))
"""


def _run(seed: str) -> dict[str, object]:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    proc = subprocess.run(
        [sys.executable, "-c", _RUNNER, str(_BACKEND / "dictionaries")],
        capture_output=True, text=True, cwd=str(_REPO), timeout=900, env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"seed={seed} 실행 실패: {proc.stderr[-1500:]}")
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def runs() -> dict[str, dict[str, object]]:
    return {seed: _run(seed) for seed in _SEEDS}


def test_multi_seed_raw_serialization_is_byte_identical(runs) -> None:
    """seed가 달라도 raw 직렬화가 완전히 같아야 한다(census 포함)."""
    eligible = set(_SEEDS)
    measured = eligible & set(runs)
    assert measured == eligible, f"불완전 계측: {sorted(measured)}"
    baseline = json.dumps(runs["1"], sort_keys=True, ensure_ascii=False)
    violations = [
        seed for seed in _SEEDS
        if json.dumps(runs[seed], sort_keys=True, ensure_ascii=False) != baseline
    ]
    assert not violations, f"raw byte 불일치 seed: {violations}"


def test_reason_codes_order_is_stable_across_seeds(runs) -> None:
    """reason_codes 순서 자체가 seed 간 동일하다(결함의 직접 회귀)."""
    per_seed = {
        seed: [c["reason_codes"] for c in run["candidates"]]
        for seed, run in runs.items()
    }
    baseline = per_seed["1"]
    for seed, codes in per_seed.items():
        assert codes == baseline, f"seed={seed} reason_codes 순서 불일치"


def test_llm_evidence_order_is_stable(runs) -> None:
    """LLM 입력 근거 순서(`signals_ko`)도 seed 간 동일하다."""
    baseline = runs["1"]["signals_ko"]
    for seed in _SEEDS:
        assert runs[seed]["signals_ko"] == baseline, f"seed={seed} signals_ko 불일치"


def test_corpus_is_not_empty(runs) -> None:
    """빈 결과로 통과하는 착시 방지."""
    assert int(runs["1"]["count"]) > 0
