"""골든 스타일 회귀 (v2.2.1 PR-D — 2026-06-12 사용자 제공 예시 기준).

기준 픽스처: tests/fixtures/golden_style_ilju_example.md (己亥 '노란 돼지' 풀이).
LLM 실호출 없이 검증 가능한 층을 고정한다:
1. '나의 일주캐릭터는?' 류 질문이 chart_analysis로 분류되고 차단 없이 흐른다.
2. 프롬프트에 골든 스타일의 재료(물상·일주 동물·서사·빛/그림자·배우자궁)가 실린다.
3. 신살 발췌는 양면 해석(길신의 그림자·흉성의 빛)을 동반한다.
4. 페르소나(쉬움·존대)는 5-3 템플릿 치환 블록으로만 생성된다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import saju_api.services.chat_service as chat_service
from saju_engines.persona import PersonaEngine
from saju_shared_types.birth_input import BirthInput
from saju_shared_types.profile import PersonaConfig

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"
_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "golden_style_ilju_example.md"
_TODAY = date(2026, 6, 11)
# 己亥 일주 차트(1980-11-22) — 골든 예시와 동일 일주.
_BIRTH = BirthInput(
    calendar_type="solar", birth_date="1980-11-22", birth_time="09:08",
    birth_place_name="서울", gender="male", reference_date="2026-06-11",
)


def test_ilju_character_question_flows_to_chart_analysis() -> None:
    """'나의 일주캐릭터는?' — Q8 분류 + B3 차단 없이 프롬프트 생성."""
    res = chat_service.chat(_BIRTH, "나의 일주캐릭터는?", _TODAY, dry_run=True)
    assert res.status == "dry_run", res.answer
    assert res.intents[0].query_type.value == "chart_analysis"


def test_prompt_carries_golden_style_materials() -> None:
    """프롬프트에 골든 스타일 체크포인트 재료가 실린다(픽스처 기준)."""
    fixture = _FIXTURE.read_text(encoding="utf-8")
    assert "노란 돼지" in fixture  # 픽스처 자체 보존 확인
    res = chat_service.chat(_BIRTH, "나의 일주캐릭터는?", _TODAY, dry_run=True)
    text = res.prompt_preview or ""
    # 1. 물상 — 들판·강물 형상
    assert "들판" in text and "강물" in text
    # 2. 일주 동물(오행색+띠)
    assert "노란 돼지" in text
    # 3. 빛/그림자 균형 + 배우자궁
    assert "밝은 면:" in text and "그림자:" in text and "배우자궁:" in text
    # 5. 단정 금지 가드 동반
    assert "금기 표현:" in text


def test_sinsal_excerpts_have_flip_side() -> None:
    """신살 발췌 — 보조 표기 + 양면 해석(길신의 그림자·흉성의 빛) 동반."""
    res = chat_service.chat(_BIRTH, "나의 일주캐릭터는?", _TODAY, dry_run=True)
    text = res.prompt_preview or ""
    assert "(보조 — 단독 판정 금지)" in text
    assert "양면:" in text


def test_persona_easy_jondae_block_is_template_only() -> None:
    """페르소나(쉬움·존대) — 5-3 템플릿 블록 생성 + 골든 예시 톤이 준수 검사를 통과."""
    engine = PersonaEngine(_DICTS)
    config = PersonaConfig(difficulty="easy")  # 기본 jondae+haeyo·친절 톤
    block = engine.build_block(config, "회원")
    assert block  # 빈 블록 금지(즉석 작문이 아니라 템플릿 치환)
    # 골든 예시의 '~이에요/~네요' 존대 톤이 준수 검사를 통과해야 한다.
    report = engine.check_compliance(
        "이 일주는 들판 아래 강물이 흐르는 형상이에요. 다정한 분이시네요.", config, "회원",
    )
    assert report.passed, report.violations
