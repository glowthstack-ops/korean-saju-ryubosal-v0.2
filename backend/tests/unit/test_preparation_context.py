"""재물 준비기(lead-up) 컨텍스트 검증 — 발현 후보 등급·준비 신호 강도·역할 판정 (P3).

데굴님 확정 규칙(2026-07-12): 발현 후보=재성 유입 등급제(strong/moderate/weak),
준비 창=직전 2년(Y-1 1.0, Y-2 0.55), 준비 신호=식상 1차·비겁 조건부·인성 단독 금지,
서술 전용 inert(점수·순위·시기·확신도 불변).
"""

from __future__ import annotations

from saju_engines.preparation_context import build_preparation_context
from saju_engines.structural_context import preparation_context_lines
from saju_shared_types.luck import LuckPillar


def _pillar(year: int, stem_tg: str, branch_tg: str) -> LuckPillar:
    return LuckPillar(
        label=str(year), period_type="year", ganji="丙午", stem="丙", branch="午",
        stem_ten_god=stem_tg, branch_ten_god=branch_tg,
    )


def test_manifestation_grades() -> None:
    luck = [
        _pillar(2026, "편재", "정재"),   # 두 자리 모두 재성 → strong
        _pillar(2027, "식신", "편재"),   # 한쪽 재성 + 식상 동반 → moderate
        _pillar(2028, "정재", "정관"),   # 한쪽 재성 단독 → weak
        _pillar(2029, "정관", "정인"),   # 재성 없음 → 후보 아님
    ]
    ctx = build_preparation_context(luck, 2026)
    by = {c.year: c for c in ctx.manifestation_candidates}
    assert by["2026"].grade == "strong"
    assert by["2027"].grade == "moderate"
    assert by["2028"].grade == "weak"
    assert "2029" not in by
    assert ctx.current_year_role == "manifestation"


def test_preparation_window_and_strengths() -> None:
    luck = [
        _pillar(2024, "정인", "비견"),   # Y-2: 비겁 단독(한 자리) → weak, 가중 0.55
        _pillar(2025, "식신", "겁재"),   # Y-1: 식상+비겁 → strong, 가중 1.0
        _pillar(2026, "편재", "정재"),   # 발현 후보(strong)
    ]
    ctx = build_preparation_context(luck, 2025)
    by = {p.year: p for p in ctx.preparation_years}
    assert by["2025"].strength == "strong" and by["2025"].weight == 1.0
    assert set(by["2025"].signals) == {"output", "peer"}
    assert by["2024"].strength == "weak" and by["2024"].weight == 0.55
    assert by["2024"].signals == ["peer"]
    assert ctx.current_year_role == "preparation"


def test_resource_alone_never_creates_preparation_year() -> None:
    # 인성 단독 해는 준비년 생성 금지 — 식상 동반 시에만 resource_support 보조 태그.
    luck = [
        _pillar(2024, "정인", "편인"),   # 인성 단독 → 준비년 아님
        _pillar(2025, "상관", "정인"),   # 식상 + 인성 → moderate + resource_support
        _pillar(2026, "편재", "편재"),
    ]
    ctx = build_preparation_context(luck, 2024)
    years = {p.year for p in ctx.preparation_years}
    assert "2024" not in years
    p2025 = next(p for p in ctx.preparation_years if p.year == "2025")
    assert p2025.strength == "moderate" and p2025.resource_support
    assert ctx.current_year_role == "none"  # 2024는 후보도 준비년도 아님


def test_no_wealth_years_yields_silence() -> None:
    luck = [_pillar(y, "정관", "정인") for y in range(2026, 2032)]
    ctx = build_preparation_context(luck, 2026)
    assert not ctx.is_detected
    assert preparation_context_lines(ctx) == []  # 미검출=무언급


def test_lines_carry_inert_directives() -> None:
    luck = [
        _pillar(2025, "식신", "비견"),
        _pillar(2026, "편재", "정재"),
    ]
    ctx = build_preparation_context(luck, 2025)
    text = "\n".join(preparation_context_lines(ctx))
    assert "서술 전용" in text and "변경 금지" in text
    assert "인과 확정 금지" in text
    assert "시간 지평" in text  # 지평 정책(docs/16) 준수 지시
    assert ctx.usage == "narrative_only"


def test_horizon_bounds_candidates() -> None:
    # 기준년+5년 밖 재성년은 후보에서 제외.
    luck = [
        _pillar(2026, "정관", "정인"),
        _pillar(2033, "편재", "정재"),
    ]
    ctx = build_preparation_context(luck, 2026)
    assert not ctx.manifestation_candidates
