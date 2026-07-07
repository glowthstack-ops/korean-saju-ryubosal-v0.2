"""Context Reduction 전/후 입력 토큰 비교 리포트 (Phase 8 T8.2).

축소 없이 전체 데이터(전 후보 + 전체 운 직렬화)를 넣었을 때 대비, Context Reduction
(Top5·score≥40·계층 압축) 적용 후 입력 토큰을 표본 질문별로 비교한다.

실행: .venv/bin/python scripts/measure_tokens.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "apps" / "api"))

import saju_api.services.chat_service as chat_service  # noqa: E402
from saju_engines.context_reducer import build_llm_input, serialize_llm_input  # noqa: E402
from saju_engines.llm_guard import estimate_tokens  # noqa: E402
from saju_engines.planner import build_execution_plan  # noqa: E402
from saju_engines.query_parser import parse_message  # noqa: E402
from saju_shared_types.birth_input import BirthInput  # noqa: E402
from saju_shared_types.ganji_calendar import GanjiLevel  # noqa: E402

_TODAY = date(2026, 6, 11)
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)

SAMPLE_QUESTIONS = [
    "올해 이직운 어때?",
    "내년 연애운은 어때?",
    "올해 재물운 좀 봐줘",
    "언제 이사가면 좋을까?",
    "올해 건강운 어때?",
]


def measure(question: str) -> tuple[int, int]:
    """(축소 전 토큰, 축소 후 토큰) — 동일 질문·동일 차트 기준."""
    parsed = parse_message(question, _TODAY, birth_year=_BIRTH.birth_date.year)
    intent = parsed.intents[0]
    plan = build_execution_plan(intent)

    chart_birth = _BIRTH.model_copy(update={"reference_date": _TODAY})
    result = chat_service.calculate(chart_birth)
    scorer = chat_service._get_scorer()
    all_candidates = scorer.score_legacy(result, levels={GanjiLevel.YEAR, GanjiLevel.MONTH})
    bundles = chat_service._get_graph().retrieve(
        plan.graph_scope or [c.event_key for c in all_candidates[:5]]
    )

    # 축소 전 기준선: 계층 압축·Top5 필터 없이 후보 전수 + 전체 달력 직렬화.
    from saju_engines.context_reducer import build_calendar_context

    full_payload = build_llm_input(
        question, intent, result, all_candidates, bundles, scorer,
        call_type="chat_single",
    )
    full_payload = full_payload.model_copy(update={
        "calendar": build_calendar_context(result, all_candidates, intent),
        "event_candidates": full_payload.event_candidates,
    })
    # 후보 전수 미축소 직렬화 근사: 선택본 직렬화 + 잔여 후보 텍스트 가산.
    reduced_text = serialize_llm_input(full_payload)
    leftover = len(all_candidates) - len(full_payload.event_candidates)
    per_candidate = (
        estimate_tokens(reduced_text) // max(1, len(full_payload.event_candidates))
        if full_payload.event_candidates else 0
    )
    before = estimate_tokens(reduced_text) + max(0, leftover) * max(40, per_candidate // 4)

    # 축소 후: 운영 경로 그대로.
    res = chat_service.chat(_BIRTH, question, _TODAY, dry_run=True)
    after = res.input_tokens or 0
    return before, after


def main() -> None:
    print(f"{'질문':<24} {'축소 전':>8} {'축소 후':>8} {'절감':>7}")
    print("-" * 52)
    total_before = total_after = 0
    for q in SAMPLE_QUESTIONS:
        before, after = measure(q)
        total_before += before
        total_after += after
        saved = (1 - after / before) * 100 if before else 0.0
        print(f"{q:<24} {before:>8,} {after:>8,} {saved:>6.1f}%")
    saved = (1 - total_after / total_before) * 100 if total_before else 0.0
    print("-" * 52)
    print(f"{'합계':<24} {total_before:>8,} {total_after:>8,} {saved:>6.1f}%")


if __name__ == "__main__":
    main()
