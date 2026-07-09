"""능동 제안 LLM 배선 (Phase C, docs/15 §6) — 선별·직렬화·캐시 순수성·chat/report 주입."""

from __future__ import annotations

from datetime import date

import pytest

from saju_api.services import report_service
from saju_api.services.manse_service import calculate
from saju_engines.context_reducer import _NO_SUGGESTION_QUERY_TYPES, serialize_chart_prefix
from saju_engines.direction_suggestion import (
    DIRECTION_SUGGESTION_INSTRUCTION,
    detect_direction_suggestions,
    format_direction_suggestion_lines,
    select_direction_suggestions,
)
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.direction_suggestions import DirectionSuggestion
from saju_shared_types.intent import QueryType
from saju_shared_types.report import ReportPeriod, ReportSpec

_TODAY = date(2026, 7, 9)
# 발화 차트 — 태신약+재성과다(WEALTH_EXCESS caution)·인성부족 운보충 발화(Phase B 검증).
_FIRING_BIRTH = BirthInput(
    calendar_type="solar",
    birth_date="1978-07-21",
    birth_time="04:00",
    birth_place_name="서울",
    gender="male",
    reference_date="2026-07-09",
)
# 균형 차트 — 전 군 임계 안, 제안 0건(억지 제안 금지 확인용).
_QUIET_BIRTH = BirthInput(
    calendar_type="solar",
    birth_date="1980-11-22",
    birth_time="09:08",
    birth_place_name="서울",
    gender="male",
    reference_date="2026-07-09",
)


def _fake(
    suggestion_id: str, group: str, strength: float, mode: str = "recommend"
) -> DirectionSuggestion:
    """선별·직렬화 단위 테스트용 최소 제안."""
    return DirectionSuggestion(
        suggestion_id=suggestion_id,
        name_ko=f"{suggestion_id} 테스트",
        group=group,
        group_state="natal_excess",
        mode=mode,  # type: ignore[arg-type]
        strength=strength,
        channel_id="c1",
        headline="테스트 방향",
        actions=["행동1", "행동2"],
        avoid=["회피1"],
        reality_note="전제 설명",
        cautions=["주의 문구"] if mode == "caution" else [],
        forbidden_framings=["단정 표현"],
        llm_tag="태그",
    )


# ── 선별·직렬화 (단위) ──────────────────────────────────────────────────


def test_select_caps_and_prioritizes_domain() -> None:
    """도메인 일치 군 우선(소프트 필터), 이후 strength, 상한 2."""
    pool = [
        _fake("A_WEALTH", "wealth", 0.9),
        _fake("B_AUTH", "authority", 0.5),
        _fake("C_RESOURCE", "resource", 0.7),
    ]
    picked = select_direction_suggestions(pool, domains=["career"])
    assert len(picked) == 2
    assert picked[0].suggestion_id == "B_AUTH"  # career→authority 우선(강도 열세여도)
    assert picked[1].suggestion_id == "A_WEALTH"  # 나머지는 strength 순 — 배제 없음
    no_domain = select_direction_suggestions(pool)
    assert [s.suggestion_id for s in no_domain] == ["A_WEALTH", "C_RESOURCE"]


def test_format_empty_no_header() -> None:
    """빈 목록은 빈 리스트 — 헤더·토큰 낭비 없음."""
    assert format_direction_suggestion_lines([]) == []


def test_format_caution_puts_warning_before_actions() -> None:
    """주의 모드 — 주의 문구가 행동 재료보다 먼저, 표현 금지 목록 동반."""
    lines = format_direction_suggestion_lines([_fake("X", "wealth", 0.5, mode="caution")])
    text = "\n".join(lines)
    assert "[제안 방향" in lines[1] and "단정 금지" in lines[1]
    assert text.index("주의: 주의 문구") < text.index("해볼 만한 것")
    assert "표현 금지: 단정 표현" in text
    assert "(주의)" in text


# ── 캐시 프리픽스 순수성 ────────────────────────────────────────────────


def test_prefix_free_of_suggestions() -> None:
    """제안 블록은 세운 의존 — 캐시 프리픽스에 절대 실리지 않는다."""
    from saju_engines.chart_interpretation import build_chart_interpretation
    from saju_engines.context_reducer import build_birth_summary

    result = calculate(_FIRING_BIRTH)
    assert detect_direction_suggestions(result), "발화 차트 전제가 깨지면 테스트 무효"
    prefix = serialize_chart_prefix(build_birth_summary(result), build_chart_interpretation(result))
    assert not any("[제안 방향" in line for line in prefix)


