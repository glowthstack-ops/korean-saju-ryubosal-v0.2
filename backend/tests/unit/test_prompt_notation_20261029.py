"""LLM 입력 표기 — 범위·자리표시 물결표 제거 (2026-10-29, docs/06 표현 원칙 8).

마크다운 뷰어가 ``~``와 ``~`` 사이를 취소선으로 그려 방위 값·표현 규칙이 지워진 것처럼
보이던 문제. 정적 지시문은 원문을 고치고, 데이터 조립 범위 라벨은 경계에서 ``–``로 바꾼다.
"""

from __future__ import annotations

from pathlib import Path

from saju_api.services.llm_client import _REPORT_SYSTEM_PROMPT, _SYSTEM_PROMPT
from saju_engines import context_reducer, structural_context
from saju_engines.persona import PersonaEngine
from saju_engines.prompt_notation import normalize_range_tilde
from saju_shared_types.sinsal_direction import branch_compass_label

_DICTS = Path(__file__).resolve().parents[2] / "dictionaries"


def test_system_prompts_and_shared_directives_have_no_tilde() -> None:
    """시스템 프롬프트 2종·공용 지시 상수에 ``~``가 없다(자리표시는 ``…``, 범위는 ``–``)."""
    for name in ("ASSERTION_POLICY", "ANSWER_CLARITY_DIRECTIVE", "AVOID_DATE_CERTAINTY_DIRECTIVE"):
        assert "~" not in getattr(structural_context, name), name
    assert "~" not in _SYSTEM_PROMPT and "~" not in _REPORT_SYSTEM_PROMPT
    assert "'…할 수 있다'" in structural_context.ASSERTION_POLICY
    for name in ("_BASE_INSTRUCTION", "_DAILY_INSTRUCTION"):
        assert "~" not in getattr(context_reducer, name), name


def test_normalize_range_tilde_only_touches_numeric_ranges() -> None:
    """숫자 범위만 ``–``로, 사용자 발화 인용의 ``~``·취소선 마크업은 손대지 않는다."""
    assert normalize_range_tilde("甲子(2026~2035, 정관)") == "甲子(2026–2035, 정관)"
    assert normalize_range_tilde("기간 2026-01-01 ~ 2026-03-31") == "기간 2026-01-01 – 2026-03-31"
    assert normalize_range_tilde("子 정북 345°~15°") == "子 정북 345°–15°"
    assert normalize_range_tilde("乙丑(2036~)") == "乙丑(2036–)"
    assert normalize_range_tilde("甲子 대운(42세~): 지속") == "甲子 대운(42세–): 지속"
    kept = "사용자: 그럼~ 이직은 언제쯤~? ~~취소~~"
    assert normalize_range_tilde(kept) == kept
    plain = "물결표 없음"
    assert normalize_range_tilde(plain) is plain


def test_compass_label_and_persona_endings_use_new_notation() -> None:
    """방위 각도 라벨은 ``–``, 페르소나 종결어미 목록은 ``…`` 자리표시."""
    assert branch_compass_label("子") == "정북 345°–15°"
    endings = PersonaEngine(_DICTS)._endings
    assert all("~" not in e for group in endings.values() for e in group)
    assert "…예요" in endings["haeyo"]
