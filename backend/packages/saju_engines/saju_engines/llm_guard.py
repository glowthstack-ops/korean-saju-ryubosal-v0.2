"""LLM 호출 토큰 거버넌스 (v2.2 Phase 2.5 T2.5.8, docs/09 8장 — 전체 한도표).

가드 규칙(docs/09):
- 입력 토큰을 호출 **전** 측정해 상한 초과 시 예외 → 호출자는 Context Reduction 재실행.
- 상한을 늘리는 코드 수정은 금지(사용자 승인 필요) — 한도표는 이 모듈의 단일 상수.
- extended thinking은 모든 운영 호출에서 **비활성** 강제.
- 모든 호출의 입출력 토큰을 로깅해 상품별 원가 대시보드에 집계.

실제 API 클라이언트는 이후 단계(llm/ 패키지)에서 이 가드를 통과해서만 호출한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class TokenBudgetExceeded(Exception):
    """입력 토큰 상한 초과 — 호출 전 차단. Context Reduction을 재실행할 것."""


@dataclass(frozen=True)
class CallLimit:
    """호출 유형별 한도 (docs/09 8장 표의 한 행)."""

    max_input_tokens: int
    max_output_tokens: int
    max_output_chars: int | None = None  # 보고서 섹션류는 글자수 상한 병행


# docs/09 8장 전체 한도표 — 항목·수치 변경은 사용자 승인 필요(임의 상향 금지).
CALL_LIMITS: dict[str, CallLimit] = {
    "chat_single": CallLimit(6_000, 1_200),
    "chat_compare": CallLimit(8_000, 1_600),
    "query_parser": CallLimit(2_000, 300),
    "report_focus_section": CallLimit(5_000, 3_500, max_output_chars=4_500),
    "report_full_section": CallLimit(5_000, 3_500, max_output_chars=4_500),
    "consistency_check": CallLimit(8_000, 500),
}


def estimate_tokens(text: str) -> int:
    """보수적(과대) 토큰 추정 — ASCII 4자/토큰, 비ASCII(한글·한자) 1자/토큰.

    가드 목적이므로 실제보다 적게 세는 것보다 많게 세는 쪽이 안전하다. 정밀 측정이
    필요하면 호출 측이 카운터를 주입한다(LLMCallGuard(token_counter=...)).
    """
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other_chars = len(text) - ascii_chars
    return math.ceil(ascii_chars / 4) + other_chars


@dataclass
class LLMCallLog:
    """호출 1건의 원가 집계 레코드 (docs/09: 상품별 원가 대시보드 원천)."""

    call_type: str
    input_tokens: int
    output_tokens: int = 0
    product_code: str | None = None  # RPT_FULL / RPT_FOCUS / CHAT
    section_id: str | None = None


@dataclass
class LLMCostLedger:
    """프로세스 내 호출 로그 수집기 — 운영에서는 영속 저장소로 교체."""

    entries: list[LLMCallLog] = field(default_factory=list)

    def record(self, log: LLMCallLog) -> None:
        """호출 로그 1건 적재."""
        self.entries.append(log)

    def total_tokens(self) -> tuple[int, int]:
        """(입력 합, 출력 합)."""
        return (
            sum(e.input_tokens for e in self.entries),
            sum(e.output_tokens for e in self.entries),
        )


class LLMCallGuard:
    """호출 유형별 토큰 가드 — 모든 LLM 호출은 이 가드를 거친다."""

    def __init__(
        self,
        call_type: str,
        ledger: LLMCostLedger | None = None,
        token_counter=estimate_tokens,
    ) -> None:
        """call_type은 CALL_LIMITS의 키여야 한다.

        Raises:
            KeyError: 한도표에 없는 호출 유형(임의 유형 추가 금지).
        """
        self._limit = CALL_LIMITS[call_type]
        self._call_type = call_type
        self._ledger = ledger
        self._count = token_counter

    @property
    def limit(self) -> CallLimit:
        """이 호출 유형의 한도."""
        return self._limit

    def check_input(self, prompt_text: str) -> int:
        """입력 토큰 측정 — 상한 초과 시 호출 전 예외(docs/09 가드 규칙).

        Returns:
            측정된 입력 토큰 수(로깅용).
        """
        tokens = self._count(prompt_text)
        if tokens > self._limit.max_input_tokens:
            raise TokenBudgetExceeded(
                f"{self._call_type}: 입력 {tokens}tok > 상한 "
                f"{self._limit.max_input_tokens}tok — Context Reduction 재실행 필요"
            )
        return tokens

    def request_params(self) -> dict:
        """API 호출 파라미터 — 출력 상한 + thinking 비활성 강제.

        thinking 비활성(절대 원칙 9)은 **파라미터 생략**으로 강제한다: 최신 모델은
        thinking 미지정 시 비활성이며, 명시적 {"type": "disabled"}는 일부 모델
        (Fable 5)에서 400을 반환한다. 이 dict에 thinking을 추가하는 변경은 금지.
        """
        return {"max_tokens": self._limit.max_output_tokens}

    def record(
        self, input_tokens: int, output_tokens: int,
        product_code: str | None = None, section_id: str | None = None,
    ) -> LLMCallLog:
        """호출 결과 토큰을 로깅(원가 집계)."""
        log = LLMCallLog(
            call_type=self._call_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            product_code=product_code,
            section_id=section_id,
        )
        if self._ledger is not None:
            self._ledger.record(log)
        return log
