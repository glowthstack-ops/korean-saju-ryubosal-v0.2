"""LLM 토큰 거버넌스 검증 (T2.5.8 — docs/09 8장 한도표·가드 규칙)."""

from __future__ import annotations

import pytest

from saju_engines.llm_guard import (
    CALL_LIMITS,
    LLMCallGuard,
    LLMCostLedger,
    TokenBudgetExceeded,
    estimate_tokens,
)


def test_limit_table_matches_spec() -> None:
    """docs/09 8장 한도표 6행이 그대로 수록된다(임의 상향 금지의 기준점)."""
    assert CALL_LIMITS["chat_single"].max_input_tokens == 6_000
    assert CALL_LIMITS["chat_single"].max_output_tokens == 1_200
    assert CALL_LIMITS["chat_compare"].max_input_tokens == 8_000
    assert CALL_LIMITS["query_parser"].max_input_tokens == 2_000
    assert CALL_LIMITS["report_focus_section"].max_output_chars == 4_500
    assert CALL_LIMITS["consistency_check"].max_output_tokens == 500
    assert len(CALL_LIMITS) == 6


def test_estimate_tokens_conservative_for_korean() -> None:
    """한글/한자는 1자=1토큰으로 과대 추정(가드는 과소 추정 금지)."""
    assert estimate_tokens("가나다라") == 4
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("") == 0


def test_check_input_blocks_before_call() -> None:
    """상한 초과 입력은 호출 전 예외 — Context Reduction 재실행 유도."""
    guard = LLMCallGuard("query_parser")  # 상한 2,000tok
    assert guard.check_input("짧은 질문") > 0
    with pytest.raises(TokenBudgetExceeded, match="Context Reduction"):
        guard.check_input("가" * 2_001)


def test_request_params_disable_thinking() -> None:
    """운영 호출 전체에서 extended thinking 비활성 강제(절대 원칙 9).

    비활성은 thinking 파라미터 생략으로 구현한다(명시적 disabled는 일부 모델 400).
    """
    params = LLMCallGuard("chat_single").request_params()
    assert "thinking" not in params  # 생략 = 비활성, 활성화 키 자체가 없어야 함
    assert params["max_tokens"] == 1_200


def test_unknown_call_type_rejected() -> None:
    """한도표에 없는 호출 유형은 생성 자체가 불가(임의 유형 추가 금지)."""
    with pytest.raises(KeyError):
        LLMCallGuard("free_call")


def test_ledger_accumulates_cost() -> None:
    """입출력 토큰이 원가 장부에 적재된다."""
    ledger = LLMCostLedger()
    guard = LLMCallGuard("report_focus_section", ledger=ledger)
    tokens = guard.check_input("섹션 입력")
    guard.record(tokens, 800, product_code="RPT_FOCUS", section_id="S03")
    guard.record(tokens, 700, product_code="RPT_FOCUS", section_id="S04")
    in_sum, out_sum = ledger.total_tokens()
    assert in_sum == tokens * 2 and out_sum == 1_500
    assert ledger.entries[0].product_code == "RPT_FOCUS"
