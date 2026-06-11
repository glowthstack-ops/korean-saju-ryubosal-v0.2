"""M03·M10·M15 모듈 검증 (T2.5.6·T2.5.7 — docs/09 4·6·7장, docs/02 E9)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from saju_api.services.manse_service import calculate
from saju_engines.precompute import CompositeBuilder
from saju_engines.relocation import RelocationResolver, is_son_eomneun_nal
from saju_engines.topic_builder import build_topic_context
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.intent import SubjectKind, SubjectRef
from saju_shared_types.relocation import RelocationPeriod, RelocationQuery
from saju_shared_types.topic_context import PeriodSpec

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_SELF = SubjectRef(kind=SubjectKind.SELF, label="본인")


@pytest.fixture(scope="module")
def chart():
    """기준 차트(1980, 기준일 2026-06-11 → 월운 2026 전체·일운 2026-06)."""
    return calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 6, 11),
    ))


@pytest.fixture(scope="module")
def composites(chart):
    """전체 레벨 LuckComposite."""
    return CompositeBuilder(_DICTS).build(
        chart, "본인", "1.0.0", "2026-06-11T00:00:00+00:00"
    )


# ── M03 personality_traits ───────────────────────────────────────


def test_m03_requires_natal_dist(composites) -> None:
    """M03은 T0 십성 분포 없이 호출하면 명시적 오류."""
    period = PeriodSpec(start="2024", end="2027", granularity="year")
    with pytest.raises(TypeError):
        build_topic_context("M03", [_SELF], period, composites)


def test_m03_trait_shifts(chart, composites) -> None:
    """대운·세운별 TraitShift — 가중식(1.0/0.45/0.25) 기반, 발현 질 플래그 포함."""
    natal_dist = chart.force_analysis.ten_gods.distribution
    period = PeriodSpec(start="2022", end="2031", granularity="year")
    ctx = build_topic_context(
        "M03", [_SELF], period, composites, natal_ten_god_dist=natal_dist,
    )
    assert ctx.module_id == "M03" and ctx.trait_shifts
    # 대운(DW:)과 세운(YYYY) 단위가 모두 산출된다.
    keys = {s.period_key for s in ctx.trait_shifts}
    assert any(k.startswith("DW:") for k in keys)
    assert any(k.isdigit() for k in keys)
    for s in ctx.trait_shifts:
        assert 2 <= len(s.dominant_ten_gods) <= 3
        assert s.quality_flag in ("favorable", "pressured", "mixed")
    # MBTI식 고정 유형화 금지가 스타일 규칙에 실린다(docs/02 E5).
    assert any("MBTI" in p for p in ctx.style_rules.prohibited_expressions)


def test_m03_deterministic(chart, composites) -> None:
    """동일 입력 → 동일 TraitShift."""
    natal_dist = chart.force_analysis.ten_gods.distribution
    period = PeriodSpec(start="2024", end="2026", granularity="year")
    a = build_topic_context("M03", [_SELF], period, composites,
                            natal_ten_god_dist=natal_dist)
    b = build_topic_context("M03", [_SELF], period, composites,
                            natal_ten_god_dist=natal_dist)
    assert a.model_dump() == b.model_dump()


# ── M15 lifestyle ────────────────────────────────────────────────


def test_m15_daily_covers_all_slots(composites) -> None:
    """일일: format_slots.json의 슬롯 7종 전부 채움(축약 금지)."""
    period = PeriodSpec(start="2026-06-11", end="2026-06-11", granularity="day")
    ctx = build_topic_context("M15", [_SELF], period, composites)
    slot_keys = [f.key for f in ctx.findings]
    assert slot_keys == [
        "slot:핵심기운", "slot:일·공부", "slot:돈·소비", "slot:관계·연애",
        "slot:건강", "slot:주의행동", "slot:활용법",
    ]
    assert all(0 <= f.score <= 100 for f in ctx.findings)


def test_m15_yearly_covers_all_slots(composites) -> None:
    """연간: 슬롯 8종 전부 + 상·하반기 집계 문자열."""
    period = PeriodSpec(start="2026", end="2026", granularity="year")
    ctx = build_topic_context("M15", [_SELF], period, composites)
    assert len(ctx.findings) == 8
    half = next(f for f in ctx.findings if f.key == "slot:상·하반기")
    assert "상반기" in half.summary and "하반기" in half.summary


# ── M10 relocation_composite ─────────────────────────────────────


@pytest.fixture(scope="module")
def relocation_query() -> RelocationQuery:
    """1인 가구 이사 질의(2026년, 제약 없음)."""
    return RelocationQuery(
        group_subjects=[_SELF],
        period=RelocationPeriod(start="2026-01", end="2026-12"),
        current_location="서울",
        housing_type="jeonse",
    )


@pytest.fixture(scope="module")
def composites_with_feb_days(composites):
    """기준 composites + 2026-02 일운 병합.

    엔진은 기준일이 속한 달의 일운만 계산하므로, 운영에서는 Precompute Store가
    미래 400일 일운을 누적 보존한다(T2.5.5). 후보 월(2026-02)의 일운을 별도 기준일
    계산으로 병합해 그 상태를 재현한다.
    """
    feb_chart = calculate(BirthInput(
        calendar_type="solar", birth_date=date(1980, 11, 22), birth_time="09:08",
        birth_place_name="서울", gender="male", reference_date=date(2026, 2, 15),
    ))
    from saju_shared_types.precompute import CompositeLevel

    feb = CompositeBuilder(_DICTS).build(
        feb_chart, "본인", "1.0.0", "2026-02-15T00:00:00+00:00",
        levels={CompositeLevel.DAY},
    )
    return [*composites, *feb]


def test_m10_resolver_ranks_move_dates(composites_with_feb_days, relocation_query) -> None:
    """S1~S10: 이사일 랭킹 + 부분점수 5종 + 방위 분리 산출."""
    resolver = RelocationResolver(_DICTS)
    result = resolver.resolve(
        relocation_query, {"본인": composites_with_feb_days}, {"본인": "土"},
    )
    assert result.move_dates, "후보 월(일운 보유 월) 내 이사일이 나와야 함"
    top = result.move_dates[0]
    assert 0 <= top.final_score <= 100
    # 부분점수 5종(docs/09 7장 S10).
    s = top.scores
    assert all(0 <= v <= 100 for v in (
        s.macro_flow, s.month_fit, s.day_execution, s.calendar_rule, s.reality_fit,
    ))
    # 방위 미지정 → 8방위 분리 산출(단일 답 강제 금지).
    assert len(top.direction_fit) == 8
    # 점수 내림차순 랭킹.
    scores = [c.final_score for c in result.move_dates]
    assert scores == sorted(scores, reverse=True)


def test_m10_weekend_constraint(composites_with_feb_days) -> None:
    """S8: '주말만 가능' 제약 시 토·일만 남는다."""
    query = RelocationQuery(
        group_subjects=[_SELF],
        period=RelocationPeriod(start="2026-01", end="2026-12"),
        current_location="서울",
        reality_constraints=["주말만 가능"],
    )
    result = RelocationResolver(_DICTS).resolve(
        query, {"본인": composites_with_feb_days}, {"본인": "土"}
    )
    for c in result.move_dates:
        assert date.fromisoformat(c.date).weekday() >= 5


def test_m10_son_eomneun_nal_rule() -> None:
    """S7: 손없는 날 = 음력 일 끝자리 9·0 (2026-06-24 = 음력 5/10)."""
    assert is_son_eomneun_nal(date(2026, 6, 24)) is True
    assert is_son_eomneun_nal(date(2026, 6, 25)) is False  # 음력 5/11


def test_m10_topic_context_wrapper(composites_with_feb_days, relocation_query) -> None:
    """M10 디스패치: ranked_results + 그룹 집계 + 예산(compare 8k)."""
    period = PeriodSpec(start="2026-01", end="2026-12", granularity="day")
    ctx = build_topic_context(
        "M10", [_SELF], period, composites_with_feb_days,
        relocation_query=relocation_query,
        composites_by_subject={"본인": composites_with_feb_days},
        yongsin_by_subject={"본인": "土"},
    )
    assert ctx.module_id == "M10" and ctx.ranked_results
    assert ctx.group_aggregation is not None
    assert ctx.budget.max_input_tokens == 8_000


def test_m10_region_fit_uses_dictionary() -> None:
    """S5 보조: 지역오행 적합(동일=1.0/생=0.8/미등재=0.5 중립)."""
    resolver = RelocationResolver(_DICTS)
    fit = resolver.region_fit(["대전", "서울", "미등재시"], {"본인": "土"})
    assert fit["대전"] == 1.0  # 大田=土, 용신 土
    assert fit["미등재시"] == 0.5
