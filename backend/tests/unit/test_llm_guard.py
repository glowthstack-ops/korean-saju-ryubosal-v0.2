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
    # v2.2.1 개정표(2026-06-12 사용자 승인 — 해석 사전 prefix 포함 상향).
    assert CALL_LIMITS["chat_single"].max_input_tokens == 20_000
    # 출력 토큰 상한 = thinking + 가시 출력 합산(Gemini) — thinking 잠식 방지 상향.
    assert CALL_LIMITS["chat_single"].max_output_tokens == 5_000
    assert CALL_LIMITS["chat_single"].max_output_chars == 1_500
    assert CALL_LIMITS["chat_compare"].max_input_tokens == 20_000
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


def test_check_input_reserve_counts_overhead() -> None:
    """reserve_tokens는 직렬화 후 덧붙는 시스템·지시문 오버헤드 몫 — 총 입력으로 본다.

    payload 단독은 상한 이내라도 payload+reserve가 상한을 넘으면 차단해야,
    serialize 통과 후 generate_reading 재검사에서 터지던 회계 불일치를 막는다.
    """
    guard = LLMCallGuard("query_parser")  # 상한 2,000tok
    payload = "가" * 1_800  # 1,800tok — 단독으로는 통과
    assert guard.check_input(payload, reserve_tokens=0) == 1_800
    with pytest.raises(TokenBudgetExceeded, match="2000tok"):
        guard.check_input(payload, reserve_tokens=300)  # 1,800+300 > 2,000


def test_request_params_no_thinking_key() -> None:
    """thinking 수준은 llm_config.json에서만 관리(절대 원칙 9 v2.2.1 — low 이하).

    가드 파라미터에는 thinking 키 자체가 없어야 한다(설정 파일 단일 관리).
    """
    params = LLMCallGuard("chat_single").request_params()
    assert "thinking" not in params
    assert params["max_tokens"] == 5_000


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
