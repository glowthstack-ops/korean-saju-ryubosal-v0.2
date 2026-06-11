"""Topic Builder 골격·M07 검증 (T2.5.6 — docs/09 4·5장)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.precompute import CompositeBuilder
from saju_engines.topic_builder import MODULES, build_topic_context
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.topic_context import PeriodSpec

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


@pytest.fixture(scope="module")
def composites():
    """기준 차트(1980)의 전체 LuckComposite."""
    result = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))
    return CompositeBuilder(_DICTS).build(
        result, "s-topic", "1.0.0", "2026-06-11T00:00:00+00:00"
    )


def test_registry_is_exactly_fifteen_modules() -> None:
    """모듈 목록은 M01~M15 전체이며 추가·누락이 없다(docs/09 4장 규격)."""
    assert set(MODULES) == {f"M{i:02d}" for i in range(1, 16)}
    assert MODULES["M07"] == "career" and MODULES["M10"] == "relocation_composite"


def test_unknown_module_rejected(composites) -> None:
    """15종 밖 모듈 ID는 명시적 거부(새 주제는 모듈 추가로만)."""
    period = PeriodSpec(start="2024-01", end="2026-12", granularity="month")
    with pytest.raises(KeyError):
        build_topic_context("M16", [], period, composites)


def test_planned_module_raises_not_implemented(composites) -> None:
    """등록만 된 모듈은 NotImplementedError로 미구현을 드러낸다."""
    period = PeriodSpec(start="2024-01", end="2026-12", granularity="month")
    with pytest.raises(NotImplementedError, match="M01"):
        build_topic_context("M01", [], period, composites)


def test_m07_career_context(composites) -> None:
    """M07: career 신호 시계열 + 상위 findings(점수 확정·Top5) + 압축 간지 동반."""
    period = PeriodSpec(start="2022", end="2031", granularity="year")
    ctx = build_topic_context("M07", [], period, composites)

    assert ctx.module_id == "M07"
    assert ctx.findings and len(ctx.findings) <= 5
    assert all(0 <= f.score <= 100 for f in ctx.findings)
    # 2024 甲辰(갑기합 — 직업 신호)이 잡혀야 한다.
    assert any(f.period_key == "2024" for f in ctx.findings)
    # 시계열 항목마다 간지가 동반된다(LLM 간지 계산 금지 보완 — 절대 원칙 2).
    assert all(p.ganji for p in ctx.time_series)
    keys = {e.period_key for e in ctx.calendar_context}
    assert {p.period_key for p in ctx.time_series} <= keys


def test_m07_findings_are_final_numbers(composites) -> None:
    """findings 수치는 빌더에서 확정 — 동일 입력 → 동일 출력(결정성)."""
    period = PeriodSpec(start="2022", end="2031", granularity="year")
    a = build_topic_context("M07", [], period, composites)
    b = build_topic_context("M07", [], period, composites)
    assert a.model_dump() == b.model_dump()


def test_m07_style_and_budget(composites) -> None:
    """단정 금지 스타일 + docs/09 8장 예산이 컨텍스트에 실린다."""
    period = PeriodSpec(start="2024", end="2024", granularity="year")
    ctx = build_topic_context("M07", [], period, composites)
    assert "반드시" in ctx.style_rules.prohibited_expressions
    assert ctx.budget.max_input_tokens == 6_000