# ── chat 배선 (동적 suffix + 지시 + 게이팅) ─────────────────────────────


def test_chat_full_input_carries_block_and_instruction() -> None:
    """재물 질문(발화 차트) — [제안 방향]이 [기준 시점] 이후에 실리고 지시문 동반."""
    import saju_api.services.chat_service as chat_service

    res = chat_service.chat(_FIRING_BIRTH, "올해 재물운은 어떤가요?", _TODAY, dry_run=True)
    assert res.prompt_preview is not None
    text = res.prompt_preview
    assert "[기준 시점]" in text
    suffix = text.split("[기준 시점]", 1)[1]
    assert "[제안 방향" in suffix, "동적 suffix에 제안 블록이 실려야 한다"
    assert "[제안 방향" not in text.split("[기준 시점]", 1)[0], "프리픽스 오염 금지"
    assert DIRECTION_SUGGESTION_INSTRUCTION in suffix
    assert "고려" in suffix


def test_chat_domain_reorders_suggestions() -> None:
    """질문 도메인에 따라 제안 순서가 달라진다 — 재물 질문은 재성 제안 먼저."""
    import saju_api.services.chat_service as chat_service

    def _first_suggestion(question: str) -> str:
        res = chat_service.chat(_FIRING_BIRTH, question, _TODAY, dry_run=True)
        assert res.prompt_preview is not None
        after = res.prompt_preview.split("[제안 방향", 1)[1]
        return after.splitlines()[1]  # 첫 제안 라인

    assert "재성" in _first_suggestion("올해 재물운은 어떤가요?")
    assert "인성" in _first_suggestion("자격증 공부를 시작해도 될까요?")


def test_chat_quiet_chart_no_block() -> None:
    """균형 차트 — 발화 없으면 블록·지시문 자체가 없다(억지 제안 금지)."""
    import saju_api.services.chat_service as chat_service

    res = chat_service.chat(_QUIET_BIRTH, "올해 재물운은 어떤가요?", _TODAY, dry_run=True)
    assert res.prompt_preview is not None
    assert "[제안 방향" not in res.prompt_preview
    assert DIRECTION_SUGGESTION_INSTRUCTION not in res.prompt_preview


def test_no_suggestion_query_types() -> None:
    """제안 미노출 유형 — 용어교육·피드백·감정지원·범위외(설계 §6)."""
    assert set(_NO_SUGGESTION_QUERY_TYPES) == {
        QueryType.TERMINOLOGY_EDUCATION,
        QueryType.FEEDBACK_CORRECTION,
        QueryType.EMOTIONAL_SUPPORT,
        QueryType.OUT_OF_SCOPE,
    }


# ── report 배선 (재물·직업 도메인 섹션) ─────────────────────────────────


@pytest.fixture(scope="module")
def wealth_report_contexts():
    spec = ReportSpec(
        product_code="RPT_FOCUS",
        subjects=[{"kind": "self", "label": "본인"}],
        topic="wealth",
        period=ReportPeriod(start="2026-01", end="2026-12"),
    )
    return report_service.plan_report(_FIRING_BIRTH, spec, _TODAY)


def test_report_wealth_sections_carry_block(wealth_report_contexts) -> None:
    """재물 도메인 섹션(W-06/W-07)에 제안 블록 + 지시문 주입."""
    domain_secs = [
        c
        for c in wealth_report_contexts
        if report_service._SECTION_DOMAIN.get(c.section_id) == "wealth"
    ]
    assert domain_secs, "재물 테마에 wealth 도메인 섹션이 있어야 한다"
    for sec in domain_secs:
        assert "[제안 방향" in sec.body_prompt
        assert DIRECTION_SUGGESTION_INSTRUCTION in sec.body_prompt


def test_report_non_domain_sections_untouched(wealth_report_contexts) -> None:
    """도메인 밖 섹션(W-01 등)에는 주입하지 않는다 — 반복·소음 방지."""
    others = [
        c
        for c in wealth_report_contexts
        if report_service._SECTION_DOMAIN.get(c.section_id) not in ("wealth", "career")
    ]
    assert others
    for sec in others:
        assert "[제안 방향" not in sec.body_prompt
